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

from app.engine.cad_elements import ColumnMarker, WallJunction, WallSegment

EWT = 0.23
IWT = 0.115
_SNAP = 0.25  # max end-extension to meet a perpendicular centreline
_MIN_WALL_LEN = 0.10


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
