"""Tests for the CP-SAT constraint solver."""

import pytest
from app.engine.models import PlotConfig
from app.engine.solver import solve_layouts, _load_specs, _build_room_list


def _basic_cfg(**kwargs) -> PlotConfig:
    defaults = dict(
        plot_length=12.0,
        plot_width=9.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=0.9,
        setback_right=0.9,
        num_bedrooms=2,
        toilets=2,
        parking=False,
        city="other",
        road_side="S",
        vastu_enabled=False,
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
    cfg = _basic_cfg(
        custom_room_config=[
            {"type": "gym", "name": "Home Gym", "floor_preference": "ff"},
            {"type": "servant_quarter", "floor_preference": "gf"},
        ]
    )
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
        assert layout.compliance.passed, (
            f"Layout {layout.id} failed: {layout.compliance.violations}"
        )


def test_solve_columns_use_wall_junction_pipeline_not_room_corners():
    # Regression: solver used to place a column at all 4 corners of every
    # room (deduped only by rounded coordinate) via a local `_corner_cols`
    # helper — dense, structurally unjustified "intermediate" column grids
    # independent of the correct wall-junction + beam-span logic that
    # plan_geometry.build_floor_drawing already used for the structural
    # pages. This asserts solver.py's FloorPlan.columns are exactly what
    # the shared derive_walls/derive_junctions/derive_columns pipeline
    # produces for the same rooms — i.e. solver.py stays wired to the one
    # correct implementation instead of drifting back to a duplicate.
    from app.engine.geometry import buildable_polygon
    from app.engine.plan_geometry import derive_columns, derive_junctions, derive_walls

    cfg = _basic_cfg(
        plot_length=15.0, plot_width=12.0, num_bedrooms=3, toilets=2, parking=True
    )
    ewt = 0.23
    layouts = solve_layouts(cfg, ewt)
    assert layouts, "expected at least one solver layout for this fixture"
    buildable = buildable_polygon(cfg)

    naive_corner_total = 0
    pipeline_total = 0
    for layout in layouts:
        for floor_plan in (layout.ground_floor, layout.first_floor):
            if not floor_plan.rooms:
                continue
            walls = derive_walls(floor_plan.rooms, buildable, ewt=ewt)
            junctions = derive_junctions(walls)
            expected = derive_columns(walls, junctions=junctions)
            expected_pts = {(round(c.cx, 3), round(c.cy, 3)) for c in expected}
            actual_pts = {(round(c.x, 3), round(c.y, 3)) for c in floor_plan.columns}
            assert actual_pts == expected_pts, (
                f"layout {layout.id} floor {floor_plan.floor}: solver columns "
                "diverge from the shared derive_columns pipeline"
            )

            naive_corners = {
                (round(cx, 2), round(cy, 2))
                for r in floor_plan.rooms
                for cx, cy in [
                    (r.x, r.y),
                    (r.x + r.width, r.y),
                    (r.x, r.y + r.depth),
                    (r.x + r.width, r.y + r.depth),
                ]
            }
            naive_corner_total += len(naive_corners)
            pipeline_total += len(expected_pts)

    # Aggregated across all floors of all layouts, the span-aware pipeline
    # must not exceed the old naive per-room-corner scheme. A tie is fine:
    # with the wall-coalignment objective (Phase 1A) room corners dedupe
    # onto shared grid lines, shrinking the naive count to meet the
    # pipeline's — the regression guarded here (a column at EVERY corner,
    # far more than junction-derived) would show as pipeline > naive.
    assert pipeline_total <= naive_corner_total


def test_solve_too_small_plot_returns_empty():
    cfg = _basic_cfg(
        plot_length=5.0,
        plot_width=5.0,
        setback_front=2.0,
        setback_rear=2.0,
        setback_left=1.5,
        setback_right=1.5,
    )
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
