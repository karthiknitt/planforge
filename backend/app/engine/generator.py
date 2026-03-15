from __future__ import annotations

from .archetypes import layout_a, layout_b, layout_c, layout_d, layout_e, layout_f
from .compliance import check, load_rules
from .models import FloorPlan, Layout, PlotConfig, Room
from .scorer import rank_and_select
from .solver import solve_layouts
from .vastu import check_vastu


# ── Blank area detection & filling ────────────────────────────────────────────

_ROOM_COUNTER: dict[str, int] = {}


def _next_id(prefix: str) -> str:
    _ROOM_COUNTER[prefix] = _ROOM_COUNTER.get(prefix, 0) + 1
    return f"{prefix}_{_ROOM_COUNTER[prefix]}"


def _plate_box(cfg: PlotConfig, ewt: float):
    """Return a Shapely box for the usable floor plate."""
    from shapely.geometry import box
    ox = cfg.setback_left + ewt
    oy = cfg.setback_front + ewt
    w = cfg.plot_width - cfg.setback_left - cfg.setback_right - 2 * ewt
    d = cfg.plot_length - cfg.setback_front - cfg.setback_rear - 2 * ewt
    return box(ox, oy, ox + w, oy + d)


def _fill_blank_areas(
    floor_plan: FloorPlan,
    cfg: PlotConfig,
    ewt: float,
    is_topmost: bool,
) -> list[str]:
    """
    Detect unoccupied space in ``floor_plan`` and fill it intelligently.

    For the topmost occupied floor:
      ≥ 15 m²  → Open Terrace
      4–15 m²  → Utility
      < 4 m²   → merge into adjacent room

    For other floors:
      ≥ 8 m²   → Store Room
      4–8 m²   → Utility
      < 4 m²   → merge into adjacent room

    Returns a list of human-readable notes about what was added/changed.
    """
    from shapely.geometry import box
    from shapely.ops import unary_union

    notes: list[str] = []
    rooms = floor_plan.rooms
    if not rooms:
        return notes

    plate = _plate_box(cfg, ewt)
    occupied = unary_union([box(r.x, r.y, r.x + r.width, r.y + r.depth) for r in rooms])
    leftover = plate.difference(occupied)

    if leftover.is_empty or leftover.area < 0.5:
        return notes

    # Decompose MultiPolygon into individual pieces
    if hasattr(leftover, "geoms"):
        regions = [g for g in leftover.geoms if g.area >= 0.5]
    else:
        regions = [leftover] if leftover.area >= 0.5 else []

    for region in regions:
        area = round(region.area, 2)
        minx, miny, maxx, maxy = region.bounds
        rw = round(maxx - minx, 3)
        rd = round(maxy - miny, 3)

        if area < 0.5:
            continue

        # Skip non-rectangular leftovers — bounding-box rooms would overlap existing rooms.
        # A region is "usable" if its area fills ≥ 70 % of its own bounding box.
        bbox_area = rw * rd
        if bbox_area > 0 and (area / bbox_area) < 0.70:
            _absorb_into_adjacent(floor_plan, region, minx, miny, maxx, maxy, notes)
            continue

        if is_topmost:
            if area >= 15.0:
                # Large top-floor leftover → Open Terrace (min 1.5 m each dimension)
                if rw >= 1.5 and rd >= 1.5:
                    room_id = _next_id("open_terrace")
                    floor_plan.rooms.append(Room(
                        id=room_id,
                        name="Open Terrace",
                        type="balcony",  # closest existing type for compliance purposes
                        x=round(minx, 3),
                        y=round(miny, 3),
                        width=rw,
                        depth=rd,
                    ))
                    notes.append(
                        f"Open Terrace ({area:.1f} sqm) added to top floor."
                    )
                else:
                    _absorb_into_adjacent(floor_plan, region, minx, miny, maxx, maxy, notes)
            elif area >= 4.0:
                # Medium top-floor leftover → Utility
                if rw >= 1.5 and rd >= 1.5:
                    room_id = _next_id("utility_auto")
                    floor_plan.rooms.append(Room(
                        id=room_id,
                        name="Utility",
                        type="utility",
                        x=round(minx, 3),
                        y=round(miny, 3),
                        width=rw,
                        depth=rd,
                    ))
                    notes.append(
                        f"Utility ({area:.1f} sqm) added to top floor."
                    )
                else:
                    _absorb_into_adjacent(floor_plan, region, minx, miny, maxx, maxy, notes)
            else:
                # < 4 m² → merge into adjacent room
                _absorb_into_adjacent(floor_plan, region, minx, miny, maxx, maxy, notes)

        else:
            if area >= 8.0:
                # Large gap → Store Room
                if rw >= 1.5 and rd >= 1.5:
                    room_id = _next_id("store_auto")
                    floor_plan.rooms.append(Room(
                        id=room_id,
                        name="Store Room",
                        type="store_room",
                        x=round(minx, 3),
                        y=round(miny, 3),
                        width=rw,
                        depth=rd,
                    ))
                    notes.append(
                        f"Store Room ({area:.1f} sqm) added to Ground Floor."
                    )
                else:
                    _absorb_into_adjacent(floor_plan, region, minx, miny, maxx, maxy, notes)
            elif area >= 4.0:
                # Medium gap → Utility
                if rw >= 1.5 and rd >= 1.5:
                    room_id = _next_id("utility_auto")
                    floor_plan.rooms.append(Room(
                        id=room_id,
                        name="Utility",
                        type="utility",
                        x=round(minx, 3),
                        y=round(miny, 3),
                        width=rw,
                        depth=rd,
                    ))
                    notes.append(
                        f"Utility ({area:.1f} sqm) added to Ground Floor."
                    )
                else:
                    _absorb_into_adjacent(floor_plan, region, minx, miny, maxx, maxy, notes)
            else:
                # < 4 m² → merge into adjacent room
                _absorb_into_adjacent(floor_plan, region, minx, miny, maxx, maxy, notes)

    return notes


