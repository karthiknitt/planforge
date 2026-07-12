from __future__ import annotations

from shapely.geometry import Polygon

from .archetypes import layout_a, layout_b, layout_c, layout_d, layout_e, layout_f
from .geometry import compute_l_shaped_polygon  # noqa: F401  (re-export; historical import site)
from .compliance import check, load_rules
from .models import FloorPlan, Layout, PlotConfig, Room
from .scorer import rank_and_select
from .solver import solve_layouts
from .vastu import check_vastu


def _remove_cutout_overlap(
    rooms: list[Room],
    cutout_polygon: Polygon,
    space_notes: list[str],
    floor: int,
) -> list[Room]:
    """Remove rooms whose centre lies within the cutout zone.

    Rooms that are mostly outside the cutout are kept as-is (minor overlaps are
    accepted — the plot boundary is dashed in SVG and real-world construction will
    handle the edge).  Rooms that are completely inside the cutout are removed.
    Rooms where more than 60 % of their area overlaps the cutout are also removed.
    """
    from shapely.geometry import box as _box

    kept: list[Room] = []
    for room in rooms:
        room_box = _box(room.x, room.y, room.x + room.width, room.y + room.depth)
        intersection = room_box.intersection(cutout_polygon)
        overlap_ratio = intersection.area / room_box.area if room_box.area > 0 else 0

        if overlap_ratio > 0.6:
            space_notes.append(
                f"{room.name} removed from floor {floor}: "
                f"{overlap_ratio * 100:.0f}% falls in the L-shaped cutout zone."
            )
        else:
            kept.append(room)
    return kept


# ── Blank area detection & filling ────────────────────────────────────────────

_ROOM_COUNTER: dict[str, int] = {}


def _next_id(prefix: str) -> str:
    _ROOM_COUNTER[prefix] = _ROOM_COUNTER.get(prefix, 0) + 1
    return f"{prefix}_{_ROOM_COUNTER[prefix]}"


def _plate_box(cfg: PlotConfig, ewt: float):
    """Return a Shapely geometry for the usable floor plate.

    For L-shaped plots, returns the L-polygon inset by setbacks + wall thickness.
    For all other shapes, returns a simple rectangle.
    """
    from shapely.geometry import box

    ox = cfg.setback_left + ewt
    oy = cfg.setback_front + ewt
    w = cfg.plot_width - cfg.setback_left - cfg.setback_right - 2 * ewt
    d = cfg.plot_length - cfg.setback_front - cfg.setback_rear - 2 * ewt
    if cfg.plot_shape == "l_shaped" and cfg.cutout_width > 0 and cfg.cutout_height > 0:
        l_poly = compute_l_shaped_polygon(cfg)
        avg_sb = (
            cfg.setback_front + cfg.setback_rear + cfg.setback_left + cfg.setback_right
        ) / 4
        inset = l_poly.buffer(-(avg_sb + ewt), join_style="mitre")
        return inset if not inset.is_empty else box(ox, oy, ox + w, oy + d)
    return box(ox, oy, ox + w, oy + d)


def _fill_blank_areas(
    floor_plan: FloorPlan,
    cfg: PlotConfig,
    ewt: float,
    is_topmost: bool,
) -> list[str]:
    """
    Detect unoccupied space in ``floor_plan`` and fill it intelligently.

    Runs up to 3 passes: absorbing strips into adjacent rooms makes the
    remaining leftover more rectangular, which lets a later pass turn it
    into a real room (Store/Utility/Open Terrace). A single pass could
    neither absorb nor room-ify L-shaped leftovers and left dead space.
    """
    notes: list[str] = []
    for _ in range(3):
        pass_notes = _fill_blank_areas_once(floor_plan, cfg, ewt, is_topmost)
        if not pass_notes:
            break
        notes.extend(pass_notes)
    # Terminating pass: whatever absorb couldn't legally reach (a rectangle
    # may only slide a full edge) is carved into maximal inscribed rectangles
    # and kept as real rooms so no usable dead space survives.
    notes.extend(_rect_fill_remainder(floor_plan, cfg, ewt, is_topmost))
    return notes


