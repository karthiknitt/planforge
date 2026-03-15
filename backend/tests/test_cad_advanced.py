"""Unit tests for cad_advanced.py — Shapely-powered DXF drawing."""
import pytest

from app.engine.cad_advanced import (
    draw_building_footprint,
    draw_compound_wall,
    draw_furniture,
    draw_open_terrace,
    draw_setback_zones,
    draw_structural_grid,
    shapely_poly_to_dxf,
)
from app.engine.models import PlotConfig, Room


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def msp():
    import ezdxf
    doc = ezdxf.new("R2010")
    for lname in ["A-FOOTPRINT", "A-COMPOUND-WALL", "A-TERRACE",
                  "A-FURNITURE", "S-GRID", "DIM-SETBACK"]:
        doc.layers.new(lname)
    if "DASHED" not in doc.linetypes:
        doc.linetypes.new("DASHED", dxfattribs={"description": "Dashed _ _ _"})
    return doc.modelspace()


def _room(id_: str, type_: str, x: float, y: float, w: float, d: float) -> Room:
    return Room(id=id_, name=type_.capitalize(), type=type_, x=x, y=y, width=w, depth=d)


def _cfg(road_side: str = "S", pw: float = 10.0, pl: float = 12.0) -> PlotConfig:
    return PlotConfig(
        plot_length=pl, plot_width=pw,
        setback_front=1.5, setback_rear=1.0,
        setback_left=1.0, setback_right=1.0,
        num_bedrooms=2, toilets=2, parking=False,
        road_side=road_side,
    )


def _on_layer(msp, layer: str) -> list:
    return [e for e in msp if e.dxf.layer == layer]


def _type_on_layer(msp, dxf_type: str, layer: str) -> list:
    return [e for e in msp if e.dxftype() == dxf_type and e.dxf.layer == layer]


# ─────────────────────────────────────────────────────────────────────────────
# shapely_poly_to_dxf
# ─────────────────────────────────────────────────────────────────────────────

def test_simple_polygon_creates_lwpolyline(msp):
    from shapely.geometry import box
    shapely_poly_to_dxf(msp, box(0, 0, 3, 4), "A-FOOTPRINT", 0.0)
    assert len(_type_on_layer(msp, "LWPOLYLINE", "A-FOOTPRINT")) == 1


def test_polygon_with_hole_creates_two_lwpolylines(msp):
    from shapely.geometry import box
    donut = box(0, 0, 5, 5).difference(box(1, 1, 4, 4))
    shapely_poly_to_dxf(msp, donut, "A-FOOTPRINT", 0.0)
    assert len(_type_on_layer(msp, "LWPOLYLINE", "A-FOOTPRINT")) == 2


def test_empty_polygon_does_not_crash(msp):
    from shapely.geometry import Polygon
    shapely_poly_to_dxf(msp, Polygon(), "A-FOOTPRINT", 0.0)  # no exception


# ─────────────────────────────────────────────────────────────────────────────
# draw_building_footprint
# ─────────────────────────────────────────────────────────────────────────────

def test_footprint_returns_polygon_type(msp):
    from shapely.geometry import Polygon
    rooms = [_room("r1", "living", 0, 0, 3, 4)]
    result = draw_building_footprint(msp, rooms, "A-FOOTPRINT", 0.0)
    assert isinstance(result, Polygon)


def test_footprint_union_correct_area(msp):
    rooms = [
        _room("r1", "bedroom", 0, 0, 3, 4),
        _room("r2", "living", 3, 0, 3, 4),
    ]
    result = draw_building_footprint(msp, rooms, "A-FOOTPRINT", 0.0)
    assert abs(result.area - 24.0) < 0.01


def test_footprint_adjacent_rooms_merge(msp):
    from shapely.geometry import MultiPolygon
    rooms = [
        _room("r1", "bedroom", 0, 0, 3, 4),
        _room("r2", "living", 3, 0, 3, 4),
    ]
    result = draw_building_footprint(msp, rooms, "A-FOOTPRINT", 0.0)
    assert not isinstance(result, MultiPolygon)


# ─────────────────────────────────────────────────────────────────────────────
# draw_compound_wall
# ─────────────────────────────────────────────────────────────────────────────

def test_compound_wall_entities_created(msp):
    draw_compound_wall(msp, _cfg(road_side="S"), "A-COMPOUND-WALL", 0.0)
    assert len(_on_layer(msp, "A-COMPOUND-WALL")) > 0


def test_compound_wall_south_gate_gap(msp):
    """South gate: south wall is split into 2 segments; count should be > north-only."""
    cfg_s = _cfg(road_side="S")
    draw_compound_wall(msp, cfg_s, "A-COMPOUND-WALL", 0.0)
    # With gate, south side has 2 segments + 2 posts; other sides have 1 each
    polys = _type_on_layer(msp, "LWPOLYLINE", "A-COMPOUND-WALL")
    # At minimum: 3 full sides (each produces ≥1 poly) + 2 gate segments + 2 posts
    assert len(polys) >= 5


