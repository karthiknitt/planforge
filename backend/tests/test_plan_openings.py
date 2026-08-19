"""Canonical opening derivation invariants (S4.2)."""

import math

from app.engine.geometry import buildable_polygon
from app.engine.plan_geometry import (
    derive_columns,
    derive_openings,
    derive_walls,
    opening_boxes,
    validate_floor_connectivity,
    wall_polygons,
)
from app.engine.standards import OpeningStandards

from tests.helpers.golden import golden_config, golden_layout
from tests.test_plan_geometry import _cfg_9x15, _room

STD = OpeningStandards()
IWT = 0.115


def _openings_for(rooms, cfg, std=STD, floor=0):
    buildable = buildable_polygon(cfg)
    walls = derive_walls(rooms, buildable)
    columns = derive_columns(walls)
    return derive_openings(rooms, walls, columns, std, buildable, floor=floor), walls


def _two_bedrooms():
    return [
        _room("a", 1.23, 1.73, 2.77, 12.04),
        _room("b", 4.115, 1.73, 3.655, 12.04),
    ]


def test_adjacent_rooms_share_one_door():
    openings, _walls = _openings_for(_two_bedrooms(), _cfg_9x15())
    doors = [o for o in openings if o.kind == "door"]
    # ONE shared door in the partition serves both rooms (no door-doubling)
    partition = [d for d in doors if abs(d.cx - 4.0575) < 1e-6]
    assert len(partition) == 1
    assert partition[0].swing_into_room_id == "a"


def test_door_swing_direction_is_room_aware():
    openings, _walls = _openings_for(_two_bedrooms(), _cfg_9x15())
    # skip the road-facing main entrance; assert on the internal partition door
    d = next(o for o in openings if o.kind == "door" and not o.is_main)
    # hinge at the low jamb, leaf along +y, swinging into room "a" (-x side)
    # => counter-clockwise
    assert d.swing_into_room_id == "a"
    assert d.swing_cw is False


def test_wet_room_door_does_not_serve_neighbour():
    rooms = [
        _room("bed", 1.23, 1.73, 2.77, 12.04),
        _room("wc", 4.115, 1.73, 3.655, 12.04, rtype="toilet"),
    ]
    openings, _walls = _openings_for(rooms, _cfg_9x15())
    doors = [o for o in openings if o.kind == "door"]
    # bed must have its own door even though the wc doored the shared gap
    assert {d.swing_into_room_id for d in doors} >= {"bed"}


def test_fit_along_shifts_clear_of_obstacle():
    from app.engine.plan_geometry import _fit_along

    c = _fit_along(2.0, 1.0, 6.0, 0.9, [(2.0, 0.16)])
    assert c is not None
    assert abs(c - 2.0) >= 0.16 + 0.45 - 1e-9
    # no room to shift -> None
    assert _fit_along(2.0, 1.7, 2.3, 0.9, [(2.0, 0.16)]) is None


def test_door_hinge_near_jamb_not_midpoint():
    openings, _walls = _openings_for(_two_bedrooms(), _cfg_9x15())
    d = next(o for o in openings if o.kind == "door" and o.swing_into_room_id == "a")
    # hinge sits at one edge of the opening, on the wall centreline
    assert math.isclose(d.hinge_x, d.cx, abs_tol=1e-9)
    assert math.isclose(abs(d.hinge_y - d.cy), d.width / 2, abs_tol=1e-6)


def test_master_bedroom_gets_window():
    rooms = [
        _room("m", 1.23, 1.73, 2.77, 12.04, rtype="master_bedroom"),
        _room("b", 4.115, 1.73, 3.655, 12.04),
    ]
    openings, _walls = _openings_for(rooms, _cfg_9x15())
    windows = [o for o in openings if o.kind == "window"]
    m_windows = [w for w in windows if 1.115 <= w.cx <= 4.0 or w.cy < 1.73]
    assert m_windows, "master_bedroom got no window (old PDF/SVG bug)"


def test_toilet_ventilator_only_when_exterior():
    rooms = [
        _room("t", 1.23, 1.73, 2.77, 12.04, rtype="toilet"),  # exterior left
        _room("b", 4.115, 1.73, 3.655, 12.04),
    ]
    openings, _walls = _openings_for(rooms, _cfg_9x15())
    vents = [o for o in openings if o.kind == "ventilator"]
    assert len(vents) >= 1
    assert all(
        math.isclose(v.width, STD.ventilator_width_m, abs_tol=1e-9) for v in vents
    )


def test_openings_use_configured_standards():
    custom = OpeningStandards(
        door_width_m=1.0,
        window_width_m=1.5,
        window_max_room_fraction=0.5,
        ventilator_width_m=0.45,
    )
    openings, _walls = _openings_for(_two_bedrooms(), _cfg_9x15(), std=custom)
    doors = [o for o in openings if o.kind == "door" and not o.is_main]
    main = [o for o in openings if o.is_main]
    windows = [o for o in openings if o.kind == "window"]
    assert all(math.isclose(d.width, 1.0, abs_tol=1e-9) for d in doors)
    # the main entrance uses the dedicated main-door width, not door_width_m
    assert main and all(
        math.isclose(m.width, custom.main_door_width_m, abs_tol=1e-9) for m in main
    )
    assert windows and all(w.width <= 1.5 + 1e-9 for w in windows)


