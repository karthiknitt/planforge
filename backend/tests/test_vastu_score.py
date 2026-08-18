"""Graded (three-tier) Vastu room rules and area-weighted scoring.

The heart of this file is not the scoring arithmetic — it is the pair of
transpose tests. `vastu_room_rules` was DERIVED from `vastu_zones`, which is
pre-existing data this task did not author, so `vastu_zones` is independent
ground truth. Asserting the two agree cell-by-cell in both directions is worth
far more than any hand-written table of expectations, which would only restate
whatever was typed into the JSON.
"""

from __future__ import annotations

from typing import get_args

import pytest

from app.engine.models import FloorPlan, PlotConfig, Room, RoomType
from app.engine.vastu import (
    VASTU_ROOM_RULES,
    VASTU_RULE_ALIASES,
    VASTU_RULES,
    VERDICT_ACCEPTABLE,
    VERDICT_AVOID,
    VERDICT_NEUTRAL,
    VERDICT_PREFERRED,
    _rule_for,
    resolve_north_angle,
    vastu_layout_score,
    vastu_room_score,
)

ZONES = ("NE", "E", "SE", "S", "SW", "W", "NW", "N", "C")

# Cell counts, pinned so a loop that silently stops iterating fails loudly.
# 41 (room, zone) pairs exist in `vastu_zones`; one of them — "bathroom" in
# E.preferred — was a dead token removed by this task (see the Task 15 report),
# leaving 40 live pairs that must round-trip.
N_TRANSPOSE_PAIRS = 40
N_ROOM_TYPES = 11
N_ACCEPTABLE_CELLS = 6


def _room(rtype: str, x: float, y: float) -> Room:
    return Room(id="r", name="R", type=rtype, x=x, y=y, width=2.0, depth=2.0)


# ── The transpose is faithful ───────────────────────────────────────────────


def test_every_zone_rule_cell_survives_into_the_room_rules() -> None:
    """Forward direction: nothing in `vastu_zones` was dropped or demoted.

    `prohibit` and `avoid` both land in the graded `avoid` tier — a score only
    needs "wrong here", not the violation/warning distinction the binary
    checker needed.
    """
    checked = 0
    for zone in ZONES:
        zone_rule = VASTU_RULES[zone]
        for old_tier, new_tier in (
            ("preferred", "preferred"),
            ("avoid", "avoid"),
            ("prohibit", "avoid"),
        ):
            for room_type in zone_rule[old_tier]:
                rule = VASTU_ROOM_RULES.get(room_type)
                assert rule is not None, (
                    f"{room_type} is tiered in vastu_zones[{zone}].{old_tier} "
                    "but absent from vastu_room_rules"
                )
                assert zone in rule[new_tier], (
                    f"vastu_zones[{zone}].{old_tier} lists {room_type}, but "
                    f"vastu_room_rules[{room_type}].{new_tier} does not list {zone}"
                )
                checked += 1
    assert checked == N_TRANSPOSE_PAIRS


def test_no_preferred_or_avoid_cell_was_invented() -> None:
    """Reverse direction: the two derived tiers contain nothing the source lacks.

    Without this half, the transpose could be faithful *and* padded with
    freehand rules that no ground truth backs.
    """
    checked = 0
    for room_type, rule in VASTU_ROOM_RULES.items():
        for zone in rule["preferred"]:
            assert room_type in VASTU_RULES[zone]["preferred"], (
                f"vastu_room_rules[{room_type}].preferred invents {zone}"
            )
            checked += 1
        for zone in rule["avoid"]:
            zone_rule = VASTU_RULES[zone]
            assert (
                room_type in zone_rule["avoid"] or room_type in zone_rule["prohibit"]
            ), f"vastu_room_rules[{room_type}].avoid invents {zone}"
            checked += 1
    assert checked == N_TRANSPOSE_PAIRS
    assert len(VASTU_ROOM_RULES) == N_ROOM_TYPES


