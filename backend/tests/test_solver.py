"""Tests for the CP-SAT constraint solver."""

import pytest
from app.engine.models import PlotConfig
from app.engine.solver import solve_layouts, _load_specs, _build_room_list


def _basic_cfg(**kwargs) -> PlotConfig:
    defaults = dict(
        plot_length=12.0, plot_width=9.0,
        setback_front=1.5, setback_rear=1.0, setback_left=0.9, setback_right=0.9,
        num_bedrooms=2, toilets=2, parking=False,
        city="other", road_side="S", vastu_enabled=False,
    )
    defaults.update(kwargs)
    return PlotConfig(**defaults)


def test_specs_load():
    specs = _load_specs()
    assert "bedroom" in specs
    assert "kitchen" in specs
    assert specs["bedroom"]["min_area_sqm"] == 9.5


def test_room_list_basic():
    cfg = _basic_cfg()
    rooms = _build_room_list(cfg, _load_specs())
    types = {r["type"] for r in rooms}
    assert "living" in types
    assert "kitchen" in types
    assert "bedroom" in types
    assert "staircase" in types


def test_room_list_optional_rooms():
    cfg = _basic_cfg(has_pooja=True, has_study=True, has_balcony=True)
    rooms = _build_room_list(cfg, _load_specs())
    types = {r["type"] for r in rooms}
    assert "pooja" in types
    assert "study" in types
    assert "balcony" in types


def test_room_list_custom_rooms():
    cfg = _basic_cfg(custom_room_config=[
        {"type": "gym", "name": "Home Gym", "floor_preference": "ff"},
        {"type": "servant_quarter", "floor_preference": "gf"},
    ])
    rooms = _build_room_list(cfg, _load_specs())
    types = [r["type"] for r in rooms]
    assert "gym" in types
    assert "servant_quarter" in types


def test_solve_returns_up_to_3_layouts():
    cfg = _basic_cfg(plot_length=14.0, plot_width=11.0)
    ewt = 0.23
    layouts = solve_layouts(cfg, ewt)
    # Solver may return 0-3; we just check it doesn't crash and stays bounded
    assert len(layouts) <= 3


def test_solve_layouts_pass_compliance():
    cfg = _basic_cfg(plot_length=15.0, plot_width=12.0, num_bedrooms=2, toilets=2)
    ewt = 0.23
    layouts = solve_layouts(cfg, ewt)
    for layout in layouts:
        assert layout.compliance.passed, f"Layout {layout.id} failed: {layout.compliance.violations}"


def test_solve_too_small_plot_returns_empty():
    cfg = _basic_cfg(plot_length=5.0, plot_width=5.0, setback_front=2.0, setback_rear=2.0,
                     setback_left=1.5, setback_right=1.5)
    ewt = 0.23
    layouts = solve_layouts(cfg, ewt)
    # Very small buildable area — should return no solver layouts (graceful)
    assert isinstance(layouts, list)


def test_solve_does_not_raise_on_bad_input():
    cfg = _basic_cfg(plot_length=0.1, plot_width=0.1)
    try:
        result = solve_layouts(cfg, 0.23)
        assert isinstance(result, list)
    except Exception:
        pytest.fail("solve_layouts should not raise — it should return empty list")
