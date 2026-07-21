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
SOLVE_TIME_S = 14.0  # per-run wall-clock budget (generation runs async)
# Wall cap for the penalty-free phase-1 warm start: it only needs A feasible
# solution to hint phase 2, not a good one, so it doesn't get the full
# SOLVE_TIME_S (which would let one zone double to ~28 s worst case).
#
# Both budgets were widened from 8.0/3.0 (2026-07-19, Task 5a): the wall
# clock cap is meant to be a pure safety net for pathologically slow
# machines — max_deterministic_time=1.5/0.7 is the value that's supposed to
# bind on any normal machine, which is what makes repeated solves return the
# SAME incumbent. Measured directly (debug instrumentation on this task):
# under ordinary CPU contention (a handful of concurrent local processes),
# a single zone's 1.5 deterministic-time-unit solve took 6.7-8.0+ real
# seconds, i.e. the OLD 8.0 s cap was already binding before the
# deterministic budget finished — non-deterministically truncating the
# incumbent depending on machine load. Because generate() ranks solver AND
# archetype layouts together and relabels the top 3 "A"/"B"/"C" purely by
# rank, a truncated solver layout can land in any of those slots and
# intermittently fail downstream geometry invariants (e.g.
# test_cross_floor_columns_stack) that assume a fully-worked incumbent.
# Widening the caps doesn't make the search itself faster, it just gives
# the deterministic budget more real-world headroom to actually be the
# thing that binds, which is what restores reproducibility.
PHASE1_TIME_S = 5.0
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
_IWT_MM = 115

# Wet rooms are excluded from the size-growth objective: they should settle
# at min-compliant size, not balloon toward spec max (mirrors
# plan_geometry._WET_TYPES, including "utility").
_WET_TYPES = {"toilet", "wc_only", "bathroom_master", "utility"}

# En-suite ↔ bedroom shared wall must fit a door (900 mm min clear width).
_ENSUITE_MIN_OVERLAP_MM = 900
# Repulsion guard bands: the solver otherwise games hard thresholds (parks a
# toilet 1 mm past the wall gap) and post-solve snapping (±SNAP_TOL_M) can
# close a raw clearance into real contact. Penalise anything within a
# 600 mm moat with >= 100 mm of facing overlap, so the snapped result can
# never end up genuinely wall-sharing.
_REPULSION_GAP_MM = 600
_MIN_SHARE_OVERLAP_MM = 100

# In-model area cap for wet rooms, aligned with generator._WET_CAP_SQM (4.6):
# anything larger would be split into toilet+passage post-solve anyway.
_WET_AREA_CAP_MM2 = 4_600_000

# Soft toilet-placement penalties (objective units). Must dominate not just
# ALIGN_BONUS (2500) but realistic adjacency-distance trades: bedroom↔toilet
# is 12 pts on DOUBLED centre distance (~24 units/mm), so relocating a
# toilet ~1-2 m costs 24k-48k — penalties below that get ignored. Soft so
# tight plots stay feasible (a boolean penalty can never go infeasible).
TOILET_FRONT_PENALTY = 150_000
TOILET_FRONT_MID_PENALTY = 100_000  # extra when centre-x faces the gate axis
# Stair/parking repulsion needs to be large enough to pull the search out of
# the packed-next-to-stair basin even when the incumbent is only FEASIBLE
# (measured: at 60k the mid-zone solve kept both toilets on the stair wall).
TOILET_STAIR_PENALTY = 200_000
TOILET_PARKING_PENALTY = 200_000
# Per-mm shrink pressure on wet rooms. Must beat BOTH the alignment bonus a
# stretch can buy (2500 per edge) and the adjacency centre-pull: growing a
# toilet toward its bedroom/kitchen partner moves its centre at half the
# growth rate against ~24 units/mm pair weights (~12-20/mm effective gain,
# measured ballooning at weight 8). 30/mm makes growth strictly unprofitable
# so wet rooms settle at their min-compliant size.
WET_SHRINK_WEIGHT = 30
# Parking road-facing penalty must dominate size/align terms — same order of
# magnitude as the toilet penalties above, since it fights the same packing
# pressure.
PARKING_ROAD_PENALTY = 250_000

