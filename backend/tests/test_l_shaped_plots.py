"""Tests for L-shaped plot support — polygon construction and layout generation."""

import pytest

from app.engine.generator import compute_l_shaped_polygon, generate
from app.engine.models import PlotConfig


# ── Test config: 15 m × 12 m plot with 4 m × 4 m NE cutout, 3BHK ────────────
# Larger plot (15×12=180 sqm, cutout=16 sqm → 164 sqm) to provide enough
# buildable area for 3BHK + mandatory rooms after setbacks.

L_SHAPED_CFG = PlotConfig(
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
    cutout_corner="NE",
    cutout_width=4.0,
    cutout_height=4.0,
)

# Original (compact) config for polygon shape tests only
L_SHAPED_COMPACT_CFG = PlotConfig(
    plot_length=12.0,
    plot_width=9.0,
    setback_front=1.2,
    setback_rear=1.2,
    setback_left=1.0,
    setback_right=1.0,
    num_bedrooms=2,
    toilets=2,
    parking=False,
    plot_shape="l_shaped",
    cutout_corner="NE",
    cutout_width=3.0,
    cutout_height=3.0,
)


def test_l_shaped_polygon_ne_cutout_area():
    """NE cutout: L-polygon area = W*L - cw*ch."""
    poly = compute_l_shaped_polygon(L_SHAPED_COMPACT_CFG)
    expected = 9.0 * 12.0 - 3.0 * 3.0  # 99 sqm
    assert abs(poly.area - expected) < 0.01, (
        f"L-polygon area {poly.area:.2f} != expected {expected:.2f}"
    )


def test_l_shaped_polygon_is_valid():
    """L-polygon must be a valid, simple polygon."""
    poly = compute_l_shaped_polygon(L_SHAPED_COMPACT_CFG)
    assert poly.is_valid, "L-polygon must be valid"
    assert poly.is_simple, "L-polygon must be simple (non-self-intersecting)"


def test_l_shaped_polygon_has_six_vertices():
    """An L-shaped polygon always has exactly 6 exterior vertices."""
    poly = compute_l_shaped_polygon(L_SHAPED_COMPACT_CFG)
    # Exterior coords include closing duplicate — exclude it
    coords = list(poly.exterior.coords)[:-1]
    assert len(coords) == 6, f"Expected 6 vertices, got {len(coords)}"


def test_l_shaped_polygon_all_corners():
    """All four cutout corners (NE/NW/SE/SW) produce valid 6-vertex polygons."""
    base = dict(
        plot_length=12.0, plot_width=9.0,
        setback_front=1.2, setback_rear=1.2, setback_left=1.0, setback_right=1.0,
        num_bedrooms=2, toilets=2, parking=False,
        plot_shape="l_shaped", cutout_width=3.0, cutout_height=3.0,
    )
    for corner in ("NE", "NW", "SE", "SW"):
        cfg = PlotConfig(**base, cutout_corner=corner)
        poly = compute_l_shaped_polygon(cfg)
        assert poly.is_valid, f"{corner}: polygon invalid"
        coords = list(poly.exterior.coords)[:-1]
        assert len(coords) == 6, f"{corner}: expected 6 vertices, got {len(coords)}"
        assert abs(poly.area - (9.0 * 12.0 - 3.0 * 3.0)) < 0.01, (
            f"{corner}: area mismatch"
        )


def test_l_shaped_generate_returns_layouts():
    """15×12 L-shaped plot with 4×4 NE cutout, 3BHK — at least 1 layout generated."""
    layouts = generate(L_SHAPED_CFG)
    assert len(layouts) >= 1, (
        "Expected at least 1 compliant layout for 15×12 L-shaped plot with 4×4 NE cutout"
    )
    # All returned layouts must have passed compliance
    for lay in layouts:
        assert lay.compliance.passed, (
            f"Layout {lay.id} has compliance violations: {lay.compliance.violations}"
        )