def _largest_inscribed_rect(piece):
    """Largest axis-aligned rectangle inside ``piece`` whose corners lie on
    the polygon's own coordinate grid."""
    from shapely.geometry import box

    coords = list(piece.exterior.coords)
    for hole in piece.interiors:
        coords.extend(hole.coords)
    xs = sorted({round(c[0], 3) for c in coords})
    ys = sorted({round(c[1], 3) for c in coords})
    best = None
    best_area = 0.5
    min_side = 1.2 - 1e-3  # tolerance: grid coords carry float noise
    for i, x0 in enumerate(xs[:-1]):
        for x1 in xs[i + 1 :]:
            w = x1 - x0
            if w < min_side:
                continue
            for k, y0 in enumerate(ys[:-1]):
                for y1 in ys[k + 1 :]:
                    if y1 - y0 < min_side:
                        continue
                    area = w * (y1 - y0)
                    if area <= best_area:
                        continue
                    cand = box(x0, y0, x1, y1)
                    if cand.difference(piece).area < 0.01:
                        best = cand
                        best_area = area
    return best


def _rect_fill_remainder(
    floor_plan: FloorPlan,
    cfg: PlotConfig,
    ewt: float,
    is_topmost: bool,
) -> list[str]:
    from shapely.geometry import box
    from shapely.ops import unary_union

    notes: list[str] = []
    if not floor_plan.rooms:
        return notes
    plate = _plate_box(cfg, ewt)
    occupied = unary_union(
        [box(r.x, r.y, r.x + r.width, r.y + r.depth) for r in floor_plan.rooms]
    )
    leftover = plate.difference(occupied)
    if leftover.is_empty or leftover.area < 1.5:
        return notes

    for _ in range(12):
        piece = _largest_piece(leftover)
        if piece is None or piece.area < 1.5:
            break
        rect = _largest_inscribed_rect(piece)
        if rect is None or rect.area < 1.5:
            break
        minx, miny, maxx, maxy = rect.bounds
        area = rect.area
        if is_topmost and area >= 15.0:
            rid, name, rtype = _next_id("open_terrace"), "Open Terrace", "balcony"
        elif area >= 4.0:
            rid, name, rtype = _next_id("utility_auto"), "Utility", "utility"
        else:
            rid, name, rtype = _next_id("store_auto"), "Store", "store_room"
        floor_plan.rooms.append(
            Room(
                id=rid,
                name=name,
                type=rtype,
                x=round(minx, 3),
                y=round(miny, 3),
                width=round(maxx - minx, 3),
                depth=round(maxy - miny, 3),
            )
        )
        notes.append(
            f"{name} ({area:.1f} sqm) added on floor {floor_plan.floor} "
            "to use residual space."
        )
        leftover = leftover.difference(rect)
    return notes


