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
from app.engine.shapes import SHAPE_TEMPLATES

_BIG = 1e5

# Mirrors solver._UNIMPLEMENTED_PLOT_TEMPLATES — kept local (not imported from
# solver.py) because geometry.py is the lower-level module solver.py itself
# depends on. A "T" plot has a notch in each rear corner and a "U" plot a
# central one; representing either as the single rectangle below would
# silently under-constrain the boundary and hand back land the user does not
# own. `notch_rect` must reject them itself rather than relying on every
# caller to have already gone through solver.validate_plot_envelope first.
_UNIMPLEMENTED_PLOT_TEMPLATES: frozenset[str] = frozenset({"T", "U"})

# Compound (boundary) wall — shared between the DXF poché renderer
# (cad_advanced.draw_compound_wall) and the PDF site plan
# (pdf._draw_compound_wall). GATE_WIDTH_M is the shipping DXF value (this was
# already 3.6 m before this module existed); it does NOT match the 3.0 m
# figure in the Task 11 spec sample, which was illustrative only.
GATE_WIDTH_M = 3.6
COMPOUND_WALL_HALF_THICKNESS_M = 0.115  # Shapely buffer distance (DXF poché)
COMPOUND_WALL_THICKNESS_M = (
    COMPOUND_WALL_HALF_THICKNESS_M * 2
)  # 0.23 m, PDF stroke width

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
    elif cfg.cutout_corner == "SW":
        vertices = [
            (cw, 0),
            (W, 0),
            (W, H),
            (0, H),
            (0, ch),
            (cw, ch),
        ]
    else:
        # Reject rather than guess: solver._notch_rect_mm's own fallback for
        # an unrecognised cutout_corner defaults to a DIFFERENT corner (NE)
        # than a silent default here would, which would forbid one corner in
        # the solver while the drawn/compliance boundary cuts out another.
        raise ValueError(
            f"unknown cutout_corner {cfg.cutout_corner!r}; expected one of "
            "'NE', 'NW', 'SE', 'SW'"
        )

    return Polygon(vertices)