def test_acceptable_may_only_fill_cells_the_zone_rules_left_silent() -> None:
    """`acceptable` is the one genuinely new tier, so it must not overwrite a
    cell the source data already had an opinion about."""
    checked = 0
    for room_type, rule in VASTU_ROOM_RULES.items():
        for zone in rule["acceptable"]:
            zone_rule = VASTU_RULES[zone]
            for tier in ("preferred", "avoid", "prohibit"):
                assert room_type not in zone_rule[tier], (
                    f"acceptable cell ({room_type}, {zone}) contradicts "
                    f"vastu_zones[{zone}].{tier}"
                )
            checked += 1
    assert checked == N_ACCEPTABLE_CELLS


def test_acceptable_cells_are_exactly_the_ones_check_vastu_already_tolerates() -> None:
    """Pins the derivation of the sourced half of the `acceptable` tier.

    `check_vastu` warns for a kitchen outside SE/NW/E and a pooja outside
    NE/N/E; SE and NE are already `preferred`, so the remainder is precisely
    what "tolerated but not ideal" means in this engine. Toilet S/W is the one
    judgement call and is listed here explicitly rather than hidden.
    """
    assert {z for z in VASTU_ROOM_RULES["kitchen"]["acceptable"]} == {"NW", "E"}
    assert {z for z in VASTU_ROOM_RULES["pooja"]["acceptable"]} == {"N", "E"}
    assert {z for z in VASTU_ROOM_RULES["toilet"]["acceptable"]} == {"S", "W"}
    others = {
        rt
        for rt, rule in VASTU_ROOM_RULES.items()
        if rule["acceptable"] and rt not in ("kitchen", "pooja", "toilet")
    }
    assert others == set()


def test_tiers_of_a_room_rule_are_mutually_exclusive() -> None:
    checked = 0
    for room_type, rule in VASTU_ROOM_RULES.items():
        cells = rule["preferred"] + rule["acceptable"] + rule["avoid"]
        assert len(cells) == len(set(cells)), f"{room_type} tiers overlap"
        checked += 1
    assert checked == N_ROOM_TYPES


# ── The rules file cannot carry dead tokens ─────────────────────────────────


def test_every_room_token_in_the_rules_file_is_a_valid_room_type() -> None:
    """Guards the class of bug that let `vastu_zones.E.preferred` carry
    "bathroom" — not a `RoomType` member, so it never matched a room and its
    rule was silently inert."""
    valid = set(get_args(RoomType))
    checked = 0
    for zone in ZONES:
        for tier in ("preferred", "avoid", "prohibit"):
            for token in VASTU_RULES[zone][tier]:
                assert token in valid, f"vastu_zones[{zone}].{tier}: {token!r}"
                checked += 1
    for room_type in VASTU_ROOM_RULES:
        assert room_type in valid, f"vastu_room_rules: {room_type!r}"
        checked += 1
    for alias, target in VASTU_RULE_ALIASES.items():
        assert alias in valid, f"alias key {alias!r} is not a RoomType"
        assert target in VASTU_ROOM_RULES, f"alias {alias!r} targets a missing rule"
        checked += 1
    assert checked == N_TRANSPOSE_PAIRS + N_ROOM_TYPES + len(VASTU_RULE_ALIASES)


def test_every_zone_token_in_the_room_rules_is_a_real_zone() -> None:
    checked = 0
    for room_type, rule in VASTU_ROOM_RULES.items():
        for tier in ("preferred", "acceptable", "avoid"):
            for zone in rule[tier]:
                assert zone in ZONES, f"vastu_room_rules[{room_type}].{tier}: {zone!r}"
                checked += 1
    assert checked == N_TRANSPOSE_PAIRS + N_ACCEPTABLE_CELLS


# ── Scoring ─────────────────────────────────────────────────────────────────
#
# All positional tests use a 10 x 10 plot with north_angle_deg=0 (road south),
# so the band boundaries are at 10/3 and 20/3 on both axes and the 3x3 grid is
#   x<3.33 -> W col,  x>6.67 -> E col;  y<3.33 -> S row,  y>6.67 -> N row.


def test_preferred_placement_scores_one() -> None:
    """Kitchen fully inside SE (Agni), its only preferred zone."""
    assert vastu_room_score(_room("kitchen", 7.5, 0.5), 10.0, 10.0, 0.0) == 1.0


