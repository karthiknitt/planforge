from shapely.geometry import LineString, box

from app.engine.cad_elements import WallSegment
from app.engine.generator import generate
from app.engine.geometry import buildable_polygon
from app.engine.models import PlotConfig
from app.engine.section_geometry import (
    derive_elevation,
    derive_section,
    room_interval,
    section_cut_line,
    wall_cut_intervals,
)
from app.engine.vertical_standards import VS

CFG = PlotConfig(
    plot_length=12.0,
    plot_width=9.0,
    setback_front=3.0,
    setback_rear=1.5,
    setback_left=1.0,
    setback_right=1.0,
    num_bedrooms=2,
    toilets=2,
    parking=True,
)


def _layout():
    return generate(CFG)[0]


def test_cut_line_passes_through_staircase():
    lay = _layout()
    stair = next(r for r in lay.ground_floor.rooms if r.type == "staircase")
    line, along_y = section_cut_line(lay.ground_floor.rooms, buildable_polygon(CFG))
    stair_box = box(stair.x, stair.y, stair.x + stair.width, stair.y + stair.depth)
    assert line.intersects(stair_box)
    assert along_y == (stair.depth >= stair.width)


def test_cut_line_spans_full_building():
    lay = _layout()
    bp = buildable_polygon(CFG)
    line, _ = section_cut_line(lay.ground_floor.rooms, bp)
    assert line.length >= max(bp.bounds[2] - bp.bounds[0], bp.bounds[3] - bp.bounds[1])


def test_wall_cut_interval_width_matches_thickness():
    line = LineString([(5.0, -1.0), (5.0, 11.0)])
    wall = WallSegment(x1=2.0, y1=4.0, x2=8.0, y2=4.0, thickness=0.23, kind="external")
    ivs = wall_cut_intervals(line, wall)
    assert len(ivs) == 1
    s0, s1 = ivs[0]
    assert abs((s1 - s0) - 0.23) < 0.01


def test_parallel_wall_not_cut():
    line = LineString([(5.0, -1.0), (5.0, 11.0)])
    wall = WallSegment(x1=2.0, y1=4.0, x2=2.0, y2=9.0, thickness=0.115, kind="internal")
    assert wall_cut_intervals(line, wall) == []


def test_room_interval():
    line = LineString([(5.0, -1.0), (5.0, 11.0)])
    from app.engine.models import Room

    r = Room(id="r1", name="Living", type="living", x=3.0, y=2.0, width=4.0, depth=5.0)
    iv = room_interval(line, r)
    assert iv is not None
    assert abs((iv[1] - iv[0]) - 5.0) < 0.01


def test_derive_section_structure():
    sd = derive_section(_layout(), CFG)
    assert sd.title == "SECTION A-A"
    mats = {p.material for p in sd.polys}
    assert {"brick", "rcc", "pcc", "earth"} <= mats
    z_top = max(p.poly.bounds[3] for p in sd.polys)
    assert abs(z_top - (2 * VS.floor_to_floor_m + VS.parapet_h_m)) < 0.01
    z_bot = min(p.poly.bounds[1] for p in sd.polys)
    assert abs(z_bot - (-VS.plinth_h_m - VS.foundation_depth_m)) < 0.01


def test_section_has_stair_profile_and_labels():
    sd = derive_section(_layout(), CFG)
    stair_polys = [
        p for p in sd.polys if p.material == "rcc" and len(p.poly.exterior.coords) > 10
    ]
    assert stair_polys, "expected a stepped stair profile polygon"
    assert any("R @" in t for _, _, t in sd.labels)
    assert len([t for _, _, t in sd.labels if "R @" not in t]) >= 2


def test_section_levels_and_dims():
    sd = derive_section(_layout(), CFG)
    label_texts = [lv.label for lv in sd.levels]
    assert any("±0.00" in t for t in label_texts)
    assert any("+3.000" in t for t in label_texts)
    assert "3000" in [d.label for d in sd.vdims]


def test_derive_elevation_silhouette_and_levels():
    ed = derive_elevation(_layout(), CFG)
    assert ed.title == "FRONT ELEVATION"
    minx, miny, maxx, maxy = ed.silhouette.bounds
    assert abs(maxy - (2 * VS.floor_to_floor_m + VS.parapet_h_m)) < 0.01
    assert abs(miny - (-VS.plinth_h_m)) < 0.01
    assert any("±0.00" in lv.label for lv in ed.levels)
    total_mm = round((2 * VS.floor_to_floor_m + VS.parapet_h_m + VS.plinth_h_m) * 1000)
    assert str(total_mm) in [d.label for d in ed.vdims]


def test_elevation_openings_inside_silhouette():
    ed = derive_elevation(_layout(), CFG)
    for rect in ed.openings:
        assert rect.within(ed.silhouette.buffer(0.01))
    for rect in ed.openings:
        assert rect.bounds[3] <= 2 * VS.floor_to_floor_m + 0.01


def test_derive_elevation_all_road_sides():
    from dataclasses import replace

    lay = _layout()
    bp = buildable_polygon(CFG)
    minx, miny, maxx, maxy = bp.bounds
    expected = {
        "S": (minx, maxx),
        "N": (minx, maxx),
        "E": (miny, maxy),
        "W": (miny, maxy),
    }
    for side, (u0, u1) in expected.items():
        ed = derive_elevation(lay, replace(CFG, road_side=side))
        b = ed.silhouette.bounds
        assert abs(b[0] - u0) < 1e-6, side
        assert abs(b[2] - u1) < 1e-6, side
        assert any("±0.00" in lv.label for lv in ed.levels), side
        for rect in ed.openings:
            assert rect.within(ed.silhouette.buffer(0.01)), side
