"""Vastu as a CP-SAT objective term (Task 17).

Deliberately structured to avoid the two traps `tests/CLAUDE.md` and this
branch's history call out:

* **No test here solves twice and compares geometry.** CP-SAT is not
  deterministic across runs, and the branch already carries two flaky tests
  built that way. The "disabled leaves the model unchanged" guarantee is
  asserted on MODEL CONSTRUCTION (no zone vars are built) rather than on two
  solutions being equal.
* The solve-based tests assert properties that hold for *any* feasible
  solution (a hard constraint was respected; a layout exists at all), so they
  do not depend on which incumbent the search happens to return.
"""

from __future__ import annotations

import pytest
from ortools.sat.python import cp_model

from app.engine import solver as S
from app.engine.models import PlotConfig
from app.engine.vastu import (
    ZONE_GRID_ROAD_S,
    _rule_for,
    resolve_north_angle,
    zone_for_point,
)

_HARD_TYPES = ("toilet", "wc_only", "bathroom_master")


def _cfg(vastu: bool, **kw) -> PlotConfig:
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
        vastu_enabled=vastu,
        road_side="S",
    )
    base.update(kw)
    return PlotConfig(**base)


def _zone_of(room, cfg: PlotConfig) -> str:
    return zone_for_point(
        room.x + room.width / 2,
        room.y + room.depth / 2,
        cfg.plot_x_extent,
        cfg.plot_y_extent,
        resolve_north_angle(cfg),
    )


# ── Hard exclusions are derived from the rules, not hardcoded ────────────────


def test_hard_excluded_zones_are_the_avoid_cells_of_eligible_types():
    """Expectations are LITERALS, not re-derived from the code under test.

    `toilet` (and its two aliases) list NE and C in their `avoid` tier, so both
    are hard-excluded. `staircase` does NOT: its rule is
    {"preferred": ["NE"], "acceptable": [], "avoid": []}, so hard-excluding it
    from NE — as the plan's draft did — would have the constraint forbid the
    single zone its own objective term rewards most, and cap every staircase at
    the neutral verdict. `kitchen` avoids NE and C too but is not an eligible
    type, so it stays entirely soft.
    """
    assert S._vastu_hard_excluded_zones("toilet") == frozenset({"NE", "C"})
    assert S._vastu_hard_excluded_zones("wc_only") == frozenset({"NE", "C"})
    assert S._vastu_hard_excluded_zones("bathroom_master") == frozenset({"NE", "C"})
    assert S._vastu_hard_excluded_zones("staircase") == frozenset()
    assert S._vastu_hard_excluded_zones("kitchen") == frozenset()
    assert S._vastu_hard_excluded_zones("bedroom") == frozenset()
    assert S._vastu_hard_excluded_zones("not_a_room_type") == frozenset()


def test_every_hard_excluded_cell_is_an_avoid_cell():
    """The plan's "Safety (Global Constraints)" clause, made checkable.

    A hard constraint the scorer disagrees with would have the model fight its
    own objective on every solve, so no zone may be forbidden unless the rules
    file already marks it `avoid` for that room type.
    """
    excluded_something = 0
    for room_type in S.VASTU_HARD_EXCLUDE_TYPES:
        rule = _rule_for(room_type)
        assert rule is not None, f"{room_type} has no rule to derive from"
        for zone in S._vastu_hard_excluded_zones(room_type):
            assert zone in rule["avoid"], f"{room_type}/{zone} is not an avoid cell"
            excluded_something += 1
    # Literal, not derived from the data it guards: 3 eligible types x the 2
    # zones each of them avoids.
    assert excluded_something == 6


# ── The reified zone predicate reproduces `zone_for_point` ───────────────────