def test_avoid_placement_scores_zero() -> None:
    """Toilet in NE (Ishanya) — `vastu_zones.NE.prohibit`, the single most
    recognised prohibition in the practice. A transpose that dropped the
    prohibit tier would score this 0.45."""
    assert vastu_room_score(_room("toilet", 7.5, 7.5), 10.0, 10.0, 0.0) == 0.0


def test_the_four_verdict_factors_are_the_specified_values() -> None:
    """Pinned as literals, not compared to themselves. Every other test that
    named a constant would happily follow it to a wrong value; this is the one
    place the numbers are actually asserted."""
    assert (VERDICT_PREFERRED, VERDICT_ACCEPTABLE, VERDICT_NEUTRAL, VERDICT_AVOID) == (
        1.0,
        0.7,
        0.45,
        0.0,
    )


def test_acceptable_placement_scores_the_acceptable_factor() -> None:
    """Kitchen in NW is tolerated, not preferred: exactly 0.7, not merely
    somewhere strictly between 0 and 1."""
    assert vastu_room_score(_room("kitchen", 0.5, 7.5), 10.0, 10.0, 0.0) == 0.7


def test_silent_cell_scores_neutral_not_avoid() -> None:
    """Kitchen in W: `vastu_zones` says nothing about it, and silence is
    neither approval nor prohibition."""
    assert vastu_room_score(_room("kitchen", 0.5, 4.0), 10.0, 10.0, 0.0) == 0.45


def test_score_is_area_weighted_not_centroid_only() -> None:
    """A kitchen spanning x=[5.5, 8.5] on a 10 m plot straddles the C/E column
    boundary at x=20/3=6.667. Its geometric split is 38.9% in S and 61.1% in
    SE, which the 40-sample lattice quantises to exactly 0.4 / 0.6.

    So the expected score is 0.4*NEUTRAL(kitchen in S) + 0.6*PREFERRED(SE)
    = 0.4*0.45 + 0.6*1.0 = 0.78. A centroid-only engine would report a flat
    1.0, since the centroid (x=7.0) sits in SE.
    """
    straddling = Room(
        id="k", name="Kitchen", type="kitchen", x=5.5, y=0.5, width=3.0, depth=2.0
    )
    assert vastu_room_score(straddling, 10.0, 10.0, 0.0) == pytest.approx(0.78)
    # The centroid alone would give the undivided SE verdict — pinned so the
    # test still means something if the lattice fractions ever change.
    assert vastu_room_score(_room("kitchen", 6.9, 0.5), 10.0, 10.0, 0.0) == 1.0


def test_unknown_type_is_neutral_even_where_a_known_type_is_prohibited() -> None:
    """A duct has no rule, so it scores neutral in NE — the same NE that scores
    a toilet 0.0. Asserting both halves is what makes this test positional
    rather than vacuous: a bug that made every room neutral would pass the
    duct assertion alone."""
    assert vastu_room_score(_room("duct", 7.5, 7.5), 10.0, 10.0, 0.0) == 0.45
    assert vastu_room_score(_room("toilet", 7.5, 7.5), 10.0, 10.0, 0.0) == 0.0


def test_rotation_moves_the_verdict() -> None:
    """The same kitchen scores 1.0 at north=0 and 0.0 at north=90: the plot
    corner that is SE (kitchen's only preferred zone) on a south-facing plot is
    NE (prohibited) once north is 90 degrees clockwise from +y. Pinning a
    rotated case stops the scorer from quietly ignoring `north_angle_deg`."""
    kitchen = _room("kitchen", 7.5, 0.5)
    assert vastu_room_score(kitchen, 10.0, 10.0, 0.0) == 1.0
    assert vastu_room_score(kitchen, 10.0, 10.0, 90.0) == 0.0


# ── Aliases ─────────────────────────────────────────────────────────────────


