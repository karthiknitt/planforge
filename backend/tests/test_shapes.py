"""Rect-union shape templates for rooms (L / T / U footprints)."""

import pytest
from app.engine.models import Room
from app.engine.shapes import Rect, parts_for, union_bbox


def test_rect_template_is_a_single_part():
    parts = parts_for(0.0, 0.0, 4.0, 3.0, "RECT")
    assert parts == (Rect(0.0, 0.0, 4.0, 3.0),)


def test_l_template_has_two_parts_and_preserves_bbox():
    parts = parts_for(0.0, 0.0, 10.0, 10.0, "L", ratio=0.6)
    assert len(parts) == 2
    assert union_bbox(parts) == (0.0, 0.0, 10.0, 10.0)


def test_l_template_parts_do_not_overlap():
    parts = parts_for(0.0, 0.0, 10.0, 10.0, "L", ratio=0.6)
    a, b = parts
    ox = max(0.0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
    oy = max(0.0, min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y))
    assert ox * oy == 0.0, "L parts must tile, not overlap"


def test_l_template_area_is_less_than_its_bbox():
    """The whole point: an L covers less than its bounding rectangle."""
    parts = parts_for(0.0, 0.0, 10.0, 10.0, "L", ratio=0.6)
    assert sum(p.area for p in parts) < 100.0


def test_t_and_u_templates_are_contiguous():
    for tmpl, n in (("T", 2), ("U", 3)):
        parts = parts_for(0.0, 0.0, 12.0, 9.0, tmpl)
        assert len(parts) == n
        assert union_bbox(parts) == (0.0, 0.0, 12.0, 9.0)


def test_t_and_u_parts_are_pairwise_disjoint():
    """A part union must never double-count area."""
    for tmpl in ("T", "U"):
        parts = parts_for(0.0, 0.0, 12.0, 9.0, tmpl)
        for i, a in enumerate(parts):
            for b in parts[i + 1 :]:
                ox = max(0.0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
                oy = max(0.0, min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y))
                assert ox * oy == 0.0, f"{tmpl} parts overlap: {a} vs {b}"


def test_u_template_leaves_a_central_notch():
    """A U is not just a T mirrored — it must have a gap between its legs."""
    parts = parts_for(0.0, 0.0, 12.0, 9.0, "U", ratio=0.6)
    assert sum(p.area for p in parts) < 12.0 * 9.0
    _base, left, right = parts
    assert left.x + left.width < right.x, "U legs must not meet"


def test_room_rects_defaults_to_one_rectangle():
    """Regression: an untemplated room behaves exactly as before."""
    r = Room(id="r", name="R", type="living", x=1.0, y=2.0, width=4.0, depth=3.0)
    assert r.template == "RECT"
    assert r.rects == (Rect(1.0, 2.0, 4.0, 3.0),)


def test_room_rects_follows_the_template():
    r = Room(
        id="r",
        name="R",
        type="living",
        x=1.0,
        y=2.0,
        width=10.0,
        depth=10.0,
        template="L",
    )
    assert len(r.rects) == 2
    assert union_bbox(r.rects) == (1.0, 2.0, 11.0, 12.0)


def test_room_area_is_the_part_union_not_the_bbox():
    r = Room(
        id="r",
        name="R",
        type="living",
        x=0.0,
        y=0.0,
        width=10.0,
        depth=10.0,
        template="L",
    )
    assert r.area < 100.0
    assert r.area == pytest.approx(sum(p.area for p in r.rects), abs=0.01)


def test_rect_room_area_is_unchanged_by_the_union():
    """Load-bearing: RECT rooms keep exactly their old width*depth area."""
    r = Room(id="r", name="R", type="living", x=1.0, y=2.0, width=3.7, depth=4.3)
    assert r.area == round(3.7 * 4.3, 2)


@pytest.mark.parametrize(
    ("width", "depth"),
    [
        (14.946, 13.796),
        (8.463, 5.527),
        (11.337, 0.632),
        (13.0, 8.595),
        (7.846, 1.409),
    ],
)
def test_rect_area_never_shifts_by_double_rounding(width: float, depth: float):
    """Rect.area must not pre-round: round(round(w*d, 4), 2) != round(w*d, 2)
    for ~0.5% of dimensions, which would silently move every RECT room's
    reported area by 1 cm2 versus the pre-template behaviour."""
    r = Room(id="r", name="R", type="living", x=0.0, y=0.0, width=width, depth=depth)
    assert r.area == round(width * depth, 2)


def test_ratio_out_of_range_is_rejected():
    with pytest.raises(ValueError, match="ratio"):
        parts_for(0.0, 0.0, 10.0, 10.0, "L", ratio=1.4)


def test_unknown_template_is_rejected():
    with pytest.raises(ValueError, match="template"):
        parts_for(0.0, 0.0, 10.0, 10.0, "Z")  # type: ignore[arg-type]


def test_room_rejects_a_bad_template_at_construction():
    with pytest.raises(ValueError, match="template"):
        Room(
            id="r",
            name="R",
            type="living",
            x=0.0,
            y=0.0,
            width=4.0,
            depth=3.0,
            template="Z",  # type: ignore[arg-type]
        )


def test_room_rejects_a_bad_shape_ratio_at_construction():
    with pytest.raises(ValueError, match="ratio"):
        Room(
            id="r",
            name="R",
            type="living",
            x=0.0,
            y=0.0,
            width=4.0,
            depth=3.0,
            template="L",
            shape_ratio=0.05,
        )


def test_net_area_subtracts_a_carved_child_part_union_not_its_bbox():
    """An L-shaped carve must not over-subtract its bounding box."""
    parent = Room(
        id="p", name="Bed", type="bedroom", x=0.0, y=0.0, width=10.0, depth=10.0
    )
    child = Room(
        id="c",
        name="Toilet",
        type="toilet",
        x=1.0,
        y=1.0,
        width=6.0,
        depth=6.0,
        template="L",
        shape_ratio=0.5,
        parent_id="p",
    )
    assert child.area == pytest.approx(27.0, abs=0.01)  # not 36.0
    assert parent.net_area([child]) == pytest.approx(73.0, abs=0.01)
