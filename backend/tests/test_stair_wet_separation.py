"""Staircase / wet-room separation invariants.

Production regression (project "MyLatest", 2026-07): the first-floor stair
core was solved 0.90 m wide with a toilet as its only partition long enough
to take a door — the stair/bed_1 wall ran just 0.90 m, short of the 1.13 m
a 900 mm leaf plus its two 115 mm jambs needs. `derive_openings` therefore
had exactly one legal wall left and put the stair's door into the toilet, so
the WC opened straight onto the landing and was itself reachable only
through the stair.

The fix is two-sided and both sides are asserted here:

* the solver must guarantee the stair core a circulation partition long
  enough for a real door (otherwise no door-placement rule can help — ban
  the toilet wall and the staircase simply ends up with no door at all);
* `derive_openings` must never put a door in a wall shared by a wet room
  and the staircase.
"""

import pytest

from app.engine.geometry import buildable_polygon
from app.engine.models import PlotConfig
from app.engine.plan_geometry import (
    _CIRCULATION_TYPES,
    _PARKING_TYPES,
    _STAIR_DOOR_MIN_RUN_M,
    _WET_TYPES,
    derive_columns,
    derive_openings,
    derive_walls,
)
from app.engine.standards import OpeningStandards

# Rooms abut across one internal wall (115 mm) plus post-solve snap jitter.
_ABUT_TOL = 0.2


def _mylatest_cfg() -> PlotConfig:
    """The exact production config that produced the stair→toilet door:
    60 x 40 ft (18.288 x 12.192 m), 2BHK, 2 attached toilets, G+1, road E.
    """
    return PlotConfig(
        plot_length=12.192,
        plot_width=18.288,
        setback_front=1.524,
        setback_rear=1.524,
        setback_left=0.914,
        setback_right=0.914,
        num_bedrooms=2,
        toilets=2,
        parking=True,
        city="other",
        road_side="E",
        vastu_enabled=True,
        attached_toilets=True,
    )


def _standard_cfg() -> PlotConfig:
    return PlotConfig(
        plot_length=15.0,
        plot_width=12.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=0.9,
        setback_right=0.9,
        num_bedrooms=3,
        toilets=2,
        parking=True,
        city="other",
        road_side="S",
        vastu_enabled=False,
    )


def _shared_wall_run(a, b, tol: float = _ABUT_TOL) -> float:
    """Length (m) of the wall `a` and `b` actually share; 0 if they don't abut."""
    x_ov = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
    y_ov = min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y)
    if abs(a.x + a.width - b.x) < tol or abs(b.x + b.width - a.x) < tol:
        return max(y_ov, 0.0)  # vertical partition — run is the y overlap
    if abs(a.y + a.depth - b.y) < tol or abs(b.y + b.depth - a.y) < tol:
        return max(x_ov, 0.0)
    return 0.0


def _doors_on_room(room, doors, tol: float = 0.13):
    out = []
    for d in doors:
        if d.is_horizontal:
            on_edge = (
                abs(d.cy - room.y) < tol or abs(d.cy - (room.y + room.depth)) < tol
            )
            inside = room.x - tol <= d.cx <= room.x + room.width + tol
        else:
            on_edge = (
                abs(d.cx - room.x) < tol or abs(d.cx - (room.x + room.width)) < tol
            )
            inside = room.y - tol <= d.cy <= room.y + room.depth + tol
        if on_edge and inside:
            out.append(d)
    return out


def _floor_plan(layout, floor_idx: int):
    return layout.ground_floor if floor_idx == 0 else layout.first_floor


_FLOORS = [0, 1]

#: (layout fixture, floor) cases, asserted over `generate()` output — i.e. over
#: whatever survives RANKING into the top 3.
#:
#: These cases are NOT a safety net on their own, and the file used to claim
#: they were: an earlier version of this comment said "only the UPPER-floor band
#: is shared (`archetypes._stair_band_rooms`), which is why every first-floor
#: case passes". That was false. Both first-floor cases were failing on
#: `layout_c` until commit e11e500 (the E/W Vastu grid fix) changed the zone
#: map, hence the Vastu score, hence the ranking — `layout_c` simply stopped
#: reaching the top 3. The bug did not move; the test stopped looking at it.
#: (`layout_c` passed the band to `_stair_band_rooms` without `reverse=True`
#: even though its stair sits at the band's TRAILING edge, so the toilet — not
#: the circulation filler — ended up hard against the stair core.)
#:
#: The real net is `test_archetype_*_direct` below, which calls every archetype
#: builder directly and cannot be silenced by a scoring tweak. Keep these
#: generate()-level cases as integration coverage, not as the invariant.
#:
#: Gotcha when extending this: `generate()` REASSIGNS layout ids to A/B/C, so
#: the layout reported as "A" is NOT necessarily `layout_a()` — identify the
#: archetype from its room ids and geometry, never from the layout id.
_CASES = [
    ("mylatest_layouts", 0),
    ("mylatest_layouts", 1),
    ("standard_layouts", 0),
    ("standard_layouts", 1),
]


