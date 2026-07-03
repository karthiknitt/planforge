"""Tests for the canonical geometry module (A2) — per-edge setbacks.

The old code averaged the four setbacks into one uniform buffer, so a plot
with front 4.5 m / sides 1.2 m was inset ~2.3 m everywhere: the front was
under-enforced and the sides over-enforced, and compliance validated against
the same wrong boundary.
"""

import pytest
from shapely.geometry import Polygon, box

from app.engine.geometry import buildable_polygon, plot_polygon
from app.engine.models import PlotConfig


def _cfg(**over) -> PlotConfig:
    base = dict(
        plot_length=18.0,
        plot_width=12.0,
        setback_front=4.5,
        setback_rear=2.0,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=2,
        toilets=2,
        parking=False,
    )
    base.update(over)
    return PlotConfig(**base)


class TestRectangular:
    def test_per_edge_setbacks_exact_bounds(self):
        b = buildable_polygon(_cfg())
        assert b.bounds == pytest.approx((1.2, 4.5, 12.0 - 1.2, 18.0 - 2.0))

    def test_wall_clearance_shrinks_further(self):
        b = buildable_polygon(_cfg(), wall_clearance=0.23)
        assert b.bounds == pytest.approx(
            (1.43, 4.73, 12.0 - 1.43, 18.0 - 2.23), abs=1e-6
        )

    def test_consuming_setbacks_give_empty(self):
        b = buildable_polygon(_cfg(setback_left=6.0, setback_right=6.5))
        assert b.is_empty


class TestQuadrilateral:
    def test_axis_aligned_quad_matches_rect(self):
        cfg = _cfg(
            plot_shape="quadrilateral",
            plot_corners=[(0, 0), (12, 0), (12, 18), (0, 18)],
        )
        assert buildable_polygon(cfg).bounds == pytest.approx((1.2, 4.5, 10.8, 16.0))

    def test_skewed_quad_respects_front_setback(self):
        cfg = _cfg(
            plot_shape="quadrilateral",
            plot_corners=[(0, 0), (12, 0.8), (11.2, 18), (0.4, 17.2)],
        )
        b = buildable_polygon(cfg)
        assert not b.is_empty
        plot = plot_polygon(cfg)
        assert b.within(plot)
        # Every buildable point must be >= 4.4 m from the front edge
        # (front setback 4.5 with a small numeric tolerance)
        front_edge = list(plot.exterior.coords)[0:2]
        from shapely.geometry import LineString

        assert b.distance(LineString(front_edge)) >= 4.4


class TestTrapezoid:
    def test_polygon_area_is_trapezoid_area(self):
        cfg = _cfg(plot_shape="trapezoid", plot_front_width=12.0, plot_rear_width=8.0)
        assert plot_polygon(cfg).area == pytest.approx((12.0 + 8.0) / 2 * 18.0)

    def test_buildable_stays_inside_slanted_sides(self):
        cfg = _cfg(plot_shape="trapezoid", plot_front_width=12.0, plot_rear_width=8.0)
        b = buildable_polygon(cfg)
        assert not b.is_empty
        assert b.within(plot_polygon(cfg))
        # The rear edge is only 8 m wide (centred at x=2..10): the buildable
        # region near the rear must be well inside that — the old code solved
        # on the full 12 m rectangle.
        minx, miny, maxx, maxy = b.bounds
        assert miny >= 4.5 - 1e-6  # front setback honoured
        assert maxy <= 16.0 + 1e-6  # rear setback honoured


class TestLShaped:
    def test_buildable_avoids_cutout(self):
        cfg = _cfg(
            plot_shape="l_shaped",
            cutout_corner="NE",
            cutout_width=4.0,
            cutout_height=6.0,
        )
        b = buildable_polygon(cfg)
        assert not b.is_empty
        # NE cutout occupies x in [8,12], y in [12,18]
        cutout = box(12.0 - 4.0, 18.0 - 6.0, 12.0, 18.0)
        assert b.intersection(cutout).area == pytest.approx(0.0, abs=1e-9)
        assert b.within(plot_polygon(cfg))

    def test_all_four_corners_valid(self):
        for corner in ("NE", "NW", "SE", "SW"):
            cfg = _cfg(
                plot_shape="l_shaped",
                cutout_corner=corner,
                cutout_width=4.0,
                cutout_height=6.0,
            )
            poly = plot_polygon(cfg)
            assert poly.is_valid
            assert poly.area == pytest.approx(12 * 18 - 4 * 6)
            assert not buildable_polygon(cfg).is_empty


class TestGeneratorReexport:
    def test_generator_still_exports_l_polygon(self):
        # compliance/solver historically import from generator — keep working
        from app.engine.generator import compute_l_shaped_polygon

        cfg = _cfg(
            plot_shape="l_shaped",
            cutout_corner="NE",
            cutout_width=4.0,
            cutout_height=6.0,
        )
        assert isinstance(compute_l_shaped_polygon(cfg), Polygon)
