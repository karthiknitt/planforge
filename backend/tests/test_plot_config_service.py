"""Regression tests for the single shared Project -> PlotConfig mapper (A3 + export drift).

Before this service existed, 8 route call sites each hand-built PlotConfig and drifted:
- share.py / rooms.py / export.py read `cutout_width_m` (column is `cutout_width`) ->
  L-shaped projects silently became full rectangles.
- export.py omitted num_floors / has_stilt / has_basement / municipality /
  custom_room_config -> exports drew a different building than the viewer.
"""

import json

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.plot_config import plot_config_from_project


def _project(**overrides) -> Project:
    base = dict(
        id="p1",
        user_id="u1",
        name="Test Project",
        plot_length=15.0,
        plot_width=10.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        road_side="S",
        north_direction="N",
        num_bedrooms=2,
        toilets=2,
        parking=False,
    )
    base.update(overrides)
    return Project(**base)


def test_l_shaped_cutout_columns_reach_config():
    p = _project(
        plot_shape="l_shaped", cutout_corner="NE", cutout_width=3.0, cutout_height=4.0
    )
    cfg = plot_config_from_project(p)
    assert cfg.plot_shape == "l_shaped"
    assert cfg.cutout_corner == "NE"
    assert cfg.cutout_width == 3.0
    assert cfg.cutout_height == 4.0


def test_multi_floor_fields_reach_config():
    p = _project(num_floors=3, has_stilt=True, has_basement=True)
    cfg = plot_config_from_project(p)
    assert cfg.num_floors == 3
    assert cfg.has_stilt is True
    assert cfg.has_basement is True


def test_municipality_and_custom_rooms_reach_config():
    p = _project(
        municipality="Chennai (CMDA)",
        custom_room_config=json.dumps([{"type": "study"}]),
    )
    cfg = plot_config_from_project(p)
    assert cfg.municipality == "Chennai (CMDA)"
    assert cfg.custom_room_config == [{"type": "study"}]


def test_plot_corners_parsed_to_tuples():
    p = _project(
        plot_shape="quadrilateral",
        plot_corners=json.dumps([[0, 0], [10, 0], [9, 15], [0, 14]]),
    )
    cfg = plot_config_from_project(p)
    assert cfg.plot_corners == [(0, 0), (10, 0), (9, 15), (0, 14)]


def test_malformed_json_fields_fall_back_to_none():
    p = _project(plot_corners="not-json", custom_room_config="{broken")
    cfg = plot_config_from_project(p)
    assert cfg.plot_corners is None
    assert cfg.custom_room_config is None


def _create_payload(**overrides) -> dict:
    base = dict(
        name="Test Project",
        plot_length=15.0,
        plot_width=10.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        road_side="S",
        north_direction="N",
        num_bedrooms=2,
        toilets=2,
    )
    base.update(overrides)
    return base


def test_project_create_schema_has_attached_toilets_default_false():
    payload = ProjectCreate(**_create_payload())
    assert payload.attached_toilets is False


def test_project_create_schema_accepts_attached_toilets_true():
    payload = ProjectCreate(**_create_payload(attached_toilets=True))
    assert payload.attached_toilets is True


def test_project_update_schema_allows_attached_toilets_none_or_bool():
    assert ProjectUpdate().attached_toilets is None
    assert ProjectUpdate(attached_toilets=True).attached_toilets is True


def test_project_read_schema_has_attached_toilets_field():
    assert "attached_toilets" in ProjectRead.model_fields


def test_attached_toilets_reaches_config():
    p = _project(attached_toilets=True)
    cfg = plot_config_from_project(p)
    assert cfg.attached_toilets is True


def test_attached_toilets_defaults_false():
    p = _project()
    cfg = plot_config_from_project(p)
    assert cfg.attached_toilets is False


def test_defaults_for_unset_optional_columns():
    """A plain (unflushed) ORM instance has None for unset columns — mapper must
    apply the same fallbacks the routes used."""
    p = _project()
    cfg = plot_config_from_project(p)
    assert cfg.city == "other"
    assert cfg.road_side == "S"
    assert cfg.road_width_m == 9.0
    assert cfg.plot_shape == "rectangular"
    assert cfg.num_floors == 1
    assert cfg.vastu_enabled is False
