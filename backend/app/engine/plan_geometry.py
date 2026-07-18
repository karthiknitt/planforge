"""Canonical drawing-geometry derivation — single source of truth for renderers.

Room-layout convention (see archetypes._inscribed_plate): room rects are CLEAR
interior spaces. Adjacent rooms are separated by an iwt-wide gap and the plate
is inset ewt from the buildable ring. Walls therefore live in the gaps:

- paired internal walls: centreline at the midpoint of the gap between two
  facing room edges
- external ring: centreline at buildable boundary − ewt/2 (outer face flush
  with the buildable polygon)
- orphan walls: room edges facing unassigned space get an iwt wall hugging
  the edge (centreline iwt/2 outside the room)

All outputs are axis-aligned centreline segments, normalized so
(x1, y1) <= (x2, y2).
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from shapely.geometry import Polygon, box
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
}
_DOOR_NEIGHBOUR_PRIORITY = {"passage": 0, "living": 1, "dining": 2, "staircase": 3}
_ENTRY_PRIORITY = {"living": 0, "passage": 1, "dining": 2}
_NO_ENTRY_TYPES = _WET_TYPES | {"parking", "staircase"}


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


def _room_edges(rooms: list[Room]) -> tuple[list[_Edge], list[_Edge]]:
    vert: list[_Edge] = []
    hor: list[_Edge] = []
    for r in rooms:
        vert.append(_Edge(r.x, r.y, r.y + r.depth, -1))
        vert.append(_Edge(r.x + r.width, r.y, r.y + r.depth, +1))
        hor.append(_Edge(r.y, r.x, r.x + r.width, -1))
        hor.append(_Edge(r.y + r.depth, r.x, r.x + r.width, +1))
    return vert, hor


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


def derive_walls(
    rooms: list[Room],
    buildable: Polygon,
    ewt: float = EWT,
    iwt: float = IWT,
    tol: float = 0.01,
) -> list[WallSegment]:
    bx1, by1, bx2, by2 = buildable.bounds
    if abs(buildable.area - (bx2 - bx1) * (by2 - by1)) > 1e-6:
        logger.warning(
            "non-rectangular buildable polygon: external ring approximated "
            "by its bounding box (trapezoid/L/quad support pending)"
        )
    cxl, cxr = bx1 + ewt / 2, bx2 - ewt / 2
    cyb, cyt = by1 + ewt / 2, by2 - ewt / 2
    px1, py1, px2, py2 = bx1 + ewt, by1 + ewt, bx2 - ewt, by2 - ewt  # plate

    walls: list[WallSegment] = [
        WallSegment(cxl, cyb, cxr, cyb, ewt, kind="external"),
        WallSegment(cxl, cyt, cxr, cyt, ewt, kind="external"),
        WallSegment(cxl, cyb, cxl, cyt, ewt, kind="external"),
        WallSegment(cxr, cyb, cxr, cyt, ewt, kind="external"),
    ]

    vert_edges, hor_edges = _room_edges(rooms)

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

    # Orphan walls: uncovered edge stretches get an iwt wall hugging the edge.
    for e in vert_edges:
        for lo, hi in _subtract_intervals((e.lo, e.hi), e.covered):
            if hi - lo < _MIN_WALL_LEN:
                continue
            mid = e.coord + e.normal * iwt / 2
            grouped.setdefault(("v", round(mid, 6)), []).append((lo, hi))
    for e in hor_edges:
        for lo, hi in _subtract_intervals((e.lo, e.hi), e.covered):
            if hi - lo < _MIN_WALL_LEN:
                continue
            mid = e.coord + e.normal * iwt / 2
            grouped.setdefault(("h", round(mid, 6)), []).append((lo, hi))

    for (orient, coord), intervals in sorted(grouped.items()):
        for lo, hi in _merge_intervals(intervals, tol):
            if orient == "v":
                walls.append(WallSegment(coord, lo, coord, hi, iwt, kind="internal"))
            else:
                walls.append(WallSegment(lo, coord, hi, coord, iwt, kind="internal"))

    _snap_ends(walls)
    return walls


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

    return _merge_adjacent_columns(kept)


_COLUMN_MERGE_TOL = 0.3  # m — junctions closer than this are one physical column


def _merge_adjacent_columns(kept: list[WallJunction]) -> list[ColumnMarker]:
    """Collapse junction clusters into single columns.

    Mixed wall conventions (zero-gap room tiling vs iwt gaps, orphan walls
    hugging a face at ±iwt/2) can put two junctions half a wall thickness
    apart; drawing a column on each reads as a detailing error ("twin
    columns") and skews structural grid extraction. Anything under one
    column width apart is a single physical column — keep the
    highest-degree junction of each cluster (best beam anchoring).
    """
    remaining = sorted(kept, key=lambda j: (-j.degree, j.x, j.y))
    merged: list[WallJunction] = []
    for j in remaining:
        if any(
            (j.x - m.x) ** 2 + (j.y - m.y) ** 2 < _COLUMN_MERGE_TOL**2 for m in merged
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
    out: list[_Adjacency] = []
    for i, ra in enumerate(rooms):
        for j, rb in enumerate(rooms):
            if i == j:
                continue
            # ra's right edge facing rb's left edge
            gap = rb.x - (ra.x + ra.width)
            if -tol <= gap <= iwt + tol:
                lo = max(ra.y, rb.y)
                hi = min(ra.y + ra.depth, rb.y + rb.depth)
                if hi - lo >= 0.05:
                    out.append(
                        _Adjacency(i, j, True, (ra.x + ra.width + rb.x) / 2, lo, hi)
                    )
            # ra's top edge facing rb's bottom edge
            gap = rb.y - (ra.y + ra.depth)
            if -tol <= gap <= iwt + tol:
                lo = max(ra.x, rb.x)
                hi = min(ra.x + ra.width, rb.x + rb.width)
                if hi - lo >= 0.05:
                    out.append(
                        _Adjacency(i, j, False, (ra.y + ra.depth + rb.y) / 2, lo, hi)
                    )
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


def _exterior_edges(room, buildable: Polygon, ewt: float, tol: float):
    """Yield (is_horizontal, ring_coord, lo, hi) for room edges on the plate boundary."""
    bx1, by1, bx2, by2 = buildable.bounds
    px1, py1, px2, py2 = bx1 + ewt, by1 + ewt, bx2 - ewt, by2 - ewt
    if abs(room.x - px1) <= 2 * tol:
        yield (False, bx1 + ewt / 2, room.y, room.y + room.depth)
    if abs(room.x + room.width - px2) <= 2 * tol:
        yield (False, bx2 - ewt / 2, room.y, room.y + room.depth)
    if abs(room.y - py1) <= 2 * tol:
        yield (True, by1 + ewt / 2, room.x, room.x + room.width)
    if abs(room.y + room.depth - py2) <= 2 * tol:
        yield (True, by2 - ewt / 2, room.x, room.x + room.width)


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


def _place_main_entrance(
    rooms: list[Room],
    obstacles: _ObstacleIndex,
    std: OpeningStandards,
    buildable: Polygon,
    ewt: float,
    tol: float,
) -> Opening | None:
    """Main entrance door (MD) in the road-facing external wall.

    The road is always the y-min edge (archetypes/vastu convention: y=0 is
    the road/front edge). Entry room preference follows Indian practice:
    living > passage > dining; never parking, stairs or wet rooms. The
    desired position is the facade midpoint so the door lines up with the
    compound-wall gate (cad_advanced centres the gate on the road side).
    """
    bx1, by1, bx2, _by2 = buildable.bounds
    py1 = by1 + ewt  # front plate boundary
    coord = by1 + ewt / 2  # front external-wall centreline
    width = std.main_door_width_m
    gate_x = (bx1 + bx2) / 2
    cands = []
    for room in rooms:
        if room.type in _NO_ENTRY_TYPES:
            continue
        if abs(room.y - py1) > 2 * tol:
            continue
        lo, hi = room.x, room.x + room.width
        if hi - lo < width + 2 * _JAMB:
            continue
        prio = _ENTRY_PRIORITY.get(room.type, 3)
        cands.append((prio, abs((lo + hi) / 2 - gate_x), room.id, room, lo, hi))
    for _prio, _dist, _rid, room, lo, hi in sorted(cands, key=lambda t: t[:3]):
        centre = _fit_along(
            gate_x, lo + _JAMB, hi - _JAMB, width, obstacles.for_wall(True, coord)
        )
        if centre is None:
            continue
        door = _make_door(
            room, False, coord, centre, width, ewt, centre <= (lo + hi) / 2
        )
        door.is_main = True
        return door
    logger.warning("no suitable road-facing room for a main entrance door")
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
) -> list[Opening]:
    adjs = _adjacencies(rooms, iwt, tol)
    obstacles = _ObstacleIndex(columns)
    openings: list[Opening] = []
    doored_gaps: set[tuple[int, int]] = set()  # room-index pairs already connected

    def place(opening: Opening | None) -> bool:
        if opening is None:
            return False
        obstacles.add(opening)
        openings.append(opening)
        return True

    # ── Main entrance first, so it claims front-wall space before windows ─
    if floor == 0:
        place(_place_main_entrance(rooms, obstacles, std, buildable, ewt, tol))

    # ── Doors: one per non-passage room; a door in a shared wall serves
    # BOTH rooms, so a room whose gap already carries a door is done ──────
    for idx, room in sorted(enumerate(rooms), key=lambda t: t[1].id):
        if room.type == "passage":
            continue
        width = _WET_DOOR if room.type in _WET_TYPES else std.door_width_m
        cands = []
        already_served = False
        for adj in adjs:
            if idx not in (adj.a, adj.b):
                continue
            other = rooms[adj.b if adj.a == idx else adj.a]
            gap_key = (min(adj.a, adj.b), max(adj.a, adj.b))
            # a shared door serves this room too — unless it leads through
            # a wet room (a bedroom must not be reachable only via a toilet)
            if gap_key in doored_gaps and other.type not in _WET_TYPES:
                already_served = True
                break
            if adj.hi - adj.lo < width + 2 * _JAMB:
                continue
            prio = _DOOR_NEIGHBOUR_PRIORITY.get(other.type, 4)
            cands.append((prio, other.id, adj))
        if already_served:
            continue
        placed = False
        for _prio, _oid, adj in sorted(cands, key=lambda t: (t[0], t[1])):
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
                _make_door(room, adj.vertical, adj.coord, centre, width, iwt, prefer_lo)
            )
            if placed:
                doored_gaps.add((min(adj.a, adj.b), max(adj.a, adj.b)))
                break
        if not placed:
            # entrance door on an exterior edge (e.g. parking, or isolated room)
            for is_h, coord, lo, hi in _exterior_edges(room, buildable, ewt, tol):
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
            _exterior_edges(room, buildable, ewt, tol),
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
        for is_h, coord, lo, hi in _exterior_edges(room, buildable, ewt, tol):
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
    return openings


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
    area_sqft = round(room.width * room.depth * 10.7639)
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
    columns = derive_columns(walls, junctions=junctions)
    openings = derive_openings(
        rooms,
        walls,
        columns,
        get_opening_standards(),
        buildable,
        floor=floorplan.floor,
    )
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
    )