@pytest.fixture(scope="module")
def mylatest_layouts():
    from app.engine.generator import generate

    layouts = generate(_mylatest_cfg())
    assert layouts, "expected at least one layout for the MyLatest config"
    return layouts


@pytest.fixture(scope="module")
def standard_layouts():
    from app.engine.generator import generate

    layouts = generate(_standard_cfg())
    assert layouts, "expected at least one layout for the standard config"
    return layouts


@pytest.mark.parametrize("fixture,floor_idx", _CASES)
def test_staircase_gets_a_doorable_circulation_wall(fixture, floor_idx, request):
    """The stair core shares enough wall with a circulation room for a real
    door leaf plus jambs. This is what makes the wet-wall ban below safe:
    banning the toilet partition is only tenable if another legal wall exists.
    """
    for layout in request.getfixturevalue(fixture):
        fp = _floor_plan(layout, floor_idx)
        # Mirror solver.py's own hard constraint exactly: a true circulation
        # room if the floor has one, else any ordinary (non-wet, non-parking)
        # room — solver.py's own comment calls a bedroom door "poor practice,
        # an unsolvable plan is worse" and accepts it as a last resort. A
        # floor with zero circulation rooms at all (an all-bedroom/utility
        # solver plate) is legal under that fallback, so the test has to
        # accept the same fallback rather than only the ideal case.
        targets = [r for r in fp.rooms if r.type in _CIRCULATION_TYPES]
        if not targets:
            targets = [
                r
                for r in fp.rooms
                if r.type not in _WET_TYPES
                and r.type not in _PARKING_TYPES
                and r.type != "staircase"
            ]
        for stair in [r for r in fp.rooms if r.type == "staircase"]:
            runs = [_shared_wall_run(stair, other) for other in targets]
            assert runs and max(runs) >= _STAIR_DOOR_MIN_RUN_M - 1e-6, (
                f"{layout.id} floor {floor_idx}: staircase {stair.id} has no "
                f"circulation partition >= {_STAIR_DOOR_MIN_RUN_M} m "
                f"(best run {max(runs, default=0.0):.3f} m) — its door has "
                "nowhere legal to go"
            )


@pytest.mark.parametrize("fixture,floor_idx", _CASES)
def test_no_door_in_a_wet_room_staircase_wall(fixture, floor_idx, request):
    """A WC/bath must never open onto the stair landing, in either direction —
    one door in a shared wall serves both rooms, so the wall itself is banned.
    """
    for layout in request.getfixturevalue(fixture):
        fp = _floor_plan(layout, floor_idx)
        buildable = buildable_polygon(
            _mylatest_cfg() if "mylatest" in fixture else _standard_cfg()
        )
        walls = derive_walls(fp.rooms, buildable)
        columns = derive_columns(walls)
        openings = derive_openings(
            fp.rooms, walls, columns, OpeningStandards(), buildable, floor=floor_idx
        )
        doors = [o for o in openings if o.kind == "door"]
        stairs = [r for r in fp.rooms if r.type == "staircase"]
        wets = [r for r in fp.rooms if r.type in _WET_TYPES]
        for stair in stairs:
            stair_doors = _doors_on_room(stair, doors)
            for wet in wets:
                if _shared_wall_run(stair, wet) <= 0:
                    continue
                shared = [d for d in stair_doors if d in _doors_on_room(wet, doors)]
                assert not shared, (
                    f"{layout.id} floor {floor_idx}: door at "
                    f"{[(round(d.cx, 2), round(d.cy, 2)) for d in shared]} sits in "
                    f"the wall shared by staircase {stair.id} and wet room {wet.id}"
                )


@pytest.mark.parametrize("floor_idx", [0, 1])
@pytest.mark.parametrize("fixture", ["mylatest_layouts", "standard_layouts"])
def test_every_staircase_still_has_a_door(fixture, floor_idx, request):
    """Guard against the ban above being satisfied by simply leaving the
    staircase doorless — the failure mode a naive wall ban introduces.
    """
    for layout in request.getfixturevalue(fixture):
        fp = _floor_plan(layout, floor_idx)
        buildable = buildable_polygon(
            _mylatest_cfg() if "mylatest" in fixture else _standard_cfg()
        )
        walls = derive_walls(fp.rooms, buildable)
        columns = derive_columns(walls)
        openings = derive_openings(
            fp.rooms, walls, columns, OpeningStandards(), buildable, floor=floor_idx
        )
        doors = [o for o in openings if o.kind == "door"]
        for stair in (r for r in fp.rooms if r.type == "staircase"):
            assert _doors_on_room(stair, doors), (
                f"{layout.id} floor {floor_idx}: staircase {stair.id} has no door"
            )


