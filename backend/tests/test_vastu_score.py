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


def test_alias_types_inherit_the_generic_rule() -> None:
    """`parking_4w` is the token models.py tells new layouts to prefer; without
    the alias only the deprecated `parking` would carry a Vastu opinion."""
    checked = 0
    for alias, target in VASTU_RULE_ALIASES.items():
        for x, y in ((7.5, 7.5), (0.5, 0.5), (5.0, 5.0), (0.5, 7.5)):
            assert vastu_room_score(_room(alias, x, y), 10.0, 10.0, 0.0) == (
                vastu_room_score(_room(target, x, y), 10.0, 10.0, 0.0)
            )
            checked += 1
    assert checked == 4 * len(VASTU_RULE_ALIASES)
    # Not vacuous: at least one of those positions is a non-neutral verdict.
    assert vastu_room_score(_room("bathroom_master", 7.5, 7.5), 10.0, 10.0, 0.0) == 0.0
    assert vastu_room_score(_room("parking_4w", 4.0, 0.5), 10.0, 10.0, 0.0) == 1.0


def test_an_alias_does_not_chain() -> None:
    """One hop only. A chained lookup would be a silent way for an alias to a
    non-existent rule to resolve to something unrelated."""
    assert "garage" not in VASTU_ROOM_RULES
    assert VASTU_RULE_ALIASES["garage"] in VASTU_ROOM_RULES


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