@pytest.mark.parametrize("angle", [0.0, 90.0, 180.0, 270.0, 37.5, -22.0])
@pytest.mark.parametrize("plot", [(9.0, 15.0), (10.0, 10.0), (7.0, 11.0)])
def test_band_predicate_reproduces_zone_for_point_away_from_boundaries(
    plot: tuple[float, float], angle: float
):
    """The integer half-planes are the float band test, up to `margin`.

    Both encodings are exact away from a band boundary; within `margin` of one
    they may pick either side, because `_vastu_bands` rounds cos/sin (and
    because `math.cos(math.radians(90))` is 6.1e-17 rather than 0, which decides
    the verdict for a centroid sitting exactly ON a boundary).
    """
    plot_w, plot_l = plot
    bands = S._vastu_bands(S._mm(plot_w), S._mm(plot_l), angle)
    compared = 0
    for i in range(0, int(plot_w / 0.05) + 1):
        x = round(i * 0.05, 3)
        for j in range(0, int(plot_l / 0.05) + 1):
            y = round(j * 0.05, 3)
            cx2, cy2 = 2 * S._mm(x), 2 * S._mm(y)
            east = bands.ex * cx2 + bands.ey * cy2 + bands.ec
            north = bands.nx * cx2 + bands.ny * cy2 + bands.nc
            if min(abs(abs(east) - bands.band), abs(abs(north) - bands.band)) <= (
                bands.margin
            ):
                continue  # boundary sliver — either side is acceptable
            compared += 1
            assert S._vastu_zone_of_centroid_mm(cx2, cy2, bands) == zone_for_point(
                x, y, plot_w, plot_l, angle
            ), f"zone mismatch at ({x}, {y}) on {plot} at {angle} deg"
    # Literal floor, not derived from the sweep: the smallest plot here is
    # 7 x 11 m = 141 x 221 lattice points, and the excluded slivers are a
    # fraction of a percent, so anything near this count means the loop ran.
    assert compared > 20_000


def test_hard_exclusion_never_leaks_a_zone_the_scorer_still_reads_as_excluded():
    """`_vastu_escape_bounds` must forbid a strict SUPERSET of the float cell.

    If the two disagreed in the other direction the solver could satisfy the
    constraint with a toilet that `vastu_room_score` still reads as sitting in
    NE — the hard constraint would be decorative.
    """
    checked = 0
    for plot_w, plot_l in [(9.0, 15.0), (10.0, 10.0), (12.0, 12.5)]:
        for angle in [0.0, 90.0, 180.0, 270.0, 37.5]:
            bands = S._vastu_bands(S._mm(plot_w), S._mm(plot_l), angle)
            for i in range(0, int(plot_w / 0.05) + 1):
                x = round(i * 0.05, 3)
                for j in range(0, int(plot_l / 0.05) + 1):
                    y = round(j * 0.05, 3)
                    cx2, cy2 = 2 * S._mm(x), 2 * S._mm(y)
                    east = bands.ex * cx2 + bands.ey * cy2 + bands.ec
                    north = bands.nx * cx2 + bands.ny * cy2 + bands.nc
                    actual = zone_for_point(x, y, plot_w, plot_l, angle)
                    for ri in range(3):
                        for ci in range(3):
                            if ZONE_GRID_ROAD_S[ri][ci] != actual:
                                continue
                            checked += 1
                            escaped = any(
                                (sign < 0 and value <= bound)
                                or (sign > 0 and value >= bound)
                                for value, index, is_row in (
                                    (north, ri, True),
                                    (east, ci, False),
                                )
                                for sign, bound in S._vastu_escape_bounds(
                                    index, bands, is_row
                                )
                            )
                            assert not escaped, (
                                f"({x}, {y}) reads as {actual} at {angle} deg on "
                                f"{plot_w}x{plot_l} but the exclusion would allow it"
                            )
    # Literal: 3 plots x 5 angles x one cell per lattice point, and the
    # smallest lattice here is 201 x 251.
    assert checked > 100_000


# ── Costs cannot be reduced by shrinking a badly-placed room ─────────────────


