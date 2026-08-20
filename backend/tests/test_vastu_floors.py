"""Task 18 — Vastu checks span every floor, and the main entrance breaks
frontage ties toward the auspicious zones.

The entrance half of this file is deliberately heavy on *inertness* pinning.
`_place_main_entrance` only ever considers the y-min (road-facing) frontage, so
every candidate shares a y and can differ only across ONE row of the 3x3 Vastu
grid. The sourced N/NE/E rule reaches that row on north and east roads; the
south road (`PlotConfig`'s default) reaches it via the product-owner SE override
and the west road via the matching NW override — both prefer the auspicious end
of the facing wall. Only the END cells are sanctioned on S/W, so their middle
cells ("S" and "W") stay inert and are pinned inauspicious here.
"""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from app.engine.geometry import buildable_polygon
from app.engine.models import ComplianceResult, FloorPlan, Layout, PlotConfig, Room
from app.engine.plan_geometry import (
    EWT,
    _ObstacleIndex,
    _place_main_entrance,
    entrance_auspicious_zones,
)
from app.engine.standards import get_opening_standards
from app.engine.vastu import check_vastu, north_angle_for_road_side, zone_for_point


def _cfg(**over) -> PlotConfig:
    base = dict(
        plot_length=12.0,
        plot_width=12.0,
        setback_front=1.5,
        setback_rear=1.5,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=3,
        toilets=2,
        parking=False,
        vastu_enabled=True,
        road_side="S",
    )
    base.update(over)
    return PlotConfig(**base)


# ── all-floors half ──────────────────────────────────────────────────────────


def test_first_floor_rooms_are_checked():
    """A toilet in NE on the FIRST floor must be reported — the old engine only
    ever looked at ground_floor.rooms.

    NE *prohibits* toilets, so this lands in `violations`, not `warnings`. (The
    plan's test sketch asserted on `warnings`; the split is `vastu_zones`'
    prohibit-vs-avoid tiers, and a toilet is prohibited in NE/SE/SW/C and merely
    avoided in N.)
    """
    gf = FloorPlan(floor=0, floor_type="ground", rooms=[])
    ff = FloorPlan(
        floor=1,
        floor_type="first",
        rooms=[
            Room(
                id="t",
                name="Zolgrat Upstairs Toilet",
                type="toilet",
                x=9.0,
                y=9.0,
                width=2.0,
                depth=2.0,
            )
        ],
    )
    layout = Layout(
        id="A",
        name="A",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )
    violations, warnings = check_vastu(layout, _cfg(), road_side="S")
    assert any("Zolgrat Upstairs Toilet" in v for v in violations), (
        f"first-floor toilet in NE was not reported; got {violations} / {warnings}"
    )


def test_second_and_basement_floors_are_checked_when_present():
    gf = FloorPlan(floor=0, floor_type="ground", rooms=[])
    ff = FloorPlan(floor=1, floor_type="first", rooms=[])
    sf = FloorPlan(
        floor=2,
        floor_type="second",
        rooms=[
            Room(
                id="t2",
                name="Zolgrat Second Toilet",
                type="toilet",
                x=9.0,
                y=9.0,
                width=2.0,
                depth=2.0,
            )
        ],
    )
    bf = FloorPlan(
        floor=-1,
        floor_type="basement",
        rooms=[
            # N zone merely *avoids* toilets, so this one exercises the
            # `warnings` branch of the same loop.
            Room(
                id="t3",
                name="Zolgrat Basement Toilet",
                type="toilet",
                x=5.0,
                y=9.0,
                width=2.0,
                depth=2.0,
            )
        ],
    )
    layout = Layout(
        id="A",
        name="A",
        ground_floor=gf,
        first_floor=ff,
        second_floor=sf,
        basement_floor=bf,
        compliance=ComplianceResult(passed=True),
    )
    violations, warnings = check_vastu(layout, _cfg(), road_side="S")
    assert any("Zolgrat Second Toilet" in v for v in violations), violations
    assert any("Zolgrat Basement Toilet" in w for w in warnings), warnings