def _absorb_into_adjacent(
    floor_plan: FloorPlan,
    region,
    minx: float, miny: float, maxx: float, maxy: float,
    notes: list[str],
) -> None:
    """Expand the largest room that shares an edge with the leftover region."""
    tol = 0.05
    candidates = []
    for room in floor_plan.rooms:
        # Shares right edge with leftover's left edge
        if abs(room.x + room.width - minx) < tol and room.y < maxy and room.y + room.depth > miny:
            candidates.append((room, "right"))
        # Shares top edge with leftover's bottom edge
        elif abs(room.y + room.depth - miny) < tol and room.x < maxx and room.x + room.width > minx:
            candidates.append((room, "top"))
        # Shares left edge with leftover's right edge
        elif abs(room.x - maxx) < tol and room.y < maxy and room.y + room.depth > miny:
            candidates.append((room, "left"))
        # Shares bottom edge with leftover's top edge
        elif abs(room.y - maxy) < tol and room.x < maxx and room.x + room.width > minx:
            candidates.append((room, "bottom"))

    if not candidates:
        return

    # Pick the candidate with the largest area
    best_room, direction = max(candidates, key=lambda rc: rc[0].area)
    old_area = best_room.area

    if direction == "right":
        best_room.width = round(best_room.width + (maxx - minx), 3)
    elif direction == "top":
        best_room.depth = round(best_room.depth + (maxy - miny), 3)
    elif direction == "left":
        best_room.x = round(minx, 3)
        best_room.width = round(best_room.width + (maxx - minx), 3)
    elif direction == "bottom":
        best_room.y = round(miny, 3)
        best_room.depth = round(best_room.depth + (maxy - miny), 3)

    notes.append(
        f"{best_room.name} expanded from {old_area:.1f} m² → {best_room.area:.1f} m² "
        f"to absorb unused space on floor {floor_plan.floor}."
    )


def generate(cfg: PlotConfig) -> list[Layout]:
    """Generate layouts using the CP-SAT solver (primary) with archetype fallback.

    Returns up to 3 passing layouts ranked by quality score.
    """
    rules = load_rules()
    ewt = rules["external_wall_thickness_mm"] / 1000
    iwt = rules["internal_wall_thickness_mm"] / 1000

    # ── Solver path (Phase A) ─────────────────────────────────────────────────
    solver_layouts: list[Layout] = []
    try:
        solver_layouts = solve_layouts(cfg, ewt)
    except Exception:
        pass  # always fall through to archetypes

    solver_ids = {l.id for l in solver_layouts}

    # ── Archetype fallback ────────────────────────────────────────────────────
    archetype_layouts: list[Layout] = []
    generators = [layout_a, layout_b, layout_c, layout_d, layout_e]

    for fn in generators:
        layout = fn(cfg, ewt=ewt, iwt=iwt)
        layout.compliance = check(layout, cfg, rules)

        if cfg.vastu_enabled:
            v_violations, v_warnings = check_vastu(layout, cfg, road_side=cfg.road_side)
            layout.compliance.violations.extend(v_violations)
            layout.compliance.warnings.extend(v_warnings)
            layout.compliance.passed = len(layout.compliance.violations) == 0

        if layout.compliance.passed and layout.id not in solver_ids:
            archetype_layouts.append(layout)

    # Layout F: courtyard — conditional on plot area >= 150 sqm
    plot_area = cfg.plot_width * cfg.plot_length
    if plot_area >= 150:
        lf = layout_f(cfg, ewt=ewt, iwt=iwt)
        if lf is not None:
            lf.compliance = check(lf, cfg, rules)
            if cfg.vastu_enabled:
                v_violations, v_warnings = check_vastu(lf, cfg, road_side=cfg.road_side)
                lf.compliance.violations.extend(v_violations)
                lf.compliance.warnings.extend(v_warnings)
                lf.compliance.passed = len(lf.compliance.violations) == 0
            if lf.compliance.passed and lf.id not in solver_ids:
                archetype_layouts.append(lf)

    all_layouts = solver_layouts + archetype_layouts

    # ── Fill blank areas in every passing layout ──────────────────────────────
    ewt = rules["external_wall_thickness_mm"] / 1000
    for layout in all_layouts:
        floor_plans = [layout.ground_floor, layout.first_floor]
        if layout.second_floor:
            floor_plans.append(layout.second_floor)

        # Determine topmost occupied floor index
        topmost_floor = max(fp.floor for fp in floor_plans if fp.rooms)

        space_notes: list[str] = []
        _ROOM_COUNTER.clear()  # reset per-layout to keep IDs readable

        for fp in floor_plans:
            if not fp.rooms:
                continue
            is_top = fp.floor == topmost_floor
            notes = _fill_blank_areas(fp, cfg, ewt, is_topmost=is_top)
            space_notes.extend(notes)

        layout.space_notes = space_notes

    # ── Score and select top 3 ────────────────────────────────────────────────
    top = rank_and_select(all_layouts, cfg, top_n=3)
    # Remap IDs to stable "A", "B", "C" so the export route default works
    for layout, letter in zip(top, ["A", "B", "C"]):
        layout.id = letter
    return top
