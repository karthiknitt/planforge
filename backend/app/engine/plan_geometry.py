"""Canonical drawing-geometry derivation — single source of truth for renderers.

Room-layout convention (see archetypes._inscribed_plate): room rects are CLEAR
interior spaces. Adjacent rooms are separated by an iwt-wide gap and the plate
is inset ewt from the buildable ring. Walls therefore live in the gaps:

- paired internal walls: centreline at the midpoint of the gap between two
  facing room edges
- external ring: centreline at the room-union bounding box ± ewt/2 (inner
  face flush with the floor's room union; falls back to the buildable plate
  when the floor has no rooms)
- orphan walls: room edges facing unassigned space get a wall hugging the
  edge. iwt (centreline iwt/2 outside the room) when a neighbouring room
  mass sits just outside; ewt when it doesn't (interior void, light well/
  duct — structurally exterior even though it's inside the footprint bbox)

All outputs are axis-aligned centreline segments, normalized so
(x1, y1) <= (x2, y2).
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from shapely.geometry import Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.engine.cad_elements import (
    ColumnMarker,
    DimChain,
    DimChainEntry,
    FloorDrawing,
    LabelBox,
    Opening,
    StairGeometry,
    WallJunction,
    WallSegment,
)
from app.engine.cad_primitives import metres_to_ftin
from app.engine.standards import OpeningStandards

if TYPE_CHECKING:
    from app.engine.models import FloorPlan, PlotConfig, Room

logger = logging.getLogger(__name__)

EWT = 0.23
IWT = 0.115
_SNAP = 0.25  # max end-extension to meet a perpendicular centreline
_MIN_WALL_LEN = 0.10
_JAMB = 0.115  # min clearance between an opening and a wall end
_COL_CLEAR = 0.16  # column half-size (0.15) + clearance, along the wall
_WET_DOOR = 0.75
_WET_TYPES = {"toilet", "wc_only", "bathroom_master", "utility"}
_WINDOW_TYPES = {
    "living",
    "bedroom",
    "master_bedroom",
    "kitchen",
    "study",
    "dining",
    "home_office",
    "gym",
    "servant_quarter",
    "foyer",
}
_DOOR_NEIGHBOUR_PRIORITY = {
    "passage": 0,
    "foyer": 0,
    "courtyard": 1,
    "living": 1,
    "dining": 2,
    "staircase": 3,
}
_ENTRY_PRIORITY = {"living": 0, "foyer": 1, "passage": 2, "dining": 3}
_PARKING_TYPES = {"parking", "parking_4w", "parking_2w"}
_NO_ENTRY_TYPES = _WET_TYPES | _PARKING_TYPES | {"staircase"}
# rooms that never host their own interior door: circulation, open-air/outdoor,
# and transitional spaces — doors serving them are placed by their neighbours.
_NO_DOOR_TYPES = _PARKING_TYPES | {"passage", "foyer", "courtyard"}
# wet rooms + kitchen: interior-accessed, exactly one door, never a transit route
_SINGLE_DOOR_TYPES = _WET_TYPES | {"kitchen"}
# rooms a navigability path may terminate in but never transit through
_NO_TRANSIT_TYPES = _SINGLE_DOOR_TYPES | _PARKING_TYPES
# rooms the staircase may legitimately take its door from
_CIRCULATION_TYPES = {"passage", "foyer", "courtyard", "living", "dining"}
# shared-wall run the staircase needs with one of those to fit a door leaf
# plus both jambs — the same test the candidate loop applies per wall below.
_STAIR_DOOR_MIN_RUN_M = 0.9 + 2 * _JAMB


def _is_wet_stair_pair(type_a: str, type_b: str) -> bool:
    """True for a wall shared by a wet room and the staircase — never doorable
    in either direction (a WC opening onto a stair landing)."""
    pair = {type_a, type_b}
    return "staircase" in pair and bool(pair & _WET_TYPES)


def _faces_main_door(adj: "_Adjacency", main_door: "Opening | None") -> bool:
    """True if a door on this adjacency would sit directly opposite the main
    entrance — i.e. a wall parallel to the front (a horizontal adjacency) whose
    span crosses the main door's x. Perpendicular (vertical) walls never face
    the entrance head-on, so they are always fine."""
    if main_door is None or adj.vertical:
        return False
    return adj.lo - 1e-9 <= main_door.cx <= adj.hi + 1e-9


def _ensuite_bedroom_id(room_id: str) -> str | None:
    """Bedroom id an en-suite (``toilet_ens_<i>``) is attached to, or None.

    Reuses the Task-1 solver id convention so the door pass and the
    connectivity graph agree on en-suite ↔ bedroom pairing.
    """
    from app.engine.solver import ensuite_attachment

    return ensuite_attachment(room_id)


def _merge_intervals(
    intervals: list[tuple[float, float]], gap: float
) -> list[tuple[float, float]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [list(intervals[0])]
    for lo, hi in intervals[1:]:
        if lo <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(lo, hi) for lo, hi in merged]


def _subtract_intervals(
    span: tuple[float, float], covered: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    remaining = [span]
    for clo, chi in sorted(covered):
        nxt: list[tuple[float, float]] = []
        for lo, hi in remaining:
            if chi <= lo or clo >= hi:
                nxt.append((lo, hi))
                continue
            if clo > lo:
                nxt.append((lo, clo))
            if chi < hi:
                nxt.append((chi, hi))
        remaining = nxt
    return remaining


class _Edge:
    __slots__ = ("coord", "lo", "hi", "normal", "covered")

    def __init__(self, coord: float, lo: float, hi: float, normal: int) -> None:
        self.coord = coord
        self.lo = lo
        self.hi = hi
        self.normal = normal  # +1: outward normal points +axis; -1: -axis
        self.covered: list[tuple[float, float]] = []


def _part_boxes(rooms: list[Room]) -> list[Polygon]:
    """One Shapely box per occupied rectangle across `rooms`.

    Shape templates (Task 6) make a room the UNION of 1-3 rectangles, so any
    footprint/mass computation must union parts, not room bounding boxes —
    an L room's notch is empty space, not room mass.
    """
    return [box(p.x, p.y, p.x + p.width, p.y + p.depth) for r in rooms for p in r.rects]


def _room_polygon(room: Room) -> BaseGeometry:
    """The room's occupied area — the union of its shape-template parts.

    For a "RECT" room this is exactly `box(x, y, x + width, y + depth)`:
    `Room.rects` is then a 1-tuple and `unary_union` of a single box returns
    it with its coordinates untouched. That identity is what keeps the
    union-boundary walk below behaviour-preserving for every existing layout.
    """
    return unary_union(_part_boxes([room]))


def _rooms_polygon(rooms: list[Room]) -> BaseGeometry:
    boxes = _part_boxes(rooms)
    return unary_union(boxes) if boxes else Polygon()


def _merge_collinear(edges: list[_Edge]) -> list[_Edge]:
    """Merge touching runs that share a coordinate and an outward normal.

    Shapely's union emits a vertex wherever two input rectangles met, so an
    L's west side arrives as two collinear segments; without this the wall
    passes would treat them as two separate runs and merge them back with a
    different (and lossy) gap tolerance.

    Output order is (normal, coord, lo) — for a RECT room that is exactly the
    order the pre-template `_room_edges` emitted (W then E, S then N), which
    matters because `_snap_ends` mutates walls in list order.
    """
    out: list[_Edge] = []
    for e in sorted(edges, key=lambda z: (z.normal, z.coord, z.lo)):
        prev = out[-1] if out else None
        if (
            prev is not None
            and prev.normal == e.normal
            and abs(prev.coord - e.coord) < 1e-9
            and prev.hi >= e.lo - 1e-9
        ):
            prev.hi = max(prev.hi, e.hi)
        else:
            out.append(e)
    return out


def _boundary_edges(geom: BaseGeometry) -> tuple[list[_Edge], list[_Edge]]:
    """Axis-aligned boundary runs of a rectilinear polygon, split into
    (vertical, horizontal).

    The outward normal is read off the ring's WINDING, not from a
    representative interior point: a representative point of an L-shaped
    polygon sits on the wrong side of at least one of its own edges, which
    would flip that edge's normal and turn a re-entrant corner into a
    phantom exterior surface. For a counter-clockwise ring the interior lies
    to the LEFT of travel, so the outward normal is the right-hand normal
    (dy, -dx); a clockwise ring (what `unary_union` returns for a merged
    footprint) is the mirror image. Interior rings of a valid polygon are
    wound opposite to the exterior, so the same rule points their normals
    into the hole, which is correct — a hole's surface faces open space.
    """
    verts: list[_Edge] = []
    horiz: list[_Edge] = []
    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    for poly in polys:
        if poly.is_empty or poly.geom_type != "Polygon":
            continue
        for ring in [poly.exterior, *poly.interiors]:
            ccw = ring.is_ccw
            coords = list(ring.coords)
            for (x0, y0), (x1, y1) in zip(coords, coords[1:], strict=False):
                dx, dy = x1 - x0, y1 - y0
                if abs(dx) < 1e-9 and abs(dy) > 1e-9:
                    verts.append(
                        _Edge(
                            x0,
                            min(y0, y1),
                            max(y0, y1),
                            1 if (dy > 0) == ccw else -1,
                        )
                    )
                elif abs(dy) < 1e-9 and abs(dx) > 1e-9:
                    horiz.append(
                        _Edge(
                            y0,
                            min(x0, x1),
                            max(x0, x1),
                            -1 if (dx > 0) == ccw else 1,
                        )
                    )
    return _merge_collinear(verts), _merge_collinear(horiz)


def _room_edges(rooms: list[Room]) -> tuple[list[_Edge], list[_Edge]]:
    """Union-boundary runs of every room, as (vertical, horizontal).

    A RECT room yields its four bbox edges — identical to the pre-template
    behaviour. An L/T/U room yields the runs of its part union, so its notch
    is a real re-entrant corner and no wall is drawn across it.
    """
    vert: list[_Edge] = []
    hor: list[_Edge] = []
    for r in rooms:
        v, h = _boundary_edges(_room_polygon(r))
        vert.extend(v)
        hor.extend(h)
    return vert, hor


_SIDE_OF_EDGE: dict[tuple[bool, int], str] = {
    (True, -1): "W",
    (True, +1): "E",
    (False, -1): "S",
    (False, +1): "N",
}
_SIDE_IS_HORIZONTAL: dict[str, bool] = {"N": True, "S": True, "E": False, "W": False}
_SIDE_SIGN: dict[str, int] = {"N": +1, "E": +1, "S": -1, "W": -1}


def _edges_by_side(room: Room) -> dict[str, list[tuple[float, float, float]]]:
    """Union-boundary runs of `room` as (coord, lo, hi), keyed by the
    plot-relative side letter `Room.open_sides` uses.

    A RECT room has exactly one run per side; an L room can have two runs on
    the same side (e.g. its base band's east face and its leg's east face),
    which is precisely why `Room.open_sides` cannot be resolved from the
    bounding box.
    """
    vert, hor = _boundary_edges(_room_polygon(room))
    out: dict[str, list[tuple[float, float, float]]] = {
        "N": [],
        "S": [],
        "E": [],
        "W": [],
    }
    for is_vertical, edges in ((True, vert), (False, hor)):
        for e in edges:
            out[_SIDE_OF_EDGE[(is_vertical, e.normal)]].append((e.coord, e.lo, e.hi))
    return out


def _pair_edges(
    edges: list[_Edge], iwt: float, tol: float
) -> list[tuple[float, float, float]]:
    """Return (centreline coord, lo, hi) for each facing edge pair."""
    out: list[tuple[float, float, float]] = []
    pos = [e for e in edges if e.normal == +1]
    neg = [e for e in edges if e.normal == -1]
    for a in pos:
        for b in neg:
            gap = b.coord - a.coord
            if gap < -tol or gap > iwt + tol:
                continue
            lo = max(a.lo, b.lo)
            hi = min(a.hi, b.hi)
            if hi - lo < 0.05:
                continue
            mid = (a.coord + b.coord) / 2
            out.append((mid, lo, hi))
            a.covered.append((lo, hi))
            b.covered.append((lo, hi))
    return out


def _raw_wall_box(w: WallSegment) -> Polygon:
    """Wall footprint at its true thickness, WITHOUT the end-extension
    `wall_polygons()` applies for rendering corner-closure — that extension
    would bleed a wall's footprint past its real end and contaminate
    `_edge_faces_open_space` classification for a nearby, unrelated edge."""
    t = w.thickness / 2
    if abs(w.x1 - w.x2) < 1e-9:
        lo, hi = min(w.y1, w.y2), max(w.y1, w.y2)
        return box(w.x1 - t, lo, w.x1 + t, hi)
    lo, hi = min(w.x1, w.x2), max(w.x1, w.x2)
    return box(lo, w.y1 - t, hi, w.y1 + t)


def _edge_faces_open_space(
    e: "_Edge", is_vertical: bool, footprint: Polygon | None, ewt: float
) -> bool:
    """True if the outward side of an uncovered room edge has no neighbouring
    room mass — i.e. it faces open/unassigned space (including an interior
    void, not just the exterior ring) rather than another room that simply
    wasn't caught by edge-pairing.

    Tests a strip offset outward from the edge by [eps, ewt] (not [0, ewt]) so
    a room merely touching the edge's own centreline — true along its full
    length — doesn't register as a false "covered" neighbour. Uses AREA
    overlap, not `intersects()`: a perpendicular room can share a full-length
    boundary LINE with the strip (zero area) without actually occupying any
    of the space the strip is probing — `intersects()` alone would treat
    that boundary contact as a real neighbour and misclassify true voids.
    """
    if footprint is None:
        return True
    eps = 0.02
    lo, hi = e.lo, e.hi
    if hi - lo < 1e-9:
        return True
    a = e.coord + e.normal * eps
    b = e.coord + e.normal * ewt
    x0, x1 = (a, b) if a <= b else (b, a)
    strip = box(x0, lo, x1, hi) if is_vertical else box(lo, x0, hi, x1)
    return footprint.intersection(strip).area < 1e-9


def _open_edge_intervals(
    rooms: list[Room], tol: float
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    """Centreline intervals declared wall-less by `Room.open_sides`.

    Returns (vertical, horizontal); each entry is (coord, lo, hi). Vertical
    entries are x-coords spanning [y_lo, y_hi]; horizontal are y-coords
    spanning [x_lo, x_hi]. `tol` is unused for the interval itself but kept
    in the signature so callers pass the same slack used to match walls to
    these intervals.

    Runs come from the room's part UNION boundary, not its bounding box: an
    L-shaped car porch declared open on "E" has two east-facing runs at two
    different x-coords, and its bbox's east line covers stretches where the
    room isn't even present.
    """
    _ = tol
    vertical: list[tuple[float, float, float]] = []
    horizontal: list[tuple[float, float, float]] = []
    for r in rooms:
        if not r.open_sides:
            continue
        sides = _edges_by_side(r)
        for side in r.open_sides:
            sink = horizontal if _SIDE_IS_HORIZONTAL[side] else vertical
            sink.extend(sides[side])
    return vertical, horizontal


def _closed_edge_intervals(
    rooms: list[Room], iwt: float, tol: float
) -> tuple[set[tuple[float, float, float]], set[tuple[float, float, float]]]:
    """Union-boundary runs that some room did NOT declare open, merged per
    centreline. Returns (vertical, horizontal).

    A shared wall where only one side declared itself open stays built, so
    these are the intervals that rescue a wall from the open-side filter.
    They are kept split by orientation so a vertical covered edge cannot
    rescue a horizontal wall that merely shares its coordinate value.

    Merging per centreline (rather than matching raw per-room runs) is
    load-bearing: by the time the filter runs, a party wall passing several
    neighbours is ONE merged segment. The `iwt + tol` gap joins neighbours
    separated by a normal partition slit — that slit is filled by the
    partition itself, so the covered run is continuous.
    """
    raw_v: dict[float, list[tuple[float, float]]] = {}
    raw_h: dict[float, list[tuple[float, float]]] = {}
    for r in rooms:
        sides = _edges_by_side(r)
        for side, runs in sides.items():
            if side in r.open_sides:
                continue
            sink = raw_h if _SIDE_IS_HORIZONTAL[side] else raw_v
            for coord, lo, hi in runs:
                sink.setdefault(round(coord, 6), []).append((lo, hi))
    return (
        {
            (coord, lo, hi)
            for coord, spans in raw_v.items()
            for lo, hi in _merge_intervals(spans, iwt + tol)
        },
        {
            (coord, lo, hi)
            for coord, spans in raw_h.items()
            for lo, hi in _merge_intervals(spans, iwt + tol)
        },
    )


def _apply_open_sides(
    w: WallSegment,
    open_v: list[tuple[float, float, float]],
    open_h: list[tuple[float, float, float]],
    covered_v: set[tuple[float, float, float]],
    covered_h: set[tuple[float, float, float]],
    tol: float,
) -> list[WallSegment]:
    """`w` with its declared-open stretches SUBTRACTED — 0, 1 or 2 segments.

    Subtraction, not all-or-nothing containment: `_merge_intervals` happily
    joins an open porch's ring run with a normal neighbour's into a single
    segment, and a containment test then keeps the whole thing (the merged
    wall is not *wholly* inside the porch's open interval), leaving a wall
    across the porch opening. Splitting removes only the open share.

    `tol` must absorb the offset between a room edge and the centreline of
    the wall serving it: an external ring wall sits ewt/2 *outside* the edge
    and is snapped out to the ring corners, a paired internal wall sits at
    the half-gap midpoint. Callers pass `ewt / 2 + tol`, the worst case.
    Both the open runs AND the rescuing covered runs are widened by that
    slack — widening the covered runs is what keeps the filter conservative,
    so a wall shared with a non-open neighbour survives intact rather than
    being nibbled at its ends.
    """
    is_v = abs(w.x1 - w.x2) < 1e-6
    coord = w.x1 if is_v else w.y1
    lo, hi = (
        (min(w.y1, w.y2), max(w.y1, w.y2))
        if is_v
        else (min(w.x1, w.x2), max(w.x1, w.x2))
    )
    opens = [
        (ilo - tol, ihi + tol)
        for c, ilo, ihi in (open_v if is_v else open_h)
        if abs(c - coord) <= tol
    ]
    if not opens:
        return [w]
    covered = [
        (clo - tol, chi + tol)
        for cc, clo, chi in (covered_v if is_v else covered_h)
        if abs(cc - coord) <= tol
    ]
    truly_open: list[tuple[float, float]] = []
    for span in _merge_intervals(opens, 0.0):
        truly_open.extend(_subtract_intervals(span, covered))
    if not truly_open:
        return [w]

    out: list[WallSegment] = []
    for rlo, rhi in _subtract_intervals((lo, hi), truly_open):
        if rhi - rlo < _MIN_WALL_LEN:
            continue
        if abs(rlo - lo) < 1e-9 and abs(rhi - hi) < 1e-9:
            out.append(w)
        elif is_v:
            out.append(WallSegment(coord, rlo, coord, rhi, w.thickness, kind=w.kind))
        else:
            out.append(WallSegment(rlo, coord, rhi, coord, w.thickness, kind=w.kind))
    return out


def _validate_carves(rooms: list[Room], tol: float = 0.01) -> None:
    """Every room with a `parent_id` must resolve, be acyclic, and lie inside
    that parent's rectangle.

    A carve that escapes its parent would add mass to the floor footprint
    that `_structural_rooms` has already filtered out, silently shrinking the
    plate and the void-classification footprint. Fail loudly instead.

    Cycles are rejected for a nastier reason: every room in a cycle has a
    `parent_id`, so `_structural_rooms` returns an EMPTY list and the plate
    silently degrades from the room union to the whole buildable plate inset
    by ewt — a 4-sided ring drawn around metres of empty plot, with no error
    anywhere. Containment alone cannot catch this (`r.parent_id == r.id` is
    trivially "contained"), so it is a separate pass.
    """
    by_id = {r.id: r for r in rooms}

    # Pass 1: every parent_id resolves.
    for r in rooms:
        if r.parent_id is not None and r.parent_id not in by_id:
            raise ValueError(f"room {r.id!r} has unknown parent_id {r.parent_id!r}")

    # Pass 2: no cycles (self-parent is the length-1 case).
    for r in rooms:
        if r.parent_id is None:
            continue
        chain = [r.id]
        seen = {r.id}
        node = r
        while node.parent_id is not None:
            node = by_id[node.parent_id]
            chain.append(node.id)
            if node.id in seen:
                raise ValueError(
                    "parent_id cycle among carved rooms: " + " -> ".join(chain)
                )
            seen.add(node.id)

    # Pass 3: containment.
    for r in rooms:
        if r.parent_id is None:
            continue
        p = by_id[r.parent_id]
        if not (
            r.x >= p.x - tol
            and r.y >= p.y - tol
            and r.x + r.width <= p.x + p.width + tol
            and r.y + r.depth <= p.y + p.depth + tol
        ):
            raise ValueError(
                f"carved room {r.id!r} is not contained in parent {p.id!r}"
            )


def _structural_rooms(rooms: list[Room]) -> list[Room]:
    """Rooms that contribute mass to the floor footprint.

    Carved children (`parent_id` set) do NOT: they sit inside a parent that
    already contributes the same area, so unioning them in again would
    double-count that mass. Only the FOOTPRINT UNION is filtered — edge
    pairing still runs over the full room list, so a carve's own edges
    become real interior partitions.
    """
    return [r for r in rooms if r.parent_id is None]


def _plate_bounds(
    rooms: list[Room], buildable: Polygon, ewt: float
) -> tuple[float, float, float, float]:
    """Plate bounds (px1, py1, px2, py2) for the floor's exterior surface.

    Room-union bbox when rooms exist (matches the derive_walls ring);
    buildable inset by ewt otherwise. THE single source of truth for both
    wall rings and opening placement — hence the carve filter lives here,
    not at the call sites, so `derive_walls` and `derive_openings` can never
    disagree about what the plate is."""
    # Bound to a distinct name (not a rebind of `rooms`) so it stays obvious
    # that the plate is built from STRUCTURAL mass only, while callers still
    # hand in the full room list.
    structural = _structural_rooms(rooms)
    if structural:
        footprint = _rooms_polygon(structural)
        px1, py1, px2, py2 = footprint.bounds
        # Clear-rect rooms always leave iwt slits between neighbours, so an
        # area-vs-bbox check false-alarms on every full-plate layout. This is
        # a heuristic: corner-jogged (L-shaped) footprints are detected via a
        # missing bbox corner; mid-edge notches (C/U shapes) are NOT detected.
        if any(
            footprint.distance(Point(cx, cy)) > 1e-6
            for cx in (px1, px2)
            for cy in (py1, py2)
        ):
            logger.warning(
                "non-rectangular room footprint: external ring approximated "
                "by the footprint bounding box (jogged outline not followed)"
            )
        return px1, py1, px2, py2
    bx1, by1, bx2, by2 = buildable.bounds
    if abs(buildable.area - (bx2 - bx1) * (by2 - by1)) > 1e-6:
        logger.warning(
            "non-rectangular buildable polygon: external ring approximated "
            "by its bounding box (trapezoid/L/quad support pending)"
        )
    return bx1 + ewt, by1 + ewt, bx2 - ewt, by2 - ewt


def derive_walls(
    rooms: list[Room],
    buildable: Polygon,
    ewt: float = EWT,
    iwt: float = IWT,
    tol: float = 0.01,
) -> list[WallSegment]:
    """Derive the floor's wall centrelines from its rooms.

    The external ring hugs this floor's room union (a partial-footprint floor
    — e.g. a GF leaving a roof void at the rear — gets no false ring around
    the empty area); with no rooms it falls back to the buildable plate. Each
    of the ring's four sides is itself built only from the room edges that
    actually reach that side of `_plate_bounds`'s bbox, not drawn full-length
    unconditionally — a jogged/notched footprint (an L-shaped floor, e.g. a
    sloped-roof void over one corner) therefore gets a wall-less gap over the
    notch instead of a false wall closing off empty space, even though the
    notch's edges lie inside the bbox rather than outside it.

    Uncovered room edges facing an *interior* void (e.g. a roof void over
    part of the GF footprint, technically inside the footprint bounding box)
    are classified via `_edge_faces_open_space`: a Shapely strip offset
    outward from the edge is tested against the room-union footprint, and an
    edge with no neighbouring room mass there gets an `external` (ewt) orphan
    wall instead of `internal` (iwt) — that surface faces open sky, not
    another room, even though it isn't on the bbox boundary. Opening
    placement shares the same exterior-surface model: `_exterior_edges`/
    `_place_main_entrance` in `derive_openings` also consume `_plate_bounds`,
    so void-facing surfaces on partial-footprint floors DO receive openings.
    Only `_place_main_entrance`'s `gate_x` (compound-wall gate/road
    alignment) still keys off the buildable plate.
    """
    _validate_carves(rooms, tol)
    px1, py1, px2, py2 = _plate_bounds(rooms, buildable, ewt)

    cxl, cxr = px1 - ewt / 2, px2 + ewt / 2
    cyb, cyt = py1 - ewt / 2, py2 + ewt / 2

    vert_edges, hor_edges = _room_edges(rooms)

    if rooms:
        # Ring walls only span the stretches where a room actually reaches
        # that plate boundary. `_plate_bounds` gives the room-union's BBOX,
        # which for a jogged/notched footprint (an L-shaped floor, e.g. a
        # sloped-roof void over part of the footprint) is strictly larger
        # than the footprint itself -- unconditionally drawing all four
        # bbox sides in full used to close a false wall ring around that
        # empty notch (#6c's remaining case: the bbox fix bounded the ring
        # to the union's bbox, but a bbox can't express a notch). Building
        # each side from the room edges that actually lie on it leaves a
        # notch's boundary wall-less, matching source drawings that show
        # bare roof texture there with no wall line at all.
        # `iwt + tol` (not `tol`) is the merge gap so same-row neighbours
        # separated by a normal partition slit still read as one
        # continuous ring wall -- only a stretch wider than a partition
        # (a genuine notch) stays split.
        ring_gap = iwt + tol
        south_x = _merge_intervals(
            [
                (e.lo, e.hi)
                for e in hor_edges
                if e.normal == -1 and abs(e.coord - py1) <= 2 * tol
            ],
            ring_gap,
        )
        north_x = _merge_intervals(
            [
                (e.lo, e.hi)
                for e in hor_edges
                if e.normal == +1 and abs(e.coord - py2) <= 2 * tol
            ],
            ring_gap,
        )
        west_y = _merge_intervals(
            [
                (e.lo, e.hi)
                for e in vert_edges
                if e.normal == -1 and abs(e.coord - px1) <= 2 * tol
            ],
            ring_gap,
        )
        east_y = _merge_intervals(
            [
                (e.lo, e.hi)
                for e in vert_edges
                if e.normal == +1 and abs(e.coord - px2) <= 2 * tol
            ],
            ring_gap,
        )
        walls: list[WallSegment] = (
            [WallSegment(lo, cyb, hi, cyb, ewt, kind="external") for lo, hi in south_x]
            + [
                WallSegment(lo, cyt, hi, cyt, ewt, kind="external")
                for lo, hi in north_x
            ]
            + [WallSegment(cxl, lo, cxl, hi, ewt, kind="external") for lo, hi in west_y]
            + [WallSegment(cxr, lo, cxr, hi, ewt, kind="external") for lo, hi in east_y]
        )
    else:
        walls = [
            WallSegment(cxl, cyb, cxr, cyb, ewt, kind="external"),
            WallSegment(cxl, cyt, cxr, cyt, ewt, kind="external"),
            WallSegment(cxl, cyb, cxl, cyt, ewt, kind="external"),
            WallSegment(cxr, cyb, cxr, cyt, ewt, kind="external"),
        ]

    # Mark plate-boundary edges as covered by the external ring.
    for e in vert_edges:
        bound = px1 if e.normal == -1 else px2
        if abs(e.coord - bound) <= 2 * tol:
            e.covered.append((e.lo, e.hi))
    for e in hor_edges:
        bound = py1 if e.normal == -1 else py2
        if abs(e.coord - bound) <= 2 * tol:
            e.covered.append((e.lo, e.hi))

    # Paired internal walls (gap midpoints), grouped for collinear merging.
    grouped: dict[tuple[str, float], list[tuple[float, float]]] = {}
    for mid, lo, hi in _pair_edges(vert_edges, iwt, tol):
        grouped.setdefault(("v", round(mid, 6)), []).append((lo, hi))
    for mid, lo, hi in _pair_edges(hor_edges, iwt, tol):
        grouped.setdefault(("h", round(mid, 6)), []).append((lo, hi))

    for (orient, coord), intervals in sorted(grouped.items()):
        for lo, hi in _merge_intervals(intervals, tol):
            if orient == "v":
                walls.append(WallSegment(coord, lo, coord, hi, iwt, kind="internal"))
            else:
                walls.append(WallSegment(lo, coord, hi, coord, iwt, kind="internal"))

    # Orphan walls: uncovered edge stretches get a wall hugging the edge.
    # An edge whose outward side has no neighbouring room mass — an interior
    # void (roof void, light well/duct) or space the pairing pass missed —
    # is structurally exterior (open to sky) and gets ewt, not iwt.
    # Room boxes ALONE aren't enough: at a T-junction, the perpendicular
    # partition's own foot leaves an iwt-wide sliver on the far room's edge
    # that no room covers (rooms are clear interior spaces — the partition
    # wall itself lives in the gap, unmodeled by room rects). Folding in the
    # ring + paired-internal walls already placed above (real built
    # structure) closes that sliver correctly, while a genuine void (roof
    # void, light well) — far wider than any wall — still reads as open.
    # Carved children are excluded from the union (`_structural_rooms`): their
    # mass is already contributed by the parent they sit inside, and counting
    # it twice would let a stray carve inflate the footprint. Their EDGES are
    # still present in `vert_edges`/`hor_edges` below, so a carve's own sides
    # are classified against the parent's mass and become internal partitions.
    #
    # NOT DEAD CODE, but currently unobservable HERE: a validated carve is a
    # subset of its parent, so the union polygon is identical either way, and
    # `_validate_carves`'s 0.01 m slack cannot reach `_edge_faces_open_space`
    # either — that probe starts its strip at eps = 0.02 outward. The filter
    # is what keeps that true: raise the carve tolerance above 0.02, or let a
    # carve be anything other than a strict sub-rectangle (Task 6's shape
    # templates), and removing it starts corrupting void classification.
    # `_plate_bounds` applies the same filter and IS observable today (a carve
    # exploiting the 0.01 m slack would otherwise inflate the plate bbox).
    structural = _structural_rooms(rooms)
    footprint = (
        unary_union(_part_boxes(structural) + [_raw_wall_box(w) for w in walls])
        if structural
        else None
    )
    orphan_groups: dict[tuple[str, float, str], list[tuple[float, float]]] = {}
    for is_vertical, edges, axis in ((True, vert_edges, "v"), (False, hor_edges, "h")):
        for e in edges:
            for lo, hi in _subtract_intervals((e.lo, e.hi), e.covered):
                if hi - lo < _MIN_WALL_LEN:
                    continue
                seg = _Edge(e.coord, lo, hi, e.normal)
                if _edge_faces_open_space(seg, is_vertical, footprint, ewt):
                    kind, thickness = "external", ewt
                else:
                    kind, thickness = "internal", iwt
                mid = e.coord + e.normal * thickness / 2
                orphan_groups.setdefault((axis, round(mid, 6), kind), []).append(
                    (lo, hi)
                )

    for (orient, coord, kind), intervals in sorted(orphan_groups.items()):
        thickness = ewt if kind == "external" else iwt
        for lo, hi in _merge_intervals(intervals, tol):
            if orient == "v":
                walls.append(WallSegment(coord, lo, coord, hi, thickness, kind=kind))
            else:
                walls.append(WallSegment(lo, coord, hi, coord, thickness, kind=kind))

    _snap_ends(walls)
    _trim_room_overreach(walls, rooms, ewt, iwt)

    # Drop walls on edges the room declared open (`Room.open_sides`) — a car
    # porch open to the driveway, a balcony open to the front. Applied last,
    # after snapping/trimming, so the comparison sees final centrelines.
    # Slack is ewt/2 + tol: the wall serving a room edge does NOT sit on that
    # edge — an external ring wall is ewt/2 outside it and snapped out to the
    # ring corners; a paired internal wall sits at the inter-room gap's
    # midpoint. A ring wall that `_merge_intervals` joined across an open
    # room AND a normal neighbour is SPLIT (interval subtraction), so only
    # the open room's share disappears.
    open_slack = ewt / 2 + tol
    open_v, open_h = _open_edge_intervals(rooms, open_slack)
    if open_v or open_h:
        # A room edge that is NOT declared open, sitting on the same
        # centreline, keeps that stretch of wall alive (party wall).
        covered_v, covered_h = _closed_edge_intervals(rooms, iwt, tol)
        walls = [
            piece
            for w in walls
            for piece in _apply_open_sides(
                w, open_v, open_h, covered_v, covered_h, open_slack
            )
        ]
    return walls


def _trim_room_overreach(
    walls: list[WallSegment], rooms: list[Room], ewt: float, iwt: float
) -> None:
    """`wall_polygons()` extends each wall's ends by half its own thickness
    for corner closure, assuming a perpendicular wall is there to close
    against — true even after `_snap_ends` legitimately extends a wall to
    meet one. An external wall (ewt) reaches further past that snapped end
    than an iwt wall would, which can land past a neighbouring room's edge
    with no wall there to close against and bite into its clear interior.
    Trims such ends back so the effective reach past a bare room corner
    matches what iwt gave before (#75 promoted some orphans to ewt).

    Operates on the FULL room list on purpose — a carved child is clear
    interior that a wall must not bite into just as much as its parent is —
    but on each room's part UNION, not its bounding box: an L room's notch is
    open space, and a wall is allowed to reach into it.
    """
    if not rooms:
        return
    rooms_union = _rooms_polygon(rooms)
    if rooms_union.is_empty:
        return
    margin = (ewt - iwt) / 2
    t = ewt / 2
    for w in walls:
        if w.kind != "external":
            continue
        if _is_vertical(w):
            lo, hi = min(w.y1, w.y2), max(w.y1, w.y2)
            lo_zone = box(w.x1 - t, lo - t, w.x1 + t, lo)
            hi_zone = box(w.x1 - t, hi, w.x1 + t, hi + t)
        else:
            lo, hi = min(w.x1, w.x2), max(w.x1, w.x2)
            lo_zone = box(lo - t, w.y1 - t, lo, w.y1 + t)
            hi_zone = box(hi, w.y1 - t, hi + t, w.y1 + t)
        new_lo, new_hi = lo, hi
        if rooms_union.intersection(lo_zone).area > 1e-6:
            new_lo += margin
        if rooms_union.intersection(hi_zone).area > 1e-6:
            new_hi -= margin
        if new_hi - new_lo < _MIN_WALL_LEN or (new_lo, new_hi) == (lo, hi):
            continue
        if _is_vertical(w):
            w.y1, w.y2 = new_lo, new_hi
        else:
            w.x1, w.x2 = new_lo, new_hi


def _is_vertical(w: WallSegment) -> bool:
    return abs(w.x1 - w.x2) < 1e-9


def _snap_ends(walls: list[WallSegment]) -> None:
    """Extend segment ends to meet nearby perpendicular centrelines."""
    for _ in range(2):  # second pass lets snapped ends enable further meets
        verts = [w for w in walls if _is_vertical(w)]
        hors = [w for w in walls if not _is_vertical(w)]
        for w in verts:
            lo, hi = min(w.y1, w.y2), max(w.y1, w.y2)
            for h in hors:
                hlo, hhi = min(h.x1, h.x2), max(h.x1, h.x2)
                if not (hlo - _SNAP <= w.x1 <= hhi + _SNAP):
                    continue
                if abs(h.y1 - lo) <= _SNAP:
                    lo = min(lo, h.y1)
                if abs(h.y1 - hi) <= _SNAP:
                    hi = max(hi, h.y1)
            w.y1, w.y2 = lo, hi
        for w in hors:
            lo, hi = min(w.x1, w.x2), max(w.x1, w.x2)
            for v in verts:
                vlo, vhi = min(v.y1, v.y2), max(v.y1, v.y2)
                if not (vlo - _SNAP <= w.y1 <= vhi + _SNAP):
                    continue
                if abs(v.x1 - lo) <= _SNAP:
                    lo = min(lo, v.x1)
                if abs(v.x1 - hi) <= _SNAP:
                    hi = max(hi, v.x1)
            w.x1, w.x2 = lo, hi


def derive_junctions(walls: list[WallSegment], tol: float = 0.01) -> list[WallJunction]:
    verts = [w for w in walls if _is_vertical(w)]
    hors = [w for w in walls if not _is_vertical(w)]

    candidates: set[tuple[float, float]] = set()
    for w in walls:
        candidates.add((round(w.x1, 4), round(w.y1, 4)))
        candidates.add((round(w.x2, 4), round(w.y2, 4)))
    for v in verts:
        vlo, vhi = min(v.y1, v.y2), max(v.y1, v.y2)
        for h in hors:
            hlo, hhi = min(h.x1, h.x2), max(h.x1, h.x2)
            if hlo - tol <= v.x1 <= hhi + tol and vlo - tol <= h.y1 <= vhi + tol:
                candidates.add((round(v.x1, 4), round(h.y1, 4)))

    junctions: list[WallJunction] = []
    for x, y in sorted(candidates):
        dirs: set[str] = set()
        for v in verts:
            if abs(v.x1 - x) > tol:
                continue
            vlo, vhi = min(v.y1, v.y2), max(v.y1, v.y2)
            if vlo - tol <= y <= vhi + tol:
                if vhi > y + tol:
                    dirs.add("N")
                if vlo < y - tol:
                    dirs.add("S")
        for h in hors:
            if abs(h.y1 - y) > tol:
                continue
            hlo, hhi = min(h.x1, h.x2), max(h.x1, h.x2)
            if hlo - tol <= x <= hhi + tol:
                if hhi > x + tol:
                    dirs.add("E")
                if hlo < x - tol:
                    dirs.add("W")
        if len(dirs) >= 2 and dirs not in ({"N", "S"}, {"E", "W"}):
            junctions.append(WallJunction(x=x, y=y, degree=len(dirs)))
    return junctions


def _on_exterior_ring(
    ext_walls: list[WallSegment], x: float, y: float, tol: float
) -> bool:
    for w in ext_walls:
        if _is_vertical(w):
            lo, hi = min(w.y1, w.y2), max(w.y1, w.y2)
            if abs(w.x1 - x) <= tol and lo - tol <= y <= hi + tol:
                return True
        else:
            lo, hi = min(w.x1, w.x2), max(w.x1, w.x2)
            if abs(w.y1 - y) <= tol and lo - tol <= x <= hi + tol:
                return True
    return False


def _through_axes(
    walls: list[WallSegment], x: float, y: float, tol: float
) -> tuple[bool, bool]:
    """(horizontal_through, vertical_through) at (x, y): whether a wall
    continues on BOTH sides along that axis (vs. dead-ending there)."""
    has_n = has_s = has_e = has_w = False
    for w in walls:
        if _is_vertical(w):
            if abs(w.x1 - x) > tol:
                continue
            lo, hi = min(w.y1, w.y2), max(w.y1, w.y2)
            if lo - tol <= y <= hi + tol:
                if hi > y + tol:
                    has_n = True
                if lo < y - tol:
                    has_s = True
        else:
            if abs(w.y1 - y) > tol:
                continue
            lo, hi = min(w.x1, w.x2), max(w.x1, w.x2)
            if lo - tol <= x <= hi + tol:
                if hi > x + tol:
                    has_e = True
                if lo < x - tol:
                    has_w = True
    return (has_e and has_w, has_n and has_s)


def derive_columns(
    walls: list[WallSegment],
    tol: float = 0.01,
    junctions: list[WallJunction] | None = None,
    max_beam_span_m: float | None = None,
    rooms: list[Room] | None = None,
) -> list[ColumnMarker]:
    """Place columns only where structurally significant.

    Every wall junction used to get a column, including interior T-ties
    where a partition simply dead-ends into another partition (degree 3,
    touching neither the exterior ring nor a true 4-way crossing) — these
    are infill ties, not load-bearing nodes, and cluttered real layouts
    with far more columns than needed (per CLAUDE.md: columns belong at
    "outer corners, staircase core, major wall intersections").

    Such interior Ts are dropped UNLESS omitting them would leave the
    through-wall's beam run exceeding max_beam_span_m between its nearest
    surviving neighbours on that same line.
    """
    if junctions is None:
        junctions = derive_junctions(walls, tol=tol)
    if max_beam_span_m is None:
        from app.engine.compliance import load_rules

        max_beam_span_m = load_rules()["max_beam_span_m"]

    ext_walls = [w for w in walls if w.kind == "external"]
    certain = [
        j
        for j in junctions
        if j.degree >= 4 or _on_exterior_ring(ext_walls, j.x, j.y, tol)
    ]
    certain_keys = {(round(j.x, 6), round(j.y, 6)) for j in certain}
    candidates = [
        j for j in junctions if (round(j.x, 6), round(j.y, 6)) not in certain_keys
    ]

    kept: list[WallJunction] = list(certain)

    for cand in sorted(candidates, key=lambda j: (j.x, j.y)):
        horiz_through, vert_through = _through_axes(walls, cand.x, cand.y, tol)
        exceeds = False
        if horiz_through:
            xs = sorted(k.x for k in kept if abs(k.y - cand.y) <= tol)
            below = max((v for v in xs if v < cand.x - tol), default=None)
            above = min((v for v in xs if v > cand.x + tol), default=None)
            # Gap that would result if cand is dropped — the span between
            # its flanking kept points, not cand's own distance to each.
            if below is not None and above is not None:
                if above - below > max_beam_span_m:
                    exceeds = True
            elif below is not None and cand.x - below > max_beam_span_m:
                exceeds = True
            elif above is not None and above - cand.x > max_beam_span_m:
                exceeds = True
        if vert_through:
            ys = sorted(k.y for k in kept if abs(k.x - cand.x) <= tol)
            below = max((v for v in ys if v < cand.y - tol), default=None)
            above = min((v for v in ys if v > cand.y + tol), default=None)
            if below is not None and above is not None:
                if above - below > max_beam_span_m:
                    exceeds = True
            elif below is not None and cand.y - below > max_beam_span_m:
                exceeds = True
            elif above is not None and above - cand.y > max_beam_span_m:
                exceeds = True
        if exceeds:
            kept.append(cand)

    return _merge_adjacent_columns(kept, rooms)


_COLUMN_MERGE_TOL = 0.3  # m — junctions closer than this are one physical column
# m — wider dedup radius, but ONLY for junction pairs where at least one sits
# on/near a staircase enclosure. A staircase core's walls and a neighbouring
# room's wall (e.g. a toilet/store abutting the stair) can each independently
# qualify as a "certain" column junction while being 0.3-1.0 m apart — too far
# for the general dedup, too close to form a sane structural grid line. This
# stays scoped to staircase-adjacent junctions so it never merges genuinely
# distinct, intentionally tight structural bays elsewhere in the plan.
_STAIR_CORE_MERGE_TOL = 1.0


def _near_staircase(
    x: float, y: float, rooms: list[Room] | None, tol: float = 0.3
) -> bool:
    """True if (x, y) sits on/within tol of a staircase room's footprint."""
    if not rooms:
        return False
    for r in rooms:
        if r.type != "staircase":
            continue
        if (
            r.x - tol <= x <= r.x + r.width + tol
            and r.y - tol <= y <= r.y + r.depth + tol
        ):
            return True
    return False


def _merge_adjacent_columns(
    kept: list[WallJunction], rooms: list[Room] | None = None
) -> list[ColumnMarker]:
    """Collapse junction clusters into single columns.

    Mixed wall conventions (zero-gap room tiling vs iwt gaps, orphan walls
    hugging a face at ±iwt/2) can put two junctions half a wall thickness
    apart; drawing a column on each reads as a detailing error ("twin
    columns") and skews structural grid extraction. Anything under one
    column width apart is a single physical column — keep the
    highest-degree junction of each cluster (best beam anchoring).

    Junction pairs adjacent to a staircase core use a wider merge radius
    (_STAIR_CORE_MERGE_TOL) instead of the general _COLUMN_MERGE_TOL — see
    _near_staircase.
    """
    remaining = sorted(kept, key=lambda j: (-j.degree, j.x, j.y))
    merged: list[WallJunction] = []
    for j in remaining:
        j_near_stair = _near_staircase(j.x, j.y, rooms)
        if any(
            (j.x - m.x) ** 2 + (j.y - m.y) ** 2
            < (
                _STAIR_CORE_MERGE_TOL
                if j_near_stair or _near_staircase(m.x, m.y, rooms)
                else _COLUMN_MERGE_TOL
            )
            ** 2
            for m in merged
        ):
            continue
        merged.append(j)
    merged.sort(key=lambda j: (j.x, j.y))
    return [ColumnMarker(cx=j.x, cy=j.y) for j in merged]


def wall_polygons(
    walls: list[WallSegment], openings: list[Polygon] = ()
) -> dict[str, Polygon]:
    """Union wall footprints per kind; opening boxes are subtracted.

    Segment boxes are extended by half their thickness at each end so
    perpendicular walls close cleanly at corners.
    """
    result: dict[str, Polygon] = {}
    for kind in ("external", "internal"):
        boxes = []
        for w in walls:
            if w.kind != kind:
                continue
            t = w.thickness / 2
            if _is_vertical(w):
                lo, hi = min(w.y1, w.y2), max(w.y1, w.y2)
                boxes.append(box(w.x1 - t, lo - t, w.x1 + t, hi + t))
            else:
                lo, hi = min(w.x1, w.x2), max(w.x1, w.x2)
                boxes.append(box(lo - t, w.y1 - t, hi + t, w.y1 + t))
        union = unary_union(boxes) if boxes else Polygon()
        for opening in openings:
            union = union.difference(opening)
        result[kind] = union
    return result


# ---------------------------------------------------------------------------
# Openings (S4.2)
# ---------------------------------------------------------------------------


class _Adjacency:
    __slots__ = ("a", "b", "vertical", "coord", "lo", "hi")

    def __init__(
        self, a: int, b: int, vertical: bool, coord: float, lo: float, hi: float
    ) -> None:
        self.a = a  # room index on the -axis side of the wall
        self.b = b  # room index on the +axis side
        self.vertical = vertical
        self.coord = coord
        self.lo = lo
        self.hi = hi


def _adjacencies(rooms: list[Room], iwt: float, tol: float) -> list[_Adjacency]:
    """Facing wall runs between every ordered room pair.

    Runs over PART pairs, not room bounding boxes: an L-shaped room touches
    its neighbour only along the parts that actually reach it, and its bbox
    would claim a shared wall across its own notch — a door hung there would
    open onto nothing. Runs on the same centreline are merged back so a
    multi-part contact still reads as one door-able wall.

    For a "RECT" room `Room.rects` is a 1-tuple, so this reduces exactly to
    the pre-template bbox pairing, in the same order.
    """
    out: list[_Adjacency] = []
    parts = [r.rects for r in rooms]
    for i, parts_a in enumerate(parts):
        for j, parts_b in enumerate(parts):
            if i == j:
                continue
            for vertical in (True, False):
                grouped: dict[float, list[tuple[float, float]]] = {}
                for pa in parts_a:
                    for pb in parts_b:
                        if vertical:
                            # pa's right edge facing pb's left edge
                            gap = pb.x - (pa.x + pa.width)
                            lo, hi = (
                                max(pa.y, pb.y),
                                min(pa.y + pa.depth, pb.y + pb.depth),
                            )
                            mid = (pa.x + pa.width + pb.x) / 2
                        else:
                            # pa's top edge facing pb's bottom edge
                            gap = pb.y - (pa.y + pa.depth)
                            lo, hi = (
                                max(pa.x, pb.x),
                                min(pa.x + pa.width, pb.x + pb.width),
                            )
                            mid = (pa.y + pa.depth + pb.y) / 2
                        if not (-tol <= gap <= iwt + tol) or hi - lo < 0.05:
                            continue
                        grouped.setdefault(round(mid, 6), []).append((lo, hi))
                for mid in sorted(grouped):
                    for lo, hi in _merge_intervals(grouped[mid], tol):
                        out.append(_Adjacency(i, j, vertical, mid, lo, hi))
    return out


def _fit_along(
    desired: float,
    lo: float,
    hi: float,
    width: float,
    obstacles: list[tuple[float, float]],
) -> float | None:
    """Find a centre position in [lo+width/2, hi-width/2] clear of obstacles.

    Obstacles are (along_position, half_forbidden_extent) pairs; the opening
    centre must satisfy |centre - pos| >= half + width/2.
    """
    span_lo = lo + width / 2
    span_hi = hi - width / 2
    if span_hi < span_lo:
        return None

    def clear(c: float) -> bool:
        return all(abs(c - p) >= h + width / 2 - 1e-9 for p, h in obstacles)

    c = min(max(desired, span_lo), span_hi)
    if clear(c):
        return c
    candidates: list[float] = []
    for p, h in obstacles:
        candidates.append(p + h + width / 2 + 1e-6)
        candidates.append(p - h - width / 2 - 1e-6)
    candidates += [span_lo, span_hi]
    valid = [
        c for c in candidates if span_lo - 1e-9 <= c <= span_hi + 1e-9 and clear(c)
    ]
    if not valid:
        return None
    return min(valid, key=lambda c: abs(c - desired))


def _exterior_edges(
    room, plate: tuple[float, float, float, float], ewt: float, tol: float
):
    """Yield (is_horizontal, ring_coord, lo, hi) for room edges on the floor's
    exterior surface (the room-union plate, see `_plate_bounds`).

    Spans come from the room's union-boundary runs, so an L room whose bbox
    reaches the plate boundary contributes only the stretch its parts
    actually occupy — the rest of that bbox line is open air over the notch,
    with no wall for an opening to cut into.
    """
    px1, py1, px2, py2 = plate
    vert, hor = _boundary_edges(_room_polygon(room))
    for e in vert:
        if e.normal == -1 and abs(e.coord - px1) <= 2 * tol:
            yield (False, px1 - ewt / 2, e.lo, e.hi)
        elif e.normal == +1 and abs(e.coord - px2) <= 2 * tol:
            yield (False, px2 + ewt / 2, e.lo, e.hi)
    for e in hor:
        if e.normal == -1 and abs(e.coord - py1) <= 2 * tol:
            yield (True, py1 - ewt / 2, e.lo, e.hi)
        elif e.normal == +1 and abs(e.coord - py2) <= 2 * tol:
            yield (True, py2 + ewt / 2, e.lo, e.hi)


def _exterior_wall_edges(room, walls: list[WallSegment], tol: float):
    """Yield (is_horizontal, wall_coord, lo, hi) for external walls bordering
    this room. Includes void-facing orphan walls (kind="external") that
    wouldn't be caught by _exterior_edges's plate-bounds check.

    A wall's centreline sits offset from the room edge by half its own
    thickness (the room-layout convention: rooms are clear interior rects,
    walls live outside them) — matching against the raw room edge with only
    `tol` slack misses every real wall, since that offset (ewt/2 = 0.115 m)
    dwarfs `tol` (typically 0.01 m).

    Matching is against the room's union-boundary runs rather than its four
    bbox edges: a non-RECT room's notch faces are real exterior surfaces
    that no bbox edge describes, and its bbox lines run past where the room
    stops.
    """
    vert, hor = _boundary_edges(_room_polygon(room))
    for w in walls:
        if w.kind != "external":
            continue
        t = w.thickness / 2
        if abs(w.x1 - w.x2) < 1e-9:  # vertical wall
            wall_x = w.x1
            wy1, wy2 = min(w.y1, w.y2), max(w.y1, w.y2)
            for e in vert:
                if abs(wall_x - (e.coord + e.normal * t)) > tol:
                    continue
                overlap_lo = max(wy1, e.lo)
                overlap_hi = min(wy2, e.hi)
                if overlap_hi - overlap_lo > tol:
                    yield (False, wall_x, overlap_lo, overlap_hi)
        else:  # horizontal wall
            wall_y = w.y1
            wx1, wx2 = min(w.x1, w.x2), max(w.x1, w.x2)
            for e in hor:
                if abs(wall_y - (e.coord + e.normal * t)) > tol:
                    continue
                overlap_lo = max(wx1, e.lo)
                overlap_hi = min(wx2, e.hi)
                if overlap_hi - overlap_lo > tol:
                    yield (True, wall_y, overlap_lo, overlap_hi)


def _is_declared_open_edge(
    room: Room,
    is_horizontal: bool,
    coord: float,
    ewt: float,
    tol: float,
    lo: float | None = None,
    hi: float | None = None,
) -> bool:
    """True if (`coord`, [`lo`, `hi`]) sits on a room edge the room declared
    open via `Room.open_sides` — no wall was ever drawn there (see
    `derive_walls`'s own open-edge subtraction), so no opening may be cut
    into it either.

    A wall centreline serving a room edge sits `ewt / 2` outside the raw
    room edge (external ring convention), so the match slack must absorb
    that offset — `ewt / 2 + tol`, matching `derive_walls`'s `open_slack`.

    Matched against the room's union-boundary runs, and against the
    candidate's own span when given: a non-RECT room can have two runs on
    the same declared-open side at different coordinates, and one run of a
    side can be open while the bbox line it lies on is not the room at all.
    """
    if not room.open_sides:
        return False
    slack = ewt / 2 + tol
    sides = _edges_by_side(room)
    for side in room.open_sides:
        if _SIDE_IS_HORIZONTAL[side] != is_horizontal:
            continue
        for c, elo, ehi in sides[side]:
            if abs(coord - (c + _SIDE_SIGN[side] * ewt / 2)) > slack:
                continue
            if lo is None or hi is None or (lo < ehi - tol and hi > elo + tol):
                return True
    return False


def _all_exterior_edges(
    room,
    walls: list[WallSegment],
    plate: tuple[float, float, float, float],
    ewt: float,
    tol: float,
):
    """Yield all (is_horizontal, coord, lo, hi) exterior edges for a room,
    combining both plate-boundary edges and void-facing orphan walls marked
    kind="external". Deduplicates edges that appear in both sources.

    Edges lying on a side the room declared open (`Room.open_sides`) are
    skipped entirely — there is no wall there for an opening to cut into.
    """
    seen = set()
    # First collect from plate bounds
    for is_h, coord, lo, hi in _exterior_edges(room, plate, ewt, tol):
        if _is_declared_open_edge(room, is_h, coord, ewt, tol, lo, hi):
            continue
        key = (is_h, round(coord, 6), round(lo, 6), round(hi, 6))
        if key not in seen:
            seen.add(key)
            yield (is_h, coord, lo, hi)
    # Then add any external walls not on plate boundary (void-facing orphans)
    for is_h, coord, lo, hi in _exterior_wall_edges(room, walls, tol):
        if _is_declared_open_edge(room, is_h, coord, ewt, tol, lo, hi):
            continue
        key = (is_h, round(coord, 6), round(lo, 6), round(hi, 6))
        if key not in seen:
            seen.add(key)
            yield (is_h, coord, lo, hi)


class _ObstacleIndex:
    """Along-wall obstacles (columns + placed openings) per wall line."""

    def __init__(self, columns: list[ColumnMarker]) -> None:
        self._columns = columns
        self._placed: list[Opening] = []

    def for_wall(self, is_horizontal: bool, coord: float) -> list[tuple[float, float]]:
        obs: list[tuple[float, float]] = []
        for c in self._columns:
            cross = c.cy if is_horizontal else c.cx
            if abs(cross - coord) <= _COL_CLEAR:
                obs.append((c.cx if is_horizontal else c.cy, _COL_CLEAR))
        for o in self._placed:
            if o.is_horizontal != is_horizontal:
                continue
            cross = o.cy if o.is_horizontal else o.cx
            if abs(cross - coord) > 1e-6:
                continue
            obs.append((o.cx if o.is_horizontal else o.cy, o.width / 2))
        return obs

    def add(self, opening: Opening) -> None:
        self._placed.append(opening)

    def remove(self, opening: Opening) -> None:
        try:
            self._placed.remove(opening)
        except ValueError:
            pass


def _make_door(
    room,
    vertical_wall: bool,
    coord: float,
    centre: float,
    width: float,
    thickness: float,
    prefer_lo_hinge: bool,
) -> Opening:
    if vertical_wall:
        cx, cy = coord, centre
        hinge = (cx, cy - width / 2) if prefer_lo_hinge else (cx, cy + width / 2)
        leaf = 1.0 if prefer_lo_hinge else -1.0  # leaf direction along +/-y
        into = 1.0 if room.x >= cx else -1.0  # served room side along x
        swing_cw = (-leaf * into) < 0
        is_horizontal = False
    else:
        cx, cy = centre, coord
        hinge = (cx - width / 2, cy) if prefer_lo_hinge else (cx + width / 2, cy)
        leaf = 1.0 if prefer_lo_hinge else -1.0  # along +/-x
        into = 1.0 if room.y >= cy else -1.0  # along y
        swing_cw = (leaf * into) < 0
        is_horizontal = True
    return Opening(
        kind="door",
        cx=cx,
        cy=cy,
        width=width,
        is_horizontal=is_horizontal,
        wall_thickness=thickness,
        hinge_x=hinge[0],
        hinge_y=hinge[1],
        swing_into_room_id=room.id,
        swing_cw=swing_cw,
    )


# The sourced main-entrance rule: an entrance in the north, north-east or east
# zone is auspicious. Module-level so tests can import it instead of keeping a
# second copy — two independent copies drifted apart once already (three
# mutations to this tuple survived the suite because the test that "documented"
# the rule asserted against its own literal).
ENTRANCE_AUSPICIOUS_ZONES: tuple[str, ...] = ("N", "NE", "E")

# Per-road-side override, REPLACING the default set for that orientation.
#
# The entrance always sits on the y-min (road-facing) wall, so every candidate
# shares one row of the 3x3 grid. On a south road that row is [SW, S, SE], which
# holds no N/NE/E cell, so the sourced rule is provably inert on `PlotConfig`'s
# DEFAULT configuration. Karthik ruled explicitly that a south-facing entrance
# should prefer the SE end of the frontage; that is a product-owner decision, not
# something derivable from the rules data, so it is scoped to south alone.
#
# Extended to west on the same principle (front row [NW, W, SW], equally inert
# under the sourced rule): Karthik ruled the west-facing entrance should prefer
# the NW end of the frontage, mirroring the sanctioned south rule — prefer the
# auspicious end of the facing wall. That decision is recorded in the
# solver-capability-uplift plan and the firing/pinning tests below.
#
# Replacement, not union with the default: a union would make widening the
# override to every road side undetectable, because every road side would keep
# the cells it already had. Replacement makes such a mistake fail the north/east
# firing tests immediately.
ENTRANCE_AUSPICIOUS_ZONES_BY_ROAD_SIDE: dict[str, tuple[str, ...]] = {
    "S": ("SE",),
    "W": ("NW",),
}


def entrance_auspicious_zones(north_angle_deg: float) -> tuple[str, ...]:
    """Auspicious main-entrance zones for a plot at `north_angle_deg`.

    Keyed off the RESOLVED orientation rather than `cfg.road_side`, because
    `north_angle_deg` — when set — is what decides which zones the frontage
    actually spans. Keying off the raw road side would let the two disagree:
    `road_side="S"` with a surveyed `north_angle_deg=180.0` faces north, its
    front row is [NE, N, NW], and the south override would strip its genuine NE
    preference while offering an SE cell that no candidate can occupy. Going
    through the resolved angle keeps the rule and the zones on the same
    orientation in every case, including the reverse pairing (`road_side="N"`
    with an explicit `0.0`, which really does face south and really should
    prefer SE).

    A non-cardinal surveyed bearing (say 37°) belongs to no road side, so it gets
    the default sourced rule.
    """
    from app.engine.vastu import road_side_for_north_angle

    side = road_side_for_north_angle(north_angle_deg)
    if side is None:
        return ENTRANCE_AUSPICIOUS_ZONES
    return ENTRANCE_AUSPICIOUS_ZONES_BY_ROAD_SIDE.get(side, ENTRANCE_AUSPICIOUS_ZONES)


def _entrance_auspicious(vastu_cfg: PlotConfig | None, x: float, y: float) -> int:
    """0 when a main-entrance candidate centred at (x, y) sits in an auspicious
    Vastu zone for the plot's orientation, else 1. Always 1 when Vastu is off, so
    the key is a constant and the ordering is untouched.

    The auspicious set is N/NE/E by default and SE on a south-facing plot; see
    `entrance_auspicious_zones`.

    The point scored is the midpoint of the candidate's usable frontage span —
    the same quantity the distance-to-gate key uses — rather than the door
    centre `_fit_along` will later pick, which is not known until after the
    ordering is decided.
    """
    if vastu_cfg is None or not vastu_cfg.vastu_enabled:
        return 1
    from app.engine.vastu import resolve_north_angle, zone_for_point

    # `cfg.north_angle_deg` is `float | None`; `resolve_north_angle` is the one
    # place that turns it into a real angle (an explicit 0.0 wins, `None` falls
    # back to the road side). Passing the raw field would send `None` into the
    # trigonometry.
    north = resolve_north_angle(vastu_cfg)
    zone = zone_for_point(x, y, vastu_cfg.plot_width, vastu_cfg.plot_length, north)
    return 0 if zone in entrance_auspicious_zones(north) else 1


def _place_main_entrance(
    rooms: list[Room],
    obstacles: _ObstacleIndex,
    std: OpeningStandards,
    buildable: Polygon,
    ewt: float,
    tol: float,
    reasons: list[str] | None = None,
    status: dict | None = None,
    vastu_cfg: PlotConfig | None = None,
) -> Opening | None:
    """Main entrance door (MD) in the road-facing external wall.

    The road is always the y-min edge (archetypes/vastu convention: y=0 is
    the road/front edge). Entry room preference follows Indian practice:
    living > foyer > passage > dining; never parking, stairs or wet rooms. The
    door sits on the floor's front exterior surface (room-union plate); its
    desired position is the facade midpoint so the door lines up with the
    compound-wall gate (cad_advanced centres the gate on the road side).

    ``status``, if given, is set with ``entrance_not_on_ground_floor=True``
    when the ENTIRE road frontage is occupied by no-entry room types
    (parking/wet/staircase) — the "upside-down duplex" typology (#6d): all
    bedrooms on GF, the real entrance is an external stair straight to the
    first floor. That's a distinct, typed condition from the generic
    "no suitable room" diagnostic below — it means no door placement here
    was ever possible, not that one was attempted and failed (too narrow,
    columns-blocked), so a caller can surface it deliberately (e.g. a
    landing-door design, or an explicit "entrance not on ground floor"
    label) rather than reading it out of the free-text diagnostic string.

    ``vastu_cfg``, when given with ``vastu_enabled``, adds an auspicious-zone
    key to the candidate ordering. Because every candidate sits on the same
    (y-min) frontage, they can only differ across ONE row of the 3x3 Vastu
    grid: ``['NE', 'N', 'NW']`` on a north road, ``['SE', 'E', 'NE']`` on an
    east road, ``['SW', 'S', 'SE']`` on a south road (the PlotConfig default)
    and ``['NW', 'W', 'SW']`` on a west road. The default N/NE/E rule can fire
    on north and east roads; the south road gets the product-owner SE override
    and the west road the matching NW override
    (``ENTRANCE_AUSPICIOUS_ZONES_BY_ROAD_SIDE``), so every road side can move
    the door toward the auspicious end of its facing wall.
    ``tests/test_vastu_floors.py`` pins both the firing and the still-inert
    middle cells ("S" on south, "W" on west).
    """
    bx1, _by1, bx2, _by2 = buildable.bounds
    _px1, py1, _px2, _py2 = _plate_bounds(rooms, buildable, ewt)
    coord = py1 - ewt / 2  # front external-wall centreline (union plate)
    width = std.main_door_width_m
    gate_x = (bx1 + bx2) / 2
    frontage_rooms = [r for r in rooms if abs(r.y - py1) <= 2 * tol]
    cands = []
    rejected: list[str] = []
    for room in frontage_rooms:
        if room.type in _NO_ENTRY_TYPES:
            rejected.append(f"{room.id}(type={room.type}) cannot host entry")
            continue
        lo, hi = room.x, room.x + room.width
        if hi - lo < width + 2 * _JAMB:
            rejected.append(
                f"{room.id} too narrow for main door "
                f"({hi - lo:.2f}m < {width + 2 * _JAMB:.2f}m)"
            )
            continue
        prio = _ENTRY_PRIORITY.get(room.type, 4)
        # Ranked immediately after `prio` and ABOVE distance-to-gate: Vastu
        # outranks gate alignment, never room-type suitability (an auspicious
        # dining room must not beat an inauspicious living room). Below `dist`
        # it would be inert a second way — `dist` is a float, so ties in it
        # essentially never occur. 0 sorts first, so 0 == auspicious.
        cands.append(
            (
                prio,
                _entrance_auspicious(vastu_cfg, (lo + hi) / 2, coord),
                abs((lo + hi) / 2 - gate_x),
                room.id,
                room,
                lo,
                hi,
            )
        )
    for _prio, _ausp, _dist, rid, room, lo, hi in sorted(cands, key=lambda t: t[:4]):
        centre = _fit_along(
            gate_x, lo + _JAMB, hi - _JAMB, width, obstacles.for_wall(True, coord)
        )
        if centre is None:
            rejected.append(f"{rid} fully blocked by columns/openings")
            continue
        door = _make_door(
            room, False, coord, centre, width, ewt, centre <= (lo + hi) / 2
        )
        door.is_main = True
        return door
    if (
        status is not None
        and not cands
        and frontage_rooms
        and all(r.type in _NO_ENTRY_TYPES for r in frontage_rooms)
    ):
        status["entrance_not_on_ground_floor"] = True
    detail = "; ".join(rejected) if rejected else "no road-facing room at front plate"
    if reasons is not None:
        reasons.append(f"main_entrance: {detail}")
    else:
        logger.warning(
            "no suitable road-facing room for a main entrance door: %s", detail
        )
    return None


def derive_openings(
    rooms: list[Room],
    walls: list[WallSegment],
    columns: list[ColumnMarker],
    std: OpeningStandards,
    buildable: Polygon,
    ewt: float = EWT,
    iwt: float = IWT,
    tol: float = 0.01,
    floor: int = 0,
    reasons: list[str] | None = None,
    status: dict | None = None,
    vastu_cfg: PlotConfig | None = None,
) -> list[Opening]:
    adjs = _adjacencies(rooms, iwt, tol)
    obstacles = _ObstacleIndex(columns)
    openings: list[Opening] = []
    doored_gaps: set[tuple[int, int]] = set()  # room-index pairs already connected
    plate = _plate_bounds(rooms, buildable, ewt)  # exterior-surface model

    def place(opening: Opening | None) -> bool:
        if opening is None:
            return False
        obstacles.add(opening)
        openings.append(opening)
        return True

    # ── Main entrance first, so it claims front-wall space before windows ─
    if floor == 0:
        place(
            _place_main_entrance(
                rooms, obstacles, std, buildable, ewt, tol, reasons, status, vastu_cfg
            )
        )

    # ── Doors: one per room not in _NO_DOOR_TYPES; a door in a shared wall
    # serves BOTH rooms, so a room whose gap already carries a door is done ──
    id_to_index = {r.id: k for k, r in enumerate(rooms)}
    ens_bed_index = {}  # en-suite room index -> its attached bedroom index
    for k, r in enumerate(rooms):
        bed_id = _ensuite_bedroom_id(r.id)
        if bed_id is not None and bed_id in id_to_index:
            ens_bed_index[k] = id_to_index[bed_id]

    main_door = next((o for o in openings if o.is_main), None)
    for idx, room in sorted(enumerate(rooms), key=lambda t: t[1].id):
        if room.type in _NO_DOOR_TYPES:
            continue
        width = _WET_DOOR if room.type in _WET_TYPES else std.door_width_m
        bed_idx = ens_bed_index.get(idx)  # set only for en-suite toilets
        # a common (non-en-suite) toilet/WC should not open directly opposite
        # the main entrance when another doorable wall is available
        is_common_toilet = bed_idx is None and room.type in {
            "toilet",
            "wc_only",
            "bathroom_master",
        }
        cands = []
        already_served = False
        for adj in adjs:
            if idx not in (adj.a, adj.b):
                continue
            other_idx = adj.b if adj.a == idx else adj.a
            other = rooms[other_idx]
            gap_key = (min(adj.a, adj.b), max(adj.a, adj.b))
            if bed_idx is not None:
                # en-suite: its door must open into its attached bedroom only
                if other_idx != bed_idx:
                    continue
                if adj.hi - adj.lo < width + 2 * _JAMB:
                    continue
                cands.append((0, 0, 0, 0, 0, other.id, adj))
                continue
            # a shared door serves this room too — unless it leads through
            # a wet room (a bedroom must not be reachable only via a toilet)
            if gap_key in doored_gaps and other.type not in _WET_TYPES:
                already_served = True
                break
            if adj.hi - adj.lo < width + 2 * _JAMB:
                continue
            prio = _DOOR_NEIGHBOUR_PRIORITY.get(other.type, 4)
            # non-circulation stays below circulation; the main-door-facing
            # penalty only ever re-orders equally-ranked circulation walls
            if is_common_toilet:
                is_noncirc = 1 if prio >= 4 else 0
                avoid = 1 if _faces_main_door(adj, main_door) else 0
            else:
                is_noncirc = 0
                avoid = 0
            # a single-door room (toilet/kitchen/...) that ends up with its
            # ONE door onto another no-transit neighbour risks orphaning
            # itself — BFS dead-ends at a no-transit node, so this doesn't
            # guarantee reachability the way an ordinary neighbour's door
            # does. Deprioritized, not excluded: still used if it's the only
            # option.
            no_transit_neighbor = (
                1
                if room.type in _SINGLE_DOOR_TYPES and other.type in _NO_TRANSIT_TYPES
                else 0
            )
            # A WC/bath must never open onto the stair landing. One door in a
            # shared wall serves BOTH rooms, so the ban is on the wall, not on
            # a direction — it has to rank the same whether we arrive here
            # from the toilet's turn or the staircase's. Ranked worst rather
            # than dropped so a stair (or toilet) whose only doorable
            # partition is the other still gets a door instead of being
            # orphaned; the solver's _STAIR_DOOR_MIN_OVERLAP_MM constraint is
            # what makes that last resort unreachable in practice.
            wet_stair_wall = 1 if _is_wet_stair_pair(room.type, other.type) else 0
            cands.append(
                (
                    wet_stair_wall,
                    no_transit_neighbor,
                    is_noncirc,
                    avoid,
                    prio,
                    other.id,
                    adj,
                )
            )
        if already_served:
            continue
        # en-suite doors swing into the bedroom; all others into the room itself
        swing_room = rooms[bed_idx] if bed_idx is not None else room
        placed = False
        for _ws, _nt, _nc, _av, _prio, _oid, adj in sorted(
            cands, key=lambda t: (t[0], t[1], t[2], t[3], t[4], t[5])
        ):
            desired = adj.lo + _JAMB + width / 2  # hinge near the jamb, not centred
            centre = _fit_along(
                desired,
                adj.lo + _JAMB,
                adj.hi - _JAMB,
                width,
                obstacles.for_wall(not adj.vertical, adj.coord),
            )
            if centre is None:
                continue
            prefer_lo = centre <= (adj.lo + adj.hi) / 2
            placed = place(
                _make_door(
                    swing_room, adj.vertical, adj.coord, centre, width, iwt, prefer_lo
                )
            )
            if placed:
                doored_gaps.add((min(adj.a, adj.b), max(adj.a, adj.b)))
                break
        if not placed:
            # entrance door on an exterior edge (e.g. parking, or isolated room)
            for is_h, coord, lo, hi in _all_exterior_edges(
                room, walls, plate, ewt, tol
            ):
                if hi - lo < width + 2 * _JAMB:
                    continue
                centre = _fit_along(
                    (lo + hi) / 2,
                    lo + _JAMB,
                    hi - _JAMB,
                    width,
                    obstacles.for_wall(is_h, coord),
                )
                if centre is None:
                    continue
                placed = place(
                    _make_door(room, not is_h, coord, centre, width, ewt, True)
                )
                if placed:
                    break

    # ── Windows: habitable rooms, up to 2 longest exterior edges ─────────
    for room in sorted(rooms, key=lambda r: r.id):
        if room.type not in _WINDOW_TYPES:
            continue
        edges = sorted(
            _all_exterior_edges(room, walls, plate, ewt, tol),
            key=lambda e: e[3] - e[2],
            reverse=True,
        )[:2]
        for is_h, coord, lo, hi in edges:
            width = min(std.window_width_m, (hi - lo) * std.window_max_room_fraction)
            if width < 0.3:
                continue
            centre = _fit_along(
                (lo + hi) / 2,
                lo + _JAMB,
                hi - _JAMB,
                width,
                obstacles.for_wall(is_h, coord),
            )
            if centre is None:
                continue
            cx, cy = (centre, coord) if is_h else (coord, centre)
            place(
                Opening(
                    kind="window",
                    cx=cx,
                    cy=cy,
                    width=width,
                    is_horizontal=is_h,
                    wall_thickness=ewt,
                )
            )

    # ── Ventilators: wet rooms with an exterior edge ─────────────────────
    for room in sorted(rooms, key=lambda r: r.id):
        if room.type not in _WET_TYPES:
            continue
        for is_h, coord, lo, hi in _all_exterior_edges(room, walls, plate, ewt, tol):
            if hi - lo < std.ventilator_width_m + 2 * _JAMB:
                continue
            centre = _fit_along(
                (lo + hi) / 2,
                lo + _JAMB,
                hi - _JAMB,
                std.ventilator_width_m,
                obstacles.for_wall(is_h, coord),
            )
            if centre is None:
                continue
            cx, cy = (centre, coord) if is_h else (coord, centre)
            place(
                Opening(
                    kind="ventilator",
                    cx=cx,
                    cy=cy,
                    width=std.ventilator_width_m,
                    is_horizontal=is_h,
                    wall_thickness=ewt,
                )
            )
            break  # one ventilator per wet room

    # ── Navigability: cap wet rooms at one door, then repair the door graph
    # so every room is reachable from the entrance (GF) / stair (FF) without
    # transiting a wet room or parking ───────────────────────────────────
    _enforce_single_door(rooms, openings, obstacles, adjs, tol)
    _repair_connectivity(
        rooms,
        walls,
        openings,
        obstacles,
        adjs,
        doored_gaps,
        std,
        buildable,
        ewt,
        iwt,
        tol,
        floor,
    )
    # repair never doors into a single-door room, but re-assert defensively
    _enforce_single_door(rooms, openings, obstacles, adjs, tol)
    return openings


# ---------------------------------------------------------------------------
# Door-graph navigability (S4.2b)
# ---------------------------------------------------------------------------


def _door_endpoints(
    o: Opening, rooms: list[Room], adjs: list[_Adjacency], tol: float
) -> tuple[object, object] | None:
    """The two graph nodes a door connects: (room_i, room_j) for an interior
    door, or (room_i, "outside") for an exterior/main door."""
    if o.kind != "door":
        return None
    if o.is_horizontal:
        door_coord, door_centre = o.cy, o.cx
    else:
        door_coord, door_centre = o.cx, o.cy
    for adj in adjs:
        # an interior door on a vertical wall is not horizontal, and v.v.
        if adj.vertical == o.is_horizontal:
            continue
        if abs(adj.coord - door_coord) > 0.06:
            continue
        if adj.lo - tol <= door_centre <= adj.hi + tol:
            return (adj.a, adj.b)
    if o.swing_into_room_id:
        for i, r in enumerate(rooms):
            if r.id == o.swing_into_room_id:
                return (i, "outside")
    return None


def _door_graph(
    rooms: list[Room], openings: list[Opening], adjs: list[_Adjacency], tol: float
) -> dict[object, set]:
    graph: dict[object, set] = {i: set() for i in range(len(rooms))}
    graph["outside"] = set()
    for o in openings:
        ep = _door_endpoints(o, rooms, adjs, tol)
        if ep is None:
            continue
        a, b = ep
        graph[a].add(b)
        graph[b].add(a)
    return graph


def _entry_seed(rooms: list[Room], openings: list[Opening], floor: int) -> int | None:
    """BFS start room: the main-door room on GF, else the staircase."""
    if floor == 0:
        for o in openings:
            if o.is_main and o.swing_into_room_id:
                for i, r in enumerate(rooms):
                    if r.id == o.swing_into_room_id:
                        return i
    for i, r in enumerate(rooms):
        if r.type == "staircase":
            return i
    return None


def _reachable_rooms(
    rooms: list[Room], graph: dict[object, set], floor: int, openings: list[Opening]
) -> set[int]:
    """Room indices reachable from the entrance (GF) / staircase (upper floors)
    without transiting a wet room or parking (those may only be endpoints).

    The exterior ring ("outside") is a valid corridor ONLY on the ground floor:
    upper floors have no street access, so a room reachable only via its own
    exterior door (open air) must NOT count as reachable there."""
    from collections import deque

    ground = floor == 0
    start: set = {"outside"} if ground else set()
    seed = _entry_seed(rooms, openings, floor)
    if seed is not None:
        start.add(seed)
    visited = set(start)
    queue = deque(start)
    while queue:
        node = queue.popleft()
        if node == "outside":
            if not ground:
                continue  # not a corridor above the ground floor
        elif rooms[node].type in _NO_TRANSIT_TYPES:
            continue  # reachable, but not a through-route
        for nbr in graph.get(node, ()):
            if nbr not in visited:
                visited.add(nbr)
                queue.append(nbr)
    return {n for n in visited if n != "outside"}


def validate_floor_connectivity(
    rooms: list[Room],
    openings: list[Opening],
    floor: int,
    iwt: float = IWT,
    tol: float = 0.01,
) -> list[str]:
    """Human-readable navigability violations for a single floor (empty ⇒ OK).

    Read-only: drawing callers keep working; the generator gate calls this
    after `derive_openings` (which already ran the repair pass)."""
    adjs = _adjacencies(rooms, iwt, tol)
    graph = _door_graph(rooms, openings, adjs, tol)
    reachable = _reachable_rooms(rooms, graph, floor, openings)
    problems: list[str] = []
    for i, r in enumerate(rooms):
        if r.type == "passage":
            continue
        if i not in reachable:
            problems.append(
                f"{r.id} ({r.type}) is not reachable from the "
                f"{'entrance' if floor == 0 else 'staircase'} without passing "
                "through a wet room or parking"
            )
    return problems


def _enforce_single_door(
    rooms: list[Room],
    openings: list[Opening],
    obstacles: _ObstacleIndex,
    adjs: list[_Adjacency],
    tol: float,
) -> None:
    """Toilets/WCs/master baths/utility/kitchen keep exactly one door — the
    highest-priority one (en-suite → its bedroom, else circulation, with a
    no-transit neighbour such as a kitchen or another wet room ranked worst
    since keeping that door risks orphaning the room: BFS dead-ends at a
    no-transit node, so a door onto one doesn't guarantee reachability the
    way an ordinary circulation neighbour's door does)."""
    for i, room in enumerate(rooms):
        if room.type not in _SINGLE_DOOR_TYPES:
            continue
        ens_bed = _ensuite_bedroom_id(room.id)
        on_room: list[tuple[int, Opening]] = []
        for o in openings:
            if o.kind != "door":
                continue
            ep = _door_endpoints(o, rooms, adjs, tol)
            if ep is None or i not in ep:
                continue
            other = ep[0] if ep[1] == i else ep[1]
            if other == "outside":
                rank = 5
            elif ens_bed is not None and rooms[other].id == ens_bed:
                rank = 0
            elif _is_wet_stair_pair(room.type, rooms[other].type):
                # ranked below even a no-transit neighbour: of all the doors a
                # wet room could keep, the one onto the stair landing is the
                # one to drop first
                rank = 7
            elif rooms[other].type in _NO_TRANSIT_TYPES:
                # A neighbour that is itself a no-transit room (kitchen, a
                # second wet room, parking) doesn't guarantee this room stays
                # reachable — BFS dead-ends there. Only keep such a door if
                # no ordinary circulation neighbour is available.
                rank = 6
            else:
                rank = _DOOR_NEIGHBOUR_PRIORITY.get(rooms[other].type, 4)
            on_room.append((rank, o))
        if len(on_room) <= 1:
            continue
        on_room.sort(key=lambda t: t[0])
        for _rank, extra in on_room[1:]:
            openings.remove(extra)
            obstacles.remove(extra)


def _repair_connectivity(
    rooms: list[Room],
    walls: list[WallSegment],
    openings: list[Opening],
    obstacles: _ObstacleIndex,
    adjs: list[_Adjacency],
    doored_gaps: set[tuple[int, int]],
    std: OpeningStandards,
    buildable: Polygon,
    ewt: float,
    iwt: float,
    tol: float,
    floor: int,
) -> None:
    """Add doors until every room is reachable, or no progress can be made.

    Prefers a shared wall with a reachable, non-wet neighbour (real
    circulation), then any undoored shared wall, then an exterior edge.

    Parking rooms are exempt, same as passage: `_NO_DOOR_TYPES` already
    keeps them out of the main per-room door loop by design (checklist
    item 3 in the reverse-engineering harness — a car porch/parking bay is
    a real, physically separate outdoor structure, reachable only from the
    driveway, not a room a resident walks into from inside the house). This
    repair pass ran unconditionally over ALL non-passage rooms regardless
    of type, so a deliberately door-less, gapped parking room always came
    back "unreachable" and got a forced door anyway — undoing the very
    exclusion `_NO_DOOR_TYPES` was there to enforce, and drawing a
    pedestrian door into a car porch no real design has one in."""
    for _ in range(len(rooms) + 1):
        graph = _door_graph(rooms, openings, adjs, tol)
        reachable = _reachable_rooms(rooms, graph, floor, openings)
        unreachable = [
            i
            for i, r in enumerate(rooms)
            if r.type not in ({"passage"} | _PARKING_TYPES) and i not in reachable
        ]
        if not unreachable:
            return
        progressed = False
        for i in unreachable:
            if _add_repair_door(
                i,
                rooms,
                walls,
                openings,
                obstacles,
                adjs,
                doored_gaps,
                reachable,
                std,
                buildable,
                ewt,
                iwt,
                tol,
                floor,
            ):
                progressed = True
                break  # rebuild the graph after each new door
        if not progressed:
            return


def _add_repair_door(
    i: int,
    rooms: list[Room],
    walls: list[WallSegment],
    openings: list[Opening],
    obstacles: _ObstacleIndex,
    adjs: list[_Adjacency],
    doored_gaps: set[tuple[int, int]],
    reachable: set[int],
    std: OpeningStandards,
    buildable: Polygon,
    ewt: float,
    iwt: float,
    tol: float,
    floor: int,
) -> bool:
    room = rooms[i]
    # never repair a single-door room directly (it keeps its single door —
    # its reachability must come via that door's non-single-door neighbour),
    # and never route a repair door INTO a single-door room (that both breaks
    # the single-door invariant and cannot help, since these rooms are not
    # through-routes)
    if room.type in _SINGLE_DOOR_TYPES:
        return False
    width = std.door_width_m
    cands = []
    for adj in adjs:
        if i not in (adj.a, adj.b):
            continue
        other_idx = adj.b if adj.a == i else adj.a
        gap_key = (min(adj.a, adj.b), max(adj.a, adj.b))
        if gap_key in doored_gaps:
            continue
        if adj.hi - adj.lo < width + 2 * _JAMB:
            continue
        other = rooms[other_idx]
        if other.type in _SINGLE_DOOR_TYPES:
            continue
        pref = 0 if other_idx in reachable else 1
        prio = _DOOR_NEIGHBOUR_PRIORITY.get(other.type, 4)
        cands.append((pref, prio, other.id, adj))
    for _pref, _prio, _oid, adj in sorted(cands, key=lambda t: (t[0], t[1], t[2])):
        desired = adj.lo + _JAMB + width / 2
        centre = _fit_along(
            desired,
            adj.lo + _JAMB,
            adj.hi - _JAMB,
            width,
            obstacles.for_wall(not adj.vertical, adj.coord),
        )
        if centre is None:
            continue
        prefer_lo = centre <= (adj.lo + adj.hi) / 2
        door = _make_door(room, adj.vertical, adj.coord, centre, width, iwt, prefer_lo)
        obstacles.add(door)
        openings.append(door)
        doored_gaps.add((min(adj.a, adj.b), max(adj.a, adj.b)))
        return True
    # exterior fallback: an entrance door on the plot boundary — ground floor
    # only (upper floors have no street access; "outside" is not a corridor)
    if floor != 0:
        return False
    plate = _plate_bounds(rooms, buildable, ewt)
    for is_h, coord, lo, hi in _all_exterior_edges(room, walls, plate, ewt, tol):
        if hi - lo < width + 2 * _JAMB:
            continue
        centre = _fit_along(
            (lo + hi) / 2,
            lo + _JAMB,
            hi - _JAMB,
            width,
            obstacles.for_wall(is_h, coord),
        )
        if centre is None:
            continue
        door = _make_door(room, not is_h, coord, centre, width, ewt, True)
        obstacles.add(door)
        openings.append(door)
        return True
    return False


def opening_boxes(openings: list[Opening]) -> list[Polygon]:
    """Shapely cut-boxes for wall_polygons(); slightly over-deep across the
    wall so the subtraction cleanly pierces both faces."""
    boxes: list[Polygon] = []
    for o in openings:
        across = o.wall_thickness / 2 + 0.01
        along = o.width / 2
        if o.is_horizontal:
            boxes.append(box(o.cx - along, o.cy - across, o.cx + along, o.cy + across))
        else:
            boxes.append(box(o.cx - across, o.cy - along, o.cx + across, o.cy + along))
    return boxes


# ---------------------------------------------------------------------------
# Dimensions, labels, stair, assembly (S4.3)
# ---------------------------------------------------------------------------

_LANES = (0.6, 1.2, 1.8)  # cross-axis offsets for levels 0/1/2
_OVERALL_LANE = 2.4  # overall (level-1) chain sits outside the plot chain
_PT_TO_MODEL_M = 0.000352778 * 100  # 1 pt on paper at 1:100 -> metres in model
_LABEL_MARGIN = 0.2
_LABEL_FONT = "Helvetica-Bold"


def derive_dim_chains(
    rooms: list[Room], walls: list[WallSegment], cfg: PlotConfig
) -> list[DimChain]:
    from app.engine.geometry import buildable_polygon

    bx1, by1, bx2, by2 = buildable_polygon(cfg).bounds
    chains: list[DimChain] = []

    def entries_for(coords: list[float], min_seg: float = 0.0) -> list[DimChainEntry]:
        kept: list[float] = []
        for cvalue in coords:
            if kept and cvalue - kept[-1] < min_seg:
                continue
            kept.append(cvalue)
        if kept and kept[-1] != coords[-1]:
            kept[-1] = coords[-1]
        out = []
        for a, b in zip(kept, kept[1:]):
            if b - a < 1e-6:
                continue
            out.append(DimChainEntry(start=a, end=b, text=metres_to_ftin(b - a)))
        return out

    # Level 0 — room chains (bottom: vertical wall xs; left: horizontal ys)
    v_xs = sorted(
        {round(w.x1, 6) for w in walls if w.kind == "internal" and _is_vertical(w)}
        | {bx1, bx2}
    )
    h_ys = sorted(
        {round(w.y1, 6) for w in walls if w.kind == "internal" and not _is_vertical(w)}
        | {by1, by2}
    )
    chains.append(
        DimChain(
            side="bottom",
            level=0,
            coord=by1 - _LANES[0],
            entries=entries_for(v_xs, min_seg=0.3),
        )
    )
    chains.append(
        DimChain(
            side="left",
            level=0,
            coord=bx1 - _LANES[0],
            entries=entries_for(h_ys, min_seg=0.3),
        )
    )

    # Level 2 — plot chain incl. setbacks. Setback segments are quoted in
    # metres (municipal rules are metric); the building span stays ft-in.
    for side, coord, coords, (blo, bhi) in (
        ("bottom", by1 - _LANES[2], [0.0, bx1, bx2, cfg.plot_width], (bx1, bx2)),
        ("top", by2 + _LANES[2], [0.0, bx1, bx2, cfg.plot_width], (bx1, bx2)),
        ("left", bx1 - _LANES[2], [0.0, by1, by2, cfg.plot_length], (by1, by2)),
        ("right", bx2 + _LANES[2], [0.0, by1, by2, cfg.plot_length], (by1, by2)),
    ):
        entries = entries_for(coords)
        for e in entries:
            if e.end <= blo + 1e-6 or e.start >= bhi - 1e-6:
                e.text = f"{e.end - e.start:.1f}M"
        chains.append(DimChain(side=side, level=2, coord=coord, entries=entries))

    # Level 1 — overall plot extent, dual-unit (ft-in + metres), outermost lane
    for side, coord, extent in (
        ("top", by2 + _OVERALL_LANE, cfg.plot_width),
        ("right", bx2 + _OVERALL_LANE, cfg.plot_length),
    ):
        chains.append(
            DimChain(
                side=side,
                level=1,
                coord=coord,
                entries=[
                    DimChainEntry(
                        start=0.0,
                        end=extent,
                        text=f"{metres_to_ftin(extent)} ({extent:.1f} m)",
                    )
                ],
            )
        )
    return chains


def setback_callouts(
    cfg: PlotConfig, bounds: tuple[float, float, float, float]
) -> list[tuple[str, float, float, bool]]:
    """(text, x, y, rotated) callouts centred inside each setback strip,
    e.g. "1.5M FRONT SETBACK" — the municipal-drawing convention. Front is
    the -y edge (see geometry._edge_setback); left/right read rotated 90°."""
    bx1, by1, bx2, by2 = bounds
    mx, my = (bx1 + bx2) / 2, (by1 + by2) / 2
    out: list[tuple[str, float, float, bool]] = []
    if cfg.setback_front > 0.05:
        out.append((f"{cfg.setback_front:.1f}M FRONT SETBACK", mx, by1 / 2, False))
    if cfg.setback_rear > 0.05:
        out.append(
            (
                f"{cfg.setback_rear:.1f}M REAR SETBACK",
                mx,
                (by2 + cfg.plot_length) / 2,
                False,
            )
        )
    if cfg.setback_left > 0.05:
        out.append((f"{cfg.setback_left:.1f}M LEFT SETBACK", bx1 / 2, my, True))
    if cfg.setback_right > 0.05:
        out.append(
            (
                f"{cfg.setback_right:.1f}M RIGHT SETBACK",
                (bx2 + cfg.plot_width) / 2,
                my,
                True,
            )
        )
    return out


def _text_width_m(text: str, font_pt: float) -> float:
    from reportlab.pdfbase import pdfmetrics

    return pdfmetrics.stringWidth(text, _LABEL_FONT, font_pt) * _PT_TO_MODEL_M


def _lines_fit(
    lines: list[str], font_pt: float, avail_w: float, avail_h: float
) -> bool:
    if any(_text_width_m(t, font_pt) > avail_w for t in lines):
        return False
    return len(lines) * font_pt * 1.3 * _PT_TO_MODEL_M <= avail_h


def _room_label_lines(room) -> list[str]:
    """Dual-unit label (ft-in + metric), matching Indian working-drawing
    convention: NAME / 11'-10" × 25'-4" / (3.6 m × 7.7 m) / 299 SQFT."""
    # Occupied area (the part union), not the bounding box: an L/T/U room
    # would otherwise print the SQFT of a rectangle it does not fill.
    # Identical to width * depth for a RECT room.
    area_sqft = round(sum(p.area for p in room.rects) * 10.7639)
    return [
        room.name.upper(),
        f"{metres_to_ftin(room.width)} × {metres_to_ftin(room.depth)}",
        f"({room.width:.1f} m × {room.depth:.1f} m)",
        f"{area_sqft} SQFT",
    ]


def derive_labels(
    rooms: list[Room], bounds: tuple[float, float, float, float] | None = None
) -> list[LabelBox]:
    labels: list[LabelBox] = []
    outside_count = 0
    for room in sorted(rooms, key=lambda r: r.id):
        lines = _room_label_lines(room)
        lines3 = [lines[0], lines[1], lines[3]]  # drop the metric line first
        avail_w = room.width - _LABEL_MARGIN
        avail_h = room.depth - _LABEL_MARGIN
        cx = room.x + room.width / 2
        cy = (
            room.y + room.depth * 2 / 3
            if room.type == "staircase"
            else room.y + room.depth / 2
        )
        chosen: tuple[list[str], float] | None = None
        for cand, fonts in (
            (lines, (12.0, 11.0, 10.0, 9.0, 8.0)),
            (lines3, (12.0, 11.0, 10.0, 9.0, 8.0)),
            (lines[:2], (8.0, 7.0, 6.0)),
            ([lines[0]], (7.0, 6.0)),
        ):
            for f in fonts:
                if _lines_fit(cand, f, avail_w, avail_h):
                    chosen = (cand, f)
                    break
            if chosen:
                break
        if chosen is None and room.depth > room.width:
            # slim vertical room: retry the ladder rotated 90 degrees
            # (metric line skipped — rotated labels are width-starved)
            for cand, fonts in (
                (lines3, (9.0, 8.0)),
                (lines[:2], (8.0, 7.0, 6.0)),
                ([lines[0]], (7.0, 6.0)),
            ):
                for f in fonts:
                    if _lines_fit(cand, f, avail_h, avail_w):
                        chosen = (cand, f)
                        break
                if chosen:
                    break
            if chosen:
                labels.append(
                    LabelBox(
                        room_id=room.id,
                        cx=cx,
                        cy=cy,
                        lines=chosen[0],
                        font_pt=chosen[1],
                        rotated=True,
                    )
                )
                continue
        if chosen:
            labels.append(
                LabelBox(
                    room_id=room.id, cx=cx, cy=cy, lines=chosen[0], font_pt=chosen[1]
                )
            )
        else:
            # stacked slots above the building, clear of the dim lanes
            if bounds is not None:
                bx1, _by1, _bx2, by2 = bounds
                slot_x = bx1 + 1.2 + 3.0 * (outside_count % 2)
                slot_y = by2 + 2.6 + 0.7 * (outside_count // 2)
            else:
                slot_x = room.x + room.width + 0.6
                slot_y = room.y + room.depth / 2
            outside_count += 1
            labels.append(
                LabelBox(
                    room_id=room.id,
                    cx=slot_x,
                    cy=slot_y,
                    lines=lines3,
                    font_pt=7.0,
                    leader=(cx, room.y + room.depth / 2),
                )
            )
    return labels


def derive_stair(rooms: list[Room], floor_height: float = 3.0) -> StairGeometry | None:
    room = next((r for r in rooms if r.type == "staircase"), None)
    if room is None:
        return None
    vertical_run = room.depth >= room.width
    riser = 0.175
    needed = math.ceil((floor_height / 2) / riser)
    run_len = room.depth if vertical_run else room.width
    max_treads = int((run_len - 1.0) / 0.25)
    count = max(0, min(needed, max_treads))

    treads: list[tuple[float, float, float, float]] = []
    for i in range(1, count + 1):
        if vertical_run:
            y = room.y + i * 0.25
            treads.append((room.x, y, room.x + room.width, y))
        else:
            x = room.x + i * 0.25
            treads.append((x, room.y, x, room.y + room.depth))

    flight = count * 0.25
    if vertical_run:
        b = room.y + flight * 0.6
        break_line = (room.x, b - 0.15, room.x + room.width, b + 0.15)
        cx = room.x + room.width / 2
        arrow = (cx, room.y + 0.15, cx, room.y + max(flight - 0.1, 0.3))
        up_xy = (cx, room.y + 0.3)
    else:
        b = room.x + flight * 0.6
        break_line = (b - 0.15, room.y, b + 0.15, room.y + room.depth)
        cy = room.y + room.depth / 2
        arrow = (room.x + 0.15, cy, room.x + max(flight - 0.1, 0.3), cy)
        up_xy = (room.x + 0.3, cy)
    return StairGeometry(
        room_id=room.id,
        treads=treads,
        break_line=break_line,
        arrow=arrow,
        up_label_xy=up_xy,
        tread_count=count,
    )


def build_floor_drawing(floorplan: FloorPlan, cfg: PlotConfig) -> FloorDrawing:
    from app.engine.geometry import buildable_polygon
    from app.engine.standards import get_opening_standards

    buildable = buildable_polygon(cfg)
    rooms = floorplan.rooms
    walls = derive_walls(rooms, buildable)
    junctions = derive_junctions(walls)
    columns = derive_columns(walls, junctions=junctions, rooms=rooms)
    diagnostics: list[str] = []
    bx1, by1, bx2, by2 = buildable.bounds
    oob = [
        r.id
        for r in rooms
        if r.x < bx1 - 0.05
        or r.y < by1 - 0.05
        or r.x + r.width > bx2 + 0.05
        or r.y + r.depth > by2 + 0.05
    ]
    if oob:
        diagnostics.append(
            "geometry: rooms outside buildable bounds: "
            + ", ".join(oob)
            + " (plot_width is the x-extent/frontage, plot_length the y-extent/depth — swapped?)"
        )
    status: dict = {}
    openings = derive_openings(
        rooms,
        walls,
        columns,
        get_opening_standards(),
        buildable,
        floor=floorplan.floor,
        reasons=diagnostics,
        status=status,
        vastu_cfg=cfg,
    )
    for d in diagnostics:
        logger.warning("floor %s: %s", floorplan.floor, d)
    walls.sort(key=lambda w: (w.kind, w.x1, w.y1, w.x2, w.y2))
    openings.sort(key=lambda o: (o.kind, o.cx, o.cy))
    columns.sort(key=lambda c: (c.cx, c.cy))
    junctions.sort(key=lambda j: (j.x, j.y))
    return FloorDrawing(
        floor=floorplan.floor,
        walls=walls,
        openings=openings,
        columns=columns,
        junctions=junctions,
        dim_chains=derive_dim_chains(rooms, walls, cfg),
        labels=derive_labels(rooms, bounds=buildable.bounds),
        stair=derive_stair(rooms),
        bounds=buildable.bounds,
        diagnostics=diagnostics,
        entrance_not_on_ground_floor=status.get("entrance_not_on_ground_floor", False),
    )