def test_kitchen_and_pooja_checks_span_upper_floors():
    """The kitchen/pooja special cases iterate all floors too — a first-floor
    kitchen in the wrong zone is a real Vastu complaint."""
    gf = FloorPlan(floor=0, floor_type="ground", rooms=[])
    ff = FloorPlan(
        floor=1,
        floor_type="first",
        rooms=[
            # NE corner (x,y high on a S road => NE): wrong for a kitchen.
            Room(id="k", name="K", type="kitchen", x=9.0, y=9.0, width=2.0, depth=2.0),
            # SW corner: wrong for a pooja room.
            Room(id="p", name="P", type="pooja", x=1.0, y=1.0, width=2.0, depth=2.0),
        ],
    )
    layout = Layout(
        id="A",
        name="A",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )
    _violations, warnings = check_vastu(layout, _cfg(), road_side="S")
    assert any("Kitchen is in" in w for w in warnings), warnings
    assert any("Pooja Room is in" in w for w in warnings), warnings


def test_master_bedroom_check_stays_ground_floor_only():
    """`bedrooms[0]` means "master bedroom" only on the ground floor. With no GF
    bedroom, an upper-floor bedroom must NOT be promoted to master and warned
    about — that would be an advisory the user cannot act on."""
    gf = FloorPlan(floor=0, floor_type="ground", rooms=[])
    ff = FloorPlan(
        floor=1,
        floor_type="first",
        rooms=[
            # NE zone on a S road — a non-SW zone, so a master-bedroom check
            # would fire here if it looked at upper floors.
            Room(
                id="b",
                name="Zolgrat Upstairs Bedroom",
                type="bedroom",
                x=9.0,
                y=9.0,
                width=3.0,
                depth=3.0,
            )
        ],
    )
    layout = Layout(
        id="A",
        name="A",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )
    _violations, warnings = check_vastu(layout, _cfg(), road_side="S")
    assert not any("Nairutya" in w for w in warnings), (
        f"upper-floor bedroom was mislabelled as the master bedroom: {warnings}"
    )


def test_ground_floor_master_bedroom_is_still_checked():
    """Guard for the test above: the GF-only rule must not have disabled the
    check outright."""
    gf = FloorPlan(
        floor=0,
        floor_type="ground",
        rooms=[
            Room(
                id="b",
                name="Master",
                type="bedroom",
                x=9.0,
                y=9.0,
                width=3.0,
                depth=3.0,
            )
        ],
    )
    ff = FloorPlan(floor=1, floor_type="first", rooms=[])
    layout = Layout(
        id="A",
        name="A",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )
    _violations, warnings = check_vastu(layout, _cfg(), road_side="S")
    assert any("Nairutya" in w for w in warnings), warnings


def test_stacked_rooms_produce_distinguishable_messages_per_floor():
    """Reading every floor made byte-identical duplicates possible, and they
    reach the user: `generator._apply_vastu` does
    `layout.compliance.warnings.extend(v_warnings)`.

    A G+1's first-floor toilet sits directly above the ground-floor one, same
    name, same (x, y) — so without a floor identifier the user sees the same
    sentence twice with no way to tell which floor is meant. Assert the
    distinguishing substrings as literals.
    """
    rooms = lambda: [  # noqa: E731 - two independent Room objects, same geometry
        Room(id="t", name="Toilet 1", type="toilet", x=9.0, y=9.0, width=2.0, depth=2.0)
    ]
    layout = Layout(
        id="A",
        name="A",
        ground_floor=FloorPlan(floor=0, floor_type="ground", rooms=rooms()),
        first_floor=FloorPlan(floor=1, floor_type="first", rooms=rooms()),
        compliance=ComplianceResult(passed=True),
    )
    violations, _warnings = check_vastu(layout, _cfg(), road_side="S")
    assert len(violations) == 2, violations
    assert len(set(violations)) == 2, f"duplicate, floor-less messages: {violations}"
    assert any("(ground floor)" in v for v in violations), violations
    assert any("(first floor)" in v for v in violations), violations
    # The UI reads these: `status-rail.tsx` filters on `startsWith("[Vastu]")`
    # and strips exactly `"[Vastu] "`, so the prefix and the room name must stay
    # contiguous and intact.
    assert all(v.startswith("[Vastu] Toilet 1 in ") for v in violations), violations


