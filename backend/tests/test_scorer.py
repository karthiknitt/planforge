"""Tests for the layout quality scorer."""

from app.engine.models import (
    ComplianceResult,
    FloorPlan,
    Layout,
    PlotConfig,
    Room,
)
from app.engine.compliance import load_rules
from app.engine.scorer import (
    _WEIGHTS,
    _score_adjacency,
    _score_aspect_ratio,
    _score_toilet_placement,
    _shares_wall,
    rank_and_select,
    score_layout,
)

_EWT = load_rules()["external_wall_thickness_mm"] / 1000


def _make_room(id, type, x, y, w, d, name=None):
    return Room(id=id, name=name or type.title(), type=type, x=x, y=y, width=w, depth=d)


def _make_layout(gf_rooms, ff_rooms=None, id="X"):
    gf = FloorPlan(floor=0, floor_type="ground", rooms=gf_rooms)
    ff = FloorPlan(floor=1, floor_type="first", rooms=ff_rooms or [])
    return Layout(
        id=id,
        name=f"Layout {id}",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )


def _basic_cfg():
    return PlotConfig(
        plot_y_extent=12.0,
        plot_x_extent=9.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=0.9,
        setback_right=0.9,
        num_bedrooms=2,
        toilets=2,
        parking=False,
    )


def test_shares_wall_adjacent():
    a = _make_room("a", "living", 0, 0, 3, 3)
    b = _make_room("b", "kitchen", 3, 0, 2, 3)  # touching right edge of a
    assert _shares_wall(a, b)


def test_shares_wall_not_adjacent():
    a = _make_room("a", "living", 0, 0, 2, 2)
    b = _make_room("b", "kitchen", 5, 5, 2, 2)  # far away
    assert not _shares_wall(a, b)


def test_score_aspect_ratio_penalty():
    # Very elongated room
    rooms = [_make_room("l", "living", 0, 0, 9, 1)]  # 9:1 ratio
    layout = _make_layout(rooms)
    score = _score_aspect_ratio(layout)
    assert score < 80  # should be penalised


def test_score_aspect_ratio_good():
    rooms = [_make_room("l", "living", 0, 0, 4, 3.5)]  # ~1.1:1
    layout = _make_layout(rooms)
    score = _score_aspect_ratio(layout)
    assert score >= 90


def test_score_adjacency_kitchen_dining():
    # Kitchen and dining adjacent
    kitchen = _make_room("k", "kitchen", 0, 0, 2, 2)
    dining = _make_room("d", "dining", 2, 0, 2, 2)  # right next to kitchen
    layout = _make_layout([kitchen, dining])
    score = _score_adjacency(layout)
    assert score > 0


def test_score_adjacency_kitchen_toilet_wetzone():
    # UPAVP EWS type-design drawings (15/25, 18/40) consistently cluster
    # kitchen with toilet/bath to share a single plumbing stack.
    kitchen = _make_room("k", "kitchen", 0, 0, 2, 2)
    toilet = _make_room("t", "toilet", 2, 0, 1.5, 2)  # shares wall with kitchen
    layout = _make_layout([kitchen, toilet])
    score = _score_adjacency(layout)
    assert score > 0


def test_score_layout_returns_all_components():
    cfg = _basic_cfg()
    rooms = [
        _make_room("l", "living", 1.13, 1.73, 3.5, 4.0),
        _make_room("k", "kitchen", 4.63, 1.73, 2.0, 2.5),
        _make_room("t", "toilet", 1.13, 5.73, 1.5, 2.0),
        _make_room("s", "staircase", 4.63, 4.23, 1.5, 1.5),
    ]
    layout = _make_layout(rooms, id="A")
    s = score_layout(layout, cfg)
    assert 0 <= s.total <= 100
    assert 0 <= s.natural_light <= 100
    assert 0 <= s.adjacency <= 100
    assert 0 <= s.aspect_ratio <= 100
    assert 0 <= s.circulation <= 100
    assert 0 <= s.vastu <= 100
    assert 0 <= s.toilet_placement <= 100