def test_no_opening_overlaps_column_or_other_opening_on_fixture():
    layout = golden_layout()
    cfg = golden_config()
    for floor in (layout.ground_floor, layout.first_floor):
        buildable = buildable_polygon(cfg)
        walls = derive_walls(floor.rooms, buildable)
        columns = derive_columns(walls)
        openings = derive_openings(floor.rooms, walls, columns, STD, buildable)
        doors = [o for o in openings if o.kind == "door"]

        def _door_on_room_wall(room, d, tol=0.13):
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
            return on_edge and inside

        for r in floor.rooms:
            if r.type == "passage":
                continue
            assert any(_door_on_room_wall(r, d) for d in doors), (
                f"room {r.id} has no door on any of its walls"
            )
        # opening vs column clearance along the shared wall
        for o in openings:
            for c in columns:
                along_o = o.cx if o.is_horizontal else o.cy
                along_c = c.cx if o.is_horizontal else c.cy
                cross_o = o.cy if o.is_horizontal else o.cx
                cross_c = c.cy if o.is_horizontal else c.cx
                if abs(cross_o - cross_c) > 0.16:
                    continue
                assert abs(along_o - along_c) >= o.width / 2 + 0.15, (
                    f"opening {o.kind}@({o.cx:.2f},{o.cy:.2f}) hits column "
                    f"({c.cx:.2f},{c.cy:.2f})"
                )
        # opening vs opening on the same wall
        for i, a in enumerate(openings):
            for b in openings[i + 1 :]:
                if a.is_horizontal != b.is_horizontal:
                    continue
                cross_a = a.cy if a.is_horizontal else a.cx
                cross_b = b.cy if b.is_horizontal else b.cx
                if abs(cross_a - cross_b) > 1e-6:
                    continue
                along_a = a.cx if a.is_horizontal else a.cy
                along_b = b.cx if b.is_horizontal else b.cy
                assert abs(along_a - along_b) >= (a.width + b.width) / 2 - 1e-9, (
                    f"{a.kind} overlaps {b.kind} at cross={cross_a:.3f}"
                )


def test_opening_boxes_subtract_from_wall_polygons():
    rooms = _two_bedrooms()
    cfg = _cfg_9x15()
    buildable = buildable_polygon(cfg)
    walls = derive_walls(rooms, buildable)
    columns = derive_columns(walls)
    openings = derive_openings(rooms, walls, columns, STD, buildable)
    full = wall_polygons(walls)
    cut = wall_polygons(walls, openings=opening_boxes(openings))
    assert cut["internal"].area < full["internal"].area
    assert cut["external"].area < full["external"].area  # windows cut the ring


# ── Main entrance door (MD) invariants ───────────────────────────────────────
EWT = 0.23
_NO_ENTRY_TYPES = {
    "toilet",
    "wc_only",
    "bathroom_master",
    "utility",
    "parking",
    "staircase",
}


def _golden_openings(floor: int):
    layout = golden_layout()
    cfg = golden_config()
    fp = layout.ground_floor if floor == 0 else layout.first_floor
    buildable = buildable_polygon(cfg)
    walls = derive_walls(fp.rooms, buildable)
    columns = derive_columns(walls)
    openings = derive_openings(fp.rooms, walls, columns, STD, buildable, floor=floor)
    return openings, fp, buildable


def test_ground_floor_has_exactly_one_main_door():
    openings, _fp, _buildable = _golden_openings(floor=0)
    mains = [o for o in openings if o.is_main]
    assert len(mains) == 1


def test_main_door_sits_on_front_external_wall():
    openings, _fp, buildable = _golden_openings(floor=0)
    md = next(o for o in openings if o.is_main)
    assert md.kind == "door"
    assert md.is_horizontal is True
    assert math.isclose(md.cy, buildable.bounds[1] + EWT / 2, abs_tol=1e-6)


def test_main_door_width_is_standard_and_above_nbc_minimum():
    openings, _fp, _buildable = _golden_openings(floor=0)
    md = next(o for o in openings if o.is_main)
    assert math.isclose(md.width, STD.main_door_width_m, abs_tol=1e-9)
    assert md.width >= 0.9  # NBC minimum clear entrance width


def test_first_floor_has_no_main_door():
    openings, _fp, _buildable = _golden_openings(floor=1)
    assert not [o for o in openings if o.is_main]


def test_main_door_room_is_never_parking_stair_or_wet():
    openings, fp, _buildable = _golden_openings(floor=0)
    md = next(o for o in openings if o.is_main)
    room = next(r for r in fp.rooms if r.id == md.swing_into_room_id)
    assert room.type not in _NO_ENTRY_TYPES


def test_main_door_does_not_overlap_other_openings_on_its_wall():
    openings, _fp, _buildable = _golden_openings(floor=0)
    md = next(o for o in openings if o.is_main)
    for o in openings:
        if o is md or o.is_horizontal != md.is_horizontal:
            continue
        if abs(o.cy - md.cy) > 1e-6:  # same horizontal wall line
            continue
        assert abs(o.cx - md.cx) >= (o.width + md.width) / 2 - 1e-9, (
            f"MD overlaps {o.kind}@({o.cx:.2f},{o.cy:.2f})"
        )


def test_no_main_door_when_only_parking_faces_front():
    cfg = _cfg_9x15()
    buildable = buildable_polygon(cfg)
    # only the parking room touches the front (y-min) plate edge; the bedroom
    # is set back behind it and never faces the road
    rooms = [
        _room("park", 1.23, 1.73, 6.54, 3.0, rtype="parking"),
        _room("bed", 1.23, 5.0, 6.54, 8.77),
    ]
    walls = derive_walls(rooms, buildable)
    columns = derive_columns(walls)
    openings = derive_openings(rooms, walls, columns, STD, buildable, floor=0)
    assert not [o for o in openings if o.is_main]