def test_kitchen_and_pooja_messages_carry_the_floor_too():
    """The bespoke kitchen/pooja checks now span floors, so they duplicate the
    same way the general loop does."""
    kitchen = lambda: [  # noqa: E731
        Room(id="k", name="K", type="kitchen", x=9.0, y=9.0, width=2.0, depth=2.0),
        Room(id="p", name="P", type="pooja", x=1.0, y=1.0, width=2.0, depth=2.0),
    ]
    layout = Layout(
        id="A",
        name="A",
        ground_floor=FloorPlan(floor=0, floor_type="ground", rooms=kitchen()),
        first_floor=FloorPlan(floor=1, floor_type="first", rooms=kitchen()),
        second_floor=FloorPlan(floor=2, floor_type="second", rooms=kitchen()),
        compliance=ComplianceResult(passed=True),
    )
    _violations, warnings = check_vastu(layout, _cfg(), road_side="S")
    kitchens = [w for w in warnings if "Kitchen is in" in w]
    poojas = [w for w in warnings if "Pooja Room is in" in w]
    assert len(set(kitchens)) == 3, kitchens
    assert len(set(poojas)) == 3, poojas
    for label in ("(ground floor)", "(first floor)", "(second floor)"):
        assert any(label in w for w in kitchens), (label, kitchens)
        assert any(label in w for w in poojas), (label, poojas)


def test_unknown_floor_type_falls_back_to_the_floor_number():
    """`FloorPlan.floor_type` is an unvalidated `str`. An unrecognised value must
    still yield an identifier rather than dropping it."""
    layout = Layout(
        id="A",
        name="A",
        ground_floor=FloorPlan(floor=0, floor_type="ground", rooms=[]),
        first_floor=FloorPlan(
            floor=3,
            floor_type="mezzanine",
            rooms=[
                Room(
                    id="t",
                    name="Zolgrat Mezzanine Toilet",
                    type="toilet",
                    x=9.0,
                    y=9.0,
                    width=2.0,
                    depth=2.0,
                )
            ],
        ),
        compliance=ComplianceResult(passed=True),
    )
    violations, _warnings = check_vastu(layout, _cfg(), road_side="S")
    assert any("(floor 3)" in v for v in violations), violations


# ── entrance tie-break half ──────────────────────────────────────────────────


# The entrance fixtures use a NON-SQUARE plot on purpose. `zone_for_point`
# normalises x by plot_width and y by plot_length before rotating, and that
# normalisation is the whole reason a 9x15 plot (the routine case on this
# branch) maps correctly. On a square plot the two arguments are
# interchangeable, so a transposed `zone_for_point(x, y, plot_length,
# plot_width, ...)` call is undetectable — which is exactly what a square
# fixture let slip through before.
E_PLOT_W = 9.0
E_PLOT_L = 15.0


def _ecfg(**over) -> PlotConfig:
    """Entrance-half config: non-square, symmetric setbacks unless overridden."""
    return _cfg(plot_width=E_PLOT_W, plot_length=E_PLOT_L, **over)


# Hand-measured front (y-min) row of the 3x3 grid, one cell per third of the
# frontage. Literals, not recomputed from zone_for_point.
FRONT_ROW = {
    "S": ["SW", "S", "SE"],
    "N": ["NE", "N", "NW"],
    "E": ["SE", "E", "NE"],
    "W": ["NW", "W", "SW"],
}
# Which road sides can move the entrance at all: N and E under the sourced
# N/NE/E rule, S under the product-owner SE override, W under the matching NW
# override. Literal on purpose — the rule itself is resolved by production code,
# so widening the shipped rule (or an override) to a cell on a front row makes
# this assertion fail instead of silently agreeing with itself.
TIE_BREAK_CAN_FIRE = {"N", "E", "S", "W"}


@pytest.mark.parametrize("road_side", ["S", "N", "E", "W"])
def test_front_row_zones_are_pinned_per_road_side(road_side):
    north = north_angle_for_road_side(road_side)
    row = [zone_for_point(x, 0.5, E_PLOT_W, E_PLOT_L, north) for x in (1.5, 4.5, 7.5)]
    assert row == FRONT_ROW[road_side]
    # The auspicious set comes from production (`entrance_auspicious_zones`), so
    # this cannot drift from the shipped rule the way a local copy did.
    can_fire = any(z in entrance_auspicious_zones(north) for z in row)
    assert can_fire is (road_side in TIE_BREAK_CAN_FIRE)


def _front(spans: list[tuple[float, float, str]]) -> list[Room]:
    """Frontage rooms at y=1.5 (the front setback line), one per (lo, hi, type)."""
    return [
        Room(
            id=f"r{i}",
            name=f"R{i}",
            type=t,
            x=lo,
            y=1.5,
            width=hi - lo,
            depth=3.0,
        )
        for i, (lo, hi, t) in enumerate(spans)
    ]