def test_zone_cost_grades_the_verdict_tiers():
    """Literal costs for each tier of `toilet`'s rule at VASTU_WEIGHT=300000."""
    assert S.VASTU_WEIGHT == 300_000
    assert S._vastu_zone_cost("toilet", "E") == 0  # preferred
    assert S._vastu_zone_cost("toilet", "NW") == 0  # preferred
    assert S._vastu_zone_cost("toilet", "S") == 90_000  # acceptable (0.7)
    assert S._vastu_zone_cost("toilet", "SE") == 300_000  # avoid (0.0)
    assert S._vastu_zone_cost("living", "C") == 165_000  # no opinion (0.45)
    assert S._vastu_zone_cost("staircase", "NE") == 0  # preferred, not forbidden


def _one_room_terms(width_mm: int, depth_mm: int, room_type: str = "kitchen"):
    """Build the Vastu terms for a single room of a given fixed size."""
    model = cp_model.CpModel()
    cfg = _cfg(True)
    x = model.new_int_var(0, 9000, "x")
    y = model.new_int_var(0, 15000, "y")
    w = model.new_int_var(width_mm, width_mm, "w")
    d = model.new_int_var(depth_mm, depth_mm, "d")
    rv = S._RoomVar(
        room_id="r1",
        room_type=room_type,
        room_name="R1",
        floor=0,
        x=x,
        y=y,
        w=w,
        d=d,
        xe=model.new_int_var(0, 9000, "xe"),
        ye=model.new_int_var(0, 15000, "ye"),
        template="RECT",
        shape_ratio=1.0,
    )
    return S._add_vastu_terms(model, cfg, [rv], 0, 0)


def test_zone_costs_are_the_same_multiset_whatever_the_room_size():
    """Half of the anti-shrink property: the COST of a cell is area-free.

    `vastu_layout_score` is area-weighted, and room width/depth ARE decision
    variables — so mirroring that weighting here would let the solver improve
    the objective by shrinking an ill-placed room toward `fit.min_area` instead
    of moving it. A 1.2 x 1.0 m room and a 5 x 4 m room of the same type
    therefore produce the same cost multiset.

    This is NOT the whole property, and the version of this test that claimed
    it was shipped a real bug: an area-free cost still leaves `w`/`d` inside
    the *cell* predicate, so the solver could shrink to move its centroid
    across a band boundary. The other half —
    `test_enabling_vastu_does_not_change_the_chosen_room_size` — is what pins
    that, by solving.
    """
    small = sorted(cost for cost, _ in _one_room_terms(1200, 1000))
    large = sorted(cost for cost, _ in _one_room_terms(5000, 4000))
    assert small, "no Vastu terms were produced at all"
    assert small == large


def _best_size_for_pinned_room(
    x_mm: int, y_mm: int, vastu: bool, room_type: str = "bedroom"
) -> tuple[int, int]:
    """Solve a one-room model that trades size against Vastu, return (w, d).

    The room's anchor is PINNED (as a room boxed in by neighbours effectively
    is) and only `w`/`d` are free, under the production growth reward — the
    objective is `-(w + d)`, `size_terms`' 1-per-mm coefficient — plus, when
    `vastu` is set, this task's zone terms. So the solve answers exactly one
    question: does enabling Vastu make the solver pick a smaller room?

    Single-worker and fully determined by the objective (no tie between two
    different sizes at the optimum), so this does not repeat the
    solve-twice-and-compare-geometry pattern `tests/CLAUDE.md` forbids.
    """
    model = cp_model.CpModel()
    cfg = _cfg(True)
    x = model.new_int_var(x_mm, x_mm, "x")
    y = model.new_int_var(y_mm, y_mm, "y")
    w = model.new_int_var(1000, 4000, "w")
    d = model.new_int_var(1000, 4000, "d")
    rv = S._RoomVar(
        room_id="r1",
        room_type=room_type,
        room_name="R1",
        floor=0,
        x=x,
        y=y,
        w=w,
        d=d,
        xe=model.new_int_var(0, 9000, "xe"),
        ye=model.new_int_var(0, 15000, "ye"),
        template="RECT",
        shape_ratio=1.0,
    )
    obj = [-w, -d]
    if vastu:
        obj += [cost * var for cost, var in S._add_vastu_terms(model, cfg, [rv], 0, 0)]
    model.minimize(sum(obj))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    status = solver.solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return solver.value(w), solver.value(d)