# ── Door-graph navigability (Task 2) ─────────────────────────────────────────


def _doors_on_room(room, doors, tol=0.13):
    """Doors whose cut sits on one of `room`'s four wall lines."""
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


def _ensuite_rooms():
    """FF-style plate: front passage, a master bedroom, its en-suite bath.

    The en-suite (`toilet_ens_0`) also borders the passage, so only the
    Task-1 attachment convention forces its door into `bedroom_0`.
    """
    return [
        _room("passage", 1.23, 1.73, 6.54, 1.5, rtype="passage"),
        _room("bedroom_0", 1.23, 3.345, 2.77, 10.425),
        _room("toilet_ens_0", 4.115, 3.345, 3.655, 3.655, rtype="bathroom_master"),
    ]


def test_ensuite_door_opens_into_attached_bedroom():
    openings, _walls = _openings_for(_ensuite_rooms(), _cfg_9x15())
    doors = [o for o in openings if o.kind == "door"]
    # the en-suite/bedroom partition is the vertical wall at x≈4.0575
    partition = [d for d in doors if not d.is_horizontal and abs(d.cx - 4.0575) < 0.13]
    assert partition, "no door on the en-suite/bedroom partition"
    assert all(d.swing_into_room_id == "bedroom_0" for d in partition)


def test_toilet_has_exactly_one_door():
    rooms = _ensuite_rooms()
    openings, _walls = _openings_for(rooms, _cfg_9x15())
    doors = [o for o in openings if o.kind == "door"]
    toilet = next(r for r in rooms if r.id == "toilet_ens_0")
    assert len(_doors_on_room(toilet, doors)) == 1


def test_bedroom_has_one_entry_from_circulation():
    rooms = _ensuite_rooms()
    openings, _walls = _openings_for(rooms, _cfg_9x15())
    doors = [o for o in openings if o.kind == "door"]
    bedroom = next(r for r in rooms if r.id == "bedroom_0")
    passage = next(r for r in rooms if r.id == "passage")
    # a door on the bedroom/passage wall (horizontal, y≈3.2875) = the entry
    entry = [
        d
        for d in _doors_on_room(bedroom, doors)
        if d.is_horizontal and abs(d.cy - 3.2875) < 0.13
    ]
    assert len(entry) == 1
    assert _doors_on_room(passage, doors)  # passage is reached by the entry door


def _kitchen_sandwich_rooms():
    """Kitchen bordered by two circulation rooms (living above, dining below) —
    each independently doors its own gap to the kitchen, so without a
    single-door rule the kitchen ends up with two doors."""
    return [
        _room("a_living", 1.23, 1.73, 6.54, 1.5, rtype="living"),
        _room("b_kitchen", 1.23, 3.345, 6.54, 3.655, rtype="kitchen"),
        _room("c_dining", 1.23, 7.115, 6.54, 6.655, rtype="dining"),
    ]


def test_kitchen_has_exactly_one_door():
    rooms = _kitchen_sandwich_rooms()
    openings, _walls = _openings_for(rooms, _cfg_9x15())
    doors = [o for o in openings if o.kind == "door"]
    kitchen = next(r for r in rooms if r.type == "kitchen")
    assert len(_doors_on_room(kitchen, doors)) == 1


def test_kitchen_keeps_circulation_door_not_dropped_to_zero():
    rooms = _kitchen_sandwich_rooms()
    openings, _walls = _openings_for(rooms, _cfg_9x15())
    doors = [o for o in openings if o.kind == "door"]
    kitchen = next(r for r in rooms if r.type == "kitchen")
    assert len(_doors_on_room(kitchen, doors)) >= 1


def test_kitchen_door_width_is_standard_not_wet_width():
    rooms = _kitchen_sandwich_rooms()
    openings, _walls = _openings_for(rooms, _cfg_9x15())
    doors = [o for o in openings if o.kind == "door"]
    kitchen = next(r for r in rooms if r.type == "kitchen")
    kitchen_doors = _doors_on_room(kitchen, doors)
    assert len(kitchen_doors) == 1
    assert math.isclose(kitchen_doors[0].width, STD.door_width_m, abs_tol=1e-6)


def _kitchen_deadend_rooms():
    """stair (front) → kitchen → bedroom (rear). Mirrors `_deadend_rooms`
    (the wet-room dead-end fixture): the bedroom's only interior neighbour
    is the kitchen, which must behave as a no-transit room just like a
    wet room."""
    return [
        _room("st", 1.23, 1.73, 6.54, 1.27, rtype="staircase"),
        _room("kit", 1.23, 3.115, 6.54, 1.885, rtype="kitchen"),
        _room("bed", 1.23, 5.115, 6.54, 8.655),
    ]


def test_room_reachable_only_via_kitchen_is_flagged_unreachable():
    from app.engine.plan_geometry import validate_floor_connectivity

    rooms = _kitchen_deadend_rooms()
    openings, _walls = _openings_for(rooms, _cfg_9x15(), floor=1)
    # upper floor: "outside" is not a corridor, so the repair pass cannot
    # punch an open-air door to rescue the bedroom — it must stay flagged
    problems = validate_floor_connectivity(rooms, openings, 1)
    flagged = {p.split()[0] for p in problems}
    assert flagged == {"bed"}, f"expected the bedroom flagged, got {problems}"


def test_ground_floor_fully_reachable_on_golden():
    from app.engine.plan_geometry import validate_floor_connectivity

    openings, fp, _buildable = _golden_openings(floor=0)
    problems = validate_floor_connectivity(fp.rooms, openings, 0)
    assert problems == [], f"GF unreachable rooms: {problems}"


