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
from app.engine.vastu import _rule_for, resolve_north_angle, zone_for_point

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


# ── Position priors (Task 10) ────────────────────────────────────────────────


def _zones_of(terms) -> set[str]:
    """Zone label each position term is gated on, read back off the var name."""
    return {var.name.rsplit("_", 1)[1] for _, var in terms}


def test_position_disabled_never_calls_the_term_builder(monkeypatch):
    """Same spy posture as the size- and adjacency-prior flag tests."""
    calls: list[int] = []
    real = S._add_position_prior_terms

    def spy(model, cfg, room_vars, ox, oy, **kw):
        calls.append(len(room_vars))
        return real(model, cfg, room_vars, ox, oy, **kw)

    monkeypatch.setattr(S, "_add_position_prior_terms", spy)

    assert S.solve_layout(_cfg(style_preset="Kerala")) is not None
    assert calls == []


def test_position_enabled_calls_the_term_builder_and_still_solves(monkeypatch):
    calls: list[int] = []
    real = S._add_position_prior_terms

    def spy(model, cfg, room_vars, ox, oy, **kw):
        calls.append(len(room_vars))
        return real(model, cfg, room_vars, ox, oy, **kw)

    monkeypatch.setattr(S, "_add_position_prior_terms", spy)

    layout = S.solve_layout(_cfg(style_preset="Kerala", corpus_priors_enabled=True))
    assert layout is not None
    assert calls and all(n > 0 for n in calls)


def test_position_terms_are_still_built_with_vastu_disabled(monkeypatch):
    """`corpus_priors_enabled` is independent of `vastu_enabled`.

    With Vastu off, `_add_vastu_terms` is never called at all, so the zone
    membership this term reads has to be built by this term itself.
    """
    built: list[int] = []
    real = S._add_position_prior_terms

    def spy(model, cfg, room_vars, ox, oy, **kw):
        terms = real(model, cfg, room_vars, ox, oy, **kw)
        built.append(len(terms))
        return terms

    monkeypatch.setattr(S, "_add_position_prior_terms", spy)

    layout = S.solve_layout(
        _cfg(style_preset="Kerala", corpus_priors_enabled=True, vastu_enabled=False)
    )
    assert layout is not None
    assert built and max(built) > 0


def test_position_prior_without_a_style_preset_builds_nothing():
    """`get_position_prior` has NO corpus-wide fallback, unlike size/adjacency.

    So the whole term is a no-op without a style, even with the flag on. The
    builder still RUNS -- this is not the flag-off case -- it just has no data.
    """
    model = cp_model.CpModel()
    rooms = [_room(model, "k1", "kitchen", (0, 5000), (0, 10000), 3000, 3000)]
    cfg = _cfg(corpus_priors_enabled=True)
    assert cfg.style_preset is None
    assert S._add_position_prior_terms(model, cfg, rooms, 0, 0) == []


def test_zones_the_corpus_favours_get_reward_terms():
    """Real corpus data, no monkeypatch: Kerala kitchen is C/NW/S/W."""
    model = cp_model.CpModel()
    rooms = [_room(model, "k1", "kitchen", (0, 5000), (0, 10000), 3000, 3000)]
    terms = S._add_position_prior_terms(model, _cfg(style_preset="Kerala"), rooms, 0, 0)
    assert _zones_of(terms) == {"C", "NW", "S", "W"}
    assert all(cost < 0 for cost, _ in terms), (
        "a bonus, and base_objective is minimised"
    )
    assert all(var.name.startswith("posp_") for _, var in terms)


def test_a_room_type_the_corpus_has_no_position_data_for_gets_no_terms():
    """`bathroom_master` is absent from every style's position histogram."""
    model = cp_model.CpModel()
    rooms = [_room(model, "b1", "bathroom_master", (0, 5000), (0, 10000), 2000, 2000)]
    assert (
        S._add_position_prior_terms(model, _cfg(style_preset="Kerala"), rooms, 0, 0)
        == []
    )