@pytest.mark.parametrize(
    ("x_mm", "y_mm"),
    [
        pytest.param(3000, 4000, id="C-to-S-by-halving-depth"),
        pytest.param(2000, 4000, id="C-westward-by-halving-width"),
        pytest.param(4000, 4000, id="E-to-SE"),
        pytest.param(5000, 9000, id="NE-to-E"),
        pytest.param(5000, 1000, id="SE-band-hop"),
    ],
)
def test_enabling_vastu_does_not_change_the_chosen_room_size(x_mm: int, y_mm: int):
    """Turning Vastu on must never make the solver pick a SMALLER room.

    Shrinking a room by D moves its centroid by D/2, so leaving `w`/`d` inside
    the zone predicate lets the solver buy a cheaper cell through the geometry
    even though the cost itself is area-free. The exchange rate makes that
    decisive rather than theoretical: one zone change is worth up to
    VASTU_WEIGHT = 300 000 against a growth reward of 1 per mm.

    Every case here is a MEASURED regression of the pre-fix code, e.g. at
    (3.0 m, 4.0 m) a bedroom went 4.0 x 4.0 m -> 4.0 x 2.0 m, 16 m2 -> 8 m2,
    purely to drag its centroid from C into S. `_add_vastu_terms` reifies the
    soft cells on an anchor point built from the room's CONSTANT minimum
    extents for exactly this reason.
    """
    assert _best_size_for_pinned_room(x_mm, y_mm, vastu=False) == (4000, 4000), (
        "sanity: without Vastu the growth reward alone must max the room out"
    )
    assert _best_size_for_pinned_room(x_mm, y_mm, vastu=True) == (4000, 4000)


def _solved_zone_of(x_mm: int, y_mm: int, size_mm: int = 1000) -> set[str]:
    """Solve a one-room model and return the zones whose cost bool came back true.

    Unlike `_one_room_terms` this SOLVES, so it exercises the reified band
    constraints in `_add_vastu_terms` — a second, independent transcription of
    the band logic that `_vastu_zone_of_centroid_mm` only mirrors. Mutations
    that invert or neuter that transcription leave the returned `(cost, var)`
    pairs untouched and are invisible without a solve.

    `living` is the room type because it has a non-zero cost in eight of the
    nine cells (only its preferred N is free), so almost every point forces
    exactly one bool; the model is minimised so the half-reification cannot
    set a bool the constraints do not force.
    """
    model = cp_model.CpModel()
    cfg = _cfg(True)
    x = model.new_int_var(x_mm, x_mm, "x")
    y = model.new_int_var(y_mm, y_mm, "y")
    w = model.new_int_var(size_mm, size_mm, "w")
    d = model.new_int_var(size_mm, size_mm, "d")
    rv = S._RoomVar(
        room_id="r1",
        room_type="living",
        room_name="R1",
        floor=0,
        x=x,
        y=y,
        w=w,
        d=d,
        xe=model.new_int_var(0, 9000, "xe"),
        ye=model.new_int_var(0, 15000, "ye"),
        template="RECT",
        shape_ratio=1.0,
    )
    terms = S._add_vastu_terms(model, cfg, [rv], 0, 0)
    # Literal, hand-counted, not derived from the grid: 9 cells minus the one
    # `living` prefers (N, verdict 1.0 -> cost 0, no bool built).
    assert len(terms) == 8
    model.minimize(sum(cost * var for cost, var in terms))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    status = solver.solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return {var.name.split("_")[-1] for _, var in terms if solver.value(var) == 1}