def test_upper_floor_flags_rooms_reachable_only_via_wet_room():
    # the frozen golden fixture's FF bedrooms sit behind the full-width toilet
    # (the stair↔bedroom wall is too narrow for a door). With "outside" barred
    # as a corridor on upper floors, they are correctly flagged as reachable
    # only through the wet room — the exact defect this task guards against.
    from app.engine.plan_geometry import validate_floor_connectivity

    openings, fp, _buildable = _golden_openings(floor=1)
    problems = validate_floor_connectivity(fp.rooms, openings, 1)
    flagged = {p.split()[0] for p in problems}
    beds = {r.id for r in fp.rooms if r.type == "bedroom"}
    assert flagged == beds, f"expected the FF bedrooms flagged, got {problems}"


def test_staircase_has_a_door_on_every_floor():
    for floor in (0, 1):
        openings, fp, _buildable = _golden_openings(floor=floor)
        doors = [o for o in openings if o.kind == "door"]
        stair = next(r for r in fp.rooms if r.type == "staircase")
        assert _doors_on_room(stair, doors), f"staircase on floor {floor} has no door"


def test_unreachable_room_gets_a_repair_door():
    from app.engine.plan_geometry import validate_floor_connectivity

    cfg = _cfg_9x15()
    buildable = buildable_polygon(cfg)
    # living (entry, front) → toilet (wet) → bedroom (rear). The bedroom only
    # borders the wet room, so without a repair pass it is reachable only by
    # passing through the toilet — a navigability violation.
    rooms = [
        _room("living", 1.23, 1.73, 6.54, 2.27, rtype="living"),
        _room("toilet", 1.23, 4.115, 6.54, 1.885, rtype="toilet"),
        _room("bedroom", 1.23, 6.115, 6.54, 7.655),
    ]
    walls = derive_walls(rooms, buildable)
    columns = derive_columns(walls)
    openings = derive_openings(rooms, walls, columns, STD, buildable, floor=0)
    problems = validate_floor_connectivity(rooms, openings, 0)
    assert problems == [], f"repair failed to connect: {problems}"
    # the repair door is an exterior door on the bedroom (only escape from the
    # wet-room dead-end), so the bedroom no longer depends on the toilet path
    ext_doors = [
        d
        for d in openings
        if d.kind == "door"
        and d.swing_into_room_id == "bedroom"
        and math.isclose(d.wall_thickness, EWT, abs_tol=1e-6)
    ]
    assert ext_doors, "bedroom got no repair door"


def _deadend_rooms():
    """stair (front) → toilet (wet) → bedroom (rear, touches exterior).

    The bedroom's only interior neighbour is the wet room, so it is a
    navigability dead-end that only an exterior door could 'fix'.
    """
    return [
        _room("st", 1.23, 1.73, 6.54, 1.27, rtype="staircase"),
        _room("wc", 1.23, 3.115, 6.54, 1.885, rtype="toilet"),
        _room("bed", 1.23, 5.115, 6.54, 8.655),
    ]


def test_ff_deadend_not_repaired_with_open_air_door():
    from app.engine.plan_geometry import validate_floor_connectivity

    rooms = _deadend_rooms()
    openings, _walls = _openings_for(rooms, _cfg_9x15(), floor=1)
    # on an upper floor "outside" is not a corridor: the dead-end bedroom must
    # stay flagged, and repair must NOT punch an exterior door to open air
    assert validate_floor_connectivity(rooms, openings, 1), (
        "FF dead-end bedroom should be unreachable"
    )
    assert not [
        o
        for o in openings
        if o.kind == "door"
        and o.swing_into_room_id == "bed"
        and math.isclose(o.wall_thickness, EWT, abs_tol=1e-6)
    ], "FF repair wrongly added an exterior (open-air) door"


def test_gf_deadend_repaired_via_exterior():
    from app.engine.plan_geometry import validate_floor_connectivity

    rooms = _deadend_rooms()
    openings, _walls = _openings_for(rooms, _cfg_9x15(), floor=0)
    # same geometry on the ground floor: the exterior ring is a valid escape
    assert validate_floor_connectivity(rooms, openings, 0) == []


def test_repair_preserves_single_wet_door():
    from app.engine.plan_geometry import validate_floor_connectivity

    # living (entry) + full-width toilet; behind them a dead-end passage +
    # bedroom island. The bedroom doors into the (unreachable) passage, so its
    # bedroom↔toilet wall stays undoored — the wall repair is tempted to use.
    # Adding a door there would give the single-door toilet a SECOND door
    # (and would not even help, since the toilet cannot be transited).
    rooms = [
        _room("living", 1.23, 1.73, 6.54, 1.27, rtype="living"),
        _room("toilet", 1.23, 3.115, 6.54, 1.385, rtype="toilet"),
        _room("pass_dead", 1.23, 4.615, 2.77, 1.385, rtype="passage"),
        _room("bedroom", 4.115, 4.615, 3.655, 9.155),
    ]
    openings, _walls = _openings_for(rooms, _cfg_9x15(), floor=0)
    doors = [o for o in openings if o.kind == "door"]
    toilet = next(r for r in rooms if r.id == "toilet")
    assert len(_doors_on_room(toilet, doors)) == 1
    assert validate_floor_connectivity(rooms, openings, 0) == []


