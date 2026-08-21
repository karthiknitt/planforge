from __future__ import annotations

import logging

from app.schemas.project import GenerateRequest

from .archetypes import layout_a, layout_b, layout_c, layout_d, layout_e, layout_f
from .geometry import (  # noqa: F401  (compute_l_shaped_polygon re-export; historical import site)
    buildable_polygon,
    compute_l_shaped_polygon,
)
from .compliance import check, load_rules
from .models import Column, FloorPlan, Layout, PlotConfig, Room
from .scorer import layout_floors, rank_and_select
from .solver import solve_layouts, validate_plot_envelope
from .vastu import check_vastu, vastu_layout_score

logger = logging.getLogger(__name__)


# NOTE: `_remove_cutout_overlap` used to live here and was called below on every
# generated layout for an L-shaped plot, deleting any room that fell >60% inside
# the cutout. That silently lost programme — a 3-bedroom request could come back
# with 2 — and it could not touch the 40%-and-under intrusions at all. The solver
# now forbids room parts from entering the cutout as a hard CP-SAT constraint
# (`solver._forbid_notch`, which resolves BOTH the new `plot_template`/`notch_*`
# fields and the legacy `plot_shape="l_shaped"` cutout corner), so there is
# nothing left to delete. The archetype fallback path never needed it either:
# `archetypes._l_shaped_floor_plate` shrinks the plate away from the cutout, and
# `compliance.check` bounds every room by `buildable_polygon`, which for an
# l_shaped plot is the notched polygon itself.


# ── Blank area detection & filling ────────────────────────────────────────────

_ROOM_COUNTER: dict[str, int] = {}


def _next_id(prefix: str) -> str:
    _ROOM_COUNTER[prefix] = _ROOM_COUNTER.get(prefix, 0) + 1
    return f"{prefix}_{_ROOM_COUNTER[prefix]}"


def _plate_box(cfg: PlotConfig, ewt: float):
    """Return a Shapely geometry for the usable floor plate.

    Delegates to the canonical buildable_polygon() (per-edge setbacks, all
    plot shapes). A plain rectangle here made the fill passes treat the
    trapezoid/quad bounding box as buildable and create rooms outside the
    slanted plot boundary.
    """
    from shapely.geometry import box

    plate = buildable_polygon(cfg, wall_clearance=ewt)
    if not plate.is_empty:
        return plate
    ox = cfg.setback_left + ewt
    oy = cfg.setback_front + ewt
    w = cfg.plot_x_extent - cfg.setback_left - cfg.setback_right - 2 * ewt
    d = cfg.plot_y_extent - cfg.setback_front - cfg.setback_rear - 2 * ewt
    return box(ox, oy, ox + w, oy + d)


def _trim_micro_overlaps(floor_plan: FloorPlan) -> None:
    """Remove millimetre-scale room overlaps left by 3-dp rounding.

    Archetype arithmetic rounds each coordinate independently, so
    ``round(a + b) != round(a) + round(b)`` can leave <=5 mm sliver overlaps
    that the room-edit validator (which rejects ANY positive-area overlap)
    would flag on the next round-trip. Trim the sliver off the larger room.
    """
    _MICRO = 0.05  # m — anything bigger is a real bug, leave it visible
    rooms = floor_plan.rooms
    for i, a in enumerate(rooms):
        for b in rooms[i + 1 :]:
            ox1 = max(a.x, b.x)
            oy1 = max(a.y, b.y)
            ox2 = min(a.x + a.width, b.x + b.width)
            oy2 = min(a.y + a.depth, b.y + b.depth)
            w_ov = ox2 - ox1
            d_ov = oy2 - oy1
            if w_ov <= 0 or d_ov <= 0:
                continue
            if min(w_ov, d_ov) > _MICRO:
                continue  # not a rounding sliver
            t = a if a.area >= b.area else b
            if w_ov <= d_ov:
                if abs(t.x + t.width - ox2) < 1e-9:  # sliver at t's right edge
                    t.width = round(t.width - w_ov, 3)
                elif abs(t.x - ox1) < 1e-9:  # sliver at t's left edge
                    t.x = round(t.x + w_ov, 3)
                    t.width = round(t.width - w_ov, 3)
            else:
                if abs(t.y + t.depth - oy2) < 1e-9:
                    t.depth = round(t.depth - d_ov, 3)
                elif abs(t.y - oy1) < 1e-9:
                    t.y = round(t.y + d_ov, 3)
                    t.depth = round(t.depth - d_ov, 3)


