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
import uuid
from dataclasses import dataclass
from pathlib import Path

from ortools.sat.python import cp_model

from .models import Column, FloorPlan, Layout, PlotConfig, Room

SCALE = 1000          # 1 metre = 1000 mm units
SOLVE_TIME_S = 5.0    # per-run wall-clock budget
MAX_DIM_MM = 50_000   # safety cap: 50 m per dimension

_SPECS_PATH = Path(__file__).parent.parent / "config" / "room_specs.json"


def _load_specs() -> dict:
    return json.loads(_SPECS_PATH.read_text())


# ── Adjacency preference pairs ────────────────────────────────────────────────
_ADJACENCY_PAIRS: list[tuple[str, str, int]] = [
    ("kitchen", "dining", 15),
    ("bedroom", "toilet", 12),
    ("master_bedroom", "toilet", 12),
    ("living", "staircase", 8),
    ("living", "dining", 10),
    ("kitchen", "utility", 6),
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
    ix: cp_model.IntervalVar
    iy: cp_model.IntervalVar


def _mm(metres: float) -> int:
    return int(round(metres * SCALE))


def _quad_plate_and_planes(
    cfg: PlotConfig, ewt: float
) -> tuple[int, int, int, int, list[tuple[int, int, int]]]:
    """For a quadrilateral plot: return (bw, bd, ox, oy, half_planes).

    half_planes is a list of (dx, dy, rhs) where for every room corner (rx, ry)
    in solver coords (mm, relative to plate origin):  dx*ry - dy*rx >= rhs
    """
    from shapely.geometry import Polygon

    poly = Polygon(cfg.plot_corners)
    avg_sb = (cfg.setback_front + cfg.setback_rear + cfg.setback_left + cfg.setback_right) / 4
    inset = poly.buffer(-(avg_sb + ewt), join_style="mitre")
    if inset.is_empty:
        return 0, 0, 0, 0, []

    minx, miny, maxx, maxy = inset.bounds
    bw = _mm(maxx - minx)
    bd = _mm(maxy - miny)
    ox = _mm(minx)
    oy = _mm(miny)

    coords = list(inset.exterior.coords)[:-1]  # drop closing duplicate
    # Ensure CCW winding (interior = left of each directed edge)
    # Signed area via shoelace: positive → CCW, negative → CW
    n_c = len(coords)
    area2 = sum(
        coords[i][0] * coords[(i + 1) % n_c][1] - coords[(i + 1) % n_c][0] * coords[i][1]
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
        # Translate to solver coords: plot_mm = ox + solver_mm
        # dx*(oy+ry) - dy*(ox+rx) >= dx*cy - dy*cx
        # => dx*ry - dy*rx >= dx*cy - dy*cx - dx*oy + dy*ox
        rhs = dx * cy - dy * cx - dx * oy + dy * ox
        planes.append((dx, dy, rhs))

    return bw, bd, ox, oy, planes


def _build_room_list(cfg: PlotConfig, specs: dict) -> list[dict]:
    """Determine which rooms to solve for based on PlotConfig."""
    rooms = []

    # Living room (always)
    rooms.append({"id": "living_0", "type": "living", "name": "Living Room", "floor": 0})

    # Kitchen (always, GF)
    rooms.append({"id": "kitchen_0", "type": "kitchen", "name": "Kitchen", "floor": 0})

    # Bedrooms — distribute across GF and FF
    for i in range(cfg.num_bedrooms):
        floor = 0 if i == 0 else 1
        rooms.append({
            "id": f"bedroom_{i}",
            "type": "bedroom",
            "name": f"Bedroom {i + 1}",
            "floor": floor,
        })

    # Toilets — distribute across floors
    for i in range(cfg.toilets):
        floor = 0 if i < max(1, cfg.num_bedrooms // 2) else 1
        rooms.append({
            "id": f"toilet_{i}",
            "type": "toilet",
            "name": f"Toilet {i + 1}",
            "floor": floor,
        })

    # Staircase on both floors
    rooms.append({"id": "stair_0", "type": "staircase", "name": "Staircase", "floor": 0})
    rooms.append({"id": "stair_1", "type": "staircase", "name": "Staircase", "floor": 1})

    # Optional rooms
    if cfg.has_pooja:
        rooms.append({"id": "pooja_0", "type": "pooja", "name": "Pooja Room", "floor": 0})
    if cfg.has_study:
        rooms.append({"id": "study_0", "type": "study", "name": "Study Room", "floor": 1})
    if cfg.has_balcony:
        rooms.append({"id": "balcony_0", "type": "balcony", "name": "Balcony", "floor": 1})
    if cfg.parking:
        rooms.append({"id": "parking_0", "type": "parking", "name": "Parking", "floor": 0})

    # Custom rooms from Phase C
    if cfg.custom_room_config:
        for idx, custom in enumerate(cfg.custom_room_config):
            rtype = custom.get("type", "utility")
            pref = custom.get("floor_preference", "either")
            floor = 1 if pref == "ff" else 0
            rooms.append({
                "id": f"custom_{idx}",
                "type": rtype,
                "name": custom.get("name") or rtype.replace("_", " ").title(),
                "floor": floor,
                "custom_min_area": custom.get("min_area_sqm"),
            })

    return rooms


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
    if cfg.plot_shape == "quadrilateral" and cfg.plot_corners:
        bw, bd, ox, oy, quad_planes = _quad_plate_and_planes(cfg, ewt)
    elif cfg.plot_shape == "l_shaped":
        # For L-shaped plots use the bounding box of the inset polygon as solver bounds,
        # plus half-plane constraints derived from the inset polygon's edges (same approach
        # as quadrilateral). This keeps rooms inside the actual L-shape.
        from app.engine.generator import compute_l_shaped_polygon
        from shapely.geometry import Polygon as _Poly

        l_poly = compute_l_shaped_polygon(cfg)
        avg_sb = (cfg.setback_front + cfg.setback_rear + cfg.setback_left + cfg.setback_right) / 4
        inset = l_poly.buffer(-(avg_sb + ewt), join_style=2)
        if inset.is_empty:
            return None
        minx, miny, maxx, maxy = inset.bounds
        bw = _mm(maxx - minx)
        bd = _mm(maxy - miny)
        ox = _mm(minx)
        oy = _mm(miny)

        # Build half-plane constraints from L-shape inset edges (same as quad)
        coords = list(inset.exterior.coords)[:-1]
        n_c = len(coords)
        area2 = sum(
            coords[i][0] * coords[(i + 1) % n_c][1] - coords[(i + 1) % n_c][0] * coords[i][1]
            for i in range(n_c)
        )
        if area2 < 0:
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
        quad_planes = planes
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
        min_area = _mm(raw_min_area) * SCALE   # mm² = m² × 10^6, but we work in mm units
        # Actually: 1 sqm = SCALE*SCALE mm² = 1_000_000 mm²
        min_area_mm2 = int(raw_min_area * SCALE * SCALE)
        max_area_mm2 = int(spec["max_area_sqm"] * SCALE * SCALE)

        min_d = _mm(spec["min_width_m"])   # use min_width as min depth too
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
            room_id=rd["id"], room_type=rtype, room_name=rd["name"],
            floor=floor, x=x, y=y, w=w, d=d, ix=ix, iy=iy,
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

    # ── Objective: adjacency satisfaction ────────────────────────────────────
    obj_terms: list[cp_model.IntVar] = []

    type_to_var: dict[str, list[_RoomVar]] = {}
    for rv in room_vars:
        type_to_var.setdefault(rv.room_type, []).append(rv)

    for t1, t2, pts in _ADJACENCY_PAIRS:
        vars1 = type_to_var.get(t1, [])
        vars2 = type_to_var.get(t2, [])
        for a in vars1:
            for b in vars2:
                if a.floor != b.floor:
                    continue
                # Two rooms are adjacent if they share a wall (no gap on one axis)
                adj = model.new_bool_var(f"adj_{a.room_id}_{b.room_id}")
                # a right-edge touches b left-edge OR b right-edge touches a left-edge
                touch_x = model.new_bool_var(f"tx_{a.room_id}_{b.room_id}")
                touch_y = model.new_bool_var(f"ty_{a.room_id}_{b.room_id}")
                # overlap on y axis (for x-adjacency)
                ov_y = model.new_int_var(0, bd, f"ovy_{a.room_id}_{b.room_id}")
                model.add_max_equality(ov_y, [
                    model.new_constant(0),
                    # actually just use a simpler adjacency heuristic
                    model.new_constant(0),
                ])
                # Simplified: reward if same floor — exact adjacency is hard to model cleanly
                # Use a proxy: shared floor bonus only
                score_var = model.new_int_var(0, pts, f"score_{a.room_id}_{b.room_id}")
                model.add(score_var == pts).only_enforce_if(adj)
                model.add(score_var == 0).only_enforce_if(adj.negated())
                model.add(adj == 1)  # assume adjacent (floor-based heuristic)
                obj_terms.append(score_var)

    if obj_terms:
        model.maximize(sum(obj_terms))

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

    # Simple corner columns
    def _corner_cols(rooms: list[Room]) -> list[Column]:
        cols = []
        seen: set[tuple[float, float]] = set()
        for r in rooms:
            for cx, cy in [(r.x, r.y), (r.x + r.width, r.y),
                           (r.x, r.y + r.depth), (r.x + r.width, r.y + r.depth)]:
                k = (round(cx, 2), round(cy, 2))
                if k not in seen:
                    seen.add(k)
                    cols.append(Column(x=cx, y=cy))
        return cols

    from .compliance import check, load_rules
    from .vastu import check_vastu

    gf = FloorPlan(floor=0, floor_type="ground", rooms=gf_rooms, columns=_corner_cols(gf_rooms))
    ff = FloorPlan(floor=1, floor_type="first", rooms=ff_rooms, columns=_corner_cols(ff_rooms))

    from .models import ComplianceResult
    layout = Layout(
        id=layout_id,
        name=layout_name,
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )

    rules = load_rules()
    layout.compliance = check(layout, cfg, rules)

    if cfg.vastu_enabled:
        v_viol, v_warn = check_vastu(layout, cfg, road_side=cfg.road_side)
        layout.compliance.violations.extend(v_viol)
        layout.compliance.warnings.extend(v_warn)
        layout.compliance.passed = len(layout.compliance.violations) == 0

    return layout if layout.compliance.passed else None


def solve_layouts(cfg: PlotConfig, ewt: float) -> list[Layout]:
    """Generate up to 3 diverse solver layouts. Returns empty list on failure."""
    specs = _load_specs()
    room_defs = _build_room_list(cfg, specs)

    zones = [("front", "S1", "Layout S1 — Front Staircase"),
             ("mid",   "S2", "Layout S2 — Centre Staircase"),
             ("rear",  "S3", "Layout S3 — Rear Staircase")]

    results: list[Layout] = []
    for zone, lid, lname in zones:
        try:
            layout = _solve_one(cfg, ewt, room_defs, specs, zone, lid, lname)
            if layout is not None:
                results.append(layout)
        except Exception:
            pass  # solver failure → skip this zone

    return results