@pytest.mark.parametrize(
    ("centre_x", "centre_y", "expected", "charged"),
    [
        (1.5, 2.5, "SW", True),
        (4.5, 2.5, "S", True),
        (7.5, 2.5, "SE", True),
        (1.5, 7.5, "W", True),
        (4.5, 7.5, "C", True),
        (7.5, 7.5, "E", True),
        (1.5, 12.5, "NW", True),
        # N is `living`'s preferred cell: cost 0, so no bool is built for it
        # and NOTHING may be charged. A mutation that reads the band upside
        # down charges S (300 000) here, so this case is not a free pass.
        (4.5, 12.5, "N", False),
        (7.5, 12.5, "NE", True),
    ],
)
def test_solved_band_bools_charge_the_cell_the_room_is_actually_in(
    centre_x: float, centre_y: float, expected: str, charged: bool
):
    """The MODEL's band transcription, solved — not the reference reimplementation.

    `test_band_predicate_reproduces_zone_for_point_away_from_boundaries` pins
    `_vastu_zone_of_centroid_mm`, which the constraints in `_add_vastu_terms`
    only mirror; and the end-to-end toilet test rides on the hard exclusion,
    which bypasses these bools by design. So without this test the entire soft
    objective can be switched off — every cost bool left unconstrained and
    minimised to zero — with the suite still green.

    The expected zone is a LITERAL per case, never `_vastu_zone_of_centroid_mm`
    of the same point: an assertion that imports its own expected value from
    the code under test passes on a shared bug. The cross-check against the
    reference below is additional, not the assertion.
    """
    size = 1000
    x_mm = S._mm(centre_x) - size // 2
    y_mm = S._mm(centre_y) - size // 2
    assert _solved_zone_of(x_mm, y_mm, size) == ({expected} if charged else set())
    # Additional, not sole: the same point read by the pure reference.
    bands = S._vastu_bands(S._mm(9.0), S._mm(15.0), 0.0)
    assert (
        S._vastu_zone_of_centroid_mm(2 * x_mm + size, 2 * y_mm + size, bands)
        == expected
    )


def test_rooms_without_a_rule_get_no_vastu_vars_at_all():
    """Mirrors `vastu_layout_score`'s exclusion: no rule means no weight.

    A `duct` scores NEUTRAL under `_verdict`, which is an *opinion*, not the
    absence of one — paying 0.55 x VASTU_WEIGHT to place a room Vastu is silent
    about would spend the search budget on nothing.
    """
    assert _rule_for("duct") is None
    assert _one_room_terms(1200, 1000, room_type="duct") == []


# ── Model construction is untouched when the feature is off ─────────────────


def test_no_zone_vars_are_added_when_vastu_is_disabled(monkeypatch):
    """Regression guard, asserted on the MODEL, not on two solutions.

    The natural form of this test — solve twice with vastu off and compare the
    geometry — is exactly the pattern `tests/CLAUDE.md` forbids and the pattern
    that already made two tests on this branch flaky. Counting the vars the
    builder adds is deterministic and needs no solve at all.
    """
    calls: list[bool] = []
    real = S._add_vastu_terms

    def spy(model, cfg, room_vars, ox, oy):
        calls.append(cfg.vastu_enabled)
        return real(model, cfg, room_vars, ox, oy)

    monkeypatch.setattr(S, "_add_vastu_terms", spy)
    # Tiny budgets: this test cares about what gets BUILT, not about solution
    # quality, and the module-level budgets exist to be tuned by tests.
    monkeypatch.setattr(S, "PHASE1_DET_BUDGET", 0.05)
    monkeypatch.setattr(S, "PHASE2_DET_BUDGET", 0.05)

    S.solve_layout(_cfg(False))
    assert calls == [], "the Vastu model builder ran with vastu_enabled=False"

    S.solve_layout(_cfg(True))
    assert calls, "the Vastu model builder never ran with vastu_enabled=True"


# ── End-to-end: the constraint holds and the plot stays solvable ────────────


@pytest.mark.slow
def test_toilets_never_land_in_ne_or_centre_when_vastu_enabled():
    """Property of ANY feasible solution, so no dependence on the incumbent."""
    cfg = _cfg(True)
    layout = S.solve_layout(cfg)
    assert layout is not None, "solver must stay feasible with Vastu constraints"
    checked = 0
    for floor in (layout.ground_floor, layout.first_floor):
        if floor is None:
            continue
        for room in floor.rooms:
            if room.type not in _HARD_TYPES:
                continue
            checked += 1
            assert _zone_of(room, cfg) not in {"NE", "C"}, (
                f"{room.type} {room.id} landed in a hard-excluded zone"
            )
    # Literal: the config asks for 2 toilets, so at least 2 wet rooms exist.
    assert checked >= 2