_PASSAGE_MAX_SQM = 6.0  # mirrors room_specs.json "passage".max_area_sqm


def _ensure_stair_circulation_room(floor_plan: FloorPlan) -> str | None:
    """Retype an auto-filler room into a circulation room if the staircase
    has no doorable circulation partition yet.

    The solver's own room list only defines a ``living`` room on the ground
    floor (``_build_room_list`` in ``solver.py``) — an upper floor can be
    bedrooms + staircase only. The CP-SAT hard constraint has a documented
    fallback for this (any non-wet/non-parking room, including a bedroom,
    satisfies its OWN door-access requirement), but that fallback doesn't
    give the staircase a *circulation* neighbour, only *some* neighbour —
    and none of the fill/split/trim passes above know to prioritise the
    staircase when choosing where to place leftover-space filler (issue
    #50's second suspect, alongside the snap pass fixed separately).

    Retypes at most one auto-filler room per stair (utility/store_room/
    balcony — the exact types ``_rect_fill_remainder`` creates), and only
    when it already shares enough wall for a door AND is passage-sized
    (``_PASSAGE_MAX_SQM``) — an Open Terrace or big Utility room sharing a
    wall with the stair must NOT be relabelled wholesale, or "passage"
    stops meaning circulation-sized. This reuses existing geometry rather
    than moving anything, so nothing structural changes, only the room's
    type/name and its resulting opening-placement eligibility.
    """
    from .plan_geometry import (
        _adjacencies,
        _CIRCULATION_TYPES,
        _STAIR_DOOR_MIN_RUN_M,
        IWT,
    )

    rooms = floor_plan.rooms
    stair_idxs = [i for i, r in enumerate(rooms) if r.type == "staircase"]
    if not stair_idxs:
        return None

    adjs = _adjacencies(rooms, IWT, 0.01)
    retyped: str | None = None
    for si in stair_idxs:
        runs = [
            (adj.hi - adj.lo, adj.b if adj.a == si else adj.a)
            for adj in adjs
            if si in (adj.a, adj.b)
        ]
        already_ok = any(
            run >= _STAIR_DOOR_MIN_RUN_M - 1e-6 and rooms[oi].type in _CIRCULATION_TYPES
            for run, oi in runs
        )
        if already_ok:
            continue
        candidates = sorted(
            (
                (run, oi)
                for run, oi in runs
                if run >= _STAIR_DOOR_MIN_RUN_M - 1e-6
                and rooms[oi].type in ("utility", "store_room", "balcony")
                and rooms[oi].area <= _PASSAGE_MAX_SQM
            ),
            reverse=True,
        )
        if not candidates:
            continue
        _, oi = candidates[0]
        rooms[oi].type = "passage"
        rooms[oi].name = "Landing"
        retyped = rooms[oi].id
    return retyped


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


_USABLE_EROSION_R = 1.2 / 2 + 0.05
_RELAXED_MIN_SIDE = 0.9


def _region_is_usable(piece) -> bool:
    """Mirror of the "usable leftover" criterion the quality checks apply:
    a ~1.3 m pocket fits inside the region after erosion."""
    eroded = piece.buffer(-_USABLE_EROSION_R)
    return not eroded.is_empty and eroded.area > 1e-4


