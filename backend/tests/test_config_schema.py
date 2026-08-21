"""GenerateRequest wire schema: north angle, plot template, style, programme, site.

This is the wizard's "Site & Style" request shape — the wire contract the
frontend Zod schema (`frontend/src/lib/schemas.ts`) must mirror byte-for-byte.
"""

import pytest
from pydantic import ValidationError
from shapely.geometry import Point

from app.engine.geometry import buildable_polygon
from app.engine.models import PlotConfig
from app.schemas.project import GenerateRequest


def _payload(**kw):
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
    return base


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


def test_defaults_reproduce_todays_behaviour():
    req = GenerateRequest(**_payload())
    assert req.north_angle_deg == 0.0
    assert req.plot_template == "RECT"
    assert req.style_preset is None
    assert req.programme == set()


def test_north_angle_is_wrapped_into_range():
    assert GenerateRequest(**_payload(north_angle_deg=370.0)).north_angle_deg == 10.0
    assert GenerateRequest(**_payload(north_angle_deg=-90.0)).north_angle_deg == 270.0


def test_notch_dims_required_for_non_rect_plot():
    with pytest.raises(ValidationError, match="notch"):
        GenerateRequest(**_payload(plot_template="L"))


def test_notch_must_fit_inside_the_plot():
    with pytest.raises(ValidationError, match="larger than the plot"):
        GenerateRequest(
            **_payload(plot_template="L", notch_width=20.0, notch_depth=2.0)
        )


def test_t_plot_is_rejected_at_the_wire_not_deep_in_the_solver():
    # Task 9 raises on plot_template T/U. Rejecting here turns what would be an
    # uncaught 500 into a 422 the wizard can render.
    with pytest.raises(ValidationError):
        GenerateRequest(
            **_payload(plot_template="T", notch_width=3.0, notch_depth=4.0)
        )


def test_l_plot_sets_back_its_notch_edges():
    # Ruling 3: plot_template="L" must not leave the two new plot edges
    # setback-free. Assert against buildable area, not raw notch dims. (The
    # subtraction surface in `buildable_polygon` already implements this; this
    # pins it so the wire-exposed L template cannot silently regress.)
    cfg = _cfg(plot_template="L", notch_width=3.0, notch_depth=4.0)
    poly = buildable_polygon(cfg)
    notch_corner = Point(cfg.plot_x_extent - 1.0, cfg.plot_y_extent - 1.0)
    assert not poly.contains(notch_corner)
    just_inside = Point(
        cfg.plot_x_extent - cfg.notch_width - 0.1,
        cfg.plot_y_extent - cfg.notch_depth - 0.1,
    )
    assert not poly.contains(just_inside)


def test_unknown_programme_flag_is_rejected():
    with pytest.raises(ValidationError):
        GenerateRequest(**_payload(programme={"swimming_pool"}))


def test_gate_side_defaults_to_the_road_side():
    req = GenerateRequest(**_payload(north_angle_deg=0.0))
    assert req.site.gate_side == "S"