_PARKING_TYPES = {"parking", "parking_4w", "parking_2w"}

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


def ensuite_attachment(room_id: str) -> str | None:
    """Map an en-suite room id (``toilet_ens_<i>``) to its bedroom id.

    The Room dataclass has no metadata field, so en-suite attachment is
    encoded in the id convention; later pipeline stages import this helper
    instead of re-parsing ids.
    """
    if room_id.startswith("toilet_ens_"):
        suffix = room_id.removeprefix("toilet_ens_")
        if suffix.isdigit():
            return f"bedroom_{suffix}"
    return None


def _build_room_list(cfg: PlotConfig, specs: dict) -> list[dict]:
    """Determine which rooms to solve for based on PlotConfig."""
    rooms = []

    # Living room (always)
    rooms.append(
        {"id": "living_0", "type": "living", "name": "Living Room", "floor": 0}
    )

    # Kitchen (always, GF)
    rooms.append({"id": "kitchen_0", "type": "kitchen", "name": "Kitchen", "floor": 0})

    # Bedrooms — distribute across GF and FF. With attached_toilets each
    # bedroom gets an en-suite on its own floor (bathroom_master for the
    # master, i.e. bedroom 0); en-suites are ADDITIVE to cfg.toilets, which
    # then counts common toilets only.
    bedroom_floors: set[int] = set()
    for i in range(cfg.num_bedrooms):
        floor = 0 if i == 0 else 1
        bedroom_floors.add(floor)
        rooms.append(
            {
                "id": f"bedroom_{i}",
                "type": "bedroom",
                "name": f"Bedroom {i + 1}",
                "floor": floor,
            }
        )
        if cfg.attached_toilets:
            rooms.append(
                {
                    "id": f"toilet_ens_{i}",
                    "type": "bathroom_master" if i == 0 else "toilet",
                    "name": "Master Bath" if i == 0 else f"Toilet (Bed {i + 1})",
                    "floor": floor,
                    "attached_to": f"bedroom_{i}",
                }
            )

    # Common toilets — distribute across floors, then guarantee every floor
    # that has rooms but no bedroom gets >= 1 (the solver always populates
    # floors 0 and 1 via the staircase). Redistribute, never add: pull one
    # toilet from the most-served floor.
    toilet_floors = [
        0 if i < max(1, cfg.num_bedrooms // 2) else 1 for i in range(cfg.toilets)
    ]
    for f in (0, 1):
        if f not in bedroom_floors and toilet_floors and f not in toilet_floors:
            donor = max(set(toilet_floors), key=toilet_floors.count)
            toilet_floors[toilet_floors.index(donor)] = f
    for i, floor in enumerate(toilet_floors):
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
    pin_room_types: set[str] | None = None,
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
    # Rooms of pinned types anchor their wall lines: neighbours merge ONTO
    # them, they never move. Used for the staircase core in the post-fill
    # snap — per-floor fill rooms cluster the stair with different
    # neighbours on each floor, and independent deltas broke the exact
    # GF/FF stair stacking the solver guarantees.
    pinned_ids = {
        r.id
        for rooms in floors
        for r in rooms
        if pin_room_types and r.type in pin_room_types
    }

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

    for e in edges:
        if e.key[1] in pinned_ids:
            e.pinned = True

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

    def cluster_feasible(cluster: list[_SnapEdge], target: float) -> bool:
        # Per-edge min-dims pre-check (approximate: ignores the room's other
        # edge moving in a different cluster — build() remains the exact
        # safety net). Lets flush() pick a target every member can reach
        # instead of the mean, which one starved room vetoes via revert,
        # leaving the near-miss lines the merge existed to remove.
        for e in cluster:
            if e.pinned:
                continue
            fi, rid, axis, side = e.key
            r = originals.get((fi, rid))
            if r is None:
                continue
            delta = target - e.line
            dim = r.width if axis == "x" else r.depth
            new_dim = dim + (delta if side == "hi" else -delta)
            mins = min_dims.get(rid, {})
            min_dim = mins.get("min_width_m" if axis == "x" else "min_depth_m", 0.0)
            other = r.depth if axis == "x" else r.width
            if (
                new_dim < min_dim - 1e-9
                or new_dim * other < mins.get("min_area_sqm", 0.0) - 1e-9
                or new_dim * other > mins.get("max_area_sqm", float("inf")) + 1e-9
            ):
                return False
        return True

    def flush(cluster: list[_SnapEdge]) -> None:
        lines = sorted({round(e.line, 6) for e in cluster})
        if len(lines) < 2:
            return  # already one line — nothing to merge
        pinned = [e for e in cluster if e.pinned]
        if pinned:
            target = pinned[0].line  # plate lines are immovable
        else:
            mean = sum(lines) / len(lines)
            target = next(
                (t for t in [mean, *lines] if cluster_feasible(cluster, t)),
                mean,
            )
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
            or cand.width * cand.depth > mins.get("max_area_sqm", float("inf")) + eps
        ):
            return r  # revert: snap would violate this room's spec min/max
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
    span_caps: dict[str, float] | None = None,
    seed_rooms: dict[str, Room] | None = None,
    deviation_weight: int = 0,
) -> Layout | None:
    """Run a single CP-SAT solve and return a Layout if successful.

    Stage 2 closed-loop knobs:
    - span_caps: {"x": metres, "y": metres} — cap every room's dimension on
      that axis (structapi found a beam span the section iteration couldn't
      satisfy; splitting the span forces an extra aligned wall/grid line).
      Rooms whose spec minimum exceeds the cap keep their minimum — the
      loop's cap-exhaustion path reports those instead of going infeasible.
    - seed_rooms: room_id -> approved Room; adds CP-SAT hints AND a
      deviation penalty so the re-solve stays as close as possible to the
      user-approved plan (drift minimisation).
    """

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
        # Wet rooms are capped at the generator's wet cap (4.6 sqm — rooms
        # above it get split into toilet+passage anyway) so the solver never
        # emits ballooned toilets; guard against custom minima above the cap.
        if rtype in _WET_TYPES:
            max_area_mm2 = max(min(max_area_mm2, _WET_AREA_CAP_MM2), min_area_mm2)

        min_d = _mm(spec["min_width_m"])  # use min_width as min depth too
        max_d = min(_mm(spec.get("max_width_m", 8.0)), bd)

        if span_caps:
            if span_caps.get("x"):
                max_w = min(max_w, max(_mm(span_caps["x"]), min_w))
            if span_caps.get("y"):
                max_d = min(max_d, max(_mm(span_caps["y"]), min_d))

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

    # Hard en-suite adjacency: each en-suite must share a wall segment with
    # its bedroom — facing edges within one internal wall thickness AND
    # perpendicular overlap >= 900 mm (door width), OR'd over the four side
    # cases (mirrors the reified align_bools pattern below).
    by_id = {rv.room_id: rv for rv in room_vars}
    for rd in room_defs:
        bed_id = rd.get("attached_to")
        if not bed_id:
            continue
        ens = by_id.get(rd["id"])
        bed = by_id.get(bed_id)
        if ens is None or bed is None or ens.floor != bed.floor:
            continue
        side_bools = []
        # (gap, a_lo, a_hi, b_lo, b_hi): gap between the facing edges, then
        # the two rooms' extents on the perpendicular axis.
        cases = (
            (bed.x - ens.xe, ens.y, ens.ye, bed.y, bed.ye),  # ens left of bed
            (ens.x - bed.xe, ens.y, ens.ye, bed.y, bed.ye),  # ens right of bed
            (bed.y - ens.ye, ens.x, ens.xe, bed.x, bed.xe),  # ens in front
            (ens.y - bed.ye, ens.x, ens.xe, bed.x, bed.xe),  # ens behind
        )
        for ci, (gap, a_lo, a_hi, b_lo, b_hi) in enumerate(cases):
            sb = model.new_bool_var(f"ens_{ens.room_id}_{ci}")
            model.add(gap >= 0).only_enforce_if(sb)
            model.add(gap <= _IWT_MM).only_enforce_if(sb)
            model.add(a_hi - b_lo >= _ENSUITE_MIN_OVERLAP_MM).only_enforce_if(sb)
            model.add(b_hi - a_lo >= _ENSUITE_MIN_OVERLAP_MM).only_enforce_if(sb)
            side_bools.append(sb)
        model.add_bool_or(side_bools)

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
    # Wet rooms are excluded — growth pressure ballooned toilets to their
    # 6 sqm spec max; they get the opposite (shrink) pressure instead so
    # they settle at min-compliant size.
    size_terms = [rv.w + rv.d for rv in room_vars if rv.room_type not in _WET_TYPES]
    wet_shrink_terms = [
        WET_SHRINK_WEIGHT * (rv.w + rv.d)
        for rv in room_vars
        if rv.room_type in _WET_TYPES
    ]

    # ── Soft toilet-placement penalties ──────────────────────────────────────
    # Common (non-en-suite) toilets/WCs: penalise the front band facing the
    # road (heavier opposite the gate/main door) and sharing a wall with the
    # staircase or parking. Soft terms only — hard versions go infeasible on
    # small plots. En-suites are exempt: their position follows the bedroom.
    penalty_terms = []
    ensuite_ids = {rd["id"] for rd in room_defs if rd.get("attached_to")}
    common_wet = [
        rv
        for rv in room_vars
        if rv.room_type in ("toilet", "wc_only") and rv.room_id not in ensuite_ids
    ]
    repel_targets = [
        rv
        for rv in room_vars
        if rv.room_type == "staircase" or rv.room_type in _PARKING_TYPES
    ]
    for rv in common_wet:
        # (a) front band: toilet within the front 25% of the plate depth
        # (road side is y-min post-rotation). Tested on the FRONT EDGE, not
        # the centre — a centre test is gameable by growing the room until
        # the centre escapes the band (measured: toilets inflated to 6 sqm
        # to dodge the penalty). Band at 30% so post-solve snap jitter
        # (±SNAP_TOL_M) can't push a compliant room back under 25%.
        fb = model.new_bool_var(f"front_{rv.room_id}")
        model.add(10 * rv.y <= 3 * bd).only_enforce_if(fb)
        model.add(10 * rv.y > 3 * bd).only_enforce_if(fb.Not())
        penalty_terms.append(TOILET_FRONT_PENALTY * fb)

        # heavier when centre-x also sits in the middle third of the plate
        # width — straight opposite the compound gate / main door axis
        m1 = model.new_bool_var(f"midx1_{rv.room_id}")
        model.add(3 * (2 * rv.x + rv.w) >= 2 * bw).only_enforce_if(m1)
        model.add(3 * (2 * rv.x + rv.w) < 2 * bw).only_enforce_if(m1.Not())
        m2 = model.new_bool_var(f"midx2_{rv.room_id}")
        model.add(3 * (2 * rv.x + rv.w) <= 4 * bw).only_enforce_if(m2)
        model.add(3 * (2 * rv.x + rv.w) > 4 * bw).only_enforce_if(m2.Not())
        fbm = model.new_bool_var(f"frontmid_{rv.room_id}")
        model.add_bool_and([fb, m1, m2]).only_enforce_if(fbm)
        model.add_bool_or([fb.Not(), m1.Not(), m2.Not()]).only_enforce_if(fbm.Not())
        penalty_terms.append(TOILET_FRONT_MID_PENALTY * fbm)

        # (b)+(c) repulsion: reified "shares a wall with staircase/parking"
        for other in repel_targets:
            if other.floor != rv.floor:
                continue
            weight = (
                TOILET_STAIR_PENALTY
                if other.room_type == "staircase"
                else TOILET_PARKING_PENALTY
            )
            share = model.new_bool_var(f"rep_{rv.room_id}_{other.room_id}")
            rep_cases = (
                (other.x - rv.xe, rv.y, rv.ye, other.y, other.ye),
                (rv.x - other.xe, rv.y, rv.ye, other.y, other.ye),
                (other.y - rv.ye, rv.x, rv.xe, other.x, other.xe),
                (rv.y - other.ye, rv.x, rv.xe, other.x, other.xe),
            )
            # One-direction encoding (exact under minimization): each literal
            # is only forced TRUE when its inequality holds (lb=0 ⇒ inequality
            # violated), and the clause forces `share` when all four hold.
            # The solver zeroes any free literal to dodge the penalty, so no
            # spurious payment — at half the enforcement cost of full
            # reification (which measurably starved the search budget).
            for ci, (gap, a_lo, a_hi, b_lo, b_hi) in enumerate(rep_cases):
                lits = []
                for li, (expr, lo) in enumerate(
                    (
                        (gap, 0),
                        (_REPULSION_GAP_MM - gap, 0),
                        (a_hi - b_lo, _MIN_SHARE_OVERLAP_MM),
                        (b_hi - a_lo, _MIN_SHARE_OVERLAP_MM),
                    )
                ):
                    lb = model.new_bool_var(
                        f"repl_{rv.room_id}_{other.room_id}_{ci}_{li}"
                    )
                    model.add(expr < lo).only_enforce_if(lb.Not())
                    lits.append(lb)
                model.add_bool_or([lb.Not() for lb in lits] + [share])
            penalty_terms.append(weight * share)

    # ── Soft parking-placement penalty ────────────────────────────────────────
    # Parking has no positional constraint otherwise and can end up boxed in
    # with no direct road/exterior access. Soft term only, matching the
    # toilet front-band precedent above — a hard rv.y == 0 constraint would
    # be an even higher infeasibility risk than the toilet case already
    # rejected as hard, given parking's larger min footprint.
    for rv in room_vars:
        if rv.room_type not in _PARKING_TYPES:
            continue
        not_road = model.new_bool_var(f"not_road_{rv.room_id}")
        model.add(rv.y > 0).only_enforce_if(not_road)
        model.add(rv.y <= 0).only_enforce_if(not_road.Not())
        penalty_terms.append(PARKING_ROAD_PENALTY * not_road)

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

    # Drift minimisation (closed-loop re-solve): hint the solver toward the
    # approved geometry and penalise deviation from it, so a structural
    # constraint changes as little of the user-approved plan as possible.
    deviation_terms = []
    if seed_rooms and deviation_weight > 0:
        for rv in room_vars:
            seed = seed_rooms.get(rv.room_id)
            if seed is None:
                continue
            targets = (
                (rv.x, _mm(seed.x) - ox, bw),
                (rv.y, _mm(seed.y) - oy, bd),
                (rv.w, _mm(seed.width), bw),
                (rv.d, _mm(seed.depth), bd),
            )
            for ti, (var, target, cap) in enumerate(targets):
                clamped = min(max(target, 0), cap)
                model.add_hint(var, clamped)
                dv = model.new_int_var(0, cap, f"dev_{rv.room_id}_{ti}")
                model.add_abs_equality(dv, var - clamped)
                deviation_terms.append(dv)

    base_objective = (
        sum(dist_terms)
        - sum(size_terms)
        - ALIGN_BONUS * sum(align_bools)
        + sum(wet_shrink_terms)
        + deviation_weight * sum(deviation_terms)
    )

    # ── Solve ─────────────────────────────────────────────────────────────────
    def _make_solver(
        det_budget: float, wall_budget: float = SOLVE_TIME_S
    ) -> cp_model.CpSolver:
        s = cp_model.CpSolver()
        s.parameters.max_time_in_seconds = wall_budget
        # Machine-independent work budget: on fast machines this binds so
        # repeated runs return the SAME incumbent; on slow machines (CI
        # runners, cold Cloud Run) the wall-clock cap above binds so runtime
        # never grows. Wall-clock-only budgets made solution quality depend
        # on machine speed — the source of CI-only/dev-only test failures in
        # the grid-alignment and leftover-gap suites.
        s.parameters.max_deterministic_time = det_budget
        s.parameters.num_search_workers = 1  # deterministic single-thread
        return s

    # Two-phase solve when placement penalties are active: the single-thread
    # deterministic budget is too small to escape a first incumbent that
    # pays the (huge) penalties — measured: 450k of penalties stayed paid,
    # or hint-repair burned the whole budget (status UNKNOWN) when guessed
    # partial hints didn't fit. Phase 1 solves the well-behaved penalty-free
    # model; its solution is a complete, feasible hint for phase 2, which
    # then spends its entire budget relocating toilets out of penalty zones.
    if penalty_terms and not seed_rooms:
        model.minimize(base_objective)
        pre = _make_solver(det_budget=0.7, wall_budget=PHASE1_TIME_S)
        pre_status = pre.solve(model)
        if pre_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Hint everything EXCEPT the common toilets' and parking's
            # positions: with the rest of the plan anchored, phase 2 reduces
            # to re-placing just those rooms — a subproblem small enough to
            # escape the penalty zones inside the budget (fully-hinted runs
            # kept them glued to their penalised phase-1 spot).
            free_ids = {rv.room_id for rv in common_wet} | {
                rv.room_id for rv in room_vars if rv.room_type in _PARKING_TYPES
            }
            model.clear_hints()
            for rv in room_vars:
                hinted = (
                    (rv.w, rv.d) if rv.room_id in free_ids else (rv.x, rv.y, rv.w, rv.d)
                )
                for var in hinted:
                    model.add_hint(var, pre.value(var))

    model.minimize(base_objective + sum(penalty_terms))
    solver = _make_solver(det_budget=1.5)

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
    solved_areas = {r.id: r.area for r in gf_rooms + ff_rooms}
    for rd2 in room_defs:
        spec2 = specs.get(rd2["type"], specs.get("utility"))
        min_dims[rd2["id"]] = {
            "min_width_m": spec2["min_width_m"],
            "min_depth_m": spec2["min_width_m"],
            "min_area_sqm": rd2.get("custom_min_area") or spec2["min_area_sqm"],
        }
        # Wet rooms leave the solve at min-compliant size (WET_SHRINK_WEIGHT)
        # but snapping has no size objective and can inflate them by up to
        # SNAP_TOL_M per edge — cap snap growth so they stay toilet-sized.
        if rd2["type"] in _WET_TYPES:
            min_dims[rd2["id"]]["max_area_sqm"] = round(
                min(
                    spec2["max_area_sqm"],
                    _WET_AREA_CAP_MM2 / (SCALE * SCALE),
                    solved_areas.get(rd2["id"], 1e9) * 1.35,
                ),
                3,
            )
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