# ---------------------------------------------------------------------------
# Direct-archetype invariants
#
# Parametrised over every archetype builder and both configs, bypassing
# `generate()` and its ranking entirely. A regression here cannot be hidden by
# a scoring change the way the generate()-level cases above were (see the
# _CASES comment).
# ---------------------------------------------------------------------------

_ARCHETYPE_NAMES = [
    "layout_a",
    "layout_b",
    "layout_c",
    "layout_d",
    "layout_e",
    "layout_f",
]
_CFGS = {"mylatest": _mylatest_cfg, "standard": _standard_cfg}


def _archetype_floors(archetype_name: str, cfg_name: str):
    """Yield (floor_plan, cfg) for every floor the archetype actually builds."""
    from app.engine import archetypes

    cfg = _CFGS[cfg_name]()
    layout = getattr(archetypes, archetype_name)(cfg)
    if layout is None:  # layout_f declines some plots
        pytest.skip(f"{archetype_name} returns no layout for the {cfg_name} config")
    for fp in (
        layout.ground_floor,
        layout.first_floor,
        layout.second_floor,
        layout.basement_floor,
    ):
        if fp is not None:
            yield fp, cfg


def _stair_door_targets(fp):
    """Mirror solver.py's own hard constraint: circulation rooms if the floor
    has any, else any ordinary (non-wet, non-parking) room as a last resort."""
    targets = [r for r in fp.rooms if r.type in _CIRCULATION_TYPES]
    if not targets:
        targets = [
            r
            for r in fp.rooms
            if r.type not in _WET_TYPES
            and r.type not in _PARKING_TYPES
            and r.type != "staircase"
        ]
    return targets


@pytest.mark.parametrize("cfg_name", sorted(_CFGS))
@pytest.mark.parametrize("archetype_name", _ARCHETYPE_NAMES)
def test_archetype_staircase_gets_a_doorable_circulation_wall_direct(
    archetype_name, cfg_name
):
    """Every archetype, every floor: the stair core shares at least a door
    leaf plus jambs of wall with a circulation room.

    `layout_c`'s first floor violated this with a best run of exactly 0.000 m
    on both configs — its stair sits at the trailing edge of the band, but the
    call to `_stair_band_rooms` omitted `reverse=True`, so the toilet took the
    edge against the stair and the Family Lounge / Landing was pushed to the
    far end of the strip.
    """
    for fp, _cfg in _archetype_floors(archetype_name, cfg_name):
        targets = _stair_door_targets(fp)
        for stair in [r for r in fp.rooms if r.type == "staircase"]:
            runs = [_shared_wall_run(stair, other) for other in targets]
            best = max(runs, default=0.0)
            assert best >= _STAIR_DOOR_MIN_RUN_M - 1e-6, (
                f"{archetype_name}/{cfg_name} floor {fp.floor}: staircase "
                f"{stair.id} has no circulation partition >= "
                f"{_STAIR_DOOR_MIN_RUN_M} m (best run {best:.3f} m) — its door "
                "has nowhere legal to go"
            )


@pytest.mark.parametrize("cfg_name", sorted(_CFGS))
@pytest.mark.parametrize("archetype_name", _ARCHETYPE_NAMES)
def test_archetype_no_door_in_a_wet_room_staircase_wall_direct(
    archetype_name, cfg_name
):
    """The other half of the same invariant, straight off the archetype: no
    door may sit in a wall shared by the staircase and a WC/bath."""
    for fp, cfg in _archetype_floors(archetype_name, cfg_name):
        buildable = buildable_polygon(cfg)
        walls = derive_walls(fp.rooms, buildable)
        columns = derive_columns(walls)
        openings = derive_openings(
            fp.rooms, walls, columns, OpeningStandards(), buildable, floor=fp.floor
        )
        doors = [o for o in openings if o.kind == "door"]
        wets = [r for r in fp.rooms if r.type in _WET_TYPES]
        for stair in [r for r in fp.rooms if r.type == "staircase"]:
            stair_doors = _doors_on_room(stair, doors)
            assert stair_doors, (
                f"{archetype_name}/{cfg_name} floor {fp.floor}: staircase "
                f"{stair.id} has no door at all — a wet-wall ban satisfied by "
                "leaving the stair doorless is not a fix"
            )
            for wet in wets:
                if _shared_wall_run(stair, wet) <= 0:
                    continue
                shared = [d for d in stair_doors if d in _doors_on_room(wet, doors)]
                assert not shared, (
                    f"{archetype_name}/{cfg_name} floor {fp.floor}: door at "
                    f"{[(round(d.cx, 2), round(d.cy, 2)) for d in shared]} sits "
                    f"in the wall shared by staircase {stair.id} and wet room "
                    f"{wet.id}"
                )
