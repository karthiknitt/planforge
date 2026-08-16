"""Canonical plot & buildable geometry — the single source of truth (A2).

Four modules previously computed the buildable boundary independently, each
with a different approximation: solver/compliance/archetypes applied ONE
averaged setback as a uniform buffer (under-enforcing the front setback,
over-enforcing the sides), rooms.py used a plain rectangle, and trapezoid
plots fell through to full rectangles entirely. Everything now derives from
plot_polygon() / buildable_polygon(), which honour PER-EDGE setbacks.

Coordinate system: x grows left->right (0..plot_width), y grows front/road ->
rear (0..plot_length). Edge setbacks are classified by the edge's outward
normal: -y => front, +y => rear, -x => left, +x => right (dominant axis for
slanted edges).
"""

from __future__ import annotations

import math

from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient

from app.engine.models import PlotConfig

_BIG = 1e5


def compute_l_shaped_polygon(cfg: PlotConfig) -> Polygon:
    """Return a Shapely Polygon for the L-shaped plot boundary.

    The L-shape is the full bounding rectangle with one rectangular corner
    cut out. Supports NE, NW, SE, SW cutout corners.
    """
    W = cfg.plot_width
    H = cfg.plot_length
    cw = cfg.cutout_width
    ch = cfg.cutout_height

    if cfg.cutout_corner == "NE":
        vertices = [
            (0, 0),
            (W, 0),
            (W, H - ch),
            (W - cw, H - ch),
            (W - cw, H),
            (0, H),
        ]
    elif cfg.cutout_corner == "NW":
        vertices = [
            (0, 0),
            (W, 0),
            (W, H),
            (cw, H),
            (cw, H - ch),
            (0, H - ch),
        ]
    elif cfg.cutout_corner == "SE":
        vertices = [
            (0, 0),
            (W - cw, 0),
            (W - cw, ch),
            (W, ch),
            (W, H),
            (0, H),
        ]
    else:  # SW
        vertices = [
            (cw, 0),
            (W, 0),
            (W, H),
            (0, H),
            (0, ch),
            (cw, ch),
        ]

    return Polygon(vertices)


def notch_rect(cfg: PlotConfig) -> tuple[float, float, float, float] | None:
    """The off-plot cutout (x0, y0, x1, y1) in plot metres, or None.

    `plot_template` surface only — the legacy `plot_shape == "l_shaped"`
    cutout keeps its own long-standing geometry (`compute_l_shaped_polygon`)
    untouched. Lives here rather than in solver.py because the boundary, the
    compliance check and the fill passes all need it and none of them may
    import the solver.
    """
    if cfg.plot_template == "RECT" or cfg.notch_width <= 0 or cfg.notch_depth <= 0:
        return None
    return (
        cfg.plot_width - cfg.notch_width,
        cfg.plot_length - cfg.notch_depth,
        cfg.plot_width,
        cfg.plot_length,
    )


def notch_keepout(cfg: PlotConfig, wall_clearance: float = 0.0) -> Polygon | None:
    """The notch GROWN by the setbacks its two new plot edges attract.

    Cutting a corner out of a plot creates two new boundary edges, and a
    boundary edge earns a setback like any other: the rear-right cutout's
    vertical face looks outward in +x, so it takes `setback_right`, and its
    horizontal face looks outward in +y, so it takes `setback_rear`.

    Growing both and keeping a single rectangle also removes the little square
    diagonally inside the reflex corner. That is deliberate, not sloppiness:
    a point there is within the setback distance of the corner itself, so a
    perpendicular-distance reading of the byelaw excludes it anyway.

    This one rectangle is THE forbidden region — `buildable_polygon` subtracts
    it and `solver._forbid_notch` constrains parts out of it, so the solver,
    the compliance check and the fill passes cannot disagree about where the
    notch begins.
    """
    rect = notch_rect(cfg)
    if rect is None:
        return None
    x0, y0, x1, y1 = rect
    gx0, gy0, gx1, gy1 = rect  # grown copy; tests read the ORIGINAL edges
    if x1 >= cfg.plot_width:  # cutout on the right edge
        gx0 -= cfg.setback_right + wall_clearance
    if x0 <= 0:  # cutout on the left edge
        gx1 += cfg.setback_left + wall_clearance
    if y1 >= cfg.plot_length:  # cutout at the rear
        gy0 -= cfg.setback_rear + wall_clearance
    if y0 <= 0:  # cutout at the front
        gy1 += cfg.setback_front + wall_clearance
    return box(gx0, gy0, gx1, gy1)