def notch_rect(cfg: PlotConfig) -> tuple[float, float, float, float] | None:
    """The off-plot cutout (x0, y0, x1, y1) in plot metres, or None.

    `plot_template` surface only — the legacy `plot_shape == "l_shaped"`
    cutout keeps its own long-standing geometry (`compute_l_shaped_polygon`)
    untouched. Lives here rather than in solver.py because the boundary, the
    compliance check and the fill passes all need it and none of them may
    import the solver.

    Raises ValueError if a `plot_template` notch is combined with a
    non-rectangular `plot_shape`. Every consumer of this function models the
    notch as a corner cut out of a RECTANGLE — `plot_polygon` builds the
    hexagon from `plot_width`/`plot_length`, and `buildable_polygon` insets a
    plain box — so a trapezoid/quad/legacy-`l_shaped` outline would be
    silently discarded and the plan drawn on a plot the user does not have.
    Unreachable while the fields are engine-only, but Task 22 plumbs them
    through, and a wrong answer is worse than a refusal.
    """
    if cfg.plot_template == "RECT" or cfg.notch_width <= 0 or cfg.notch_depth <= 0:
        return None
    if cfg.plot_template not in SHAPE_TEMPLATES:
        raise ValueError(
            f"unknown plot_template {cfg.plot_template!r}; expected one of "
            f"{sorted(SHAPE_TEMPLATES)}"
        )
    if cfg.plot_template in _UNIMPLEMENTED_PLOT_TEMPLATES:
        raise ValueError(
            f"plot_template={cfg.plot_template!r} is not implemented: a T plot "
            "has a notch in each rear corner and a U plot a central one, so "
            "the single-rectangle notch this function returns would "
            "under-constrain the boundary and hand back land the user does "
            "not own."
        )
    if cfg.plot_shape != "rectangular":
        raise ValueError(
            f"plot_template={cfg.plot_template!r} (a notch) cannot be combined with "
            f"plot_shape={cfg.plot_shape!r}: the notch is only defined as a corner "
            "cut out of a rectangular plot. Use one or the other — for an L-shaped "
            'trapezoid/quadrilateral neither surface applies, and plot_shape="l_shaped" '
            "already has its own cutout fields."
        )
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
    fixture). The new surface instead gets the exact region: rectangle inset by
    the four outer setbacks, minus the setback-grown notch keep-out.

    The legacy `plot_shape == "l_shaped"` surface is left on the loop only
    because changing it is out of this change's scope — NOT because anything
    depends on its conservatism. Nothing is calibrated against it: for the
    12x15 m NE-cutout config this loop returns 37.09 m² while
    `archetypes._l_shaped_floor_plate` hands back a 61.65 m² plate reaching
    y=13.27, so `compliance.check(archetypes.layout_a(cfg), ...)` fails with
    six "extends outside the setback boundary" violations. The two disagree,
    and the legacy surface is broken end to end today — a 3BHK needing ~96 m²
    cannot fit in 37 m², and the archetype fallback fails compliance. Fixing
    this loop is a P1 correctness fix; see the Task 9 report.
    """
    keepout = notch_keepout(cfg, wall_clearance)
    if keepout is not None:
        x0 = cfg.setback_left + wall_clearance
        y0 = cfg.setback_front + wall_clearance
        x1 = cfg.plot_width - cfg.setback_right - wall_clearance
        y1 = cfg.plot_length - cfg.setback_rear - wall_clearance
        # shapely.box() does not validate its bounds — reversed corners
        # (x1 <= x0 or y1 <= y0, i.e. setbacks consuming the whole plot)
        # still produce a positive-area polygon instead of an empty one, so
        # the inversion must be caught here before box() is called.
        if x1 <= x0 or y1 <= y0:
            return Polygon()
        outer = box(x0, y0, x1, y1)
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


def landscape_region(cfg: PlotConfig) -> Polygon:
    """The setback margin: `plot_polygon(cfg)` minus `buildable_polygon(cfg)`.

    Deliberately built from the two canonical polygons rather than
    `box(plot_width, plot_length).difference(box(...))`: the naive rectangle
    difference is only correct when the plot itself is an axis-aligned
    rectangle. `plot_polygon` honours `plot_template` notches and the
    trapezoid/quadrilateral/L-shaped `plot_shape`s, and `buildable_polygon`
    honours PER-EDGE setbacks on all of those — see this module's docstring.
    A rectangle-diff implementation would report a chunk of the trapezoid's
    narrowing rear corner (which is not plot land at all) as landscaped, and
    would use the same uniform inset on every edge of a quad or notched plot.

    `buildable_polygon` returns an empty Polygon when the setbacks consume
    the whole plot. There is then no legal buildable envelope, so every
    square metre of the plot IS the landscaped margin — this returns the
    whole plot rather than an empty region in that case.
    """
    plot = plot_polygon(cfg)
    buildable = buildable_polygon(cfg)
    if buildable.is_empty:
        return orient(plot, 1.0)
    return plot.difference(buildable)


# ─────────────────────────────────────────────────────────────────────────────
# Compound (boundary) wall — pure geometry shared by both renderers
# ─────────────────────────────────────────────────────────────────────────────


def _compound_wall_sides(
    pw: float, pl: float
) -> list[tuple[tuple[float, float], tuple[float, float], str]]:
    """The 4 plot-edge runs as (start, end, side_id), same order/winding as
    the pre-existing DXF implementation this was extracted from."""
    return [
        ((0.0, 0.0), (pw, 0.0), "S"),
        ((pw, 0.0), (pw, pl), "E"),
        ((pw, pl), (0.0, pl), "N"),
        ((0.0, pl), (0.0, 0.0), "W"),
    ]


def _gate_span(
    p1: tuple[float, float], p2: tuple[float, float], gate_cx: float | None
) -> tuple[float, float, float, float, float]:
    """Gate-gap placement along p1->p2. Returns (length, dx, dy, gate_start_d,
    gate_end_d), all as distances along the p1->p2 direction.

    Centred by default; centred on `gate_cx` (clamped to stay on the wall)
    when given and the run is horizontal — matches the main-entrance-aligned
    gate the DXF renderer has always drawn.
    """
    length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if length < 0.01:
        return length, 0.0, 0.0, 0.0, 0.0
    dx = (p2[0] - p1[0]) / length
    dy = (p2[1] - p1[1]) / length
    gate_w = min(GATE_WIDTH_M, length)
    if gate_cx is not None and abs(dx) > 0.5:
        gate_start_d = max(
            0.0, min((gate_cx - p1[0]) / dx - gate_w / 2, length - gate_w)
        )
    else:
        gate_start_d = max(0.0, (length - gate_w) / 2)
    gate_end_d = min(length, gate_start_d + gate_w)
    return length, dx, dy, gate_start_d, gate_end_d


def compound_wall_segments(
    cfg: PlotConfig, gate_cx: float | None = None
) -> list[tuple[float, float, float, float]]:
    """Boundary-wall centrelines as (x1, y1, x2, y2) in plot metres.

    One run per plot edge, except the road-facing edge (`cfg.road_side`),
    which is split into two runs around a `GATE_WIDTH_M`-wide gate gap —
    centred on the edge, or on `gate_cx` when given (see `_gate_span`).

    Plot coords: y=0 is the front/road edge, x=0 the left edge — the same
    convention `plan_geometry` and `cad_advanced` use.
    """
    pw, pl = cfg.plot_width, cfg.plot_length
    road = (cfg.road_side or "S").upper()
    out: list[tuple[float, float, float, float]] = []
    for p1, p2, side_id in _compound_wall_sides(pw, pl):
        if side_id != road:
            if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) >= 0.01:
                out.append((p1[0], p1[1], p2[0], p2[1]))
            continue
        length, dx, dy, gate_start_d, gate_end_d = _gate_span(p1, p2, gate_cx)
        if length < 0.01:
            continue
        if gate_start_d > 0.1:
            ep = (p1[0] + gate_start_d * dx, p1[1] + gate_start_d * dy)
            out.append((p1[0], p1[1], ep[0], ep[1]))
        if gate_end_d < length - 0.1:
            sp = (p1[0] + gate_end_d * dx, p1[1] + gate_end_d * dy)
            out.append((sp[0], sp[1], p2[0], p2[1]))
    return out


def compound_wall_gate_posts(
    cfg: PlotConfig, gate_cx: float | None = None
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Centre points of the two gate posts bracketing the road-side gate gap,
    or None if the road-side run has ~zero length. Shares `_gate_span` with
    `compound_wall_segments` so post positions always agree with the gap."""
    pw, pl = cfg.plot_width, cfg.plot_length
    road = (cfg.road_side or "S").upper()
    for p1, p2, side_id in _compound_wall_sides(pw, pl):
        if side_id != road:
            continue
        length, dx, dy, gate_start_d, gate_end_d = _gate_span(p1, p2, gate_cx)
        if length < 0.01:
            return None
        gp1 = (p1[0] + gate_start_d * dx, p1[1] + gate_start_d * dy)
        gp2 = (p1[0] + gate_end_d * dx, p1[1] + gate_end_d * dy)
        return gp1, gp2
    return None