def _entrance(rooms: list[Room], cfg: PlotConfig, vastu: bool):
    buildable: Polygon = buildable_polygon(cfg)
    return _place_main_entrance(
        rooms,
        _ObstacleIndex([]),
        get_opening_standards(),
        buildable,
        EWT,
        0.01,
        vastu_cfg=cfg if vastu else None,
    )


# Frontage thirds on a 9 m frontage: [0,3) | [3,6) | [6,9].
# Geometry A: the near-gate candidate sits in the HIGH-x third, the far one in
# the LOW-x third. gate_x = 4.5 (symmetric setbacks), so the high-x room wins on
# distance alone.
GEOM_A = [(1.2, 2.85, "living"), (4.8, 7.8, "living")]
# Geometry B: mirrored — the near-gate candidate is in the LOW-x third.
GEOM_B = [(1.2, 4.2, "living"), (6.15, 7.8, "living")]


def test_tie_break_fires_on_a_north_road():
    """road_side='N' puts NE on the low-x third. The distance winner is the
    high-x room (NW, inauspicious); Vastu must flip the door to the low-x one."""
    cfg = _ecfg(road_side="N")
    off = _entrance(_front(GEOM_A), _ecfg(road_side="N", vastu_enabled=False), False)
    on = _entrance(_front(GEOM_A), cfg, True)
    assert off is not None and on is not None
    assert off.cx > 4.5, f"expected the high-x room to win on distance, got {off.cx}"
    assert on.cx < 3.0, f"Vastu did not move the entrance to the NE third: {on.cx}"


def test_tie_break_fires_on_a_south_road():
    """road_side='S' is the PlotConfig DEFAULT and the whole reason the SE
    override exists: its front row [SW, S, SE] holds no N/NE/E cell, so before
    the override the tie-break could never fire on the commonest configuration.

    SE is the HIGH-x third. GEOM_B's distance winner is the low-x room (SW,
    inauspicious), so only the override can move the door to the high-x one.
    """
    cfg = _ecfg(road_side="S")
    off = _entrance(_front(GEOM_B), _ecfg(road_side="S", vastu_enabled=False), False)
    on = _entrance(_front(GEOM_B), cfg, True)
    assert off is not None and on is not None
    assert off.cx < 4.5, f"expected the low-x room to win on distance, got {off.cx}"
    assert on.cx > 6.0, f"Vastu did not move the entrance to the SE third: {on.cx}"


def test_tie_break_fires_on_an_east_road():
    """road_side='E' mirrors it: the front row is [SE, E, NE], so NE is on the
    HIGH-x third."""
    cfg = _ecfg(road_side="E")
    off = _entrance(_front(GEOM_B), _ecfg(road_side="E", vastu_enabled=False), False)
    on = _entrance(_front(GEOM_B), cfg, True)
    assert off is not None and on is not None
    assert off.cx < 4.5, f"expected the low-x room to win on distance, got {off.cx}"
    assert on.cx > 6.0, f"Vastu did not move the entrance to the NE third: {on.cx}"


def test_tie_break_fires_on_a_west_road():
    """road_side='W' front row is [NW, W, SW]. GEOM_A's distance winner is the
    high-x room (SW, inauspicious); only the NW override can move the door to
    the low-x third."""
    cfg = _ecfg(road_side="W")
    off = _entrance(_front(GEOM_A), _ecfg(road_side="W", vastu_enabled=False), False)
    on = _entrance(_front(GEOM_A), cfg, True)
    assert off is not None and on is not None
    assert off.cx > 4.5, f"expected the high-x room to win on distance, got {off.cx}"
    assert on.cx < 3.0, f"Vastu did not move the entrance to the NW third: {on.cx}"