def test_the_reward_scales_with_the_zone_frequency():
    """Kerala kitchen: C is 0.5 and S is 0.25, so C must pay exactly twice."""
    model = cp_model.CpModel()
    rooms = [_room(model, "k1", "kitchen", (0, 5000), (0, 10000), 3000, 3000)]
    terms = S._add_position_prior_terms(model, _cfg(style_preset="Kerala"), rooms, 0, 0)
    by_zone = {var.name.rsplit("_", 1)[1]: cost for cost, var in terms}
    assert by_zone["C"] == -round(S.POSITION_PRIOR_WEIGHT * 0.5)
    assert by_zone["C"] == 2 * by_zone["S"]


def test_a_hard_excluded_zone_never_gets_a_reward():
    """Kerala's corpus puts a toilet in C 47% of the time -- its single
    largest bucket -- and C is a HARD-excluded zone for toilets. Paying a
    bonus there would reward a placement the model forbids outright, and the
    soft anchor point can sit in C while the true centroid (which the hard
    exclusion tests) does not, so the solver could even collect it."""
    model = cp_model.CpModel()
    rooms = [_room(model, "t1", "toilet", (0, 5000), (0, 10000), 1500, 1500)]
    terms = S._add_position_prior_terms(model, _cfg(style_preset="Kerala"), rooms, 0, 0)
    assert _zones_of(terms) == {"E", "S", "SE"}
    assert "C" in S._vastu_hard_excluded_zones("toilet")


def test_a_room_type_with_no_vastu_rule_still_gets_position_terms():
    """Half the room types with position priors have no Vastu rule at all, so
    the zone reification cannot be gated on having one."""
    assert _rule_for("courtyard") is None
    model = cp_model.CpModel()
    rooms = [_room(model, "c1", "courtyard", (0, 5000), (0, 10000), 3000, 3000)]
    terms = S._add_position_prior_terms(model, _cfg(style_preset="Kerala"), rooms, 0, 0)
    assert _zones_of(terms) == {"C"}


def test_zone_membership_is_reified_once_per_room_across_both_terms():
    """The whole point of the shared cache: Vastu and position priors ask the
    same question, so the cols/rows bools must be built exactly once."""
    model = cp_model.CpModel()
    rooms = [_room(model, "k1", "kitchen", (0, 5000), (0, 10000), 3000, 3000)]
    cfg = _cfg(style_preset="Kerala")
    cache: dict = {}
    S._add_vastu_terms(model, cfg, rooms, 0, 0, zone_cache=cache)
    S._add_position_prior_terms(model, cfg, rooms, 0, 0, zone_cache=cache)
    names = [v.name for v in model.proto.variables]
    assert names.count("vcol0_k1") == 1
    assert names.count("vrow0_k1") == 1


def test_the_reward_cannot_be_claimed_from_outside_the_zone():
    """One-directional reification again: nothing forces `posp_` false, only
    the enforced zone membership stops the solver taking a free bonus."""
    model = cp_model.CpModel()
    # Pinned hard into the SW corner of a 9 x 15 m plot: never in C.
    rooms = [_room(model, "c1", "courtyard", (0, 0), (0, 0), 2000, 2000)]
    terms = S._add_position_prior_terms(model, _cfg(style_preset="Kerala"), rooms, 0, 0)
    assert terms
    assert _bonus_of(model, terms) == 0


@pytest.mark.slow
def test_position_prior_does_not_alter_vastu_hard_exclusions():
    """The uplift spec's safety constraint stays load-bearing under the bonus.

    Kerala's corpus puts a toilet in C nearly half the time, so this is the
    case where the new reward pulls hardest against the exclusion.
    """
    cfg = _cfg(
        num_bedrooms=2,
        style_preset="Kerala",
        corpus_priors_enabled=True,
        vastu_enabled=True,
    )
    layout = S.solve_layout(cfg)
    assert layout is not None
    checked = 0
    for floor in (layout.ground_floor, layout.first_floor):
        if floor is None:
            continue
        for room in floor.rooms:
            if room.type not in ("toilet", "wc_only", "bathroom_master"):
                continue
            checked += 1
            zone = zone_for_point(
                room.x + room.width / 2,
                room.y + room.depth / 2,
                cfg.plot_x_extent,
                cfg.plot_y_extent,
                resolve_north_angle(cfg),
            )
            assert zone not in ("NE", "C"), f"{room.type} {room.id} landed in {zone}"
    assert checked >= 2


