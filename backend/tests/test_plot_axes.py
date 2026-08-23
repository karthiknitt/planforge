"""Plot-axis rename: `plot_x_extent`/`plot_y_extent` are primary;
`plot_width`/`plot_length` remain read/write aliases so persisted configs and
in-flight API payloads keep working. DB columns are unchanged (auto-migrate is
add-only, so a column rename would orphan stored rows)."""

import pytest

from app.engine.models import PlotConfig
from app.schemas.project import ProjectCreate


def _cfg(**kw) -> PlotConfig:
    base = dict(
        plot_x_extent=9.0,
        plot_y_extent=15.0,
        setback_front=3.0,
        setback_rear=1.5,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=3,
        toilets=2,
        parking=True,
    )
    base.update(kw)
    return PlotConfig(**base)


def test_new_names_are_primary():
    cfg = _cfg()
    assert cfg.plot_x_extent == 9.0
    assert cfg.plot_y_extent == 15.0


def test_old_names_still_read():
    cfg = _cfg()
    assert cfg.plot_x_extent == 9.0
    assert cfg.plot_y_extent == 15.0


def test_old_names_still_write():
    cfg = _cfg()
    cfg.plot_x_extent = 10.0
    assert cfg.plot_x_extent == 10.0
    cfg.plot_y_extent = 12.0
    assert cfg.plot_y_extent == 12.0


def test_constructing_with_old_names_still_works():
    cfg = PlotConfig(
        plot_width=9.0,
        plot_length=15.0,
        setback_front=3.0,
        setback_rear=1.5,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=3,
        toilets=2,
        parking=True,
    )
    assert cfg.plot_x_extent == 9.0
    assert cfg.plot_y_extent == 15.0


def test_conflicting_old_and_new_names_raise():
    with pytest.raises(ValueError):
        _cfg(plot_x_extent=9.0, plot_width=10.0)


def test_unknown_kwargs_raise():
    with pytest.raises(TypeError):
        _cfg(plot_bogus=1.0)


def test_api_schema_accepts_pre_rename_payload():
    """A payload written BEFORE the rename (old field names) must still parse —
    this is what keeps already-persisted rows and in-flight bodies working."""
    payload = {
        "name": "p",
        "plot_length": 15.0,
        "plot_width": 9.0,
        "setback_front": 3.0,
        "setback_rear": 1.5,
        "setback_left": 1.2,
        "setback_right": 1.2,
        "road_side": "S",
        "north_direction": "S",
        "num_bedrooms": 3,
        "toilets": 2,
        "parking": True,
    }
    create = ProjectCreate(**payload)
    assert create.plot_y_extent == 15.0
    assert create.plot_x_extent == 9.0


def test_api_schema_accepts_new_names():
    payload = {
        "name": "p",
        "plot_y_extent": 15.0,
        "plot_x_extent": 9.0,
        "setback_front": 3.0,
        "setback_rear": 1.5,
        "setback_left": 1.2,
        "setback_right": 1.2,
        "road_side": "S",
        "north_direction": "S",
        "num_bedrooms": 3,
        "toilets": 2,
        "parking": True,
    }
    create = ProjectCreate(**payload)
    assert create.plot_y_extent == 15.0
    assert create.plot_x_extent == 9.0