# ── middle-third coverage ────────────────────────────────────────────────────
#
# Without these, only the NE member of the ("N", "NE", "E") rule was ever
# exercised: every other fixture's candidates land in the OUTER two thirds of
# the frontage, and the middle cell — "N" on a north road, "E" on a west road —
# was never a candidate zone anywhere. Three mutations to the shipped rule
# (widen with "S", drop "N", drop "E") survived the whole file as a result.
#
# Getting a middle-third candidate to *lose* on distance needs asymmetric
# setbacks: `gate_x` is the buildable midpoint, so with equal side setbacks it
# sits dead centre of the middle third and the middle candidate wins the
# distance key outright, which would prove nothing.
#
# Each case is (road_side, setback_left, setback_right, spans, middle_mid):
# the FIRST span is the distance winner in an inauspicious outer third, the
# SECOND is the auspicious middle-third candidate Vastu must flip to.
MIDDLE_THIRD_CASES = [
    # North road, front row [NE, N, NW]. gate_x = (4.5 + 8.1) / 2 = 6.3, in the
    # high-x third; the high-x candidate (NW) wins on distance, and only "N"
    # being in the rule can move the door to the middle third.
    ("N", 4.5, 0.9, [(6.0, 7.5, "living"), (4.5, 6.0, "living")], 5.25),
    # East road, front row [SE, E, NE]. Mirrored: gate_x = (0.9 + 4.5) / 2 =
    # 2.7, in the low-x third; the low-x candidate (SE) wins on distance, and
    # only "E" being in the rule can move the door to the middle third.
    ("E", 0.9, 4.5, [(1.5, 3.0, "living"), (3.0, 4.5, "living")], 3.75),
]


@pytest.mark.parametrize(
    ("road_side", "sb_left", "sb_right", "spans", "middle_mid"),
    MIDDLE_THIRD_CASES,
    ids=["N-middle-is-N", "E-middle-is-E"],
)
def test_tie_break_reaches_the_middle_third(
    road_side, sb_left, sb_right, spans, middle_mid
):
    """The middle cell of the front row is auspicious and Vastu must reach it.

    Fails if the shipped rule drops "N" (north case) or "E" (east case): the
    middle candidate stops being auspicious, both candidates tie at 1, and the
    distance winner — the outer third — keeps the door.
    """
    kw = dict(road_side=road_side, setback_left=sb_left, setback_right=sb_right)
    rooms = _front(spans)
    off = _entrance(rooms, _ecfg(vastu_enabled=False, **kw), False)
    on = _entrance(rooms, _ecfg(**kw), True)
    assert off is not None and on is not None
    outer_lo, outer_hi = spans[0][0], spans[0][1]
    mid_lo, mid_hi = spans[1][0], spans[1][1]
    assert outer_lo <= off.cx <= outer_hi, (
        f"expected the outer-third room to win on distance, got {off.cx}"
    )
    assert mid_lo <= on.cx <= mid_hi, (
        f"Vastu did not move the entrance into the middle third "
        f"(centred {middle_mid}): {on.cx}"
    )


# `test_tie_break_is_inert_on_a_west_road` (and its south-inclusive
# predecessor) lived here — both retired now that south AND west fire via
# their NW/SE overrides, leaving nothing road-wide left to pin as inert. The
# narrower claim that survives, that each override's own MIDDLE cell stays
# inauspicious, is `test_middle_front_row_cell_is_not_auspicious` below.


# Which of the two asymmetric geometries above to reuse when pinning that a
# road side's MIDDLE front-row cell is NOT auspicious. The geometry must be the
# one whose middle candidate LOSES the distance key, otherwise vastu-on equals
# vastu-off for a reason that has nothing to do with the rule.
#
# W borrows the north geometry (gate in the HIGH-x third): candidates are SW
# (outer, wins on distance) and W (middle). Only the NW END of the west front
# row is sanctioned now, so neither SW nor the middle W is auspicious.
# S borrows the east geometry (gate in the LOW-x third): candidates are SW
# (outer, wins on distance) and S (middle). The north geometry would NOT work
# for S: its outer candidate lands in SE, which the override makes auspicious
# AND which already wins on distance, so the middle cell would never be tested.
MIDDLE_THIRD_INERT_GEOMETRY = {"W": MIDDLE_THIRD_CASES[0], "S": MIDDLE_THIRD_CASES[1]}


@pytest.mark.parametrize("road_side", ["S", "W"])
def test_middle_front_row_cell_is_not_auspicious(road_side):
    """The MIDDLE cell of the S and W front rows — "S" on a south road, "W" on a
    west road — must stay inauspicious, and that is the one place the
    outer-third fixtures above never reach.

    South is no longer inert overall (SE fires), but its middle cell must not
    move the door: widening the override from ("SE",) to ("S", "SE") makes this
    fail on the south road. West likewise fires at its NW end now, and widening
    the west override from ("NW",) to ("NW", "W") fails the west case here.
    """
    _rs, sb_left, sb_right, spans, _mid = MIDDLE_THIRD_INERT_GEOMETRY[road_side]
    kw = dict(road_side=road_side, setback_left=sb_left, setback_right=sb_right)
    rooms = _front(spans)
    on = _entrance(rooms, _ecfg(**kw), True)
    off = _entrance(rooms, _ecfg(vastu_enabled=False, **kw), False)
    assert on is not None and off is not None
    assert on.cx == off.cx