def test_common_toilet_door_avoids_main_door_wall_when_alternative():
    # main door lands near plot-centre x≈4.5. The toilet borders one passage on
    # the wall the entrance faces (horizontal, spanning x≈4.5) and another
    # passage on its side (vertical). Both are equal-priority circulation, so
    # only the "avoid the main-door-facing wall" heuristic can break the tie —
    # the door must take the SIDE passage.
    rooms = [
        _room("z_entry", 1.23, 1.73, 6.54, 1.27, rtype="living"),
        _room("p_a", 3.5, 3.115, 2.0, 1.385, rtype="passage"),
        _room("toilet_c", 3.5, 4.615, 2.0, 1.885, rtype="toilet"),
        _room("p_b", 5.615, 4.615, 2.155, 1.885, rtype="passage"),
    ]
    openings, _walls = _openings_for(rooms, _cfg_9x15(), floor=0)
    doors = [o for o in openings if o.kind == "door"]
    toilet = next(r for r in rooms if r.id == "toilet_c")
    tdoors = _doors_on_room(toilet, doors)
    assert len(tdoors) == 1
    d = tdoors[0]
    # the side passage wall is vertical (x≈5.5575); the main-door-facing wall is
    # horizontal at y≈4.5575 — the toilet must use the side wall
    assert not d.is_horizontal, "toilet door sits on the main-door-facing wall"
    assert abs(d.cx - 5.5575) < 0.13


def test_single_door_room_prefers_circulation_over_no_transit_neighbour():
    # A toilet between a kitchen and an ordinary bedroom: both adjacencies
    # tie on priority (neither is in _DOOR_NEIGHBOUR_PRIORITY), and the
    # bedroom's id ("z_bed") sorts AFTER "kitchen" alphabetically — so a
    # naive id tiebreak would pick the kitchen door. That door would be
    # useless for reachability once kitchen joins the no-transit set (BFS
    # dead-ends there), so the toilet must prefer the bedroom instead.
    rooms = [
        _room("kitchen", 1.23, 1.73, 2.0, 2.0, rtype="kitchen"),
        _room("toilet_0", 3.345, 1.73, 1.5, 2.0, rtype="toilet"),
        _room("z_bed", 4.96, 1.73, 2.0, 2.0, rtype="bedroom"),
    ]
    openings, _walls = _openings_for(rooms, _cfg_9x15(), floor=1)
    doors = [o for o in openings if o.kind == "door"]
    toilet = next(r for r in rooms if r.id == "toilet_0")
    kitchen = next(r for r in rooms if r.id == "kitchen")
    bedroom = next(r for r in rooms if r.id == "z_bed")

    tdoors = _doors_on_room(toilet, doors)
    assert len(tdoors) == 1, "toilet must keep exactly one door"
    assert _doors_on_room(bedroom, doors), (
        "toilet's single door should open onto the ordinary bedroom, not the kitchen"
    )
    assert not _doors_on_room(kitchen, doors), (
        "toilet must not route its only door through the kitchen"
    )


def test_parking_never_hosts_interior_door():
    # _cfg_9x15 plate front: x 1.23 (=1.0+0.23), y 1.73 (=1.5+0.23)
    # both id orderings: pre-fix the porch placed its own door whenever it
    # sorted before its neighbour in the per-room door loop (issue #2)
    for porch_id in ("porch", "a_porch"):
        rooms = [
            _room("living", 1.23, 1.73, 3.5, 5.0),
            _room(porch_id, 1.23, 6.73, 3.5, 3.0, rtype="parking"),
        ]
        openings, _walls = _openings_for(rooms, _cfg_9x15())
        porch_doors = [
            o for o in openings if o.kind == "door" and o.swing_into_room_id == porch_id
        ]
        assert porch_doors == [], f"{porch_id} hosts its own interior door"
        # the porch must still be served as a no-transit endpoint by the
        # neighbour's door on the shared wall
        assert validate_floor_connectivity(rooms, openings, 0) == []


def test_gapped_parking_gets_no_repair_door():
    """A car porch held a real physical gap from every neighbour (the
    reverse-engineering harness's checklist item 3 — RoomType alone isn't
    enough, parking needs actual clearance so it never LOOKS like a normal
    walled room with a pedestrian door) has no shared wall with anything,
    so `_repair_connectivity`'s reachability pass always finds it
    "unreachable" and used to force a door onto its own exterior wall
    anyway — the repair pass didn't share `_NO_DOOR_TYPES`'s exclusion the
    main per-room door loop already enforces. A real carport is reachable
    only from the driveway/outside, never via an interior door; forcing one
    drew a pedestrian door into what should read as open parking space."""
    for rtype in ("parking", "parking_4w", "parking_2w"):
        rooms = [
            _room("living", 1.23, 1.73, 3.5, 5.0),
            # gap of 0.2m from living's rear edge (6.73) — well past
            # iwt + tol (0.125), so no shared-wall adjacency exists at all
            _room("porch", 1.23, 6.93, 3.5, 3.0, rtype=rtype),
        ]
        openings, _walls = _openings_for(rooms, _cfg_9x15())
        porch_doors = [
            o for o in openings if o.kind == "door" and o.swing_into_room_id == "porch"
        ]
        assert porch_doors == [], (
            f"{rtype} got a repair-pass door despite being gapped from every neighbour"
        )


