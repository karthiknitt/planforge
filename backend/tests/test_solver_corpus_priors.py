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


# ── Corpus-mined adjacency priors (Task 9) ───────────────────────────────────


def _room(
    model: cp_model.CpModel,
    room_id: str,
    room_type: str,
    x: tuple[int, int],
    y: tuple[int, int],
    w: int,
    d: int,
    floor: int = 0,
) -> S._RoomVar:
    """A room with pinned w/d and a free-or-pinned x/y, plus consistent ends."""
    xv = model.new_int_var(x[0], x[1], f"x_{room_id}")
    yv = model.new_int_var(y[0], y[1], f"y_{room_id}")
    wv = model.new_int_var(w, w, f"w_{room_id}")
    dv = model.new_int_var(d, d, f"d_{room_id}")
    xe = model.new_int_var(x[0], x[1] + w, f"xe_{room_id}")
    ye = model.new_int_var(y[0], y[1] + d, f"ye_{room_id}")
    model.add(xe == xv + wv)
    model.add(ye == yv + dv)
    return S._RoomVar(
        room_id=room_id,
        room_type=room_type,
        room_name=room_id.upper(),
        floor=floor,
        x=xv,
        y=yv,
        w=wv,
        d=dv,
        xe=xe,
        ye=ye,
        template="RECT",
        shape_ratio=1.0,
    )


def _flat_prior(monkeypatch, freq: float) -> None:
    monkeypatch.setattr(S, "get_adjacency_prior", lambda cfg, a, b: freq)


def _bonus_of(model: cp_model.CpModel, terms) -> int:
    """Best achievable value of the adjacency terms alone, as a plain int."""
    model.minimize(sum(cost * var for cost, var in terms))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    assert solver.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return int(solver.objective_value)


def test_adjacency_disabled_never_calls_the_term_builder(monkeypatch):
    """Same spy posture as the size-prior flag test: never invoked, so nothing
    it could add to the model exists on the flag-off path."""
    calls: list[int] = []
    real = S._add_adjacency_prior_terms

    def spy(model, cfg, room_vars):
        calls.append(len(room_vars))
        return real(model, cfg, room_vars)

    monkeypatch.setattr(S, "_add_adjacency_prior_terms", spy)

    assert S.solve_layout(_cfg(style_preset="Kerala")) is not None
    assert calls == []


def test_adjacency_enabled_calls_the_term_builder_and_still_solves(monkeypatch):
    calls: list[int] = []
    real = S._add_adjacency_prior_terms

    def spy(model, cfg, room_vars):
        calls.append(len(room_vars))
        return real(model, cfg, room_vars)

    monkeypatch.setattr(S, "_add_adjacency_prior_terms", spy)

    layout = S.solve_layout(_cfg(style_preset="Kerala", corpus_priors_enabled=True))
    assert layout is not None
    assert calls and all(n > 0 for n in calls)


def test_a_pair_the_corpus_finds_typical_gets_a_term():
    """Real corpus data, no monkeypatch: bedroom|toilet is a known positive."""
    model = cp_model.CpModel()
    rooms = [
        _room(model, "b1", "bedroom", (0, 5000), (0, 0), 3000, 3000),
        _room(model, "t1", "toilet", (0, 5000), (0, 0), 1500, 1500),
    ]
    terms = S._add_adjacency_prior_terms(model, _cfg(style_preset="Kerala"), rooms)
    assert len(terms) == 1
    cost, var = terms[0]
    assert cost < 0, "adjacency is a reward, and base_objective is minimised"
    assert var.name.startswith("adjp_")


def test_a_pair_the_corpus_never_observed_gets_no_term():
    # bedroom|bedroom is 0.0 in both the Kerala block and corpus-wide -- not
    # because the corpus never saw two bedrooms touch, but because
    # mine_adjacency_priors structurally excludes same-RoomType pairs.
    model = cp_model.CpModel()
    rooms = [
        _room(model, "b1", "bedroom", (0, 5000), (0, 0), 3000, 3000),
        _room(model, "b2", "bedroom", (0, 5000), (0, 0), 3000, 3000),
    ]
    assert S._add_adjacency_prior_terms(model, _cfg(style_preset="Kerala"), rooms) == []


