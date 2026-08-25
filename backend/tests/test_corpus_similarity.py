"""Corpus-similarity diagnostic score (Task 12) -- never a gate, just a
regression harness Task 13 tunes weights against. Follows `test_gcs.py`'s
reuse of `tests/helpers/golden.py` for real-corpus-data coverage, plus
synthetic fixtures (built the way `test_solver_corpus_priors.py` builds its
`PlotConfig`s) for the "closer to corpus scores higher" comparisons, since
the golden layout carries no `style_preset`.
"""

from __future__ import annotations

from app.engine.models import ComplianceResult, FloorPlan, Layout, PlotConfig, Room
from app.quality.corpus_similarity import compute_corpus_similarity
from tests.helpers.golden import golden_config, golden_layout


def _cfg(**kw) -> PlotConfig:
    base = dict(
        plot_x_extent=9.0,
        plot_y_extent=15.0,
        setback_front=3.0,
        setback_rear=1.5,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=3,
        toilets=2,
        parking=True,
        road_side="S",
    )
    base.update(kw)
    return PlotConfig(**base)


def _room(room_id: str, room_type: str, x: float, y: float, w: float, d: float) -> Room:
    return Room(id=room_id, name=room_type, type=room_type, x=x, y=y, width=w, depth=d)


def _layout(rooms: list[Room]) -> Layout:
    gf = FloorPlan(floor=0, floor_type="ground", rooms=rooms)
    ff = FloorPlan(floor=1, floor_type="first", rooms=[])
    return Layout(
        id="T",
        name="test",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )


# ── Bounded scores ───────────────────────────────────────────────────────────


def test_similarity_score_is_bounded_on_the_golden_layout():
    layout = golden_layout()
    cfg = golden_config()
    score = compute_corpus_similarity(layout, cfg)
    assert 0 <= score.overall <= 100
    for value in (score.size_score, score.adjacency_score):
        assert value is None or 0 <= value <= 100


def test_bounded_with_a_style_preset_too():
    layout = golden_layout()
    cfg = _cfg(style_preset="Kerala")
    score = compute_corpus_similarity(layout, cfg)
    for value in (
        score.size_score,
        score.adjacency_score,
        score.position_score,
        score.shape_score,
    ):
        assert value is None or 0 <= value <= 100
    assert 0 <= score.overall <= 100


# ── Discrimination: close-to-corpus scores higher than far-from-corpus ──────


def test_size_score_prefers_a_room_near_the_corpus_mean():
    cfg = _cfg(style_preset="Kerala")
    # Kerala bedroom corpus prior: area_mean ~140.4 sqft, area_std ~26.3 sqft.
    close = _layout([_room("r1", "bedroom", 1.0, 1.0, 3.6, 3.6)])  # ~139.5 sqft
    far = _layout([_room("r1", "bedroom", 1.0, 1.0, 2.0, 2.0)])  # ~43.1 sqft
    close_score = compute_corpus_similarity(close, cfg)
    far_score = compute_corpus_similarity(far, cfg)
    assert close_score.size_score is not None
    assert far_score.size_score is not None
    assert close_score.size_score > far_score.size_score


def test_adjacency_score_rewards_a_high_frequency_pair_actually_sharing_a_wall():
    cfg = _cfg(style_preset="Kerala")
    # Kerala bedroom|living adjacency frequency is 0.6 -- above threshold.
    adjacent = _layout(
        [
            _room("r1", "bedroom", 0.0, 0.0, 3.0, 3.0),
            _room("r2", "living", 3.0, 0.0, 4.0, 4.0),  # shares the x=3.0 wall
        ]
    )
    apart = _layout(
        [
            _room("r1", "bedroom", 0.0, 0.0, 3.0, 3.0),
            _room("r2", "living", 8.0, 8.0, 4.0, 4.0),  # nowhere near r1
        ]
    )
    adjacent_score = compute_corpus_similarity(adjacent, cfg)
    apart_score = compute_corpus_similarity(apart, cfg)
    assert adjacent_score.adjacency_score is not None
    assert apart_score.adjacency_score is not None
    assert adjacent_score.adjacency_score > apart_score.adjacency_score


def test_position_score_rewards_a_high_frequency_zone_match():
    cfg = _cfg(style_preset="Kerala", plot_x_extent=9.0, plot_y_extent=15.0)
    # Kerala bedroom position histogram: zone "C" (centre) has frequency
    # 0.3125, well above threshold; the far front-left corner ("SW" band) is
    # absent from the histogram entirely (frequency 0.0).
    centered = _layout(
        [_room("r1", "bedroom", 3.75, 6.5, 1.5, 2.0)]
    )  # near plot centre
    corner = _layout([_room("r1", "bedroom", 0.0, 0.0, 1.5, 2.0)])  # front-left corner
    centered_score = compute_corpus_similarity(centered, cfg)
    corner_score = compute_corpus_similarity(corner, cfg)
    assert centered_score.position_score is not None
    assert corner_score.position_score is not None
    assert centered_score.position_score > corner_score.position_score


# ── No-style-preset graceful degradation ─────────────────────────────────────


def test_no_style_preset_excludes_position_and_shape_but_keeps_size_and_adjacency():
    layout = golden_layout()
    cfg = golden_config()
    assert cfg.style_preset is None
    score = compute_corpus_similarity(layout, cfg)
    assert score.position_score is None
    assert score.shape_score is None
    # size/adjacency have corpus-wide fallbacks, so the golden layout (which
    # has bedroom/living/etc rooms) should still produce a real number.
    assert score.size_score is not None
    assert 0 <= score.overall <= 100


# ── Empty layout ──────────────────────────────────────────────────────────────


def test_empty_layout_does_not_crash():
    empty = _layout([])
    score = compute_corpus_similarity(empty, _cfg(style_preset="Kerala"))
    assert score.overall == 0.0
    assert score.size_score is None
    assert score.adjacency_score is None
    assert score.position_score is None
    assert score.shape_score is None


# ── as_dict ───────────────────────────────────────────────────────────────────


def test_as_dict_matches_gcs_style():
    layout = golden_layout()
    cfg = golden_config()
    d = compute_corpus_similarity(layout, cfg).as_dict()
    assert set(d) == {
        "overall",
        "size_score",
        "adjacency_score",
        "position_score",
        "shape_score",
    }