# ── Corpus-mined shape usage (Task 11) ───────────────────────────────────────
#
# Task 11 is NOT an `_add_*_prior_terms` objective term. Template choice is
# resolved in plain Python before the CP-SAT model exists (see the solver's
# SHAPE USAGE IS NOT A DECISION VARIABLE note), so these tests exercise a
# pre-model gate, not a `(cost, var)` pair. The flag-off posture is unchanged:
# spy on the gate and assert it is never consulted.


def _templatable_types() -> list[str]:
    return sorted(S._TEMPLATE_TYPES)


def _spy_gate(monkeypatch) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    real = S._shape_usage_allows_template

    def spy(cfg, room_id, room_type):
        seen.append((room_id, room_type))
        return real(cfg, room_id, room_type)

    monkeypatch.setattr(S, "_shape_usage_allows_template", spy)
    return seen


def test_shape_gate_never_consulted_when_templates_are_disallowed(monkeypatch):
    """`allow_shape_templates` off is the outer gate: nothing corpus runs."""
    seen = _spy_gate(monkeypatch)
    layout = S.solve_layout(
        _cfg(
            style_preset="Tibetan-Buddhist",
            corpus_priors_enabled=True,
            allow_shape_templates=False,
        )
    )
    assert layout is not None
    assert seen == []
    assert all(r.template == "RECT" for r in layout.ground_floor.rooms)


def test_shape_gate_never_consulted_when_corpus_priors_are_off(monkeypatch):
    """The two flags are independent gates; either one off means no gate call.

    With `corpus_priors_enabled` off the pre-change behaviour must survive
    exactly: every eligible room is templated, unconditionally.
    """
    seen = _spy_gate(monkeypatch)
    layout = S.solve_layout(
        _cfg(
            style_preset="Tibetan-Buddhist",
            corpus_priors_enabled=False,
            allow_shape_templates=True,
        )
    )
    assert layout is not None
    assert seen == []
    templated_types = {
        r.type
        for floor in (layout.ground_floor, layout.first_floor)
        if floor is not None
        for r in floor.rooms
        if r.template != "RECT"
    }
    assert templated_types, (
        "pre-change behaviour must survive: some eligible room should still "
        "be templated unconditionally with the gate never consulted"
    )


def test_shape_gate_is_consulted_when_both_flags_are_on(monkeypatch):
    seen = _spy_gate(monkeypatch)
    layout = S.solve_layout(
        _cfg(
            style_preset="Tibetan-Buddhist",
            corpus_priors_enabled=True,
            allow_shape_templates=True,
        )
    )
    assert layout is not None
    assert seen, "gate was never consulted with both flags on"
    assert {rtype for _, rtype in seen} <= set(_templatable_types())


def test_templating_is_still_reachable_with_both_flags_on():
    """Real rates are near zero -- confirm the gate can still fire, not just run.

    A plausible failure mode for a near-always-False gate is that templating
    becomes unreachable in practice even though the code path is exercised.
    Tibetan-Buddhist `living` at plot_x_extent=10.1 is a verified hit -- pin
    it so a future corpus refresh that silently zeroes the rate everywhere is
    caught here rather than discovered by its absence.

    plot_x_extent=10.1, not 10.0 (Task 11's original pin): the seed a
    follow-up fix widened to also cover setbacks (previously only
    style/extents/bedrooms/room -- see `_shape_usage_allows_template`'s
    seed construction) changes the sha256 draw for every existing pinned
    input, including this one. 10.0 stopped being a hit under the new seed;
    10.1 was re-verified as one (both directly via
    `_shape_usage_allows_template` and end-to-end via `solve_layout`).
    """
    cfg = _cfg(
        style_preset="Tibetan-Buddhist",
        corpus_priors_enabled=True,
        allow_shape_templates=True,
        plot_x_extent=10.1,
    )
    layout = S.solve_layout(cfg)
    assert layout is not None
    templates = {
        r.template
        for floor in (layout.ground_floor, layout.first_floor)
        if floor is not None
        for r in floor.rooms
    }
    assert templates - {"RECT"}, "templating should still be reachable, not dead code"


