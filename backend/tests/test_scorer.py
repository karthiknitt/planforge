"""Tests for the layout quality scorer."""

import pytest
from app.engine.models import Column, ComplianceResult, FloorPlan, Layout, PlotConfig, Room
from app.engine.scorer import (
    _score_adjacency,
    _score_aspect_ratio,
    _score_circulation,
    _score_natural_light,
    _shares_wall,
    rank_and_select,
    score_layout,
)


def _make_room(id, type, x, y, w, d, name=None):
    return Room(id=id, name=name or type.title(), type=type, x=x, y=y, width=w, depth=d)


def _make_layout(gf_rooms, ff_rooms=None, id="X"):
    gf = FloorPlan(floor=0, floor_type="ground", rooms=gf_rooms)
    ff = FloorPlan(floor=1, floor_type="first", rooms=ff_rooms or [])
    return Layout(id=id, name=f"Layout {id}", ground_floor=gf, first_floor=ff,
                  compliance=ComplianceResult(passed=True))


def _basic_cfg():
    return PlotConfig(
        plot_length=12.0, plot_width=9.0,
        setback_front=1.5, setback_rear=1.0, setback_left=0.9, setback_right=0.9,
        num_bedrooms=2, toilets=2, parking=False,
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


def test_rank_and_select_top_n():
    cfg = _basic_cfg()
    rooms = [_make_room("l", "living", 1.13, 1.73, 3.5, 4.0)]
    layouts = [_make_layout(rooms, id=id_) for id_ in ["A", "B", "C", "D"]]
    ranked = rank_and_select(layouts, cfg, top_n=3)
    assert len(ranked) == 3
    # Verify descending score order
    scores = [l.score.total for l in ranked]
    assert scores == sorted(scores, reverse=True)
    # Verify scores attached
    for l in ranked:
        assert l.score is not None
