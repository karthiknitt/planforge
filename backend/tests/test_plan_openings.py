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


def _openings_for(rooms, cfg, std=STD):
    buildable = buildable_polygon(cfg)
    walls = derive_walls(rooms, buildable)
    columns = derive_columns(walls)
    return derive_openings(rooms, walls, columns, std, buildable), walls


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
    d = next(o for o in openings if o.kind == "door")
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
    doors = [o for o in openings if o.kind == "door"]
    windows = [o for o in openings if o.kind == "window"]
    assert all(math.isclose(d.width, 1.0, abs_tol=1e-9) for d in doors)
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
