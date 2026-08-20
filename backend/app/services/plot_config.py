"""Single canonical Project -> PlotConfig mapper.

Every route that turns a stored Project row into an engine PlotConfig MUST use
this function. Hand-rolled copies drifted apart (wrong column names, dropped
multi-floor/municipality fields) and produced different buildings per endpoint.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from app.engine.models import PlotConfig
from app.models.project import Project


def _f(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    return float(v) if isinstance(v, Decimal) else float(v)


def _json_or_none(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def plot_config_from_project(project: Project) -> PlotConfig:
    raw_corners = _json_or_none(project.plot_corners)
    plot_corners = (
        [tuple(pt) for pt in raw_corners] if isinstance(raw_corners, list) else None
    )

    return PlotConfig(
        plot_y_extent=_f(project.plot_length),
        plot_x_extent=_f(project.plot_width),
        setback_front=_f(project.setback_front),
        setback_rear=_f(project.setback_rear),
        setback_left=_f(project.setback_left),
        setback_right=_f(project.setback_right),
        num_bedrooms=project.num_bedrooms,
        toilets=project.toilets,
        parking=project.parking,
        city=project.city or "other",
        vastu_enabled=project.vastu_enabled or False,
        road_width_m=_f(project.road_width_m, 9.0) or 9.0,
        road_side=project.road_side or "S",
        has_pooja=project.has_pooja or False,
        has_study=project.has_study or False,
        has_balcony=project.has_balcony or False,
        attached_toilets=project.attached_toilets or False,
        plot_shape=project.plot_shape or "rectangular",
        plot_front_width=_f(project.plot_front_width),
        plot_rear_width=_f(project.plot_rear_width),
        plot_side_offset=_f(project.plot_side_offset),
        plot_corners=plot_corners,
        cutout_corner=project.cutout_corner or "NE",
        cutout_width=_f(project.cutout_width),
        cutout_height=_f(project.cutout_height),
        num_floors=project.num_floors or 1,
        has_stilt=project.has_stilt or False,
        has_basement=project.has_basement or False,
        municipality=project.municipality,
        custom_room_config=_json_or_none(project.custom_room_config),
    )