def test_no_opening_on_an_open_side():
    """A room with a declared-open N and E side (e.g. an open-air sit-out
    off the living room) gets no door, window, or vent cut into either edge:
    there is no wall there for an opening to cut into.

    `Opening` has no `x1/y1/x2/y2` fields (see `cad_elements.py`) — it stores
    a centre `(cx, cy)` sitting ON the wall centreline plus `width` running
    along the wall, and `is_horizontal` selects which axis that is. A wall
    centreline sits `ewt / 2` (0.115 m) outside the raw room edge, so we
    compare against the centreline position with a 0.125 tolerance — the
    same slack `derive_walls` uses for its own open-edge drop (Task 2).

    Two scenario choices matter to avoid a vacuous pass (Task 2 already
    learned this the hard way):

    1. The target room's type is `"living"` (in `_WINDOW_TYPES`), not
       `"parking_4w"` — parking rooms never get windows/vents at all
       (`_WINDOW_TYPES`/`_WET_TYPES` exclude them), so an open-sided
       *parking* room would pass this assertion regardless of whether the
       open-edge filter under test does anything.
    2. The room sits in the plate's NE corner, so its N and E edges land
       exactly on the buildable plate boundary (x2=7.77/y2=13.77 for
       `_cfg_9x15`) — `_all_exterior_edges`'s plate-boundary source
       (`_exterior_edges`) yields a candidate edge purely from plate
       geometry, independent of whether `derive_walls` drew a wall there.
       Its S and W sides are filled by neighbour rooms so they read as
       internal walls, not additional exterior edges an opening could
       legitimately land on instead.
    """
    from app.engine.models import Room

    rooms = [
        _room("west", 2.27, 10.77, 2.0, 3.0, rtype="bedroom"),
        _room("south", 4.27, 9.77, 3.5, 1.0, rtype="bedroom"),
        Room(
            id="target",
            name="Open Sit-out",
            type="living",
            x=4.27,
            y=10.77,
            width=3.5,
            depth=3.0,
            open_sides=frozenset({"N", "E"}),
        ),
    ]
    openings, _walls = _openings_for(rooms, _cfg_9x15())
    ewt = EWT
    tol = 0.125
    # target's declared-open N edge: y = 13.77 (== plate y2), x in [4.27, 7.77].
    n_centreline = 10.77 + 3.0 + ewt / 2
    n_span = (4.27, 7.77)
    # target's declared-open E edge: x = 7.77 (== plate x2), y in [10.77, 13.77].
    e_centreline = 4.27 + 3.5 + ewt / 2
    e_span = (10.77, 13.77)

    def _overlaps(along_lo: float, along_hi: float, span: tuple[float, float]) -> bool:
        return along_lo < span[1] - tol and along_hi > span[0] + tol

    for o in openings:
        if o.is_horizontal and abs(o.cy - n_centreline) < tol:
            along_lo, along_hi = o.cx - o.width / 2, o.cx + o.width / 2
            assert not _overlaps(along_lo, along_hi, n_span), (
                f"{o.kind} at (cx={o.cx}, cy={o.cy}) placed on the target's open N edge"
            )
        if (not o.is_horizontal) and abs(o.cx - e_centreline) < tol:
            along_lo, along_hi = o.cy - o.width / 2, o.cy + o.width / 2
            assert not _overlaps(along_lo, along_hi, e_span), (
                f"{o.kind} at (cx={o.cx}, cy={o.cy}) placed on the target's open E edge"
            )


# ── Entrance-placement diagnostics (Task 6: #6, #6b, G, #6d) ─────────────────


def _drawing_for(rooms):
    from app.engine.models import FloorPlan
    from app.engine.plan_geometry import build_floor_drawing

    fp = FloorPlan(floor=0, floor_type="ground", rooms=rooms)
    return build_floor_drawing(fp, _cfg_9x15())


def test_main_door_all_parking_frontage_is_diagnosed():  # #6d
    # every parking type (2W/4W variants included) is ineligible to host the
    # main entrance — a frontage of only parking + stair must be diagnosed
    for rtype in ("parking", "parking_4w", "parking_2w"):
        drawing = _drawing_for(
            [
                _room("porch", 1.23, 1.73, 4.0, 3.0, rtype=rtype),
                _room("stair", 5.23, 1.73, 2.0, 7.0, rtype="staircase"),
                _room("living", 1.23, 4.73, 4.0, 3.0),
            ]
        )
        diag = [d for d in drawing.diagnostics if d.startswith("main_entrance:")]
        assert diag and "porch" in diag[0], f"{rtype}: no main_entrance diagnostic"
        assert not any(o.is_main for o in drawing.openings), (
            f"{rtype}: porch hosted the main door"
        )


def test_main_door_all_parking_frontage_flags_entrance_not_on_ground_floor():  # #77
    # Same "Modern-26" scenario as the diagnostic test above: the entire road
    # frontage is parking/staircase (no room TYPE there can ever host a
    # door), which is a distinct, typology-level condition — an "upside-down"
    # duplex whose real entry is an external stair straight to the first
    # floor — from an incidental placement failure (too narrow, columns
    # blocked). Only that typology case should set the flag.
    drawing = _drawing_for(
        [
            _room("porch", 1.23, 1.73, 4.0, 3.0, rtype="parking"),
            _room("stair", 5.23, 1.73, 2.0, 7.0, rtype="staircase"),
            _room("living", 1.23, 4.73, 4.0, 3.0),
        ]
    )
    assert drawing.entrance_not_on_ground_floor is True


def test_main_door_too_narrow_candidate_does_not_flag_entrance_not_on_ground_floor():  # #77
    # A too-narrow ROAD-FACING room is an incidental placement failure, not a
    # typology-level "no entry room exists at all" case — must not set the flag.
    drawing = _drawing_for(
        [
            _room("entry", 1.23, 1.73, 0.97, 3.0),  # < 1.05 + 2 jambs
            _room("living", 1.23, 4.73, 4.0, 4.0),
        ]
    )
    assert drawing.entrance_not_on_ground_floor is False


