"""Corpus-mined size priors as a CP-SAT objective term (Task 8).

Follows `tests/test_solver_vastu.py`'s structure and, deliberately, its two
avoidance rules: no test here solves the same model twice and compares
geometry (CP-SAT is not deterministic across runs), and the "flag off changes
nothing" guarantee is asserted on MODEL CONSTRUCTION -- the term builder is
never even called -- rather than on two solutions being equal.
"""

from __future__ import annotations

import pytest
from ortools.sat.python import cp_model

from app.engine import solver as S
from app.engine.corpus_priors import SizePrior
from app.engine.models import PlotConfig

_SQFT_TO_MM2 = 92903.04


def _cfg(**kw) -> PlotConfig:
    base = dict(
        plot_y_extent=15.0,
        plot_x_extent=9.0,
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


def _room_var(
    model: cp_model.CpModel,
    room_type: str,
    w_lo: int,
    w_hi: int,
    d_lo: int,
    d_hi: int,
) -> S._RoomVar:
    """One `_RoomVar` with free-or-pinned w/d, mirroring test_solver_vastu.py."""
    return S._RoomVar(
        room_id="r1",
        room_type=room_type,
        room_name="R1",
        floor=0,
        x=model.new_int_var(0, 9000, "x"),
        y=model.new_int_var(0, 15000, "y"),
        w=model.new_int_var(w_lo, w_hi, "w"),
        d=model.new_int_var(d_lo, d_hi, "d"),
        xe=model.new_int_var(0, 9000, "xe"),
        ye=model.new_int_var(0, 15000, "ye"),
        template="RECT",
        shape_ratio=1.0,
    )


# ── The flag ─────────────────────────────────────────────────────────────────


def test_corpus_priors_are_off_by_default():
    assert _cfg().corpus_priors_enabled is False
    assert _cfg(corpus_priors_enabled=True).corpus_priors_enabled is True


def test_disabled_never_calls_the_term_builder(monkeypatch):
    """The flag-off path must be the pre-change model, byte for byte.

    Asserted by spying on the builder rather than by comparing two solves:
    if it is never invoked, no variable and no objective term it could add
    exists in the model, which is a stronger statement than any comparison of
    two nondeterministic incumbents.
    """
    calls: list[int] = []
    real = S._add_size_prior_terms

    def spy(model, cfg, room_vars):
        calls.append(len(room_vars))
        return real(model, cfg, room_vars)

    monkeypatch.setattr(S, "_add_size_prior_terms", spy)

    assert S.solve_layout(_cfg(style_preset="Kerala")) is not None
    assert calls == []


def test_enabled_calls_the_term_builder_and_still_finds_a_layout(monkeypatch):
    calls: list[int] = []
    real = S._add_size_prior_terms

    def spy(model, cfg, room_vars):
        calls.append(len(room_vars))
        return real(model, cfg, room_vars)

    monkeypatch.setattr(S, "_add_size_prior_terms", spy)

    layout = S.solve_layout(_cfg(style_preset="Kerala", corpus_priors_enabled=True))
    assert layout is not None
    assert calls and all(n > 0 for n in calls)


# ── Which rooms get a term ───────────────────────────────────────────────────


def test_room_type_with_corpus_data_gets_exactly_one_term():
    model = cp_model.CpModel()
    rv = _room_var(model, "bedroom", 2500, 4500, 2500, 4500)
    terms = S._add_size_prior_terms(model, _cfg(style_preset="Kerala"), [rv])
    assert len(terms) == 1
    cost, var = terms[0]
    assert cost == S.SIZE_PRIOR_WEIGHT
    assert var.name.startswith("size_prior_")


def test_room_type_absent_from_the_corpus_gets_no_term():
    model = cp_model.CpModel()
    rv = _room_var(model, "not_a_room_type", 2500, 4500, 2500, 4500)
    assert S._add_size_prior_terms(model, _cfg(style_preset="Kerala"), [rv]) == []


def test_a_zero_std_prior_is_skipped(monkeypatch):
    """A degenerate prior would divide by zero in the inverse-std weighting."""
    monkeypatch.setattr(
        S,
        "get_size_prior",
        lambda cfg, rt: SizePrior(
            area_mean=150.0, area_std=0.0, aspect_mean=1.2, aspect_std=0.2
        ),
    )
    model = cp_model.CpModel()
    rv = _room_var(model, "bedroom", 2500, 4500, 2500, 4500)
    assert S._add_size_prior_terms(model, _cfg(style_preset="Kerala"), [rv]) == []


# ── The term actually steers, and is inverse-std weighted ────────────────────


def _cost_of_pinned_room(
    area_sqft: float, std_sqft: float, w_mm: int, d_mm: int, monkeypatch
) -> int:
    """Objective value of the size-prior terms for a room of a FIXED size."""
    monkeypatch.setattr(
        S,
        "get_size_prior",
        lambda cfg, rt: SizePrior(
            area_mean=area_sqft, area_std=std_sqft, aspect_mean=1.2, aspect_std=0.2
        ),
    )
    model = cp_model.CpModel()
    rv = _room_var(model, "bedroom", w_mm, w_mm, d_mm, d_mm)
    terms = S._add_size_prior_terms(model, _cfg(style_preset="Kerala"), [rv])
    assert terms
    model.minimize(sum(cost * var for cost, var in terms))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    assert solver.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return int(solver.objective_value)


def test_a_room_at_the_prior_mean_pays_nothing(monkeypatch):
    # 4000 x 3000 mm = 12 m2 = 129.167 sqft.
    cost = _cost_of_pinned_room(
        12_000_000 / _SQFT_TO_MM2, 20.0, 4000, 3000, monkeypatch
    )
    assert cost == 0


def test_a_tightly_agreed_room_type_pays_more_for_the_same_miss(monkeypatch):
    """The inverse-std weighting, isolated.

    Same mean, same actual size, only the corpus's own spread differs. The
    type the corpus agrees about (std 10 sqft) must be penalised harder than
    the one it disagrees about (std 40 sqft) -- and, since the cost is
    proportional to 1/std, by very close to the 4x ratio between them.
    """
    mean = 12_000_000 / _SQFT_TO_MM2
    tight = _cost_of_pinned_room(mean, 10.0, 4000, 4000, monkeypatch)
    loose = _cost_of_pinned_room(mean, 40.0, 4000, 4000, monkeypatch)
    assert tight > loose > 0
    assert 3.8 < tight / loose < 4.2


def test_one_sigma_of_deviation_costs_about_the_documented_weight(monkeypatch):
    """A 1-sigma miss costs ~100 units x SIZE_PRIOR_WEIGHT, by construction."""
    # mean 12 m2, std 4 m2; the pinned room is 16 m2 = mean + 1 std.
    mean = 12_000_000 / _SQFT_TO_MM2
    std = 4_000_000 / _SQFT_TO_MM2
    cost = _cost_of_pinned_room(mean, std, 4000, 4000, monkeypatch)
    expected = S.SIZE_PRIOR_UNITS_PER_STD * S.SIZE_PRIOR_WEIGHT
    assert cost == pytest.approx(expected, rel=0.02)


def test_the_term_pulls_a_free_room_toward_the_prior_mean(monkeypatch):
    """Minimising only this term must land the room at the prior area.

    Fully determined by the objective under a single worker, so this is not
    the forbidden solve-twice-and-compare pattern.
    """
    mean_mm2 = 12_000_000.0
    monkeypatch.setattr(
        S,
        "get_size_prior",
        lambda cfg, rt: SizePrior(
            area_mean=mean_mm2 / _SQFT_TO_MM2,
            area_std=20.0,
            aspect_mean=1.2,
            aspect_std=0.2,
        ),
    )
    model = cp_model.CpModel()
    rv = _room_var(model, "bedroom", 1000, 6000, 1000, 6000)
    terms = S._add_size_prior_terms(model, _cfg(style_preset="Kerala"), [rv])
    model.minimize(sum(cost * var for cost, var in terms))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    assert solver.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    area = solver.value(rv.w) * solver.value(rv.d)
    # Within a hundredth of a sigma -- the resolution the divisor quantises to.
    assert abs(area - mean_mm2) <= 20.0 * _SQFT_TO_MM2 / S.SIZE_PRIOR_UNITS_PER_STD