def _largest_inscribed_rect(piece, min_side: float = 1.2 - 1e-3):
    """Largest axis-aligned rectangle inside ``piece`` whose corners lie on
    the polygon's own coordinate grid. ``min_side`` default carries a float
    tolerance: grid coords are differences of 3-dp values, so an intended
    1.2 m leg can measure 1.1989999…."""
    from shapely.geometry import box

    # Raw coords — rounding here can push a candidate past the true boundary
    # into a neighbouring room; callers snap the winning rect inward instead.
    coords = list(piece.exterior.coords)
    for hole in piece.interiors:
        coords.extend(hole.coords)
    xs = sorted({c[0] for c in coords})
    ys = sorted({c[1] for c in coords})
    best = None
    best_area = 0.5
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
                    if cand.difference(piece).area < 1e-6:
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
        if leftover.geom_type in ("MultiPolygon", "GeometryCollection"):
            pieces = [g for g in leftover.geoms if g.geom_type == "Polygon"]
        else:
            pieces = [leftover] if leftover.geom_type == "Polygon" else []
        rect = None
        for piece in sorted(pieces, key=lambda g: g.area, reverse=True):
            if piece.area < 1.5:
                break
            rect = _largest_inscribed_rect(piece)
            if rect is not None and rect.area >= 1.5:
                break
            # A usable pocket can exist with no ≥1.2 m rectangle at all (an
            # L whose legs are ~1.19 m — the CI gap of 2026-07-17). The fill
            # must be at least as inclusive as the usability criterion, so
            # reclaim it as a niche room: erosion-usable regions always
            # contain a ≥0.92 m square, hence 0.9 always finds a candidate.
            if _region_is_usable(piece):
                rect = _largest_inscribed_rect(piece, min_side=_RELAXED_MIN_SIDE)
                if rect is not None and rect.area >= 0.8:
                    break
            rect = None
        if rect is None:
            break
        minx, miny, maxx, maxy = _snap_rect_inward(rect.bounds)
        area = round((maxx - minx) * (maxy - miny), 2)
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

        # Non-rectangular leftovers: grow adjacent rooms into contained
        # strips; the terminating rect-fill pass mops up what remains.
        bbox_area = rw * rd
        if bbox_area > 0 and (area / bbox_area) < 0.70:
            _absorb_into_adjacent(floor_plan, region, minx, miny, maxx, maxy, notes)
            continue

        # Created rooms must NEVER overlap neighbours — use the largest
        # inscribed rectangle, not the bounding box (a 70 %-filled bbox
        # room overlapped adjacent rooms by up to 30 % of its area).
        rect = _largest_inscribed_rect(region)
        if rect is None or rect.area < 1.5:
            _absorb_or_store(
                floor_plan, region, minx, miny, maxx, maxy, notes, area, rw, rd
            )
            continue
        rminx, rminy, rmaxx, rmaxy = _snap_rect_inward(rect.bounds)
        rarea = round((rmaxx - rminx) * (rmaxy - rminy), 2)

        if is_topmost:
            if rarea >= 15.0:
                rid, name, rtype = _next_id("open_terrace"), "Open Terrace", "balcony"
                note = f"Open Terrace ({rarea:.1f} sqm) added to top floor."
            elif rarea >= 4.0:
                rid, name, rtype = _next_id("utility_auto"), "Utility", "utility"
                note = f"Utility ({rarea:.1f} sqm) added to top floor."
            else:
                _absorb_or_store(
                    floor_plan, region, minx, miny, maxx, maxy, notes, area, rw, rd
                )
                continue
        else:
            if rarea >= 8.0:
                rid, name, rtype = _next_id("store_auto"), "Store Room", "store_room"
                note = f"Store Room ({rarea:.1f} sqm) added to Ground Floor."
            elif rarea >= 4.0:
                rid, name, rtype = _next_id("utility_auto"), "Utility", "utility"
                note = f"Utility ({rarea:.1f} sqm) added to Ground Floor."
            else:
                _absorb_or_store(
                    floor_plan, region, minx, miny, maxx, maxy, notes, area, rw, rd
                )
                continue

        floor_plan.rooms.append(
            Room(
                id=rid,
                name=name,
                type=rtype,
                x=round(rminx, 3),
                y=round(rminy, 3),
                width=round(rmaxx - rminx, 3),
                depth=round(rmaxy - rminy, 3),
            )
        )
        notes.append(note)

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
_WET_CAP_SQM = 4.6
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


def _floor_mm(v: float) -> float:
    """Round DOWN to mm — expansions/creations must never overshoot into a
    neighbour (the edit validator rejects any positive-area overlap)."""
    import math

    return math.floor(v * 1000 + 1e-9) / 1000


def _ceil_mm(v: float) -> float:
    import math

    return math.ceil(v * 1000 - 1e-9) / 1000