def test_each_unordered_pair_is_counted_exactly_once(monkeypatch):
    """Three mutually-typical rooms must yield C(3,2) = 3 terms, not 6 or 9."""
    _flat_prior(monkeypatch, 1.0)
    model = cp_model.CpModel()
    rooms = [
        _room(model, f"r{i}", "bedroom", (0, 5000), (0, 0), 2000, 2000)
        for i in range(3)
    ]
    terms = S._add_adjacency_prior_terms(model, _cfg(style_preset="Kerala"), rooms)
    assert len(terms) == 3
    assert len({var.name for _, var in terms}) == 3


def test_rooms_on_different_floors_are_never_paired(monkeypatch):
    """A wall cannot be shared across a slab, whatever the corpus says."""
    _flat_prior(monkeypatch, 1.0)
    model = cp_model.CpModel()
    rooms = [
        _room(model, "g1", "bedroom", (0, 5000), (0, 0), 2000, 2000, floor=0),
        _room(model, "f1", "bedroom", (0, 5000), (0, 0), 2000, 2000, floor=1),
    ]
    assert S._add_adjacency_prior_terms(model, _cfg(style_preset="Kerala"), rooms) == []


def test_the_bonus_scales_with_the_corpus_frequency(monkeypatch):
    def cost_at(freq: float) -> int:
        _flat_prior(monkeypatch, freq)
        model = cp_model.CpModel()
        rooms = [
            _room(model, "a", "bedroom", (0, 5000), (0, 0), 2000, 2000),
            _room(model, "b", "toilet", (0, 5000), (0, 0), 2000, 2000),
        ]
        terms = S._add_adjacency_prior_terms(model, _cfg(style_preset="Kerala"), rooms)
        assert len(terms) == 1
        return terms[0][0]

    assert cost_at(1.0) == -S.ADJACENCY_PRIOR_WEIGHT
    assert cost_at(0.5) == pytest.approx(-S.ADJACENCY_PRIOR_WEIGHT / 2, abs=1)


def test_a_frequency_too_small_to_price_gets_no_term(monkeypatch):
    """A term whose reward rounds to zero is pure model bloat -- skip it."""
    _flat_prior(monkeypatch, 1e-9)
    model = cp_model.CpModel()
    rooms = [
        _room(model, "a", "bedroom", (0, 5000), (0, 0), 2000, 2000),
        _room(model, "b", "toilet", (0, 5000), (0, 0), 2000, 2000),
    ]
    assert S._add_adjacency_prior_terms(model, _cfg(style_preset="Kerala"), rooms) == []


def test_the_bonus_is_earned_when_the_rooms_can_share_a_wall(monkeypatch):
    """Minimising the term alone must pull the pair into real wall contact."""
    _flat_prior(monkeypatch, 1.0)
    model = cp_model.CpModel()
    a = _room(model, "a", "bedroom", (0, 6000), (0, 0), 2000, 2000)
    b = _room(model, "b", "toilet", (0, 6000), (0, 0), 2000, 2000)
    terms = S._add_adjacency_prior_terms(model, _cfg(style_preset="Kerala"), [a, b])
    assert _bonus_of(model, terms) == -S.ADJACENCY_PRIOR_WEIGHT


def test_the_bonus_cannot_be_claimed_when_the_rooms_are_far_apart(monkeypatch):
    """The reification is one-directional, so this is the load-bearing test:
    nothing forces the boolean false, only the enforced geometry stops the
    solver helping itself to a reward it has not earned."""
    _flat_prior(monkeypatch, 1.0)
    model = cp_model.CpModel()
    a = _room(model, "a", "bedroom", (0, 0), (0, 0), 2000, 2000)
    b = _room(model, "b", "toilet", (5000, 5000), (0, 0), 2000, 2000)
    terms = S._add_adjacency_prior_terms(model, _cfg(style_preset="Kerala"), [a, b])
    assert terms
    assert _bonus_of(model, terms) == 0


def test_touching_edges_with_no_overlap_is_not_a_shared_wall(monkeypatch):
    """Corner-to-corner contact aligns edges but shares no wall segment.

    This is exactly what the `align_bools` this term deliberately does NOT
    reuse would score as adjacency: `a.xe == b.x` holds, yet the rooms meet
    at a single point.
    """
    _flat_prior(monkeypatch, 1.0)
    model = cp_model.CpModel()
    a = _room(model, "a", "bedroom", (0, 0), (0, 0), 2000, 2000)
    b = _room(model, "b", "toilet", (2000, 2000), (2000, 2000), 2000, 2000)
    terms = S._add_adjacency_prior_terms(model, _cfg(style_preset="Kerala"), [a, b])
    assert terms
    assert _bonus_of(model, terms) == 0
