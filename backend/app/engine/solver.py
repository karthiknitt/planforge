"""CP-SAT constraint solver for PlanForge layout generation.

Replaces the purely deterministic archetype slicer with an optimisation-based
approach. All spatial values use millimetre integers (SCALE = 1000) because
OR-Tools CP-SAT only handles integer domains.

Three diverse layouts are produced by forcing the staircase position to
different thirds of the buildable area on each solver run (symmetry breaking).

Falls back gracefully — caller should catch all exceptions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from ortools.sat.python import cp_model

from .models import Column, FloorPlan, Layout, PlotConfig, Room
from app.engine.adjacency import load_adjacency_pairs

SCALE = 1000  # 1 metre = 1000 mm units
SOLVE_TIME_S = 8.0  # per-run wall-clock budget (generation runs async)
MAX_DIM_MM = 50_000  # safety cap: 50 m per dimension

# Wall-coalignment bonus (objective units = mm) per exactly-aligned edge
# pair. Must beat the per-mm size term (so the solver gives up room growth
# to land partitions on shared grid lines) and typical adjacency-distance
# trades — popular grid lines earn quadratically (C(n,2) pairs), which is
# exactly the pressure that consolidates walls onto few lines.
ALIGN_BONUS = 2500
# Post-solve wall-line snapping reach. Facing edge pairs (the two faces of
# one wall) are detected and moved rigidly as a unit, so a large tolerance
# can never collapse a wall gap — it only merges genuinely distinct wall
# LINES, i.e. exactly the near-miss offsets that split the column grid.
SNAP_TOL_M = 0.45
_IWT_M = 0.115  # internal wall thickness (mirrors plan_geometry.IWT)

_SPECS_PATH = Path(__file__).parent.parent / "config" / "room_specs.json"


def _load_specs() -> dict:
    return json.loads(_SPECS_PATH.read_text())


# ── Adjacency preference pairs ────────────────────────────────────────────────

_ADJACENCY_PAIRS: list[tuple[str, str, int]] = [
    (a, b, int(pts)) for a, b, pts in load_adjacency_pairs()
]


@dataclass
class _RoomVar:
    """All CP-SAT variables for one room on one floor."""

    room_id: str
    room_type: str
    room_name: str
    floor: int
    x: cp_model.IntVar
    y: cp_model.IntVar
    w: cp_model.IntVar
    d: cp_model.IntVar
    xe: cp_model.IntVar  # x + w (explicit end var, OR-Tools 9.x affine rule)
    ye: cp_model.IntVar  # y + d
    ix: cp_model.IntervalVar
    iy: cp_model.IntervalVar


def _mm(metres: float) -> int:
    return int(round(metres * SCALE))


def _plate_and_planes_from_polygon(
    inset,
) -> tuple[int, int, int, int, list[tuple[int, int, int]]]:
    """Solver plate bounds + half-plane constraints from a buildable polygon.

    half_planes is a list of (dx, dy, rhs) where for every room corner
    (rx, ry) in solver coords (mm, relative to plate origin):
    dx*ry - dy*rx >= rhs.  Interior must be left of each CCW edge.
    """
    minx, miny, maxx, maxy = inset.bounds
    bw = _mm(maxx - minx)
    bd = _mm(maxy - miny)
    ox = _mm(minx)
    oy = _mm(miny)

    coords = list(inset.exterior.coords)[:-1]
    n_c = len(coords)
    area2 = sum(
        coords[i][0] * coords[(i + 1) % n_c][1]
        - coords[(i + 1) % n_c][0] * coords[i][1]
        for i in range(n_c)
    )
    if area2 < 0:  # CW — reverse to CCW
        coords = coords[::-1]

    planes: list[tuple[int, int, int]] = []
    n = len(coords)
    for i in range(n):
        p1 = coords[i]
        p2 = coords[(i + 1) % n]
        dx = round((p2[0] - p1[0]) * SCALE)
        dy = round((p2[1] - p1[1]) * SCALE)
        cx = round(p1[0] * SCALE)
        cy = round(p1[1] * SCALE)
        rhs = dx * cy - dy * cx - dx * oy + dy * ox
        planes.append((dx, dy, rhs))

    return bw, bd, ox, oy, planes


def _build_room_list(cfg: PlotConfig, specs: dict) -> list[dict]:
    """Determine which rooms to solve for based on PlotConfig."""
    rooms = []

    # Living room (always)
    rooms.append(
        {"id": "living_0", "type": "living", "name": "Living Room", "floor": 0}
    )

    # Kitchen (always, GF)
    rooms.append({"id": "kitchen_0", "type": "kitchen", "name": "Kitchen", "floor": 0})

    # Bedrooms — distribute across GF and FF
    for i in range(cfg.num_bedrooms):
        floor = 0 if i == 0 else 1
        rooms.append(
            {
                "id": f"bedroom_{i}",
                "type": "bedroom",
                "name": f"Bedroom {i + 1}",
                "floor": floor,
            }
        )

    # Toilets — distribute across floors
    for i in range(cfg.toilets):
        floor = 0 if i < max(1, cfg.num_bedrooms // 2) else 1
        rooms.append(
            {
                "id": f"toilet_{i}",
                "type": "toilet",
                "name": f"Toilet {i + 1}",
                "floor": floor,
            }
        )

    # Staircase on both floors
    rooms.append(
        {"id": "stair_0", "type": "staircase", "name": "Staircase", "floor": 0}
    )
    rooms.append(
        {"id": "stair_1", "type": "staircase", "name": "Staircase", "floor": 1}
    )

    # Optional rooms
    if cfg.has_pooja:
        rooms.append(
            {"id": "pooja_0", "type": "pooja", "name": "Pooja Room", "floor": 0}
        )
    if cfg.has_study:
        rooms.append(
            {"id": "study_0", "type": "study", "name": "Study Room", "floor": 1}
        )
    if cfg.has_balcony:
        rooms.append(
            {"id": "balcony_0", "type": "balcony", "name": "Balcony", "floor": 1}
        )
    if cfg.parking:
        rooms.append(
            {"id": "parking_0", "type": "parking", "name": "Parking", "floor": 0}
        )

    # Custom rooms from Phase C
    if cfg.custom_room_config:
        for idx, custom in enumerate(cfg.custom_room_config):
            rtype = custom.get("type", "utility")
            pref = custom.get("floor_preference", "either")
            floor = 1 if pref == "ff" else 0
            rooms.append(
                {
                    "id": f"custom_{idx}",
                    "type": rtype,
                    "name": custom.get("name") or rtype.replace("_", " ").title(),
                    "floor": floor,
                    "custom_min_area": custom.get("min_area_sqm"),
                }
            )

    return rooms


@dataclass
class _SnapEdge:
    key: tuple[int, str, str, str]  # (floor_idx, room_id, axis, "lo"|"hi")
    coord: float
    lo: float  # perpendicular interval (for facing detection)
    hi: float
    pinned: bool = False
    unit: int = -1  # union-find root index, -1 = solitary
    line: float = 0.0  # implied wall-line coordinate used for clustering


def snap_rooms_to_shared_grid(
    floors: list[list[Room]],
    min_dims: dict[str, dict],
    tol: float = SNAP_TOL_M,
    plate_bounds: tuple[tuple[float, float], tuple[float, float]] | None = None,
) -> list[list[Room]]:
    """Best-effort post-solve pass: merge near-aligned wall LINES (across
    ALL floors, so columns stack vertically) onto shared grid lines.

    Facing edge pairs — a room's hi edge and a neighbour's lo edge within
    one wall thickness, with perpendicular overlap — are the two faces of
    ONE wall and move rigidly together, so the pass can never collapse a
    wall gap regardless of tolerance. Edges on the buildable plate boundary
    are pinned and act as cluster anchors.

    Guarantees, in order:
    - wall faces keep their gap (rigid units)
    - no room shrinks below its spec minimums (per-room revert)
    - no room overlap (participants of an overlap revert)

    Feasibility beyond that (setbacks, compliance) is the caller's problem:
    _solve_one re-runs the compliance check and falls back to the unsnapped
    rooms if the snapped layout fails.
    """
    originals = {(fi, r.id): r for fi, rooms in enumerate(floors) for r in rooms}

    edges: list[_SnapEdge] = []
    for fi, rooms in enumerate(floors):
        for r in rooms:
            edges.append(_SnapEdge((fi, r.id, "x", "lo"), r.x, r.y, r.y + r.depth))
            edges.append(
                _SnapEdge((fi, r.id, "x", "hi"), r.x + r.width, r.y, r.y + r.depth)
            )
            edges.append(_SnapEdge((fi, r.id, "y", "lo"), r.y, r.x, r.x + r.width))
            edges.append(
                _SnapEdge((fi, r.id, "y", "hi"), r.y + r.depth, r.x, r.x + r.width)
            )

    if plate_bounds is not None:
        (px1, px2), (py1, py2) = plate_bounds
        for e in edges:
            bounds = (px1, px2) if e.key[2] == "x" else (py1, py2)
            if any(abs(e.coord - b) <= 0.02 for b in bounds):
                e.pinned = True
        # Virtual anchors at the plate bounds themselves: a lone edge that
        # stops just short of the plate (orphan sliver strip) snaps onto it
        # even when no real room edge sits there to pin the cluster.
        for axis, (b1, b2) in (("x", (px1, px2)), ("y", (py1, py2))):
            for b in (b1, b2):
                anchor = _SnapEdge((-1, "__plate__", axis, "lo"), b, 0.0, 0.0)
                anchor.pinned = True
                edges.append(anchor)

    # Facing pairs (same floor, hi face meets lo face across <= one wall
    # gap, perpendicular overlap) -> rigid wall units via union-find.
    parent = list(range(len(edges)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_axis_floor: dict[tuple[str, int], list[int]] = {}
    for idx, e in enumerate(edges):
        by_axis_floor.setdefault((e.key[2], e.key[0]), []).append(idx)
    for group in by_axis_floor.values():
        for i in group:
            a = edges[i]
            if a.key[3] != "hi":
                continue
            for j in group:
                b = edges[j]
                if b.key[3] != "lo" or b.key[1] == a.key[1]:
                    continue
                gap = b.coord - a.coord
                if -0.02 <= gap <= _IWT_M + 0.02 and (
                    min(a.hi, b.hi) - max(a.lo, b.lo) >= 0.05
                ):
                    parent[find(i)] = find(j)

    # Cluster on the wall-unit centre for paired faces, on the raw edge
    # coordinate for solitary edges. (No +-IWT/2 orphan-wall estimates:
    # coordinate-level equality already puts DERIVED wall lines within
    # half a wall thickness of each other — far below any structural bay —
    # and the micro-shuffles those estimates cause trigger min-dim/overlap
    # revert cascades that destroy the real merges.)
    members: dict[int, list[int]] = {}
    for idx in range(len(edges)):
        members.setdefault(find(idx), []).append(idx)
    for root, idxs in members.items():
        if len(idxs) > 1:
            line = sum(edges[i].coord for i in idxs) / len(idxs)
            for i in idxs:
                edges[i].unit = root
                edges[i].line = line
        else:
            edges[idxs[0]].line = edges[idxs[0]].coord

    # Cluster wall lines per axis (chain gap AND diameter <= tol), then move
    # every member line to the cluster target — anchored on a pinned edge's
    # line when one is present. Units translate rigidly (same delta for all
    # faces), so gaps are preserved exactly.
    deltas: dict[tuple[int, str, str, str], float] = {}

    def flush(cluster: list[_SnapEdge]) -> None:
        lines = sorted({round(e.line, 6) for e in cluster})
        if len(lines) < 2:
            return  # already one line — nothing to merge
        pinned = [e for e in cluster if e.pinned]
        target = pinned[0].line if pinned else sum(lines) / len(lines)
        for e in cluster:
            if not e.pinned:
                deltas[e.key] = target - e.line

    def split(chunk: list[_SnapEdge]) -> list[list[_SnapEdge]]:
        # Enforce the diameter cap by splitting at the LARGEST internal gap
        # (greedy left-to-right splitting can separate two near-identical
        # lines just because an unrelated line started the chain earlier).
        if chunk[-1].line - chunk[0].line <= tol:
            return [chunk]
        gi = max(range(1, len(chunk)), key=lambda i: chunk[i].line - chunk[i - 1].line)
        return split(chunk[:gi]) + split(chunk[gi:])

    for axis in ("x", "y"):
        axis_edges = sorted(
            (e for e in edges if e.key[2] == axis), key=lambda e: e.line
        )
        chain: list[_SnapEdge] = []
        for e in axis_edges:
            if chain and e.line - chain[-1].line > tol:
                for cluster in split(chain):
                    flush(cluster)
                chain = []
            chain.append(e)
        if chain:
            for cluster in split(chain):
                flush(cluster)

    def build(fi: int, r: Room) -> Room:
        x_lo = r.x + deltas.get((fi, r.id, "x", "lo"), 0.0)
        x_hi = r.x + r.width + deltas.get((fi, r.id, "x", "hi"), 0.0)
        y_lo = r.y + deltas.get((fi, r.id, "y", "lo"), 0.0)
        y_hi = r.y + r.depth + deltas.get((fi, r.id, "y", "hi"), 0.0)
        cand = replace(
            r,
            x=round(x_lo, 3),
            y=round(y_lo, 3),
            width=round(x_hi - x_lo, 3),
            depth=round(y_hi - y_lo, 3),
        )
        mins = min_dims.get(r.id, {})
        eps = 1e-9
        if (
            cand.width < mins.get("min_width_m", 0.0) - eps
            or cand.depth < mins.get("min_depth_m", 0.0) - eps
            or cand.width * cand.depth < mins.get("min_area_sqm", 0.0) - eps
        ):
            return r  # revert: snap would violate this room's spec minimums
        return cand

    result = [[build(fi, r) for r in rooms] for fi, rooms in enumerate(floors)]

    # Overlap guard: revert every participant of an overlap, repeat until
    # stable (reverting one room can only remove overlaps, never add them,
    # because originals were overlap-free — but a revert can pair an
    # original with a still-snapped neighbour, so re-check).
    for _ in range(3):
        dirty = False
        for fi, rooms in enumerate(result):
            for i, ra in enumerate(rooms):
                for j in range(i + 1, len(rooms)):
                    rb = rooms[j]
                    x_ov = min(ra.x + ra.width, rb.x + rb.width) - max(ra.x, rb.x)
                    y_ov = min(ra.y + ra.depth, rb.y + rb.depth) - max(ra.y, rb.y)
                    if x_ov > 1e-6 and y_ov > 1e-6:
                        rooms[i] = originals[(fi, ra.id)]
                        rooms[j] = originals[(fi, rb.id)]
                        ra = rooms[i]
                        dirty = True
        if not dirty:
            break
    return result


def _solve_one(
    cfg: PlotConfig,
    ewt: float,
    room_defs: list[dict],
    specs: dict,
    stair_zone: str,  # "front" | "mid" | "rear"
    layout_id: str,
    layout_name: str,
) -> Layout | None:
    """Run a single CP-SAT solve and return a Layout if successful."""

    # Buildable plate dimensions in mm
    quad_planes: list[tuple[int, int, int]] = []
    if cfg.plot_shape != "rectangular":
        from app.engine.geometry import buildable_polygon

        inset = buildable_polygon(cfg, wall_clearance=ewt)
        if inset.is_empty:
            return None
        bw, bd, ox, oy, quad_planes = _plate_and_planes_from_polygon(inset)
    else:
        bw = _mm(cfg.plot_width - cfg.setback_left - cfg.setback_right - 2 * ewt)
        bd = _mm(cfg.plot_length - cfg.setback_front - cfg.setback_rear - 2 * ewt)
        ox = _mm(cfg.setback_left + ewt)
        oy = _mm(cfg.setback_front + ewt)

    if bw <= 0 or bd <= 0:
        return None

    model = cp_model.CpModel()
    room_vars: list[_RoomVar] = []
    gf_vars: list[_RoomVar] = []
    ff_vars: list[_RoomVar] = []

    for rd in room_defs:
        rtype = rd["type"]
        spec = specs.get(rtype, specs.get("utility"))

        min_w = _mm(spec["min_width_m"])
        max_w = min(_mm(spec["max_width_m"]), bw)
        custom_min_area = rd.get("custom_min_area")
        raw_min_area = custom_min_area if custom_min_area else spec["min_area_sqm"]
        # 1 sqm = SCALE*SCALE mm² = 1_000_000 mm²
        min_area_mm2 = int(raw_min_area * SCALE * SCALE)
        max_area_mm2 = int(spec["max_area_sqm"] * SCALE * SCALE)

        min_d = _mm(spec["min_width_m"])  # use min_width as min depth too
        max_d = min(_mm(spec.get("max_width_m", 8.0)), bd)

        if max_w < min_w or max_d < min_d:
            return None

        floor = rd["floor"]
        x = model.new_int_var(0, bw - min_w, f"x_{rd['id']}")
        y = model.new_int_var(0, bd - min_d, f"y_{rd['id']}")
        w = model.new_int_var(min_w, max_w, f"w_{rd['id']}")
        d = model.new_int_var(min_d, max_d, f"d_{rd['id']}")
        # OR-Tools 9.x: new_interval_var end must be an IntVar (affine), not x+w (two-var sum)
        ex = model.new_int_var(min_w, bw, f"ex_{rd['id']}")
        ey = model.new_int_var(min_d, bd, f"ey_{rd['id']}")
        model.add(ex == x + w)
        model.add(ey == y + d)
        ix = model.new_interval_var(x, w, ex, f"ix_{rd['id']}")
        iy = model.new_interval_var(y, d, ey, f"iy_{rd['id']}")

        # Bounds: x+w <= bw, y+d <= bd
        model.add(x + w <= bw)
        model.add(y + d <= bd)

        # Area lower bound (linearised product via AddMultiplicationEquality)
        area = model.new_int_var(0, max_area_mm2, f"area_{rd['id']}")
        model.add_multiplication_equality(area, [w, d])
        model.add(area >= min_area_mm2)

        # Aspect ratio max 3:1
        model.add(w * 3 >= d)
        model.add(d * 3 >= w)

        rv = _RoomVar(
            room_id=rd["id"],
            room_type=rtype,
            room_name=rd["name"],
            floor=floor,
            x=x,
            y=y,
            w=w,
            d=d,
            xe=ex,
            ye=ey,
            ix=ix,
            iy=iy,
        )
        room_vars.append(rv)
        (gf_vars if floor == 0 else ff_vars).append(rv)

    # Quadrilateral half-plane constraints — all 4 corners of each room inside inset polygon
    if quad_planes:
        for rv in room_vars:
            for corner_x, corner_y in [
                (rv.x, rv.y),
                (rv.x + rv.w, rv.y),
                (rv.x, rv.y + rv.d),
                (rv.x + rv.w, rv.y + rv.d),
            ]:
                for dx, dy, rhs in quad_planes:
                    model.add(dx * corner_y - dy * corner_x >= rhs)

    # No-overlap per floor
    if gf_vars:
        model.add_no_overlap_2d([v.ix for v in gf_vars], [v.iy for v in gf_vars])
    if ff_vars:
        model.add_no_overlap_2d([v.ix for v in ff_vars], [v.iy for v in ff_vars])

    # Staircase alignment across floors
    gf_stairs = [v for v in gf_vars if v.room_type == "staircase"]
    ff_stairs = [v for v in ff_vars if v.room_type == "staircase"]
    if gf_stairs and ff_stairs:
        gs, fs = gf_stairs[0], ff_stairs[0]
        model.add(gs.x == fs.x)
        model.add(gs.y == fs.y)
        model.add(gs.w == fs.w)
        model.add(gs.d == fs.d)

    # Symmetry-breaking: force staircase to a third of plot depth
    if gf_stairs:
        stair = gf_stairs[0]
        third = bd // 3
        if stair_zone == "front":
            model.add(stair.y + stair.d <= third)
        elif stair_zone == "rear":
            model.add(stair.y >= 2 * third)
        else:  # mid
            model.add(stair.y >= third)
            model.add(stair.y + stair.d <= 2 * third)

    # ── Objective: pull preferred-adjacency pairs together ───────────────────
    # The previous "objective" forced adj==1 and maximized a constant — the
    # solver returned the first feasible packing with zero optimization
    # pressure. Minimize the points-weighted Manhattan distance between the
    # centres of preferred pairs instead (a linear, solver-friendly proxy
    # for shared-wall adjacency).
    dist_terms = []

    type_to_var: dict[str, list[_RoomVar]] = {}
    for rv in room_vars:
        type_to_var.setdefault(rv.room_type, []).append(rv)

    for t1, t2, pts in _ADJACENCY_PAIRS:
        for a in type_to_var.get(t1, []):
            for b in type_to_var.get(t2, []):
                if a.floor != b.floor:
                    continue
                pair = f"{a.room_id}_{b.room_id}"
                # doubled centres keep everything integral: 2*cx = 2x + w
                dxv = model.new_int_var(0, 2 * bw, f"dx_{pair}")
                dyv = model.new_int_var(0, 2 * bd, f"dy_{pair}")
                model.add_abs_equality(dxv, 2 * a.x + a.w - 2 * b.x - b.w)
                model.add_abs_equality(dyv, 2 * a.y + a.d - 2 * b.y - b.d)
                dist_terms.append(pts * (dxv + dyv))

    # Secondary pressure: grow rooms toward their spec max (w+d is a linear
    # size proxy). Without this the solver returns minimum-area rooms and
    # dumps all slack into leftover space (the "5 sqm Study, 38 sqm Passage"
    # bug). Adjacency terms are points-weighted per mm, so they still dominate.
    size_terms = [rv.w + rv.d for rv in room_vars]

    # Wall-coalignment bonus: reified equalities between room edge
    # coordinates — same floor (partitions land on shared grid lines, no
    # mid-span T columns) and cross-floor (GF/FF columns stack). Without
    # this, size_terms grows every room independently and adjacent rooms
    # almost never share a wall line (pro-tester regression, 2026-07-16).
    align_bools = []
    for i, a in enumerate(room_vars):
        for b in room_vars[i + 1 :]:
            if a.room_type == "staircase" and b.room_type == "staircase":
                continue  # already hard-equal across floors
            # All 4 end combos per axis: rooms pack with gaps anywhere in
            # [0, iwt+], so a shared wall line shows up as lo↔lo, hi↔hi or
            # the mixed hi↔lo forms depending on which side of the gap each
            # room sits.
            for e1, e2, tag in (
                (a.x, b.x, "xll"),
                (a.xe, b.xe, "xhh"),
                (a.xe, b.x, "xhl"),
                (a.x, b.xe, "xlh"),
                (a.y, b.y, "yll"),
                (a.ye, b.ye, "yhh"),
                (a.ye, b.y, "yhl"),
                (a.y, b.ye, "ylh"),
            ):
                bv = model.new_bool_var(f"al_{a.room_id}_{b.room_id}_{tag}")
                model.add(e1 == e2).only_enforce_if(bv)
                model.add(e1 != e2).only_enforce_if(bv.Not())
                align_bools.append(bv)

    if dist_terms or size_terms or align_bools:
        model.minimize(
            sum(dist_terms) - sum(size_terms) - ALIGN_BONUS * sum(align_bools)
        )

    # ── Solve ─────────────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVE_TIME_S
    solver.parameters.num_search_workers = 1  # deterministic single-thread

    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    # ── Extract solution into Layout ──────────────────────────────────────────
    gf_rooms: list[Room] = []
    ff_rooms: list[Room] = []

    for rv in room_vars:
        rx = ox / SCALE + solver.value(rv.x) / SCALE
        ry = oy / SCALE + solver.value(rv.y) / SCALE
        rw = solver.value(rv.w) / SCALE
        rd = solver.value(rv.d) / SCALE
        room = Room(
            id=rv.room_id,
            name=rv.room_name,
            type=rv.room_type,
            x=round(rx, 3),
            y=round(ry, 3),
            width=round(rw, 3),
            depth=round(rd, 3),
        )
        (gf_rooms if rv.floor == 0 else ff_rooms).append(room)

    # Structural columns: only at exterior-ring junctions, true 4-way
    # crossings, or interior T-junctions whose removal would leave a beam
    # span exceeding max_beam_span_m — NOT at every room corner (that placed
    # a column on both sides of every internal partition, producing dense,
    # visually cluttered "intermediate" grids that add no structural value).
    def _wall_junction_cols(rooms: list[Room]) -> list[Column]:
        if not rooms:
            return []
        from app.engine.geometry import buildable_polygon
        from app.engine.plan_geometry import (
            derive_columns,
            derive_junctions,
            derive_walls,
        )

        buildable = buildable_polygon(cfg)
        walls = derive_walls(rooms, buildable, ewt=ewt)
        junctions = derive_junctions(walls)
        columns = derive_columns(walls, junctions=junctions)
        return [Column(x=c.cx, y=c.cy) for c in columns]

    from .compliance import check, load_rules
    from .models import ComplianceResult
    from .vastu import check_vastu

    rules = load_rules()

    def _build_layout(gf_list: list[Room], ff_list: list[Room]) -> Layout:
        layout = Layout(
            id=layout_id,
            name=layout_name,
            ground_floor=FloorPlan(
                floor=0,
                floor_type="ground",
                rooms=gf_list,
                columns=_wall_junction_cols(gf_list),
            ),
            first_floor=FloorPlan(
                floor=1,
                floor_type="first",
                rooms=ff_list,
                columns=_wall_junction_cols(ff_list),
            ),
            compliance=ComplianceResult(passed=True),
        )
        layout.compliance = check(layout, cfg, rules)
        if cfg.vastu_enabled:
            v_viol, v_warn = check_vastu(layout, cfg, road_side=cfg.road_side)
            layout.compliance.violations.extend(v_viol)
            layout.compliance.warnings.extend(v_warn)
            layout.compliance.passed = len(layout.compliance.violations) == 0
        return layout

    # Post-solve snap: coalesce residual near-aligned wall lines (the
    # objective rewards exact alignment, but the solver may stop at a
    # near-miss under its time budget). Falls back to the unsnapped rooms
    # if snapping breaks compliance — the snap is best-effort by design.
    min_dims = {}
    for rd2 in room_defs:
        spec2 = specs.get(rd2["type"], specs.get("utility"))
        min_dims[rd2["id"]] = {
            "min_width_m": spec2["min_width_m"],
            "min_depth_m": spec2["min_width_m"],
            "min_area_sqm": rd2.get("custom_min_area") or spec2["min_area_sqm"],
        }
    snapped_gf, snapped_ff = snap_rooms_to_shared_grid(
        [gf_rooms, ff_rooms],
        min_dims,
        plate_bounds=(
            (ox / SCALE, (ox + bw) / SCALE),
            (oy / SCALE, (oy + bd) / SCALE),
        ),
    )

    layout = _build_layout(snapped_gf, snapped_ff)
    if not layout.compliance.passed and (
        snapped_gf != gf_rooms or snapped_ff != ff_rooms
    ):
        layout = _build_layout(gf_rooms, ff_rooms)

    return layout if layout.compliance.passed else None


def solve_layouts(cfg: PlotConfig, ewt: float) -> list[Layout]:
    """Generate up to 3 diverse solver layouts. Returns empty list on failure."""
    specs = _load_specs()
    room_defs = _build_room_list(cfg, specs)

    zones = [
        ("front", "S1", "Layout S1 — Front Staircase"),
        ("mid", "S2", "Layout S2 — Centre Staircase"),
        ("rear", "S3", "Layout S3 — Rear Staircase"),
    ]

    results: list[Layout] = []
    for zone, lid, lname in zones:
        try:
            layout = _solve_one(cfg, ewt, room_defs, specs, zone, lid, lname)
            if layout is not None:
                results.append(layout)
        except Exception:
            pass  # solver failure → skip this zone

    return results
