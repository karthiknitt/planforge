"""Vastu ranks layouts; it no longer rejects them.

Vastu used to be appended to `compliance.violations` in `generator.generate`,
which flipped `compliance.passed` and deleted the layout from the candidate
set. It is now a warning plus a graded 0–100 score that reaches ranking through
`scorer._score_vastu` (10% of the layout score).

These tests build `Layout` fixtures by hand and exercise the scoring/ranking
functions directly — `backend/tests/CLAUDE.md`: CP-SAT is not deterministic, so
nothing here re-solves. The single end-to-end test is marked `slow` and asserts
only invariants that hold for every seed.

Plot is 9 m x 12 m with road_side "S", so the Vastu 3x3 grid is
    x in [0,3) left, [3,6) middle, [6,9) right
    y in [0,4) front (SW,S,SE), [4,8) middle (W,C,E), [8,12) rear (NW,N,NE)
"""

import pytest

from app.engine.generator import _attach_vastu
from app.engine.models import (
    ComplianceResult,
    FloorPlan,
    Layout,
    PlotConfig,
    Room,
)
from app.engine.scorer import _score_vastu, rank_and_select

PLOT_W = 9.0
PLOT_L = 12.0

# Zone anchors: (x, y) of a 2 m x 2 m room that sits wholly inside the zone.
SE_CORNER = (6.5, 1.0)
NE_CORNER = (6.5, 9.0)
SW_CORNER = (0.5, 1.0)
E_MIDDLE = (6.5, 5.0)


def _room(rid: str, rtype: str, x: float, y: float, w: float = 2.0, d: float = 2.0):
    return Room(id=rid, name=rtype.title(), type=rtype, x=x, y=y, width=w, depth=d)


def _layout(gf_rooms: list[Room], ff_rooms: list[Room] | None = None, rid: str = "X"):
    return Layout(
        id=rid,
        name=f"Layout {rid}",
        ground_floor=FloorPlan(floor=0, floor_type="ground", rooms=gf_rooms),
        first_floor=FloorPlan(floor=1, floor_type="first", rooms=ff_rooms or []),
        compliance=ComplianceResult(passed=True),
    )


def _cfg(vastu_enabled: bool = True) -> PlotConfig:
    return PlotConfig(
        plot_length=PLOT_L,
        plot_width=PLOT_W,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=0.9,
        setback_right=0.9,
        num_bedrooms=2,
        toilets=2,
        parking=False,
        vastu_enabled=vastu_enabled,
        road_side="S",
    )


# ── scorer._score_vastu: the ranking channel ──────────────────────────────────


def test_score_vastu_stays_neutral_100_when_vastu_is_disabled():
    """With Vastu off this component must be inert, not a 10-point tax.

    `vastu_layout_score` would return 0.0 for this layout, so dropping the
    early return would silently penalise every layout in the default config.
    """
    kitchen = _room("k", "kitchen", *NE_CORNER)  # NE: kitchen's worst zone
    assert _score_vastu(_layout([kitchen]), _cfg(vastu_enabled=False)) == 100.0


def test_score_vastu_is_graded_not_a_count_of_findings():
    """A kitchen in E is 'acceptable' — neither preferred nor avoided.

    The old implementation scored 100.0 here (no violation, no warning: E is one
    of the three zones its bespoke kitchen check tolerates). The graded score
    distinguishes 'acceptable' from 'preferred', which is the whole point of
    ranking by Vastu rather than gating on it.
    """
    kitchen = _room("k", "kitchen", *E_MIDDLE)
    assert _score_vastu(_layout([kitchen]), _cfg()) == 70.0


def test_score_vastu_rewards_the_preferred_zone_over_the_avoided_one():
    preferred = _score_vastu(_layout([_room("k", "kitchen", *SE_CORNER)]), _cfg())
    avoided = _score_vastu(_layout([_room("k", "kitchen", *NE_CORNER)]), _cfg())
    assert preferred == 100.0
    assert avoided == 0.0


def test_score_vastu_counts_upper_floors_not_just_the_ground_floor():
    """`check_vastu` only ever looked at the ground floor, so a first-floor
    master bedroom in a prohibited zone was invisible. Equal-area rooms, one
    perfect (SE kitchen, 1.0) and one avoided (NE kitchen, 0.0), average to 50.
    A ground-floor-only score would read 100.0 here.
    """
    layout = _layout(
        [_room("k0", "kitchen", *SE_CORNER)],
        [_room("k1", "kitchen", *NE_CORNER)],
    )
    assert _score_vastu(layout, _cfg()) == 50.0


# ── rank_and_select: Vastu changes the returned order ─────────────────────────


