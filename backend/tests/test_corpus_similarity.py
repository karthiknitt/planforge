"""Corpus-similarity diagnostic score (Task 12) -- never a gate, just a
regression harness Task 13 tunes weights against. Follows `test_gcs.py`'s
reuse of `tests/helpers/golden.py` for real-corpus-data coverage, plus
synthetic fixtures (built the way `test_solver_corpus_priors.py` builds its
`PlotConfig`s) for the "closer to corpus scores higher" comparisons, since
the golden layout carries no `style_preset`.
"""

from __future__ import annotations

import pytest

from app.engine.models import ComplianceResult, FloorPlan, Layout, PlotConfig, Room
from app.engine.solver import solve_layout
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


# ── shape_score's per-type "no data" hole (Task 12 review Finding C) ──────────


def test_shape_score_excludes_a_templatable_type_the_style_never_recorded():
    """Kerala's shape_usage block has no `passage` entry at all -- a RECT
    passage must be excluded, not auto-scored 100 from zero real signal.
    """
    cfg = _cfg(style_preset="Kerala")
    from app.engine.corpus_priors import load_priors

    assert "passage" not in load_priors()["by_style"]["Kerala"]["shape_usage"]
    layout = _layout([_room("p1", "passage", 0.0, 0.0, 1.0, 2.0)])
    score = compute_corpus_similarity(layout, cfg)
    assert score.shape_score is None


def test_shape_score_still_scores_a_type_the_style_did_record():
    """Sanity check the fix didn't just exclude everything: Kerala DOES
    carry a `living` entry (p_nonrect == 0.0), so a RECT living room must
    still score 100.
    """
    cfg = _cfg(style_preset="Kerala")
    from app.engine.corpus_priors import load_priors

    assert "living" in load_priors()["by_style"]["Kerala"]["shape_usage"]
    layout = _layout([_room("l1", "living", 0.0, 0.0, 4.0, 4.0)])
    score = compute_corpus_similarity(layout, cfg)
    assert score.shape_score == 100.0


# ── Task 13's go/no-go findings, pinned ──────────────────────────────────────
# Both tests below solve for real, so they carry the `slow` marker. The solver
# runs single-threaded under a deterministic budget
# (`num_search_workers = 1`, `max_deterministic_time`), so identical inputs
# give identical output and a pinned-input assertion is legitimate here --
# these still assert a DIRECTION rather than a number, because any future
# weight change would move the numbers without invalidating the finding.


@pytest.mark.slow
def test_corpus_wide_priors_raise_the_size_score():
    """The one direction that held in every cell of Task 13's sweep.

    Corpus-wide priors (priors on, `style_preset` unset) beat priors-off on
    `size_score` in 48/48 sampled cells, by +3.3 to +15.4 points. Only
    `size_score` is asserted: `adjacency_score` regressed in 19/48 and
    `position_score` in 9/48, so neither is a stable direction to pin, and
    `overall` is not comparable here at all (no `style_preset` on either
    side changes which components are present -- see
    `compute_corpus_similarity`'s docstring).

    Uses the default `_cfg()` (3BR), below `CORPUS_PRIORS_WIDE_BUDGET_MIN_BEDROOMS`
    (solver.py) -- deliberately, so this stays on the original (narrower)
    solve budget. A follow-up to the budget-exhaustion fix below found that
    widening the budget for EVERY priors-on solve (not just the dense/at-risk
    ones) measurably worsened this exact direction on a normal-sized plot --
    the two-phase warm-start hand-off means more search time can settle on a
    genuinely different phase-1 sketch, not just a more-polished one, so it
    is not a "monotonically better with more time" search. Keeping small
    plots off the widened budget is what keeps this direction intact.
    """
    off = _cfg(corpus_priors_enabled=False)
    on = _cfg(corpus_priors_enabled=True)
    layout_off = solve_layout(off)
    layout_on = solve_layout(on)
    assert layout_off is not None and layout_on is not None
    score_off = compute_corpus_similarity(layout_off, off)
    score_on = compute_corpus_similarity(layout_on, on)
    assert score_on.size_score > score_off.size_score


@pytest.mark.slow
def test_corpus_priors_no_longer_exhaust_the_solve_budget_on_a_dense_plot():
    """Regression guard for the Task 13 -> follow-up budget fix.

    Originally: the priors' extra objective terms enlarged the model past
    what the flat `PHASE2_DET_BUDGET` (1.5 deterministic units, calibrated
    on the priors-off model) could find ANY incumbent for on a dense plot --
    solve returned None where priors-off succeeded (status UNKNOWN, not
    INFEASIBLE -- a budget calibration gap, not a modelling error; lowering
    weights did not fix it since model *size*, not coefficient magnitude,
    cost the budget).

    Fix: `CORPUS_PRIORS_DET_BUDGET_MULTIPLIER` (solver.py) scales both phase
    budgets by 3x, but ONLY when `cfg.corpus_priors_enabled` is True AND
    `cfg.num_bedrooms >= CORPUS_PRIORS_WIDE_BUDGET_MIN_BEDROOMS` (4) -- an
    earlier version gated purely on the flag and was reverted: it fixed this
    dense-plot crash but was measured to make a normal-sized plot's
    corpus-similarity WORSE (see `test_corpus_wide_priors_raise_the_size_score`
    above), because widening the budget changes the phase-1 warm-start's
    outcome for every priors-on solve, not just the ones that need it. 3x
    was the smallest multiplier where both sampled dense cells (12x18m 3BR
    and 4BR) returned a layout, but only the 4BR cell actually needed it --
    the 3BR one already solved fine at the base budget, which is the measured
    basis for the >=4 bedroom cutoff.

    IF THIS TEST STARTS FAILING the fix has regressed -- re-run
    `scripts/tune_corpus_priors.py` and re-measure both the multiplier and
    the bedroom cutoff before touching anything here.
    """
    dense = dict(plot_x_extent=12.0, plot_y_extent=18.0, num_bedrooms=4, toilets=3)
    assert solve_layout(_cfg(**dense, corpus_priors_enabled=False)) is not None
    assert solve_layout(_cfg(**dense, corpus_priors_enabled=True)) is not None