# Every alias pinned against a LITERAL, not against `VASTU_RULE_ALIASES` itself.
# The previous guard was `checked == 4 * len(VASTU_RULE_ALIASES)` — derived from
# the very dict it was iterating, so it shrank quietly with the dict: deleting
# `wc_only`, `master_bedroom`, `parking_2w` or `garage` outright left all 22
# tests passing. Without its alias a modern token carries no Vastu opinion at
# all and scores a flat neutral 0.45.
EXPECTED_ALIASES = {
    "master_bedroom": "bedroom",
    "wc_only": "toilet",
    "bathroom_master": "toilet",
    "parking_4w": "parking",
    "parking_2w": "parking",
    "garage": "parking",
}

# (alias, x, y, expected score) — one literal non-neutral verdict per alias, so
# losing any single alias flips its row to the neutral 0.45 and fails loudly.
# NE (7.5, 7.5) prohibits bedroom, toilet and parking alike; SE (7.5, 0.5) is
# silent for all three, which is what makes the neutral value observable.
ALIAS_ANCHORS = (
    ("master_bedroom", 7.5, 7.5, 0.0),
    ("wc_only", 7.5, 7.5, 0.0),
    ("bathroom_master", 7.5, 7.5, 0.0),
    ("parking_4w", 7.5, 7.5, 0.0),
    ("parking_2w", 7.5, 7.5, 0.0),
    ("garage", 7.5, 7.5, 0.0),
    ("master_bedroom", 0.5, 0.5, 1.0),
    ("parking_4w", 4.0, 0.5, 1.0),
    ("parking_2w", 4.0, 0.5, 1.0),
    ("garage", 4.0, 0.5, 1.0),
    ("wc_only", 0.5, 7.5, 1.0),
    ("bathroom_master", 0.5, 7.5, 1.0),
)


def test_the_alias_map_is_exactly_these_six_pairs() -> None:
    """Literal, so deleting an alias or silently retargeting one fails here."""
    assert VASTU_RULE_ALIASES == EXPECTED_ALIASES


@pytest.mark.parametrize(("alias", "x", "y", "expected"), ALIAS_ANCHORS)
def test_each_alias_scores_its_targets_literal_verdict(
    alias: str, x: float, y: float, expected: float
) -> None:
    """`parking_4w` is the token models.py tells new layouts to prefer; without
    the alias only the deprecated `parking` would carry a Vastu opinion.

    Pinned against a literal verdict rather than against the target's own score,
    so this cannot pass by both sides degrading to neutral together.
    """
    assert vastu_room_score(_room(alias, x, y), 10.0, 10.0, 0.0) == expected
    # Not vacuous: the neutral value an unaliased token would take is different.
    assert expected != VERDICT_NEUTRAL


def test_alias_types_inherit_the_generic_rule() -> None:
    """The literal anchors cover one or two zones each; this sweeps all six
    aliases across four zones against their target, catching a partial
    divergence the anchors would miss."""
    checked = 0
    for alias, target in EXPECTED_ALIASES.items():
        for x, y in ((7.5, 7.5), (0.5, 0.5), (5.0, 5.0), (0.5, 7.5)):
            assert vastu_room_score(_room(alias, x, y), 10.0, 10.0, 0.0) == (
                vastu_room_score(_room(target, x, y), 10.0, 10.0, 0.0)
            )
            checked += 1
    assert checked == 24


def test_an_alias_does_not_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """One hop only. A chained lookup would be a silent way for an alias to a
    non-existent rule to resolve to something unrelated.

    This must exercise `_rule_for`, not just assert facts about the data. The
    data-only version of this test could not observe the resolution strategy at
    all: rewriting `_rule_for` to follow aliases in a `while` loop — full
    recursive chaining, exactly what this test forbids — left it passing.

    `passage` -> `garage` -> `parking` is a two-hop path that only exists inside
    this test, since the real alias keys and rule keys are disjoint. One hop
    stops at `garage`, which has no rule of its own, and yields None.
    """
    assert "garage" not in VASTU_ROOM_RULES
    assert VASTU_RULE_ALIASES["garage"] in VASTU_ROOM_RULES

    monkeypatch.setitem(VASTU_RULE_ALIASES, "passage", "garage")
    assert _rule_for("passage") is None, "alias resolution chained past one hop"
    # Control: one hop does resolve, so the None above is the hop limit and not
    # a lookup that is broken outright.
    assert _rule_for("garage") == VASTU_ROOM_RULES["parking"]
    # And the chained target is reachable, so None is not "parking is missing".
    assert vastu_room_score(_room("passage", 7.5, 7.5), 10.0, 10.0, 0.0) == 0.45
    assert vastu_room_score(_room("garage", 7.5, 7.5), 10.0, 10.0, 0.0) == 0.0


