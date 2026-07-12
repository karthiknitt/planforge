from shapely.geometry import LineString, box

from app.engine.cad_elements import WallSegment
from app.engine.generator import generate
from app.engine.geometry import buildable_polygon
from app.engine.models import PlotConfig
from app.engine.section_geometry import (
    room_interval,
    section_cut_line,
    wall_cut_intervals,
)

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