def test_vastu_never_outranks_room_type():
    """The auspicious key is ranked BELOW `prio`: an auspicious dining room must
    not beat an inauspicious living room."""
    cfg = _ecfg(road_side="N")
    # low-x third = NE (auspicious) but only a dining room;
    # high-x third = NW (inauspicious) with the living room.
    rooms = _front([(1.2, 2.85, "dining"), (4.8, 7.8, "living")])
    door = _entrance(rooms, cfg, True)
    assert door is not None
    assert door.cx > 4.5, f"Vastu overrode room-type priority: {door.cx}"


def test_vastu_disabled_config_does_not_move_the_entrance():
    """Threading a cfg with vastu_enabled=False must behave like passing None."""
    rooms = _front(GEOM_A)
    disabled = _ecfg(road_side="N", vastu_enabled=False)
    assert _entrance(rooms, disabled, True).cx == _entrance(rooms, disabled, False).cx


def test_explicit_north_angle_overrides_the_road_side():
    """`resolve_north_angle`, not `north_angle_for_road_side(cfg.road_side)`.

    road_side='E' would put NE on the HIGH-x third, so the distance winner
    (also high-x, see GEOM_A) would already be auspicious and the door would not
    move. north_angle_deg=180.0 is the north orientation, which puts NE on the
    LOW-x third — so the door must move there instead.
    """
    rooms = _front(GEOM_A)
    cfg = _ecfg(road_side="E", north_angle_deg=180.0)
    off = _entrance(
        rooms, _ecfg(road_side="E", north_angle_deg=180.0, vastu_enabled=False), False
    )
    on = _entrance(rooms, cfg, True)
    assert off is not None and on is not None
    assert off.cx > 4.5, off.cx
    assert on.cx < 3.0, (
        f"north_angle_deg=180 was ignored in favour of road_side='E': {on.cx}"
    )


def test_explicit_north_angle_of_zero_overrides_the_road_side():
    """`0.0` is the dangerous value: `if cfg.north_angle_deg is not None` is
    correct, but a future `if cfg.north_angle_deg:` would silently fall back to
    the road side.

    road_side='N' would put NE on the LOW-x third, so falling back would move the
    door there. An explicit 0.0 is the south orientation: GEOM_A's high-x
    candidate is SE, which the override makes auspicious AND which already wins
    on distance — so the door must NOT move. The equality therefore still
    catches a `0.0`-treated-as-unset regression.

    This is also the pairing that decided how `entrance_auspicious_zones` is
    keyed: off the RESOLVED angle, not `cfg.road_side`. Keyed off the raw road
    side this plot would be scored with the N/NE/E rule while its zones are the
    south row, and the SE preference would silently not apply to a genuinely
    south-facing plot.
    """
    rooms = _front(GEOM_A)
    cfg = _ecfg(road_side="N", north_angle_deg=0.0)
    on = _entrance(rooms, cfg, True)
    off = _entrance(
        rooms, _ecfg(road_side="N", north_angle_deg=0.0, vastu_enabled=False), False
    )
    assert on is not None and off is not None
    assert on.cx == off.cx, (
        f"an explicit north_angle_deg=0.0 was treated as unset and fell back to "
        f"road_side='N': {on.cx} vs {off.cx}"
    )


def test_drawing_path_threads_vastu_cfg():
    """build_floor_drawing must pass its cfg down, or the drawn entrance would
    differ from the one the Vastu-aware placement chose."""
    from app.engine.plan_geometry import build_floor_drawing

    fp = FloorPlan(floor=0, floor_type="ground", rooms=_front(GEOM_A))
    on = build_floor_drawing(fp, _ecfg(road_side="N"))
    off = build_floor_drawing(fp, _ecfg(road_side="N", vastu_enabled=False))
    on_md = next(o for o in on.openings if getattr(o, "is_main", False))
    off_md = next(o for o in off.openings if getattr(o, "is_main", False))
    assert off_md.cx > 4.5
    assert on_md.cx < 3.0
