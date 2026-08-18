"""Task 18 — Vastu checks span every floor, and the main entrance breaks
frontage ties toward the auspicious zones.

The entrance half of this file is deliberately heavy on *inertness* pinning.
`_place_main_entrance` only ever considers the y-min (road-facing) frontage, so
every candidate shares a y and can differ only across ONE row of the 3x3 Vastu
grid. On two of the four road sides that row contains no N/NE/E cell at all, so
the tie-break provably cannot fire — including on `PlotConfig`'s default
`road_side="S"`. That is a design boundary, not a bug, so it is pinned here
rather than left to be rediscovered.
"""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from app.engine.geometry import buildable_polygon
from app.engine.models import ComplianceResult, FloorPlan, Layout, PlotConfig, Room
from app.engine.plan_geometry import EWT, _ObstacleIndex, _place_main_entrance
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


# ── entrance tie-break half ──────────────────────────────────────────────────


# Hand-measured front (y-min) row of the 3x3 grid, one cell per third of the
# frontage, on a 12x12 plot. Literals, not recomputed from zone_for_point.
FRONT_ROW = {
    "S": ["SW", "S", "SE"],
    "N": ["NE", "N", "NW"],
    "E": ["NW", "W", "SW"],
    "W": ["SE", "E", "NE"],
}
# The tie-break prefers N/NE/E. Only two road sides put such a cell on the
# front row; on the other two it is provably inert.
TIE_BREAK_CAN_FIRE = {"N", "W"}


@pytest.mark.parametrize("road_side", ["S", "N", "E", "W"])
def test_front_row_zones_are_pinned_per_road_side(road_side):
    north = north_angle_for_road_side(road_side)
    row = [zone_for_point(x, 0.5, 12.0, 12.0, north) for x in (2.0, 6.0, 10.0)]
    assert row == FRONT_ROW[road_side]
    can_fire = any(z in ("N", "NE", "E") for z in row)
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


# Geometry A: the near-gate candidate sits in the HIGH-x third, the far one in
# the LOW-x third. gate_x = 6.0, so the high-x room wins on distance alone.
GEOM_A = [(1.2, 3.8, "living"), (6.4, 10.8, "living")]
# Geometry B: mirrored — the near-gate candidate is in the LOW-x third.
GEOM_B = [(1.2, 5.6, "living"), (8.2, 10.8, "living")]


def test_tie_break_fires_on_a_north_road():
    """road_side='N' puts NE on the low-x third. The distance winner is the
    high-x room (NW, inauspicious); Vastu must flip the door to the low-x one."""
    cfg = _cfg(road_side="N")
    off = _entrance(_front(GEOM_A), _cfg(road_side="N", vastu_enabled=False), False)
    on = _entrance(_front(GEOM_A), cfg, True)
    assert off is not None and on is not None
    assert off.cx > 6.0, f"expected the high-x room to win on distance, got {off.cx}"
    assert on.cx < 4.0, f"Vastu did not move the entrance to the NE third: {on.cx}"


def test_tie_break_fires_on_a_west_road():
    """road_side='W' mirrors it: NE is on the HIGH-x third."""
    cfg = _cfg(road_side="W")
    off = _entrance(_front(GEOM_B), _cfg(road_side="W", vastu_enabled=False), False)
    on = _entrance(_front(GEOM_B), cfg, True)
    assert off is not None and on is not None
    assert off.cx < 6.0, f"expected the low-x room to win on distance, got {off.cx}"
    assert on.cx > 8.0, f"Vastu did not move the entrance to the NE third: {on.cx}"


@pytest.mark.parametrize("road_side", ["S", "E"])
@pytest.mark.parametrize("geom", [GEOM_A, GEOM_B])
def test_tie_break_is_inert_on_south_and_east_roads(road_side, geom):
    """Pinned limitation: the front row on a S or E road holds no N/NE/E cell,
    so enabling Vastu cannot move the entrance. `road_side='S'` is the
    PlotConfig default, i.e. the most common configuration."""
    on = _entrance(_front(geom), _cfg(road_side=road_side), True)
    off = _entrance(_front(geom), _cfg(road_side=road_side, vastu_enabled=False), False)
    assert on is not None and off is not None
    assert on.cx == off.cx


def test_vastu_never_outranks_room_type():
    """The auspicious key is ranked BELOW `prio`: an auspicious dining room must
    not beat an inauspicious living room."""
    cfg = _cfg(road_side="N")
    # low-x third = NE (auspicious) but only a dining room;
    # high-x third = NW (inauspicious) with the living room.
    rooms = _front([(1.2, 3.8, "dining"), (6.4, 10.8, "living")])
    door = _entrance(rooms, cfg, True)
    assert door is not None
    assert door.cx > 6.0, f"Vastu overrode room-type priority: {door.cx}"


def test_vastu_disabled_config_does_not_move_the_entrance():
    """Threading a cfg with vastu_enabled=False must behave like passing None."""
    rooms = _front(GEOM_A)
    disabled = _cfg(road_side="N", vastu_enabled=False)
    assert _entrance(rooms, disabled, True).cx == _entrance(rooms, disabled, False).cx


def test_drawing_path_threads_vastu_cfg():
    """build_floor_drawing must pass its cfg down, or the drawn entrance would
    differ from the one the Vastu-aware placement chose."""
    from app.engine.plan_geometry import build_floor_drawing

    fp = FloorPlan(floor=0, floor_type="ground", rooms=_front(GEOM_A))
    on = build_floor_drawing(fp, _cfg(road_side="N"))
    off = build_floor_drawing(fp, _cfg(road_side="N", vastu_enabled=False))
    on_md = next(o for o in on.openings if getattr(o, "is_main", False))
    off_md = next(o for o in off.openings if getattr(o, "is_main", False))
    assert off_md.cx > 6.0
    assert on_md.cx < 4.0