@pytest.mark.slow
@pytest.mark.parametrize(
    "kw",
    [
        pytest.param({}, id="road-S"),
        pytest.param({"road_side": "N"}, id="road-N"),
        pytest.param({"north_angle_deg": 37.5}, id="off-axis-north"),
        pytest.param(
            {
                "plot_y_extent": 12.0,
                "plot_x_extent": 7.5,
                "setback_front": 2.0,
                "setback_rear": 1.0,
                "setback_left": 0.9,
                "setback_right": 0.9,
                "num_bedrooms": 3,
                "toilets": 2,
            },
            id="tight-plot",
        ),
    ],
)
def test_solver_stays_feasible_with_vastu_enabled(kw: dict):
    """Over-constraining is the real risk — preferences must stay soft.

    The tight case is a 7.5 x 12 m plot (5.7 x 9.0 m = 51.3 m2 buildable
    plate, before wall thickness) carrying 3
    bedrooms and 2 toilets, and the off-axis case is the one that actually
    regressed during development: at a larger `_VASTU_BAND_SCALE` the zone
    coefficients grew to ~2e9 and CP-SAT stopped finding ANY solution inside
    its budget for both `road_side="N"` and `north_angle_deg=37.5`.
    """
    assert S.solve_layout(_cfg(True, **kw)) is not None


@pytest.mark.slow
def test_a_failed_vastu_solve_falls_back_to_a_layout_without_it(monkeypatch):
    """Vastu must never be the reason a user gets no plan at all."""
    attempts: list[bool] = []
    real = S._solve_one

    def flaky(*args, **kwargs):
        steering = kwargs.get("vastu_steering", True)
        attempts.append(steering)
        if steering:
            return None  # pretend the Vastu model missed its budget
        return real(*args, **kwargs)

    monkeypatch.setattr(S, "_solve_one", flaky)
    layout = S.solve_layout(_cfg(True))
    assert attempts == [True, False]
    assert layout is not None


def test_the_fallback_does_not_fire_when_vastu_is_disabled():
    """A plot that is genuinely unsolvable must not pay for a second solve."""
    attempts: list[bool] = []

    def never(steering: bool):
        attempts.append(steering)
        return None

    assert S._vastu_feasibility_fallback(_cfg(False), never) is None
    assert attempts == [True]

    attempts.clear()
    assert S._vastu_feasibility_fallback(_cfg(True), never) is None
    assert attempts == [True, False]


def test_bands_decouple_the_axes_at_the_cardinal_angles():
    """Sanity on the derivation: at 0 deg north is +y and east is +x, and each
    axis is normalised by its OWN plot extent.

    The second half is the bug `vastu.zone_for_point` documents at length —
    rotating in metres instead of normalised space mixes a 9 m width with a
    15 m length and folds corners onto edges. Here that would show up as
    `ex == ny`; correct is `ex / ny == plot_l / plot_w == 15 / 9`, expressed
    below as a cross-multiplication so it does not depend on the band scale.
    The tolerance is the integer rounding of the two coefficients carried
    through the multipliers: 0.5 * 9 + 0.5 * 15 = 12.
    """
    bands = S._vastu_bands(9000, 15000, 0.0)
    assert bands.ey == 0 and bands.nx == 0
    assert bands.ex > 0 and bands.ny > 0
    assert bands.ex != bands.ny, "the axes were normalised by the same extent"
    assert abs(bands.ex * 9 - bands.ny * 15) <= 12

    # At 90 deg the roles swap: north is +x, east is +y (and the sign flips).
    turned = S._vastu_bands(9000, 15000, 90.0)
    assert turned.ex == 0 and turned.ny == 0
    assert turned.nx > 0 and turned.ey < 0
