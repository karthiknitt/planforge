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

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from app.engine.cad_elements import (
    ColumnMarker,
    Opening,
    WallJunction,
    WallSegment,
)
from app.engine.standards import OpeningStandards

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


def _room_edges(rooms) -> tuple[list[_Edge], list[_Edge]]:
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
    rooms,
    buildable: Polygon,
    ewt: float = EWT,
    iwt: float = IWT,
    tol: float = 0.01,
) -> list[WallSegment]:
    bx1, by1, bx2, by2 = buildable.bounds
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


def derive_columns(walls: list[WallSegment], tol: float = 0.01) -> list[ColumnMarker]:
    return [ColumnMarker(cx=j.x, cy=j.y) for j in derive_junctions(walls, tol=tol)]


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


def _adjacencies(rooms, iwt: float, tol: float) -> list[_Adjacency]:
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


def derive_openings(
    rooms,
    walls: list[WallSegment],
    columns: list[ColumnMarker],
    std: OpeningStandards,
    buildable: Polygon,
    ewt: float = EWT,
    iwt: float = IWT,
    tol: float = 0.01,
) -> list[Opening]:
    adjs = _adjacencies(rooms, iwt, tol)
    obstacles = _ObstacleIndex(columns)
    openings: list[Opening] = []

    def place(opening: Opening | None) -> bool:
        if opening is None:
            return False
        obstacles.add(opening)
        openings.append(opening)
        return True

    # ── Doors: one per non-passage room ──────────────────────────────────
    for idx, room in sorted(enumerate(rooms), key=lambda t: t[1].id):
        if room.type == "passage":
            continue
        width = _WET_DOOR if room.type in _WET_TYPES else std.door_width_m
        cands = []
        for adj in adjs:
            if idx not in (adj.a, adj.b):
                continue
            if adj.hi - adj.lo < width + 2 * _JAMB:
                continue
            other = rooms[adj.b if adj.a == idx else adj.a]
            prio = _DOOR_NEIGHBOUR_PRIORITY.get(other.type, 4)
            cands.append((prio, other.id, adj))
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