def test_a_zero_rate_room_type_is_never_templated(monkeypatch):
    """p_nonrect == 0 means the corpus never saw this shape: stay RECT.

    This is the direction that actually matters on real data -- `living` and
    `dining` sit at 0.0 in most styles, while the pre-change code templated
    them 100% of the time whenever the flag was on.
    """
    monkeypatch.setattr(S, "get_shape_usage_prior", lambda cfg, rt: 0.0)
    cfg = _cfg(
        style_preset="Kerala",
        corpus_priors_enabled=True,
        allow_shape_templates=True,
    )
    layout = S.solve_layout(cfg)
    assert layout is not None
    for floor in (layout.ground_floor, layout.first_floor):
        if floor is None:
            continue
        assert all(r.template == "RECT" for r in floor.rooms)


def test_a_certain_room_type_is_always_templated(monkeypatch):
    """p_nonrect == 1 must never be rejected by the draw (strict `<` on 1.0)."""
    monkeypatch.setattr(S, "get_shape_usage_prior", lambda cfg, rt: 1.0)
    cfg = _cfg(
        style_preset="Kerala",
        corpus_priors_enabled=True,
        allow_shape_templates=True,
    )
    for rtype in _templatable_types():
        assert S._shape_usage_allows_template(cfg, f"{rtype}_0", rtype) is True


def test_the_draw_is_deterministic_across_calls():
    cfg = _cfg(style_preset="Kerala", corpus_priors_enabled=True)
    first = [
        S._shape_usage_allows_template(cfg, f"living_{i}", "living") for i in range(25)
    ]
    second = [
        S._shape_usage_allows_template(cfg, f"living_{i}", "living") for i in range(25)
    ]
    assert first == second


def test_the_draw_frequency_tracks_the_prior(monkeypatch):
    """The gate reproduces the corpus rate in aggregate, not per room."""
    monkeypatch.setattr(S, "get_shape_usage_prior", lambda cfg, rt: 0.3)
    cfg = _cfg(style_preset="Kerala", corpus_priors_enabled=True)
    hits = sum(
        S._shape_usage_allows_template(cfg, f"living_{i}", "living")
        for i in range(2000)
    )
    assert 0.25 <= hits / 2000 <= 0.35


def test_the_draw_varies_with_the_plot(monkeypatch):
    """Two different plots in one style must not share a single verdict.

    A plan carries at most one `living`, so seeding on room id alone would
    freeze the answer per style and the corpus rate could never show up.
    """
    monkeypatch.setattr(S, "get_shape_usage_prior", lambda cfg, rt: 0.5)
    verdicts = {
        S._shape_usage_allows_template(
            _cfg(
                style_preset="Kerala",
                corpus_priors_enabled=True,
                plot_x_extent=x,
            ),
            "living_0",
            "living",
        )
        for x in (8.0, 9.0, 10.0, 11.0, 12.0, 13.0)
    }
    assert verdicts == {True, False}


def test_real_corpus_data_suppresses_a_kerala_living_room():
    """No monkeypatch: Kerala's corpus records living at p_nonrect == 0.0."""
    cfg = _cfg(
        style_preset="Kerala",
        corpus_priors_enabled=True,
        allow_shape_templates=True,
    )
    assert S.get_shape_usage_prior(cfg, "living") == 0.0
    assert S._shape_usage_allows_template(cfg, "living_0", "living") is False


def test_an_unknown_style_suppresses_every_template():
    """No style block means p_nonrect 0.0 everywhere -- no corpus-wide fallback."""
    cfg = _cfg(
        style_preset=None,
        corpus_priors_enabled=True,
        allow_shape_templates=True,
    )
    for rtype in _templatable_types():
        assert S._shape_usage_allows_template(cfg, f"{rtype}_0", rtype) is False
