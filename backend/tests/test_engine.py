"""Tests for the layout engine — compliance, room areas, structural grid."""

import pytest

from app.engine.generator import generate
from app.engine.models import PlotConfig

# Standard test plot: 9 m × 12 m, typical Indian site
STANDARD_CFG = PlotConfig(
    plot_width=9.0,
    plot_length=12.0,
    setback_front=1.5,
    setback_rear=1.5,
    setback_left=1.0,
    setback_right=1.0,
    num_bedrooms=2,
    toilets=2,
    parking=False,
)

STANDARD_CFG_3BHK = PlotConfig(
    plot_width=9.0,
    plot_length=12.0,
    setback_front=1.5,
    setback_rear=1.5,
    setback_left=1.0,
    setback_right=1.0,
    num_bedrooms=3,
    toilets=3,
    parking=True,
)


def test_layouts_generated():
    layouts = generate(STANDARD_CFG)
    # Should produce at least A, B, C, D, E (5 archetypes for a standard plot)
    assert len(layouts) >= 3
    ids = [lay.id for lay in layouts]
    # Core archetypes must all appear
    for expected in ["A", "B", "C"]:
        assert expected in ids, f"Expected layout {expected} in generated layouts"


def test_all_layouts_pass_compliance_2bhk():
    layouts = generate(STANDARD_CFG)
    for lay in layouts:
        assert lay.compliance.passed, (
            f"Layout {lay.id} failed compliance: {lay.compliance.violations}"
        )


def test_all_layouts_pass_compliance_3bhk():
    layouts = generate(STANDARD_CFG_3BHK)
    for lay in layouts:
        assert lay.compliance.passed, (
            f"Layout {lay.id} failed compliance: {lay.compliance.violations}"
        )


def test_bedroom_areas_meet_minimum():
    min_area = 9.5
    for cfg in (STANDARD_CFG, STANDARD_CFG_3BHK):
        for lay in generate(cfg):
            all_rooms = lay.ground_floor.rooms + lay.first_floor.rooms
            bedrooms = [r for r in all_rooms if r.type == "bedroom"]
            for room in bedrooms:
                assert room.area >= min_area, (
                    f"Layout {lay.id} / {room.name}: {room.area} sqm < {min_area} sqm"
                )


def test_kitchen_area_meets_minimum():
    min_area = 4.5  # NBC 2016 minimum for kitchen
    for lay in generate(STANDARD_CFG):
        all_rooms = lay.ground_floor.rooms + lay.first_floor.rooms
        kitchens = [r for r in all_rooms if r.type == "kitchen"]
        assert len(kitchens) == 1, f"Layout {lay.id}: expected 1 kitchen"
        assert kitchens[0].area >= min_area, (
            f"Layout {lay.id} kitchen: {kitchens[0].area} sqm < {min_area} sqm"
        )


def test_toilet_area_meets_minimum():
    min_area = 2.8  # NBC minimum for combined bath+WC
    for lay in generate(STANDARD_CFG):
        all_rooms = lay.ground_floor.rooms + lay.first_floor.rooms
        toilets = [r for r in all_rooms if r.type == "toilet"]
        for room in toilets:
            assert room.area >= min_area, (
                f"Layout {lay.id} / {room.name}: {room.area} sqm < {min_area} sqm"
            )


def test_staircase_width():
    min_w = 0.9
    for lay in generate(STANDARD_CFG):
        all_rooms = lay.ground_floor.rooms + lay.first_floor.rooms
        stairs = [r for r in all_rooms if r.type == "staircase"]
        assert len(stairs) >= 1, f"Layout {lay.id}: no staircase found"
        for stair in stairs:
            assert stair.width >= min_w or stair.depth >= min_w, (
                f"Layout {lay.id} staircase too narrow: w={stair.width}"
            )


def test_staircase_aligned_vertically():
    """Staircase on first floor must be at the same position as ground floor."""
    for lay in generate(STANDARD_CFG):
        gf_stairs = [r for r in lay.ground_floor.rooms if r.type == "staircase"]
        ff_stairs = [r for r in lay.first_floor.rooms if r.type == "staircase"]
        assert gf_stairs and ff_stairs, f"Layout {lay.id}: missing staircase on one floor"
        assert gf_stairs[0].x == pytest.approx(ff_stairs[0].x, abs=0.01)
        assert gf_stairs[0].y == pytest.approx(ff_stairs[0].y, abs=0.01)


def test_columns_generated():
    for lay in generate(STANDARD_CFG):
        assert len(lay.ground_floor.columns) > 0, f"Layout {lay.id}: no GF columns"
        assert len(lay.first_floor.columns) > 0, f"Layout {lay.id}: no FF columns"


def test_parking_included_when_requested():
    layouts = generate(STANDARD_CFG_3BHK)
    for lay in layouts:
        all_rooms = lay.ground_floor.rooms + lay.first_floor.rooms
        parking = [r for r in all_rooms if r.type == "parking"]
        assert len(parking) >= 1, f"Layout {lay.id}: parking requested but not found"


def test_1bhk_generates_layouts():
    cfg_1bhk = PlotConfig(
        plot_width=6.0,
        plot_length=9.0,
        setback_front=1.0,
        setback_rear=1.0,
        setback_left=0.75,
        setback_right=0.75,
        num_bedrooms=1,
        toilets=1,
        parking=False,
    )
    layouts = generate(cfg_1bhk)
    assert len(layouts) >= 1, "1 BHK should generate at least one layout"
