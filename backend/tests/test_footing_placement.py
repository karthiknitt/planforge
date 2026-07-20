import pytest

from app.engine.cad_elements import ColumnMarker, WallSegment
from app.engine.footing_placement import place_footings


def test_place_footings_classifies_and_sizes_by_grid_position():
    # 3x2 grid, corners at the 4 extreme intersections
    columns = [
        ColumnMarker(cx=0.0, cy=0.0),
        ColumnMarker(cx=4.0, cy=0.0),
        ColumnMarker(cx=8.0, cy=0.0),
        ColumnMarker(cx=0.0, cy=4.5),
        ColumnMarker(cx=4.0, cy=4.5),
        ColumnMarker(cx=8.0, cy=4.5),
    ]
    walls = [
        WallSegment(x1=0, y1=0, x2=0, y2=4.5, thickness=0.23, kind="external"),
        WallSegment(x1=4, y1=0, x2=4, y2=4.5, thickness=0.23, kind="external"),
        WallSegment(x1=8, y1=0, x2=8, y2=4.5, thickness=0.23, kind="external"),
        WallSegment(x1=0, y1=0, x2=8, y2=0, thickness=0.23, kind="external"),
        WallSegment(x1=0, y1=4.5, x2=8, y2=4.5, thickness=0.23, kind="external"),
    ]
    footings_data = {
        "corner": {"data": {"L_m": 1.35, "B_m": 1.35}},
        "edge": {"data": {"L_m": 1.5, "B_m": 1.35}},
        "interior": {"data": {"L_m": 1.65, "B_m": 1.65}},
    }

    placed = place_footings(columns, walls, footings_data)

    assert len(placed) == 6
    corner = next(p for p in placed if p.cx == 0.0 and p.cy == 0.0)
    assert corner.footing_type == "corner"
    assert corner.length_m == 1.35 and corner.width_m == 1.35


def test_place_footings_raises_when_footing_data_missing_for_type():
    # Only a corner column here, but footings_data lacks a "corner" entry --
    # must error loudly rather than silently emit a 0x0 footing.
    columns = [ColumnMarker(cx=0.0, cy=0.0)]
    walls = [
        WallSegment(x1=0, y1=0, x2=0, y2=4.5, thickness=0.23, kind="external"),
        WallSegment(x1=4, y1=0, x2=4, y2=4.5, thickness=0.23, kind="external"),
        WallSegment(x1=0, y1=0, x2=8, y2=0, thickness=0.23, kind="external"),
        WallSegment(x1=0, y1=4.5, x2=8, y2=4.5, thickness=0.23, kind="external"),
    ]
    footings_data = {
        "edge": {"data": {"L_m": 1.5, "B_m": 1.35}},
        "interior": {"data": {"L_m": 1.65, "B_m": 1.65}},
    }

    with pytest.raises(ValueError, match="No footing design found"):
        place_footings(columns, walls, footings_data)