def _snap_rect_inward(bounds: tuple) -> tuple:
    minx, miny, maxx, maxy = bounds
    return _ceil_mm(minx), _ceil_mm(miny), _floor_mm(maxx), _floor_mm(maxy)


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
    subtract it. Expansion is strictly containment-checked — a room never
    grows over another room. Returns True if any room was expanded.
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

        # Raw coords — see _largest_inscribed_rect; rounded coords can push a
        # strip past the true boundary into a neighbouring room.
        coords = list(piece.exterior.coords)
        for hole in piece.interiors:
            coords.extend(hole.coords)
        xs = sorted({c[0] for c in coords})
        ys = sorted({c[1] for c in coords})

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
                if strip.difference(piece).area > 1e-6:
                    continue  # not fully contained in empty space
                cand = (tier, room.area, -strip.area, room, strip, direction, dist)
                if best is None or cand[:3] < best[:3]:
                    best = cand
            # (largest contained strip per direction wins via -gain ordering)

        if best is None:
            # No contained strip — leave the remainder for the rect-fill
            # pass. (The old fallback expanded a room across the region's
            # whole bounding box, stamping it over other rooms.)
            return absorbed_any

        _, _, _, room, strip, direction, dist = best
        old_area = room.area
        dist = _floor_mm(dist)  # never overshoot into a neighbour
        if dist <= 0:
            return absorbed_any
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


def _attach_vastu(layout: Layout, cfg: PlotConfig) -> None:
    """Record Vastu on a layout as a *warning* and a graded score — never as a
    compliance violation.

    Vastu is a cultural preference, not a building bye-law, but it used to be
    appended to `compliance.violations` and then flip `compliance.passed`, so a
    single prohibited-zone room deleted an otherwise legal layout from the
    candidate set — on some configs, every candidate. The graded score feeds
    ranking through `scorer._score_vastu` (10% of the layout score) instead, so
    a Vastu-poor layout is now out-ranked rather than dropped.

    Applied once per layout on the final post-fill geometry, so `vastu_score`
    is the same number `score_layout` sees. Both the solver and archetype paths
    flow through here; the archetype loop used to be the only path that ran
    `check_vastu` at all, so solver layouts silently carried no Vastu warnings.
    """
    if not cfg.vastu_enabled:
        return
    _v_violations, v_warnings = check_vastu(layout, cfg, road_side=cfg.road_side)
    layout.compliance.warnings.extend(v_warnings)
    layout.vastu_score = vastu_layout_score(layout_floors(layout), cfg)


