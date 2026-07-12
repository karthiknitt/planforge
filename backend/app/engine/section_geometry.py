from shapely.geometry import LineString, Point, Polygon, box

from app.engine.cad_elements import WallSegment
from app.engine.models import Room


def _line_segments(geom) -> list[LineString]:
    if geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type in ("MultiLineString", "GeometryCollection"):
        return [g for g in geom.geoms if g.geom_type == "LineString"]
    return []


def section_cut_line(rooms: list[Room], buildable: Polygon) -> tuple[LineString, bool]:
    stair = next(r for r in rooms if r.type == "staircase")
    minx, miny, maxx, maxy = buildable.bounds
    along_y = stair.depth >= stair.width
    if along_y:
        cx = stair.x + stair.width / 2
        return LineString([(cx, miny - 1.0), (cx, maxy + 1.0)]), True
    cy = stair.y + stair.depth / 2
    return LineString([(minx - 1.0, cy), (maxx + 1.0, cy)]), False


def _intervals(line: LineString, poly: Polygon) -> list[tuple[float, float]]:
    out = []
    for seg in _line_segments(line.intersection(poly)):
        t0 = line.project(Point(seg.coords[0]))
        t1 = line.project(Point(seg.coords[-1]))
        if abs(t1 - t0) > 1e-6:
            out.append((min(t0, t1), max(t0, t1)))
    return sorted(out)


def wall_cut_intervals(
    line: LineString, wall: WallSegment
) -> list[tuple[float, float]]:
    h = wall.thickness / 2
    wall_box = box(
        min(wall.x1, wall.x2) - h,
        min(wall.y1, wall.y2) - h,
        max(wall.x1, wall.x2) + h,
        max(wall.y1, wall.y2) + h,
    )
    # skip walls the line runs along (parallel & coincident): interval far wider than thickness
    return [
        iv
        for iv in _intervals(line, wall_box)
        if (iv[1] - iv[0]) <= wall.thickness * 2.5
    ]


def room_interval(line: LineString, room: Room) -> tuple[float, float] | None:
    ivs = _intervals(
        line, box(room.x, room.y, room.x + room.width, room.y + room.depth)
    )
    return ivs[0] if ivs else None
