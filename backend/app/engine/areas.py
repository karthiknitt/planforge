"""Area accounting that understands voids.

A void (`Room.is_void`) is a hole in the floor slab — a double-height living
area or courtyard opening onto a room on the floor below. It has no slab, so
it contributes no carpet area, and its footprint must lie entirely within the
room it opens onto.
"""

from __future__ import annotations

from shapely.geometry import box
from shapely.ops import unary_union

from app.engine.models import FloorPlan, Room

_TOL = 0.01


def carpet_area(floor: FloorPlan) -> float:
    """Sum of room areas on a floor, excluding voids (holes have no floor)."""
    return round(sum(r.area for r in floor.rooms if not r.is_void), 2)


def _room_polygon(room: Room):
    """The room's occupied area — the union of its shape-template parts.

    Mirrors `plan_geometry._room_polygon`: containment must be checked over
    the actual part union, not the bounding box, or an L/T/U-templated void
    could poke outside an equally-shaped host while still passing a bbox
    check.
    """
    return unary_union(
        [box(p.x, p.y, p.x + p.width, p.y + p.depth) for p in room.rects]
    )


def validate_voids(below: FloorPlan, above: FloorPlan) -> None:
    """Every void on `above` must sit inside a real room on `below`."""
    by_id = {r.id: r for r in below.rooms}
    for v in above.rooms:
        if not v.is_void:
            continue
        host = by_id.get(v.void_over)
        if host is None:
            raise ValueError(
                f"room {v.id!r} has void_over={v.void_over!r} but no such room "
                f"exists on floor {below.floor}"
            )
        host_poly = _room_polygon(host).buffer(_TOL, join_style=2)
        void_poly = _room_polygon(v)
        if not host_poly.contains(void_poly):
            raise ValueError(
                f"void {v.id!r} is not contained in its host room {host.id!r}"
            )