def _swapped_pair() -> tuple[Layout, Layout]:
    """Two layouts with identical geometry, differing only in which room type
    occupies which zone — so every non-Vastu score component is equal and any
    ranking difference is attributable to Vastu alone.

    good: kitchen in SE (preferred 1.0) + utility in NE (preferred 1.0) -> 100.0
    bad:  kitchen in NE (avoid 0.0)     + utility in SE (no rule -> 0.45) -> 22.5
    """
    good = _layout(
        [_room("k", "kitchen", *SE_CORNER), _room("u", "utility", *NE_CORNER)],
        rid="good",
    )
    bad = _layout(
        [_room("k", "kitchen", *NE_CORNER), _room("u", "utility", *SE_CORNER)],
        rid="bad",
    )
    return good, bad


def test_rank_and_select_puts_the_vastu_better_layout_first():
    good, bad = _swapped_pair()
    cfg = _cfg()
    assert _score_vastu(good, cfg) == 100.0
    assert _score_vastu(bad, cfg) == 22.5

    ranked = rank_and_select([bad, good], cfg, top_n=2)
    assert [lay.id for lay in ranked] == ["good", "bad"]
    # 10% weight on a 77.5-point Vastu gap = 7.75 points of layout score, which
    # LayoutScore.total rounds to 1 dp before the subtraction (41.6 - 33.9).
    assert good.score.vastu == 100.0
    assert bad.score.vastu == 22.5
    assert round(good.score.total - bad.score.total, 1) == 7.7


def test_rank_and_select_does_not_split_the_pair_when_vastu_is_disabled():
    """Same two layouts, Vastu off: the component is neutral for both, so their
    totals are identical and neither is penalised for its room placement."""
    good, bad = _swapped_pair()
    ranked = rank_and_select([bad, good], _cfg(vastu_enabled=False), top_n=2)
    assert [lay.score.vastu for lay in ranked] == [100.0, 100.0]
    assert ranked[0].score.total == ranked[1].score.total


# ── generator._attach_vastu: warnings, never violations ───────────────────────


def test_attach_vastu_records_warnings_and_never_violations():
    """A SW kitchen was a prohibited-zone *violation* under the old code, which
    set compliance.passed False and dropped the layout before ranking."""
    layout = _layout([_room("k", "kitchen", *SW_CORNER)])
    _attach_vastu(layout, _cfg())

    assert layout.compliance.violations == []
    assert layout.compliance.passed is True
    assert any("[Vastu]" in w for w in layout.compliance.warnings)
    assert layout.vastu_score == 0.0


def test_attach_vastu_scores_a_good_layout_high_with_no_vastu_warnings():
    layout = _layout([_room("k", "kitchen", *SE_CORNER)])
    _attach_vastu(layout, _cfg())

    assert layout.vastu_score == 100.0
    assert [w for w in layout.compliance.warnings if "[Vastu]" in w] == []


def test_attach_vastu_leaves_the_layout_untouched_when_disabled():
    layout = _layout([_room("k", "kitchen", *SW_CORNER)])
    _attach_vastu(layout, _cfg(vastu_enabled=False))

    assert layout.vastu_score is None
    assert layout.compliance.warnings == []
    assert layout.compliance.violations == []


def test_attach_vastu_matches_the_score_component_it_feeds():
    """`vastu_score` is stored for the API; it must be the same number ranking
    used, or the UI would explain a ranking with an unrelated figure."""
    layout, _bad = _swapped_pair()
    cfg = _cfg()
    _attach_vastu(layout, cfg)
    assert layout.vastu_score == _score_vastu(layout, cfg)


# ── End to end ────────────────────────────────────────────────────────────────


@pytest.mark.slow
def test_generate_with_vastu_returns_scored_layouts_with_no_vastu_violations():
    """Runs a real CP-SAT solve, so it asserts only per-seed invariants: Vastu
    never empties the candidate set, never lands in `violations`, and every
    returned layout carries a score in range.
    """
    from app.engine.generator import generate

    layouts = generate(
        PlotConfig(
            plot_length=15.0,
            plot_width=9.0,
            setback_front=3.0,
            setback_rear=1.5,
            setback_left=1.2,
            setback_right=1.2,
            num_bedrooms=3,
            toilets=2,
            parking=True,
            vastu_enabled=True,
            road_side="S",
        )
    )

    assert len(layouts) > 0
    for lay in layouts:
        assert not any("[Vastu]" in v for v in lay.compliance.violations)
        assert lay.compliance.passed is True
        assert lay.vastu_score is not None
        assert 0.0 <= lay.vastu_score <= 100.0
        assert lay.score.vastu == round(lay.vastu_score, 1)