def generate(cfg: PlotConfig) -> list[Layout]:
    """Generate layouts using the CP-SAT solver (primary) with archetype fallback.

    Returns up to 3 passing layouts ranked by quality score.
    """
    rules = load_rules()
    ewt = rules["external_wall_thickness_mm"] / 1000
    iwt = rules["internal_wall_thickness_mm"] / 1000

    # A plot notch that cannot house the requested programme is a user-input
    # problem, so it is raised BEFORE the blanket try/except below — falling
    # through to archetypes would hand the user a plan that ignores the notch.
    validate_plot_envelope(cfg, ewt)

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

    def _snap_layout_floors(layout: Layout) -> None:
        """Run the shared-grid snap pass (PR #26) on a layout's floors.

        The solver snaps inside solve(), but archetype layouts skipped it
        entirely, and the fill/absorb/wet-split passes reintroduce edges at
        wall FACES (±iwt/2 off the centreline another room pairs on), so
        near-aligned partitions reappear post-fill and every such pair
        produced adjacent twin columns. Called on archetype admission and
        again after the fill passes for every layout. Best-effort like the
        solver: revert to the unsnapped rooms on compliance failure.
        """
        from .geometry import buildable_polygon
        from .solver import _load_specs, snap_rooms_to_shared_grid

        floor_plans = [
            fp
            for fp in (
                layout.ground_floor,
                layout.first_floor,
                layout.second_floor,
                layout.basement_floor,
            )
            if fp is not None and fp.rooms
        ]
        if not floor_plans:
            return
        specs = _load_specs()
        min_dims: dict[str, dict] = {}
        for fp in floor_plans:
            for r in fp.rooms:
                spec = specs.get(r.type, specs.get("utility"))
                min_dims[r.id] = {
                    "min_width_m": spec["min_width_m"],
                    "min_depth_m": spec["min_width_m"],
                    "min_area_sqm": spec["min_area_sqm"],
                }
        bx1, by1, bx2, by2 = buildable_polygon(cfg, wall_clearance=ewt).bounds
        originals = [list(fp.rooms) for fp in floor_plans]
        snapped = snap_rooms_to_shared_grid(
            [fp.rooms for fp in floor_plans],
            min_dims,
            plate_bounds=((bx1, bx2), (by1, by2)),
            pin_room_types={"staircase"},
        )
        for fp, rooms in zip(floor_plans, snapped):
            fp.rooms = rooms
        if not check(layout, cfg, rules).passed:
            for fp, rooms in zip(floor_plans, originals):
                fp.rooms = rooms

    for fn in generators:
        layout = fn(cfg, ewt=ewt, iwt=iwt)
        _snap_layout_floors(layout)
        layout.compliance = check(layout, cfg, rules)

        # Vastu is deliberately absent here: it neither adds violations nor
        # gates admission any more. Both were applied once per layout, on the
        # final post-fill geometry, just before ranking (see _attach_vastu).
        if layout.compliance.passed and layout.id not in solver_ids:
            archetype_layouts.append(layout)

    # Layout F: courtyard — conditional on plot area >= 150 sqm
    plot_area = cfg.plot_x_extent * cfg.plot_y_extent
    if plot_area >= 150:
        lf = layout_f(cfg, ewt=ewt, iwt=iwt)
        if lf is not None:
            _snap_layout_floors(lf)
            lf.compliance = check(lf, cfg, rules)
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
            space_notes.extend(_split_oversized_wet_rooms(fp))
            _trim_micro_overlaps(fp)
            _ensure_stair_circulation_room(fp)

        layout.space_notes = list(layout.space_notes) + space_notes

    # ── Re-snap + recompute columns from the FINAL rooms ─────────────────────
    # Two historical defects converge here: archetype layouts carried
    # _columns_from_rooms' edge-line cross-product (a column on BOTH faces of
    # every 115 mm partition — the "twin columns" bug), and both paths
    # computed columns before the fill/split/trim passes mutated rooms. The
    # fill passes also grow rooms to wall FACES, reintroducing near-aligned
    # partitions after the solver's snap — so snap again on the final
    # geometry, then derive columns from wall junctions, keeping the stored
    # columns identical to what the PDF/DXF pipeline draws and what
    # structural grid extraction consumes.
    from app.engine.plan_geometry import derive_columns, derive_walls

    buildable = buildable_polygon(cfg)
    for layout in all_layouts:
        _snap_layout_floors(layout)
        for fp in [
            layout.ground_floor,
            layout.first_floor,
            layout.second_floor,
            layout.basement_floor,
        ]:
            if fp is None or not fp.rooms:
                continue
            walls = derive_walls(fp.rooms, buildable)
            fp.columns = [
                Column(x=round(c.cx, 3), y=round(c.cy, 3))
                for c in derive_columns(walls, rooms=fp.rooms)
            ]

    # ── Navigability gate: reject layouts whose door graph cannot be
    # repaired into a fully-reachable floor (same drop pattern as the
    # compliance gate above). derive_openings runs the repair pass; the
    # check re-derives openings exactly as build_floor_drawing does. ──────────
    from app.engine.plan_geometry import (
        derive_openings,
        validate_floor_connectivity,
    )
    from app.engine.standards import get_opening_standards

    std = get_opening_standards()
    navigable_layouts = []
    for layout in all_layouts:
        ok = True
        for fp in [
            layout.ground_floor,
            layout.first_floor,
            layout.second_floor,
            layout.basement_floor,
        ]:
            if fp is None or not fp.rooms:
                continue
            walls = derive_walls(fp.rooms, buildable)
            columns = derive_columns(walls, rooms=fp.rooms)
            openings = derive_openings(
                fp.rooms,
                walls,
                columns,
                std,
                buildable,
                floor=fp.floor,
                # Same cfg the drawing path passes. Without it the layout
                # validated for connectivity would have its entrance somewhere
                # other than the layout actually drawn.
                vastu_cfg=cfg,
            )
            if validate_floor_connectivity(fp.rooms, openings, fp.floor):
                ok = False
                break
        if ok:
            navigable_layouts.append(layout)
    if navigable_layouts:
        all_layouts = navigable_layouts
    else:
        # repair pass too weak for this config — never return zero layouts
        logger.warning(
            "navigability gate rejected every layout; keeping unfiltered set"
        )

    # ── Required-programme gate (Task 25) ─────────────────────────────────────
    # The archetype fallback builds fixed programmes and cannot honour wizard
    # programme flags, so without this gate an explicitly requested courtyard
    # could be outranked by an archetype that lacks one. Same never-return-zero
    # rule as the navigability gate.
    if cfg.required_types or cfg.open_parking:
        required = set(cfg.required_types)

        def _satisfies(lay: Layout) -> bool:
            floors = layout_floors(lay)
            present = {r.type for fp in floors for r in fp.rooms}
            if not required <= present:
                return False
            if cfg.open_parking:
                # Archetypes build fully-walled parking; a request for an open
                # car porch is only honoured by layouts whose ground-floor
                # porch actually declares its road-facing edge open.
                porches = [
                    r
                    for fp in floors
                    if fp.floor == 0
                    for r in fp.rooms
                    if r.type in ("parking", "parking_4w", "parking_2w")
                ]
                if porches and not all(p.open_sides for p in porches):
                    return False
            return True

        honoured = [lay for lay in all_layouts if _satisfies(lay)]
        if honoured:
            all_layouts = honoured
        else:
            logger.warning(
                "no layout satisfies the requested programme %s; keeping "
                "unfiltered set",
                sorted(required),
            )

    # ── Vastu: warnings + graded score on the final geometry ─────────────────
    for layout in all_layouts:
        _attach_vastu(layout, cfg)

    # ── Score and select top 3 ────────────────────────────────────────────────
    top = rank_and_select(all_layouts, cfg, top_n=3)
    # Remap IDs to stable "A", "B", "C" so the export route default works
    for layout, letter in zip(top, ["A", "B", "C"]):
        layout.id = letter
    return top