def _fill_blank_areas_once(
    floor_plan: FloorPlan,
    cfg: PlotConfig,
    ewt: float,
    is_topmost: bool,
) -> list[str]:
    """
    One fill pass.

    For the topmost occupied floor:
      ≥ 15 m²  → Open Terrace
      4–15 m²  → Utility
      < 4 m²   → merge into adjacent room, else a small Store

    For other floors:
      ≥ 8 m²   → Store Room
      4–8 m²   → Utility
      < 4 m²   → merge into adjacent room, else a small Store

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
    if leftover.geom_type in ("MultiPolygon", "GeometryCollection"):
        regions = [
            g for g in leftover.geoms if g.geom_type == "Polygon" and g.area >= 0.5
        ]
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
                    floor_plan.rooms.append(
                        Room(
                            id=room_id,
                            name="Open Terrace",
                            type="balcony",  # closest existing type for compliance purposes
                            x=round(minx, 3),
                            y=round(miny, 3),
                            width=rw,
                            depth=rd,
                        )
                    )
                    notes.append(f"Open Terrace ({area:.1f} sqm) added to top floor.")
                else:
                    _absorb_into_adjacent(
                        floor_plan, region, minx, miny, maxx, maxy, notes
                    )
            elif area >= 4.0:
                # Medium top-floor leftover → Utility
                if rw >= 1.5 and rd >= 1.5:
                    room_id = _next_id("utility_auto")
                    floor_plan.rooms.append(
                        Room(
                            id=room_id,
                            name="Utility",
                            type="utility",
                            x=round(minx, 3),
                            y=round(miny, 3),
                            width=rw,
                            depth=rd,
                        )
                    )
                    notes.append(f"Utility ({area:.1f} sqm) added to top floor.")
                else:
                    _absorb_into_adjacent(
                        floor_plan, region, minx, miny, maxx, maxy, notes
                    )
            else:
                # < 4 m² → merge into adjacent room, else keep as a small Store
                _absorb_or_store(
                    floor_plan, region, minx, miny, maxx, maxy, notes, area, rw, rd
                )

        else:
            if area >= 8.0:
                # Large gap → Store Room
                if rw >= 1.5 and rd >= 1.5:
                    room_id = _next_id("store_auto")
                    floor_plan.rooms.append(
                        Room(
                            id=room_id,
                            name="Store Room",
                            type="store_room",
                            x=round(minx, 3),
                            y=round(miny, 3),
                            width=rw,
                            depth=rd,
                        )
                    )
                    notes.append(f"Store Room ({area:.1f} sqm) added to Ground Floor.")
                else:
                    _absorb_into_adjacent(
                        floor_plan, region, minx, miny, maxx, maxy, notes
                    )
            elif area >= 4.0:
                # Medium gap → Utility
                if rw >= 1.5 and rd >= 1.5:
                    room_id = _next_id("utility_auto")
                    floor_plan.rooms.append(
                        Room(
                            id=room_id,
                            name="Utility",
                            type="utility",
                            x=round(minx, 3),
                            y=round(miny, 3),
                            width=rw,
                            depth=rd,
                        )
                    )
                    notes.append(f"Utility ({area:.1f} sqm) added to Ground Floor.")
                else:
                    _absorb_into_adjacent(
                        floor_plan, region, minx, miny, maxx, maxy, notes
                    )
            else:
                # < 4 m² → merge into adjacent room, else keep as a small Store
                _absorb_or_store(
                    floor_plan, region, minx, miny, maxx, maxy, notes, area, rw, rd
                )

    return notes


def _absorb_or_store(
    floor_plan: FloorPlan,
    region,
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
    notes: list[str],
    area: float,
    rw: float,
    rd: float,
) -> None:
    """Absorb a small leftover into a neighbour; if geometry forbids that
    (no room edge can slide over it), keep it as a small Store Room rather
    than leaving dead space — but only when it is genuinely rectangular."""
    if _absorb_into_adjacent(floor_plan, region, minx, miny, maxx, maxy, notes):
        return
    bbox_area = rw * rd
    if area >= 1.5 and rw >= 1.2 and rd >= 1.2 and bbox_area > 0:
        if area / bbox_area >= 0.95:
            floor_plan.rooms.append(
                Room(
                    id=_next_id("store_auto"),
                    name="Store",
                    type="store_room",
                    x=round(minx, 3),
                    y=round(miny, 3),
                    width=rw,
                    depth=rd,
                )
            )
            notes.append(
                f"Store ({area:.1f} sqm) added on floor {floor_plan.floor} "
                "(leftover space not absorbable by any adjacent room)."
            )


_NO_ABSORB_TYPES = {
    "toilet",
    "wc_only",
    "bathroom_master",
    "utility",
    "staircase",
    "pooja",
}
_WET_SPLIT_TYPES = {"toilet", "wc_only", "bathroom_master"}
_WET_CAP_SQM = 6.0
_WET_MAX_ASPECT = 3.5
_IWT_GAP = 0.115


def _split_oversized_wet_rooms(floor_plan: FloorPlan) -> list[str]:
    """Carve absurdly large/stretched wet rooms into a compliant wet room
    plus a passage, preserving toilet count (a bare relabel would break
    compliance) and the iwt gap convention between rooms."""
    notes: list[str] = []
    for room in list(floor_plan.rooms):
        if room.type not in _WET_SPLIT_TYPES:
            continue
        aspect = max(room.width, room.depth) / max(min(room.width, room.depth), 1e-6)
        if room.area <= _WET_CAP_SQM and aspect <= _WET_MAX_ASPECT:
            continue
        along_width = room.width >= room.depth  # split along the long axis
        short_side = room.depth if along_width else room.width
        # wet room keeps a compliant slice at the low end of the long axis
        wet_len = max(1.2, min(_WET_CAP_SQM / short_side, 2.2))
        if wet_len * short_side < 3.0:
            # band too narrow to yield a min-area toilet — leave it whole
            # (still compliance-valid at its original size)
            continue
        long_len = room.width if along_width else room.depth
        rem_len = long_len - wet_len - _IWT_GAP
        if rem_len < 0.9:  # nothing meaningful to carve off
            continue
        old_area = room.area
        rem_area = rem_len * short_side
        # A remainder bigger than a real passage becomes a real room —
        # labelling a 15 m² strip "Passage" was the 38 sqm-Passage bug.
        if rem_area >= 9.5:
            rem_name, rem_type = "Family Lounge", "living"
        elif rem_area > 6.0:
            rem_name, rem_type = "Utility", "utility"
        else:
            rem_name, rem_type = "Passage", "passage"
        if along_width:
            passage = Room(
                id=f"{room.id}_passage",
                name=rem_name,
                type=rem_type,
                x=round(room.x + wet_len + _IWT_GAP, 3),
                y=room.y,
                width=round(rem_len, 3),
                depth=room.depth,
            )
            room.width = round(wet_len, 3)
        else:
            passage = Room(
                id=f"{room.id}_passage",
                name=rem_name,
                type=rem_type,
                x=room.x,
                y=round(room.y + wet_len + _IWT_GAP, 3),
                width=room.width,
                depth=round(rem_len, 3),
            )
            room.depth = round(wet_len, 3)
        floor_plan.rooms.append(passage)
        notes.append(
            f"{room.name} ({old_area:.1f} m²) was implausibly large for a wet "
            f"room — split into {room.name} ({room.area:.1f} m²) + {rem_name} "
            f"({passage.area:.1f} m²) on floor {floor_plan.floor}."
        )
    return notes


# Absorption priority: starved habitable rooms grow first; circulation last.
# (Growing the largest neighbour — the old rule — is what ballooned Passages
# to 38 sqm while a 5 sqm Study sat next to dead space.)
_ABSORB_TIER = {
    "study": 0,
    "bedroom": 0,
    "dining": 0,
    "living": 0,
    "home_office": 0,
    "kitchen": 1,
    "store_room": 2,
    "balcony": 2,
    "parking": 3,
    "passage": 4,
}


def _largest_piece(geom):
    if geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        polys = [g for g in geom.geoms if g.geom_type == "Polygon"]
        return max(polys, key=lambda g: g.area) if polys else None
    return geom if geom.geom_type == "Polygon" else None


def _absorb_into_adjacent(
    floor_plan: FloorPlan,
    region,
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
    notes: list[str],
) -> bool:
    """Distribute a leftover region into adjacent rooms.

    Greedy strip decomposition: repeatedly find the best (priority tier,
    smallest room, largest gain) axis-aligned strip that extends one room's
    edge and is fully contained in the remaining empty region, apply it, and
    subtract it. Falls back to the legacy single-shot expansion when no
    contained strip exists. Returns True if any room was expanded.
    """
    from shapely.geometry import box

    remaining = region
    absorbed_any = False
    for _ in range(10):
        if remaining.is_empty or remaining.area < 0.3:
            return absorbed_any
        piece = _largest_piece(remaining)
        if piece is None or piece.area < 0.3:
            return absorbed_any

        coords = list(piece.exterior.coords)
        xs = sorted({round(c[0], 3) for c in coords})
        ys = sorted({round(c[1], 3) for c in coords})

        best = None  # (tier, room_area, -gain, room, strip, direction, dist)
        for room in floor_plan.rooms:
            if room.type in _NO_ABSORB_TYPES:
                continue
            tier = _ABSORB_TIER.get(room.type, 1)
            rx2 = round(room.x + room.width, 3)
            ry2 = round(room.y + room.depth, 3)
            trials = []
            for t in (x - rx2 for x in xs if x > rx2 + 0.05):
                trials.append(("right", box(rx2, room.y, rx2 + t, ry2), t))
            for t in (room.x - x for x in xs if x < room.x - 0.05):
                trials.append(("left", box(room.x - t, room.y, room.x, ry2), t))
            for t in (y - ry2 for y in ys if y > ry2 + 0.05):
                trials.append(("top", box(room.x, ry2, rx2, ry2 + t), t))
            for t in (room.y - y for y in ys if y < room.y - 0.05):
                trials.append(("bottom", box(room.x, room.y - t, rx2, room.y), t))
            for direction, strip, dist in trials:
                if strip.area < 0.25:
                    continue
                if strip.difference(piece).area > 0.02:
                    continue  # not fully contained in empty space
                cand = (tier, room.area, -strip.area, room, strip, direction, dist)
                if best is None or cand[:3] < best[:3]:
                    best = cand
            # (largest contained strip per direction wins via -gain ordering)

        if best is None:
            if not absorbed_any:
                return _legacy_absorb(floor_plan, minx, miny, maxx, maxy, notes)
            return absorbed_any

        _, _, _, room, strip, direction, dist = best
        old_area = room.area
        if direction == "right":
            room.width = round(room.width + dist, 3)
        elif direction == "left":
            room.x = round(room.x - dist, 3)
            room.width = round(room.width + dist, 3)
        elif direction == "top":
            room.depth = round(room.depth + dist, 3)
        else:  # bottom
            room.y = round(room.y - dist, 3)
            room.depth = round(room.depth + dist, 3)
        remaining = remaining.difference(strip)
        absorbed_any = True
        notes.append(
            f"{room.name} expanded from {old_area:.1f} m² → {room.area:.1f} m² "
            f"to absorb unused space on floor {floor_plan.floor}."
        )
    return absorbed_any


def _legacy_absorb(
    floor_plan: FloorPlan,
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
    notes: list[str],
) -> bool:
    """Expand the largest room that shares an edge with the leftover region."""
    tol = 0.05
    candidates = []
    for room in floor_plan.rooms:
        # Shares right edge with leftover's left edge
        if (
            abs(room.x + room.width - minx) < tol
            and room.y < maxy
            and room.y + room.depth > miny
        ):
            candidates.append((room, "right"))
        # Shares top edge with leftover's bottom edge
        elif (
            abs(room.y + room.depth - miny) < tol
            and room.x < maxx
            and room.x + room.width > minx
        ):
            candidates.append((room, "top"))
        # Shares left edge with leftover's right edge
        elif abs(room.x - maxx) < tol and room.y < maxy and room.y + room.depth > miny:
            candidates.append((room, "left"))
        # Shares bottom edge with leftover's top edge
        elif abs(room.y - maxy) < tol and room.x < maxx and room.x + room.width > minx:
            candidates.append((room, "bottom"))

    if not candidates:
        return False

    # Wet rooms and stairs must not swallow leftover space — a toilet that
    # absorbs a 2 m band stays labelled "Toilet" at an absurd size (the
    # "TOILET 2 — 275 SQFT" bug). Prefer any non-capped neighbour.
    preferred = [rc for rc in candidates if rc[0].type not in _NO_ABSORB_TYPES]
    if preferred:
        candidates = preferred

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
    return True


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

    solver_ids = {lay.id for lay in solver_layouts}

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

    # ── L-shaped plot: remove rooms in the cutout zone ────────────────────────
    if cfg.plot_shape == "l_shaped" and cfg.cutout_width > 0 and cfg.cutout_height > 0:
        # Build the actual cutout rectangle (the removed corner)
        W = cfg.plot_width
        H = cfg.plot_length
        cw = cfg.cutout_width
        ch = cfg.cutout_height
        from shapely.geometry import box as _sbox

        if cfg.cutout_corner == "NE":
            cutout_zone = _sbox(W - cw, H - ch, W, H)
        elif cfg.cutout_corner == "NW":
            cutout_zone = _sbox(0, H - ch, cw, H)
        elif cfg.cutout_corner == "SE":
            cutout_zone = _sbox(W - cw, 0, W, ch)
        else:  # SW
            cutout_zone = _sbox(0, 0, cw, ch)

        for layout in all_layouts:
            cutout_notes: list[str] = []
            for fp in [
                layout.ground_floor,
                layout.first_floor,
                layout.second_floor,
                layout.basement_floor,
            ]:
                if fp is None or not fp.rooms:
                    continue
                fp.rooms = _remove_cutout_overlap(
                    fp.rooms, cutout_zone, cutout_notes, fp.floor
                )
            # prepend cutout notes so they appear first in space_notes
            layout.space_notes = cutout_notes + layout.space_notes

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
            space_notes.extend(_split_oversized_wet_rooms(fp))

        layout.space_notes = list(layout.space_notes) + space_notes

    # ── Score and select top 3 ────────────────────────────────────────────────
    top = rank_and_select(all_layouts, cfg, top_n=3)
    # Remap IDs to stable "A", "B", "C" so the export route default works
    for layout, letter in zip(top, ["A", "B", "C"]):
        layout.id = letter
    return top