def resolve_with_constraints(
    cfg: PlotConfig,
    ewt: float,
    approved: Layout,
    span_caps: dict[str, float],
    deviation_weight: int = 3,
) -> Layout | None:
    """Closed-loop re-solve: same room programme as the approved layout,
    with structural span caps applied and drift from the approved geometry
    minimised (hints + deviation penalty). Returns None when infeasible."""
    specs = _load_specs()
    room_defs = _build_room_list(cfg, specs)
    seed_rooms = {
        r.id: r for r in approved.ground_floor.rooms + approved.first_floor.rooms
    }

    stair_zone = "mid"
    stair = next(
        (r for r in approved.ground_floor.rooms if r.type == "staircase"), None
    )
    if stair is not None:
        by1 = cfg.setback_front + ewt
        bd_m = cfg.plot_length - cfg.setback_front - cfg.setback_rear - 2 * ewt
        if bd_m > 0:
            rel = (stair.y + stair.depth / 2 - by1) / bd_m
            stair_zone = "front" if rel < 1 / 3 else ("mid" if rel < 2 / 3 else "rear")

    try:
        return _solve_one(
            cfg,
            ewt,
            room_defs,
            specs,
            stair_zone,
            approved.id,
            approved.name,
            span_caps=span_caps,
            seed_rooms=seed_rooms,
            deviation_weight=deviation_weight,
        )
    except Exception:
        return None


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
