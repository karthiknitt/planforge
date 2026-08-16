import pytest

from app.engine.areas import carpet_area, validate_voids
from app.engine.models import FloorPlan, Room


def test_void_is_excluded_from_carpet_area():
    living = Room(id="lv", name="Living", type="living", x=0, y=0, width=5, depth=4)
    gf = FloorPlan(floor=0, floor_type="ground", rooms=[living])
    void = Room(
        id="v",
        name="Open to Below",
        type="open_to_sky",
        x=0,
        y=0,
        width=5,
        depth=4,
        void_over="lv",
    )
    ff = FloorPlan(floor=1, floor_type="first", rooms=[void])
    assert carpet_area(gf) == 20.0
    assert carpet_area(ff) == 0.0


def test_void_must_reference_a_room_on_the_floor_below():
    void = Room(
        id="v",
        name="Open to Below",
        type="open_to_sky",
        x=0,
        y=0,
        width=5,
        depth=4,
        void_over="nonexistent",
    )
    ff = FloorPlan(floor=1, floor_type="first", rooms=[void])
    gf = FloorPlan(floor=0, floor_type="ground", rooms=[])
    with pytest.raises(ValueError, match="void_over"):
        validate_voids(below=gf, above=ff)


def test_void_must_lie_within_the_room_it_opens_onto():
    living = Room(id="lv", name="Living", type="living", x=0, y=0, width=5, depth=4)
    gf = FloorPlan(floor=0, floor_type="ground", rooms=[living])
    void = Room(
        id="v",
        name="Open to Below",
        type="open_to_sky",
        x=8,
        y=8,
        width=2,
        depth=2,
        void_over="lv",
    )
    ff = FloorPlan(floor=1, floor_type="first", rooms=[void])
    with pytest.raises(ValueError, match="not contained"):
        validate_voids(below=gf, above=ff)


def test_void_bbox_fits_but_shape_parts_do_not_must_raise():
    """Regression for a bbox-only containment check.

    Host is L-shaped (ratio 0.5 on a 6x6 bbox): it covers the full-width
    bottom half (y 0-3) plus only the left half of the top (x 0-3, y 3-6) —
    the top-right quadrant (x 3-6, y 3-6) is NOT part of the host's footprint.

    The void is also L-shaped, with a bbox (x 2-5, y 2-5) that sits entirely
    inside the host's bbox (x 0-6, y 0-6) — a bbox-only check would pass this.
    But the void's base band spans x 2-5 for y in [3, 3.5], which pokes into
    the host's uncovered top-right quadrant (x > 3, y > 3) — the real part
    union is NOT contained in the host's real footprint.
    """
    host = Room(
        id="lv",
        name="Living",
        type="living",
        x=0,
        y=0,
        width=6,
        depth=6,
        template="L",
        shape_ratio=0.5,
    )
    gf = FloorPlan(floor=0, floor_type="ground", rooms=[host])
    void = Room(
        id="v",
        name="Open to Below",
        type="open_to_sky",
        x=2,
        y=2,
        width=3,
        depth=3,
        template="L",
        shape_ratio=0.5,
        void_over="lv",
    )
    ff = FloorPlan(floor=1, floor_type="first", rooms=[void])
    with pytest.raises(ValueError, match="not contained"):
        validate_voids(below=gf, above=ff)


def test_normal_rooms_are_unaffected():
    bed = Room(id="b", name="Bed", type="bedroom", x=0, y=0, width=4, depth=3)
    ff = FloorPlan(floor=1, floor_type="first", rooms=[bed])
    assert bed.void_over is None
    assert carpet_area(ff) == 12.0
