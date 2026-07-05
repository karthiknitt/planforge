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


def test_each_room_gets_a_door_no_overlaps():
    openings, _walls = _openings_for(_two_bedrooms(), _cfg_9x15())
    doors = [o for o in openings if o.kind == "door"]
    assert {d.swing_into_room_id for d in doors} == {"a", "b"}
    # both doors share the partition at x=4.0575 and must not overlap
    partition = [d for d in doors if abs(d.cx - 4.0575) < 1e-6]
    assert len(partition) == 2
    partition.sort(key=lambda d: d.cy)
    assert (
        partition[0].cy + partition[0].width / 2
        <= partition[1].cy - partition[1].width / 2 + 1e-9
    )


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
        served = {d.swing_into_room_id for d in doors}
        for r in floor.rooms:
            if r.type == "passage":
                continue
            assert r.id in served, f"room {r.id} has no door"
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