def plot_polygon(cfg: PlotConfig) -> Polygon:
    """The plot boundary polygon for any supported plot shape (CCW).

    `plot_template` is checked FIRST and independently of `plot_shape`, which
    stays "rectangular" on that surface. Without this, every downstream
    consumer of the boundary — `buildable_polygon`, `compliance.check`,
    generator.py's blank-area fill/absorb passes, the archetype floor plate —
    would see the full rectangle and could put a room straight back into the
    notch that the solver's `_forbid_notch` had just kept clear, with
    compliance unable to see it.
    """
    rect = notch_rect(cfg)
    if rect is not None:
        # Rear-right corner cut out (the only `plot_template` geometry there
        # is; T/U are rejected in `solver.validate_plot_envelope`).
        nx0, ny0, _, _ = rect
        w, ln = cfg.plot_width, cfg.plot_length
        return orient(
            Polygon([(0.0, 0.0), (w, 0.0), (w, ny0), (nx0, ny0), (nx0, ln), (0.0, ln)]),
            1.0,
        )
    shape = cfg.plot_shape
    if shape == "quadrilateral" and cfg.plot_corners:
        return orient(Polygon(cfg.plot_corners), 1.0)
    if shape == "trapezoid" and cfg.plot_front_width and cfg.plot_rear_width:
        # Both edges centred on the plot axis — matches the SVG renderer
        w = max(cfg.plot_front_width, cfg.plot_rear_width)
        f0 = (w - cfg.plot_front_width) / 2
        r0 = (w - cfg.plot_rear_width) / 2
        return Polygon(
            [
                (f0, 0.0),
                (f0 + cfg.plot_front_width, 0.0),
                (r0 + cfg.plot_rear_width, cfg.plot_length),
                (r0, cfg.plot_length),
            ]
        )
    if shape == "l_shaped" and cfg.cutout_width > 0 and cfg.cutout_height > 0:
        return orient(compute_l_shaped_polygon(cfg), 1.0)
    return box(0.0, 0.0, cfg.plot_width, cfg.plot_length)


def _edge_setback(p1, p2, cfg: PlotConfig) -> float:
    """Setback for the plot edge p1->p2 (CCW), by outward-normal direction."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    nx, ny = dy, -dx  # outward normal of a CCW edge
    if abs(ny) >= abs(nx):
        return cfg.setback_front if ny < 0 else cfg.setback_rear
    return cfg.setback_left if nx < 0 else cfg.setback_right


def _halfplane_inward(p1, p2, offset: float) -> Polygon:
    """Half-plane at `offset` inward (left, for CCW) of the line p1->p2."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    ln = math.hypot(dx, dy)
    ux, uy = dx / ln, dy / ln
    nx, ny = -uy, ux  # inward (left) normal for CCW winding
    ax, ay = p1[0] + nx * offset, p1[1] + ny * offset
    bx, by = p2[0] + nx * offset, p2[1] + ny * offset
    return Polygon(
        [
            (ax - ux * _BIG, ay - uy * _BIG),
            (bx + ux * _BIG, by + uy * _BIG),
            (bx + ux * _BIG + nx * _BIG, by + uy * _BIG + ny * _BIG),
            (ax - ux * _BIG + nx * _BIG, ay - uy * _BIG + ny * _BIG),
        ]
    )


def buildable_polygon(cfg: PlotConfig, wall_clearance: float = 0.0) -> Polygon:
    """Plot polygon inset by each edge's OWN setback (+ wall_clearance).

    Returns an empty Polygon when the setbacks consume the plot. If the inset
    splits (deep L-shape cutouts), the largest piece is returned.

    A `plot_template` notch is handled by SUBTRACTION rather than by the
    half-plane loop below. That loop intersects one inward half-plane per edge,
    which is only correct for a convex outline: on a notched plot the two
    cutout edges' half-planes extend across the whole plot and shear off
    buildable land nowhere near the notch (91.8 m² -> 37.1 m² on the 12x15 m L
    fixture). The legacy `plot_shape == "l_shaped"` surface still goes through
    the loop — that conservatism is long-standing behaviour there and
    `archetypes._l_shaped_floor_plate` is calibrated against it — but the new
    surface gets the exact region: rectangle inset by the four outer setbacks,
    minus the setback-grown notch keep-out.
    """
    keepout = notch_keepout(cfg, wall_clearance)
    if keepout is not None:
        outer = box(
            cfg.setback_left + wall_clearance,
            cfg.setback_front + wall_clearance,
            cfg.plot_width - cfg.setback_right - wall_clearance,
            cfg.plot_length - cfg.setback_rear - wall_clearance,
        )
        if outer.is_empty or outer.area <= 0:
            return Polygon()
        result = outer.difference(keepout)
        if result.geom_type == "MultiPolygon":
            result = max(result.geoms, key=lambda g: g.area)
        if result.geom_type != "Polygon" or result.is_empty:
            return Polygon()
        return orient(result, 1.0)

    poly = orient(plot_polygon(cfg), 1.0)
    result: Polygon = poly
    coords = list(poly.exterior.coords)[:-1]
    n = len(coords)
    for i in range(n):
        p1, p2 = coords[i], coords[(i + 1) % n]
        inset = _edge_setback(p1, p2, cfg) + wall_clearance
        if inset <= 0:
            continue
        clipped = result.intersection(_halfplane_inward(p1, p2, inset))
        if clipped.is_empty:
            return Polygon()
        result = clipped
    if result.geom_type == "MultiPolygon":
        result = max(result.geoms, key=lambda g: g.area)
    if result.geom_type != "Polygon" or result.is_empty:
        return Polygon()
    return orient(result, 1.0)