# ── Layout score and orientation resolution ─────────────────────────────────


def _cfg(**kwargs: object) -> PlotConfig:
    base: dict[str, object] = dict(
        plot_length=10.0,
        plot_width=10.0,
        setback_front=3.0,
        setback_rear=1.5,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=2,
        toilets=1,
        parking=False,
        vastu_enabled=True,
    )
    base.update(kwargs)
    return PlotConfig(**base)  # type: ignore[arg-type]


def _floor(floor: int, *rooms: Room) -> FloorPlan:
    return FloorPlan(floor=floor, rooms=list(rooms))


def test_layout_score_is_the_mean_over_every_floor() -> None:
    """Ground kitchen in SE (1.0) and a FIRST-floor toilet in NE (0.0) average
    to 50.0 — the first-floor room is counted, which ground-floor-only scoring
    would have missed (it would report 100.0)."""
    floors = [
        _floor(0, _room("kitchen", 7.5, 0.5)),
        _floor(1, _room("toilet", 7.5, 7.5)),
    ]
    assert vastu_layout_score(floors, _cfg(north_angle_deg=0.0)) == 50.0


def test_layout_score_of_an_empty_plan_is_zero() -> None:
    assert vastu_layout_score([_floor(0)], _cfg(north_angle_deg=0.0)) == 0.0
    assert vastu_layout_score([], _cfg(north_angle_deg=0.0)) == 0.0


# ── The three ranking pathologies of a plain mean, pinned as fixed ──────────
#
# `vastu_layout_score` was a plain unweighted mean over all rooms. Task 15's
# review measured three ways that misranks layouts, and every number in the
# "was" column below is that review's own measurement, reproduced against the
# old implementation before this fix. They are literals, not recomputed from
# the code under test.


def _sized(rtype: str, x: float, y: float, w: float, d: float) -> Room:
    return Room(id="r", name="R", type=rtype, x=x, y=y, width=w, depth=d)


def _score(*rooms: Room) -> float:
    return vastu_layout_score([_floor(0, *rooms)], _cfg(north_angle_deg=0.0))


def test_rooms_with_no_rule_do_not_move_the_score() -> None:
    """Pathology (a). A `duct` has no rule, so `_verdict` calls it NEUTRAL 0.45
    — which under a plain mean dragged every layout toward 0.45 rather than
    leaving it alone.

    Was: two prohibited toilets 0.0, +1 duct 15.0, +3 ducts 27.0 — padding a bad
    plan with rooms Vastu is silent about improved it. And two perfect rooms
    100.0 dropped to 81.67 on one duct — padding a good plan hurt it.
    """
    bad = (_room("toilet", 7.5, 7.5), _room("toilet", 7.4, 7.4))
    duct = _room("duct", 5.0, 5.0)
    assert _score(*bad) == 0.0
    assert _score(*bad, duct) == 0.0
    assert _score(*bad, duct, duct, duct) == 0.0

    good = (_room("kitchen", 7.5, 0.5), _room("parking", 4.0, 0.5))
    assert _score(*good) == 100.0
    assert _score(*good, duct) == 100.0


def test_a_ruled_room_in_a_silent_zone_still_counts() -> None:
    """The exclusion is "no rule at all", NOT "verdict came out neutral" — the
    distinction the fix turns on, so it is pinned.

    A kitchen in W is a room Vastu has an opinion about that was placed where
    that opinion is silent; it is assessable and scored a mediocre 0.45, so it
    must dilute a perfect kitchen. A duct, on the same 0.45, must not.
    """
    perfect = _room("kitchen", 7.5, 0.5)
    silent_placement = _room("kitchen", 0.5, 4.0)
    assert vastu_room_score(silent_placement, 10.0, 10.0, 0.0) == 0.45
    assert _score(perfect, silent_placement) == 72.5
    assert _score(perfect, _room("duct", 0.5, 4.0)) == 100.0


