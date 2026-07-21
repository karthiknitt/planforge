"""Canonical opening derivation invariants (S4.2)."""

import math

from app.engine.geometry import buildable_polygon
from app.engine.plan_geometry import (
    derive_columns,
    derive_openings,
    derive_walls,
    opening_boxes,
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