def test_main_door_success_does_not_flag_entrance_not_on_ground_floor():  # #77
    drawing = _drawing_for(_two_bedrooms())
    assert any(o.is_main for o in drawing.openings)
    assert drawing.entrance_not_on_ground_floor is False


def test_main_door_too_narrow_candidate_is_diagnosed():  # #6b
    # entry is the ONLY road-facing room; living sits behind it
    drawing = _drawing_for(
        [
            _room("entry", 1.23, 1.73, 0.97, 3.0),  # < 1.05 + 2 jambs
            _room("living", 1.23, 4.73, 4.0, 4.0),
        ]
    )
    diag = [d for d in drawing.diagnostics if d.startswith("main_entrance:")]
    assert diag and "too narrow" in diag[0]


def test_main_door_off_plate_front_is_diagnosed():  # #6
    drawing = _drawing_for(
        [
            _room("living", 1.23, 2.5, 5.0, 5.0),  # 0.77m behind plate front 1.73
            _room("stair", 6.23, 1.73, 1.5, 6.0, rtype="staircase"),
        ]
    )
    assert not any(o.is_main for o in drawing.openings)
    assert any(d.startswith("main_entrance:") for d in drawing.diagnostics)


def test_main_door_columns_blocked_is_diagnosed():  # G
    # living is the ONLY eligible road-facing room, barely wider than the
    # minimum (1.32 >= 1.07 + 2*0.115 jamb). Its partition with the stair
    # meets the front wall at a junction that auto-derives a column at
    # (2.55, 1.615); that column forbids door centres > 2.55 - 0.695 = 1.855
    # while the fit window is [1.88, 1.90], so _fit_along returns None.
    drawing = _drawing_for(
        [
            _room("living", 1.23, 1.73, 1.32, 4.0),
            _room("stair", 2.55, 1.73, 2.0, 4.0, rtype="staircase"),
        ]
    )
    assert not any(o.is_main for o in drawing.openings)
    diag = [d for d in drawing.diagnostics if d.startswith("main_entrance:")]
    assert diag and "fully blocked" in diag[0]


def test_diagnostics_key_present_in_drawing_dict():
    drawing = _drawing_for([_room("a", 1.23, 1.73, 3.0, 3.0)])
    assert "diagnostics" in drawing.to_dict()


def test_partial_footprint_rear_surface_gets_window():
    """Rooms fill only the front part of the plate (#6c floor): the living
    room's REAR edge is a true exterior surface after the wall-ring fix — it
    must receive a window on the union rear ring (cy = rear + ewt/2), not be
    silently omitted as before.

    (living is wider than deep so its front/rear edges are its two longest
    exterior edges — a square room would tie and a vertical edge would win
    the stable :2 selection, hiding the effect this test pins down.)"""
    openings, _ = _openings_for(
        [
            _room("living", 1.23, 1.73, 5.0, 3.0),
            _room("stair", 6.345, 1.73, 1.425, 3.0, rtype="staircase"),
        ],
        _cfg_9x15(),
    )
    rear_windows = [
        o for o in openings if o.kind == "window" and abs(o.cy - (4.73 + 0.115)) < 1e-6
    ]
    assert rear_windows, "no window was placed on the union rear surface"


def test_main_door_on_setback_building_uses_union_front():
    """#6 healed for partial footprints: no room at the buildable front plate,
    but the front-most room defines the building's real front wall."""
    openings, _ = _openings_for(
        [
            _room("living", 1.23, 2.5, 4.0, 4.0),
            _room("bed", 4.23, 2.5, 3.0, 4.0, rtype="bedroom"),
            _room("stair", 4.23, 6.5, 2.0, 3.0, rtype="staircase"),
        ],
        _cfg_9x15(),
    )
    main = next((o for o in openings if o.is_main), None)
    assert main is not None
    assert abs(main.cy - (2.5 - 0.115)) < 1e-6  # union front minus ewt/2


# ── Out-of-bounds room validation (Task 7: #F) ───────────────────────────────


def test_rooms_outside_buildable_bounds_are_flagged():
    drawing = _drawing_for(
        [
            _room("living", 1.23, 1.73, 4.0, 5.0),
            _room(
                "stray", 12.0, 1.73, 3.0, 3.0
            ),  # buildable max x is 8.0 for _cfg_9x15
        ]
    )
    assert any(d.startswith("geometry:") for d in drawing.diagnostics)


# ── New room types: foyer / courtyard / wardrobe (Task 8: #C) ────────────────


def test_foyer_hosts_main_entrance():
    openings, _ = _openings_for(
        [
            _room("foyer", 1.23, 1.73, 2.5, 3.0, rtype="foyer"),
            _room("stair", 3.73, 1.73, 2.0, 3.0, rtype="staircase"),
            _room("living", 1.23, 4.73, 5.0, 4.0),
        ],
        _cfg_9x15(),
    )
    main = next((o for o in openings if o.is_main), None)
    assert main is not None
    assert main.swing_into_room_id == "foyer"


def test_courtyard_gets_no_own_door_but_is_reachable():
    rooms = [  # 3 rooms stacked around a central courtyard strip
        _room("living", 1.23, 1.73, 4.0, 3.0),
        _room("court", 1.23, 4.73, 4.0, 2.0, rtype="courtyard"),
        _room("stair", 1.23, 6.73, 4.0, 3.0, rtype="staircase"),
    ]
    openings, _ = _openings_for(rooms, _cfg_9x15())
    court_doors = [
        o for o in openings if o.kind == "door" and o.swing_into_room_id == "court"
    ]
    assert court_doors == []
    # reachable via the neighbours' doors on the shared walls
    assert validate_floor_connectivity(rooms, openings, 0) == []