def test_a_large_room_outweighs_a_small_one() -> None:
    """Pathology (b). Rooms used to be averaged one-for-one, so 1.44 m2 of
    correctly-placed utility outvoted a 16 m2 master bedroom in the worst zone.

    Was: bedroom alone 20.93, + four 0.36 m2 utilities 84.19 — quadrupled by
    1.4 m2 while the bedroom sat in prohibited NE. Area-weighting moves it to
    27.46, i.e. barely, which is what 8% of the floor area should do.
    """
    bedroom = _sized("bedroom", 6.0, 6.0, 4.0, 4.0)
    utilities = [_sized("utility", 7.5 + i * 0.1, 7.5, 0.6, 0.6) for i in range(4)]
    assert _score(bedroom) == 20.93
    assert _score(bedroom, *utilities) == 27.46


def test_the_score_does_not_drift_with_room_count() -> None:
    """Pathology (c). The same one perfect kitchen used to score 72.5 / 58.75 /
    51.88 at 2 / 4 / 8 total rooms, so a 2BHK variant and a 3BHK variant were
    ranked against different denominators."""
    kitchen = _room("kitchen", 7.5, 0.5)
    duct = _room("duct", 5.0, 5.0)
    for total in (2, 4, 8):
        assert _score(kitchen, *[duct] * (total - 1)) == 100.0, total


def test_a_layout_with_no_ruled_rooms_scores_zero_not_neutral() -> None:
    """The denominator is ruled floor area, so it can be zero while rooms exist.

    0.0, not 45.0: there is no Vastu content to credit, and it is the
    incentive-safe answer — a layout can never *gain* by shedding its last
    ruled room. Zero-area rooms take the same path.
    """
    assert _score(_room("duct", 5.0, 5.0), _room("foyer", 1.0, 1.0)) == 0.0
    assert _score(_sized("kitchen", 7.5, 0.5, 0.0, 0.0)) == 0.0


def test_alias_rooms_are_not_excluded_as_ruleless() -> None:
    """`master_bedroom` reaches a rule only through `VASTU_RULE_ALIASES`, so an
    exclusion test written against `VASTU_ROOM_RULES` alone would silently drop
    the most Vastu-significant room in an Indian plan from the denominator."""
    assert _score(_room("master_bedroom", 7.5, 7.5)) == 0.0
    assert _score(_room("kitchen", 7.5, 0.5), _room("master_bedroom", 7.5, 7.5)) == 50.0


def test_unsurveyed_north_falls_back_to_the_road_side() -> None:
    """`cfg.north_angle_deg` is `float | None`; None must resolve via
    `road_side` and never reach the trigonometry. A west-facing plot is 90
    degrees, so the same kitchen that is preferred on a south-facing plot is
    not preferred here — proving the fallback consults road_side rather than
    defaulting to 0.0.
    """
    floors = [_floor(0, _room("kitchen", 7.5, 0.5))]
    assert (
        vastu_layout_score(floors, _cfg(road_side="S", north_angle_deg=None)) == 100.0
    )
    west = vastu_layout_score(floors, _cfg(road_side="W", north_angle_deg=None))
    assert west != 100.0
    # And it equals the explicitly-surveyed equivalent of that road side.
    assert west == vastu_layout_score(floors, _cfg(north_angle_deg=90.0))


def test_explicit_zero_north_angle_beats_the_road_side() -> None:
    """0.0 is a surveyed value, not a missing one — the classic falsy-check bug."""
    assert resolve_north_angle(_cfg(road_side="W", north_angle_deg=0.0)) == 0.0
    assert resolve_north_angle(_cfg(road_side="W", north_angle_deg=None)) == 90.0


def test_resolve_north_angle_prefers_the_explicit_road_side_argument() -> None:
    """`check_vastu` takes `road_side` as its own parameter, which may differ
    from `cfg.road_side`; the argument must win, as it did before this helper
    existed."""
    cfg = _cfg(road_side="S", north_angle_deg=None)
    assert resolve_north_angle(cfg, "E") == 270.0
    assert resolve_north_angle(cfg) == 0.0
