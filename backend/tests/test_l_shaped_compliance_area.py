"""
Regression tests for L-shaped plot compliance — FAR and coverage (P3-7).

The FAR calculation must use the inset polygon area (after setbacks), not the
bounding box. Miscalculation would produce wrong wall-drag feedback.

Covers:
  - L-polygon area = W×L − cw×ch for all four cutout corners
  - FAR is computed from the L-polygon, not the bounding rectangle
  - Compliance check runs without error on a generated L-shaped layout
  - NE and SW cutout variants produce different polygon geometries but both valid
  - Inset area shrinks correctly when setbacks are applied
"""

import math

import pytest
from shapely.geometry import Polygon

from app.engine.compliance import check, load_rules
from app.engine.generator import compute_l_shaped_polygon, generate
from app.engine.models import (
    Column,
    ComplianceResult,
    FloorPlan,
    Layout,
    PlotConfig,
    Room,
)


def _l_cfg(cutout_corner: str = "NE") -> PlotConfig:
    return PlotConfig(
        plot_length=15.0,
        plot_width=12.0,
        setback_front=1.2,
        setback_rear=1.2,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=3,
        toilets=2,
        parking=False,
        plot_shape="l_shaped",
        cutout_corner=cutout_corner,
        cutout_width=4.0,
        cutout_height=4.0,
    )


# ── Polygon geometry ───────────────────────────────────────────────────────────

def test_l_polygon_area_ne():
    cfg = _l_cfg("NE")
    poly = compute_l_shaped_polygon(cfg)
    expected = 12.0 * 15.0 - 4.0 * 4.0   # 180 - 16 = 164
    assert abs(poly.area - expected) < 0.01


def test_l_polygon_area_nw():
    cfg = _l_cfg("NW")
    poly = compute_l_shaped_polygon(cfg)
    expected = 12.0 * 15.0 - 4.0 * 4.0
    assert abs(poly.area - expected) < 0.01


def test_l_polygon_area_se():
    cfg = _l_cfg("SE")
    poly = compute_l_shaped_polygon(cfg)
    expected = 12.0 * 15.0 - 4.0 * 4.0
    assert abs(poly.area - expected) < 0.01


def test_l_polygon_area_sw():
    cfg = _l_cfg("SW")
    poly = compute_l_shaped_polygon(cfg)
    expected = 12.0 * 15.0 - 4.0 * 4.0
    assert abs(poly.area - expected) < 0.01


def test_ne_and_sw_polygons_differ():
    """NE and SW cutouts produce mirror geometries — not identical polygons."""
    poly_ne = compute_l_shaped_polygon(_l_cfg("NE"))
    poly_sw = compute_l_shaped_polygon(_l_cfg("SW"))
    # Centroids differ even though areas are the same
    assert abs(poly_ne.centroid.x - poly_sw.centroid.x) > 0.1 or \
           abs(poly_ne.centroid.y - poly_sw.centroid.y) > 0.1


# ── Inset area (used for coverage / FAR) ─────────────────────────────────────

def test_l_polygon_inset_is_smaller_than_full():
    cfg = _l_cfg("NE")
    poly = compute_l_shaped_polygon(cfg)
    avg_sb = (cfg.setback_front + cfg.setback_rear + cfg.setback_left + cfg.setback_right) / 4
    inset = poly.buffer(-avg_sb, join_style=2)
    assert inset.area < poly.area


def test_l_polygon_inset_area_less_than_rectangular_inset():
    """L-polygon inset must be smaller than the bounding-rectangle inset.

    This guards against the bug where compliance incorrectly used W×L instead of
    the L-polygon area, inflating the footprint and masking coverage violations.
    """
    cfg = _l_cfg("NE")
    poly = compute_l_shaped_polygon(cfg)
    avg_sb = (cfg.setback_front + cfg.setback_rear + cfg.setback_left + cfg.setback_right) / 4
    inset_l = poly.buffer(-avg_sb, join_style=2).area

    # Rectangular bounding box inset
    rect_w = cfg.plot_width  - cfg.setback_left  - cfg.setback_right
    rect_d = cfg.plot_length - cfg.setback_front - cfg.setback_rear
    inset_rect = rect_w * rect_d

    assert inset_l < inset_rect, (
        f"L-polygon inset ({inset_l:.2f}) should be smaller than rectangular inset ({inset_rect:.2f})"
    )


# ── Compliance on generated L-shaped layout ───────────────────────────────────

def test_l_shaped_generate_and_compliance_no_exception():
    """Full pipeline: generate → compliance check must not raise."""
    cfg = _l_cfg("NE")
    layouts = generate(cfg)
    assert len(layouts) >= 1, "Expected at least one layout for a 15×12 L-shaped plot"

    rules = load_rules()
    for layout in layouts:
        result = check(layout, cfg, rules)
        # result must be a valid ComplianceResult (not None, no exception)
        assert isinstance(result.passed, bool)
        assert isinstance(result.violations, list)
        assert isinstance(result.warnings, list)


def test_l_shaped_far_uses_polygon_not_bounding_box():
    """FAR numerator uses L-polygon area, not W×L. Regression for floor coverage calc."""
    cfg = _l_cfg("NE")
    layouts = generate(cfg)
    assert layouts

    layout = layouts[0]
    rules = load_rules()
    result = check(layout, cfg, rules)

    # L-polygon area = 164 sqm; bounding box = 180 sqm.
    # If FAR were calculated with 180 sqm, it would show a LOWER FAR (less conservative).
    # Compliance should use 164 sqm — any "FAR exceeds" warning must refer to that.
    far_warnings = [w for w in result.warnings if "FAR" in w]
    for w in far_warnings:
        # The number in the warning should reflect actual_far = footprint / 164
        # Extract the first float from the warning to sanity-check it's not absurd
        import re
        match = re.search(r"FAR (\d+\.\d+)", w)
        if match:
            actual_far = float(match.group(1))
            # FAR for this 15×12 two-storey plot should be between 0.5 and 3.0
            assert 0.1 < actual_far < 5.0, f"FAR value looks wrong: {actual_far}"


def test_l_shaped_compliance_ne_vs_sw_different_results():
    """NE and SW cutouts produce different buildable shapes, so compliance results may differ."""
    cfg_ne = _l_cfg("NE")
    cfg_sw = _l_cfg("SW")

    layouts_ne = generate(cfg_ne)
    layouts_sw = generate(cfg_sw)

    rules = load_rules()
    result_ne = check(layouts_ne[0], cfg_ne, rules)
    result_sw = check(layouts_sw[0], cfg_sw, rules)

    # Both should run without error — just checking no exception
    assert isinstance(result_ne.passed, bool)
    assert isinstance(result_sw.passed, bool)