_PROGRAMME_TYPES: dict[str, str] = {
    "courtyard": "courtyard",
    "verandah": "verandah",
    "pooja": "pooja",
    "terrace": "terrace",
    "study": "study",
}


def _programme_types(flags: set[str]) -> frozenset[str]:
    """Wizard programme flags → room types the solver must place.

    `car_porch_open` is deliberately absent: it does not add a room, it opens
    the existing parking room's road-facing edge (`open_parking`).
    """
    return frozenset(_PROGRAMME_TYPES[f] for f in flags if f in _PROGRAMME_TYPES)


def generate_from_request(req: GenerateRequest) -> list[Layout]:
    """Map an API request onto a PlotConfig plus programme requirements.

    Note that `style_preset` is deliberately NOT read here: presets seed the
    wizard form's checkboxes, and the resulting explicit `programme` set is the
    only thing the engine honours. A user who unticks every box on a Kerala
    preset gets no courtyard. See spec section 6 on why style signal is too
    weak to drive generation directly.
    """
    cfg = PlotConfig(
        plot_x_extent=req.plot_x_extent,
        plot_y_extent=req.plot_y_extent,
        setback_front=req.setback_front,
        setback_rear=req.setback_rear,
        setback_left=req.setback_left,
        setback_right=req.setback_right,
        num_bedrooms=req.num_bedrooms,
        toilets=req.toilets,
        parking=req.parking,
        north_angle_deg=req.north_angle_deg,
        plot_template=req.plot_template,
        notch_width=req.notch_width or 0.0,
        notch_depth=req.notch_depth or 0.0,
        # NOT coupled to plot_template — see "Task 9 rulings" ruling 2. Forcing
        # room templates on for an L plot makes layouts strictly worse until a
        # notch-filling objective term exists.
        allow_shape_templates=False,
        required_types=_programme_types(req.programme),
        open_parking=("car_porch_open" in req.programme),
    )
    return generate(cfg)