def test_foyer_gets_window():
    # "b" defaults to type "bedroom" (already in _WINDOW_TYPES), so only the
    # foyer's own LEFT exterior edge (cx ~= 1.115, unique to "f" — "b" has no
    # exterior edge in that x-range) unambiguously proves the fix, not any
    # front-wall window that could belong to "b" instead.
    rooms = [
        _room("f", 1.23, 1.73, 2.77, 12.04, rtype="foyer"),
        _room("b", 4.115, 1.73, 3.655, 12.04),
    ]
    openings, _walls = _openings_for(rooms, _cfg_9x15())
    f_windows = [
        o
        for o in openings
        if o.kind == "window" and not o.is_horizontal and abs(o.cx - 1.115) < 1e-6
    ]
    assert f_windows, (
        "foyer got no window on its exterior left wall (_WINDOW_TYPES gap)"
    )


def test_foyer_hosting_main_door_gets_no_overlapping_window():
    openings, _ = _openings_for(
        [
            _room("foyer", 1.23, 1.73, 2.5, 3.0, rtype="foyer"),
            _room("stair", 3.73, 1.73, 2.0, 3.0, rtype="staircase"),
            _room("living", 1.23, 4.73, 5.0, 4.0),
        ],
        _cfg_9x15(),
    )
    md = next(o for o in openings if o.is_main)
    assert md.swing_into_room_id == "foyer"
    for o in openings:
        if o is md or o.kind != "window" or o.is_horizontal != md.is_horizontal:
            continue
        same_line = (
            abs(o.cy - md.cy) < 1e-6 if md.is_horizontal else abs(o.cx - md.cx) < 1e-6
        )
        if not same_line:
            continue
        along_o = o.cx if md.is_horizontal else o.cy
        along_md = md.cx if md.is_horizontal else md.cy
        assert abs(along_o - along_md) >= (o.width + md.width) / 2 - 1e-9, (
            f"foyer window overlaps main door at ({o.cx:.2f},{o.cy:.2f})"
        )


def _void_isolated_room_rooms(target_id: str, target_type: str):
    """`target_id` sandwiched front/left/right by other rooms, with only its
    rear open to a genuine interior void (nothing covers that area up to the
    plate's own rear at y=7.73) — its ONLY exterior surface is void-facing,
    unlike a fixture where the target also happens to touch the plate
    boundary on another side (those edges would out-rank or pre-empt the
    void edge in window/ventilator selection, defeating the point of the
    test)."""
    return [
        _room("living", 1.23, 1.73, 6.54, 2.0),  # full-width front row
        _room("left", 1.23, 3.73, 2.0, 2.0),  # closes target's left (internal)
        _room(target_id, 3.23, 3.73, 2.54, 2.0, rtype=target_type),
        _room("right", 5.77, 3.73, 2.0, 2.0),  # closes target's right (internal)
    ]


def test_void_facing_room_receives_window():
    """A room whose only exterior edge faces an interior void (not the plate
    boundary) must still receive a window. The void-facing orphan wall is
    marked kind="external" by derive_walls; derive_openings must recognize it
    as a valid exterior edge candidate."""
    cfg = _cfg_9x15()
    rooms = _void_isolated_room_rooms("bed", "bedroom")
    openings, walls = _openings_for(rooms, cfg)
    # bed's rear edge (y=5.73) faces the interior void (nothing covers that
    # area up to the plate's rear at y=7.73) and is not on the plate boundary
    # — so it has no plate-based exterior edge, only a void-facing orphan
    # wall marked kind="external"
    ext_walls_on_bed_rear = [
        w
        for w in walls
        if w.kind == "external"
        and abs(w.y1 - w.y2) < 1e-9
        and abs(w.y1 - (5.73 + 0.115)) < 1e-6
        and min(w.x1, w.x2) < 5.77
        and max(w.x1, w.x2) > 3.23
    ]
    assert ext_walls_on_bed_rear, "bed's void-facing rear wall should be external"
    # bed must get a window on that rear void-facing edge
    bed_windows = [
        o
        for o in openings
        if o.kind == "window"
        and o.is_horizontal
        and abs(o.cy - (5.73 + 0.115)) < 0.13
        and 3.23 - 0.13 <= o.cx <= 5.77 + 0.13
    ]
    assert bed_windows, "bed got no window on its void-facing exterior wall"


def test_void_facing_wet_room_receives_ventilator():
    """A wet room whose only exterior edge faces an interior void must still
    receive a ventilator. Mirrors test_void_facing_room_receives_window."""
    cfg = _cfg_9x15()
    rooms = _void_isolated_room_rooms("toilet", "toilet")
    openings, walls = _openings_for(rooms, cfg)
    ext_walls_on_toilet_rear = [
        w
        for w in walls
        if w.kind == "external"
        and abs(w.y1 - w.y2) < 1e-9
        and abs(w.y1 - (5.73 + 0.115)) < 1e-6
        and min(w.x1, w.x2) < 5.77
        and max(w.x1, w.x2) > 3.23
    ]
    assert ext_walls_on_toilet_rear, "toilet's void-facing rear wall should be external"
    # toilet must get a ventilator on that rear void-facing edge
    toilet_vents = [
        o
        for o in openings
        if o.kind == "ventilator"
        and o.is_horizontal
        and abs(o.cy - (5.73 + 0.115)) < 0.13
        and 3.23 - 0.13 <= o.cx <= 5.77 + 0.13
    ]
    assert toilet_vents, "toilet got no ventilator on its void-facing exterior wall"