def test_rank_and_select_top_n():
    cfg = _basic_cfg()
    rooms = [_make_room("l", "living", 1.13, 1.73, 3.5, 4.0)]
    layouts = [_make_layout(rooms, id=id_) for id_ in ["A", "B", "C", "D"]]
    ranked = rank_and_select(layouts, cfg, top_n=3)
    assert len(ranked) == 3
    # Verify descending score order
    scores = [lay.score.total for lay in ranked]
    assert scores == sorted(scores, reverse=True)
    # Verify scores attached
    for lay in ranked:
        assert lay.score is not None


def test_scorer_weights_sum_to_one():
    assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_toilet_placement_no_wet_rooms_neutral():
    layout = _make_layout([_make_room("l", "living", 1.13, 1.73, 3.5, 4.0)])
    assert _score_toilet_placement(layout, _basic_cfg(), _EWT) == 100.0


def test_score_toilet_placement_front_band_penalized():
    cfg = _basic_cfg()
    front_toilet = _make_room("t1", "toilet", 1.13, 1.73, 1.5, 2.0)
    back_toilet = _make_room("t2", "toilet", 1.13, 8.0, 1.5, 2.0)
    front_score = _score_toilet_placement(_make_layout([front_toilet]), cfg, _EWT)
    back_score = _score_toilet_placement(_make_layout([back_toilet]), cfg, _EWT)
    assert front_score < back_score


def test_score_toilet_placement_middle_third_heavier_penalty():
    cfg = _basic_cfg()
    # Both in the front band; one centred under the main door (middle third), one to the side.
    middle_toilet = _make_room("t1", "toilet", 4.0, 1.73, 1.5, 2.0)
    side_toilet = _make_room("t2", "toilet", 1.13, 1.73, 1.5, 2.0)
    middle_score = _score_toilet_placement(_make_layout([middle_toilet]), cfg, _EWT)
    side_score = _score_toilet_placement(_make_layout([side_toilet]), cfg, _EWT)
    assert middle_score < side_score


def test_score_toilet_placement_stair_adjacency_penalized():
    cfg = _basic_cfg()
    stair = _make_room("s", "staircase", 4.87, 5.0, 1.5, 1.5)
    toilet_adjacent = _make_room("ta", "toilet", 6.37, 5.0, 1.5, 2.0)
    toilet_far = _make_room("tf", "toilet", 1.13, 5.0, 1.5, 2.0)
    adjacent_score = _score_toilet_placement(
        _make_layout([stair, toilet_adjacent]), cfg, _EWT
    )
    far_score = _score_toilet_placement(_make_layout([stair, toilet_far]), cfg, _EWT)
    assert adjacent_score < far_score


def test_score_toilet_placement_ensuite_exempt_from_adjacency_penalty():
    cfg = _basic_cfg()
    stair = _make_room("s", "staircase", 4.87, 5.0, 1.5, 1.5)
    bath = _make_room("b", "bathroom_master", 6.37, 5.0, 1.5, 2.0)
    bedroom = _make_room("mb", "master_bedroom", 6.37, 7.0, 1.5, 3.0)
    # Non-ensuite toilet in the same stair-adjacent spot, no bedroom neighbour.
    plain_toilet = _make_room("t", "toilet", 6.37, 5.0, 1.5, 2.0)

    ensuite_score = _score_toilet_placement(
        _make_layout([stair, bath, bedroom]), cfg, _EWT
    )
    plain_score = _score_toilet_placement(
        _make_layout([stair, plain_toilet]), cfg, _EWT
    )
    assert ensuite_score > plain_score


def test_score_toilet_placement_no_external_wall_penalized():
    cfg = _basic_cfg()
    interior_toilet = _make_room("ti", "toilet", 3.13, 5.0, 1.5, 2.0)
    boundary_toilet = _make_room("tb", "toilet", 1.13, 5.0, 1.5, 2.0)
    interior_score = _score_toilet_placement(_make_layout([interior_toilet]), cfg, _EWT)
    boundary_score = _score_toilet_placement(_make_layout([boundary_toilet]), cfg, _EWT)
    assert interior_score < boundary_score
