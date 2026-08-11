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


def test_derive_elevation_front_facade_is_always_y_min():
    # Rooms are always laid out with the road at the y-min edge; road_side only
    # records the compass direction that edge faces. The front facade (and thus
    # the elevation silhouette) must therefore span the x-axis of the buildable
    # bounds for every road_side value.
    from dataclasses import replace

    lay = _layout()
    bp = buildable_polygon(CFG)
    minx, _miny, maxx, _maxy = bp.bounds
    for side in ("S", "N", "E", "W"):
        ed = derive_elevation(lay, replace(CFG, road_side=side))
        b = ed.silhouette.bounds
        assert abs(b[0] - minx) < 1e-6, side
        assert abs(b[2] - maxx) < 1e-6, side
        assert any("±0.00" in lv.label for lv in ed.levels), side
        for rect in ed.openings:
            assert rect.within(ed.silhouette.buffer(0.01)), side


def test_elevation_includes_full_height_main_door():
    from app.engine.plan_geometry import (
        derive_columns,
        derive_openings,
        derive_walls,
    )
    from app.engine.standards import OpeningStandards
    from tests.helpers.golden import golden_config, golden_layout

    lay = golden_layout()
    cfg = golden_config()
    bp = buildable_polygon(cfg)
    walls = derive_walls(lay.ground_floor.rooms, bp)
    columns = derive_columns(walls)
    md = next(
        o
        for o in derive_openings(
            lay.ground_floor.rooms, walls, columns, OpeningStandards(), bp, floor=0
        )
        if o.is_main
    )

    ed = derive_elevation(lay, cfg)
    # silhouette spans the x-axis (front facade = y-min wall), not the y-axis
    minx, _miny, maxx, _maxy = bp.bounds
    assert abs(ed.silhouette.bounds[0] - minx) < 1e-6
    assert abs(ed.silhouette.bounds[2] - maxx) < 1e-6

    # a full-height door rect (0 -> door_h_m) appears at the MD's x position
    door_rects = [
        r
        for r in ed.openings
        if abs(r.bounds[1] - 0.0) < 1e-6 and abs(r.bounds[3] - VS.door_h_m) < 1e-6
    ]
    assert door_rects, "no full-height door rect in the elevation"
    assert any(r.bounds[0] <= md.cx <= r.bounds[2] for r in door_rects), (
        "no elevation door rect at the main-door x position"
    )


def test_section_cut_line_falls_back_without_staircase():
    from shapely.geometry import box

    from app.engine.section_geometry import section_cut_line
    from tests.test_multi_floor import _room

    rooms = [_room("living", "living", 1.13, 1.73, 4.0, 5.0)]
    buildable = box(1.0, 2.0, 10.0, 14.0)
    line, along_y = section_cut_line(rooms, buildable)
    # graceful fallback: plain vertical mid-line through the buildable bounds
    assert along_y is True
    coords = list(line.coords)
    assert coords[0][0] == coords[1][0] == 5.5
    assert coords[0][1] == 1.0 and coords[1][1] == 15.0  # padded by 1.0


def test_render_pdf_handles_stairless_ground_floor():
    """End-to-end: a genuinely stair-less single-story home renders (H)."""
    from app.engine.pdf import render_pdf
    from tests.test_multi_floor import _cfg, _make_layout, _room

    rooms = [  # front rooms at 1.73 = setback_front(1.5) + EWT(0.23)
        _room("living", "living", 1.13, 1.73, 4.0, 5.0),
        _room("bed", "bedroom", 5.13, 1.73, 4.0, 5.0),
    ]
    lay = _make_layout(rooms, ff_rooms=[])
    pdf = render_pdf("Stairless", lay, _cfg(), 3)
    from tests.helpers.pdf_png import pdf_pages

    assert pdf_pages(pdf) == 6