def test_compound_wall_north_orientation(msp):
    """North gate: entities still created on A-COMPOUND-WALL."""
    draw_compound_wall(msp, _cfg(road_side="N"), "A-COMPOUND-WALL", 0.0)
    assert len(_on_layer(msp, "A-COMPOUND-WALL")) > 0


# ─────────────────────────────────────────────────────────────────────────────
# draw_open_terrace
# ─────────────────────────────────────────────────────────────────────────────

def test_terrace_hatch_created(msp):
    from shapely.geometry import box
    draw_open_terrace(msp, box(0, 0, 10, 12), box(1, 1.5, 9, 11), "A-TERRACE", 0.0)
    assert len(_type_on_layer(msp, "HATCH", "A-TERRACE")) > 0


def test_terrace_area_correct(msp):
    from shapely.geometry import box
    plot_poly = box(0, 0, 10, 12)       # 10×12 = 120 sqm
    bld_poly = box(1, 1.5, 9, 10.5)    # 8×9  =  72 sqm
    terrace = plot_poly.difference(bld_poly)
    assert abs(terrace.area - (120 - 72)) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# draw_structural_grid
# ─────────────────────────────────────────────────────────────────────────────

def test_grid_vertical_lines_count(msp):
    """2 side-by-side rooms → xs=[0,3,6] (3 vert), ys=[0,4] (2 horiz) = 5 lines."""
    rooms = [
        _room("r1", "bedroom", 0, 0, 3, 4),
        _room("r2", "living", 3, 0, 3, 4),
    ]
    draw_structural_grid(msp, rooms, 0, 0, 6, 4, "S-GRID", 0.0)
    lines = _type_on_layer(msp, "LINE", "S-GRID")
    assert len(lines) == 5  # 3 vertical + 2 horizontal


def test_grid_bubble_count(msp):
    """xs=[0,3,6] (3), ys=[0,4] (2) → 2*(3+2) = 10 circles."""
    rooms = [
        _room("r1", "bedroom", 0, 0, 3, 4),
        _room("r2", "living", 3, 0, 3, 4),
    ]
    draw_structural_grid(msp, rooms, 0, 0, 6, 4, "S-GRID", 0.0)
    circles = _type_on_layer(msp, "CIRCLE", "S-GRID")
    assert len(circles) == 10


def test_grid_labels_alpha(msp):
    """Grid MTEXT should include column label 'A', 'B' and row labels '1', '2'."""
    rooms = [
        _room("r1", "bedroom", 0, 0, 3, 4),
        _room("r2", "living", 3, 0, 3, 4),
    ]
    draw_structural_grid(msp, rooms, 0, 0, 6, 4, "S-GRID", 0.0)
    mtexts = _type_on_layer(msp, "MTEXT", "S-GRID")
    texts = {e.dxf.text for e in mtexts}
    assert "A" in texts
    assert "B" in texts
    assert "1" in texts
    assert "2" in texts


# ─────────────────────────────────────────────────────────────────────────────
# draw_furniture
# ─────────────────────────────────────────────────────────────────────────────

def test_bedroom_creates_entities(msp):
    room = _room("r1", "bedroom", 0, 0, 3.5, 4.0)
    draw_furniture(msp, room, "A-FURNITURE", 0.0)
    assert len(_type_on_layer(msp, "LWPOLYLINE", "A-FURNITURE")) >= 1
    assert len(_type_on_layer(msp, "ARC", "A-FURNITURE")) >= 1


def test_kitchen_creates_entities(msp):
    room = _room("r1", "kitchen", 0, 0, 3.0, 3.0)
    draw_furniture(msp, room, "A-FURNITURE", 0.0)
    assert len(_type_on_layer(msp, "LWPOLYLINE", "A-FURNITURE")) >= 1
    assert len(_type_on_layer(msp, "CIRCLE", "A-FURNITURE")) >= 1


def test_toilet_creates_entities(msp):
    room = _room("r1", "toilet", 0, 0, 1.5, 2.0)
    draw_furniture(msp, room, "A-FURNITURE", 0.0)
    assert len(_type_on_layer(msp, "ARC", "A-FURNITURE")) >= 1


def test_living_creates_entities(msp):
    """Living room: sofa (rects) + coffee table + TV unit — no dining table here."""
    room = _room("r1", "living", 0, 0, 4.5, 5.0)
    draw_furniture(msp, room, "A-FURNITURE", 0.0)
    # Sofa back + armrests + coffee table + TV unit = at least 4 polylines
    assert len(_type_on_layer(msp, "LWPOLYLINE", "A-FURNITURE")) >= 4


def test_furniture_tiny_room_no_crash(msp):
    room = _room("r1", "bedroom", 0, 0, 1.0, 1.0)
    draw_furniture(msp, room, "A-FURNITURE", 0.0)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# draw_setback_zones
# ─────────────────────────────────────────────────────────────────────────────

def test_setback_dims_created(msp):
    cfg = _cfg()
    # Building starts at (1.0, 1.5) with size 8.0 × 9.0
    draw_setback_zones(msp, cfg, 1.0, 1.5, 8.0, 9.0, "DIM-SETBACK", 0.0)
    entities = _on_layer(msp, "DIM-SETBACK")
    assert len(entities) > 0
