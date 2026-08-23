"""
Advanced CAD drawing using Shapely set operations for DXF export.

Produces:
- Building footprint (unary_union of all room boxes)
- Setback dimension callouts (4 sides)
- Compound boundary wall with gate gap on road-facing side
- Open terrace / setback zone hatching
- Structural grid with alphanumeric bubble labels
- Furniture symbols dispatched by room type
"""

from __future__ import annotations

import logging
import string

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Shapely → DXF conversion helpers
# ─────────────────────────────────────────────────────────────────────────────


def shapely_poly_to_dxf(msp, poly, layer: str, z: float) -> None:
    """Convert a Shapely Polygon (with possible holes) to DXF LWPOLYLINE(s).

    Notes
    -----
    - Do NOT pass ``elevation`` in ``dxfattribs`` to ``add_lwpolyline``;
      set ``.dxf.elevation`` on the returned entity instead.
    - ``exterior.coords[:-1]`` drops the closing duplicate point Shapely appends.
    - Interior rings (holes) are drawn as separate closed polylines.
    """
    if poly is None or poly.is_empty:
        return

    if poly.geom_type in ("MultiPolygon", "GeometryCollection"):
        for geom in poly.geoms:
            if geom.geom_type == "Polygon":
                shapely_poly_to_dxf(msp, geom, layer, z)
        return

    ext_pts = [(x, y) for x, y in poly.exterior.coords[:-1]]
    if len(ext_pts) < 3:
        return
    ent = msp.add_lwpolyline(ext_pts, close=True, dxfattribs={"layer": layer})
    ent.dxf.elevation = z

    for interior in poly.interiors:
        int_pts = [(x, y) for x, y in interior.coords[:-1]]
        if len(int_pts) < 3:
            continue
        ent_i = msp.add_lwpolyline(int_pts, close=True, dxfattribs={"layer": layer})
        ent_i.dxf.elevation = z


def _hatch_polygon(msp, poly, pattern: str, scale: float, layer: str, z: float) -> None:
    """Hatch a Shapely polygon with a named DXF fill pattern.

    Interior rings (holes) use ``flags=1`` so ezdxf treats them as exclusion paths.
    """
    if poly is None or poly.is_empty:
        return

    if poly.geom_type in ("MultiPolygon", "GeometryCollection"):
        for geom in poly.geoms:
            if geom.geom_type == "Polygon":
                _hatch_polygon(msp, geom, pattern, scale, layer, z)
        return

    try:
        hatch = msp.add_hatch(dxfattribs={"layer": layer})
        hatch.dxf.elevation = z
        hatch.set_pattern_fill(pattern, scale=scale)

        ext_pts = [(x, y) for x, y in poly.exterior.coords[:-1]]
        hatch.paths.add_polyline_path(ext_pts, is_closed=True)

        for interior in poly.interiors:
            int_pts = [(x, y) for x, y in interior.coords[:-1]]
            hatch.paths.add_polyline_path(int_pts, is_closed=True, flags=1)
    except Exception:
        pass


def solid_fill_polygon(msp, poly, layer: str, z: float) -> None:
    """Hatch a Shapely polygon solid black (IS:962/AIA wall-poché convention).

    Interior rings (holes — door/window openings already subtracted from the
    wall footprint) use ``flags=1`` so ezdxf treats them as exclusion paths.
    ``elevation`` is set on the entity after creation, never via dxfattribs
    at add_hatch() time — passing it there raises a TypeError in ezdxf.
    """
    if poly is None or poly.is_empty:
        return

    if poly.geom_type in ("MultiPolygon", "GeometryCollection"):
        for geom in poly.geoms:
            if geom.geom_type == "Polygon":
                solid_fill_polygon(msp, geom, layer, z)
        return

    try:
        hatch = msp.add_hatch(dxfattribs={"layer": layer})
        hatch.dxf.elevation = z
        hatch.set_solid_fill()

        ext_pts = [(x, y) for x, y in poly.exterior.coords[:-1]]
        hatch.paths.add_polyline_path(ext_pts, is_closed=True)

        for interior in poly.interiors:
            int_pts = [(x, y) for x, y in interior.coords[:-1]]
            hatch.paths.add_polyline_path(int_pts, is_closed=True, flags=1)
    except Exception as exc:
        logger.warning("Wall hatch failed on layer %s: %s", layer, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Building footprint
# ─────────────────────────────────────────────────────────────────────────────


def draw_building_footprint(msp, rooms: list, layer: str, z: float):
    """
    Compute ``unary_union`` of all room bounding boxes and draw as a bold LWPOLYLINE.

    Returns the resulting Shapely Polygon (or MultiPolygon) for downstream use,
    or ``None`` when rooms is empty / geometry is degenerate.
    """
    from shapely.geometry import box
    from shapely.ops import unary_union

    if not rooms:
        return None

    polys = [box(r.x, r.y, r.x + r.width, r.y + r.depth) for r in rooms]
    footprint = unary_union(polys)

    if footprint.is_empty:
        return None

    shapely_poly_to_dxf(msp, footprint, layer, z)
    return footprint


# ─────────────────────────────────────────────────────────────────────────────
# Setback dimension callouts
# ─────────────────────────────────────────────────────────────────────────────


def draw_setback_zones(
    msp,
    cfg,
    bld_x: float,
    bld_y: float,
    bld_w: float,
    bld_d: float,
    layer: str,
    z: float,
) -> None:
    """Draw 4 linear dimension callouts (front / rear / left / right setbacks)."""
    from app.engine.cad_primitives import metres_to_ftin

    pw, pl = cfg.plot_x_extent, cfg.plot_y_extent

    def _dim(base, p1, p2, angle: int, text: str) -> None:
        try:
            dim = msp.add_linear_dim(
                base=base,
                p1=p1,
                p2=p2,
                angle=angle,
                dxfattribs={"layer": layer},
            )
            dim.set_text(text)
            dim.render()
        except Exception:
            pass

    # Front setback: plot front (y=0) → building front (y=bld_y)
    if bld_y > 0.05:
        _dim(
            base=(bld_x - 1.5, bld_y / 2),
            p1=(bld_x - 0.5, 0.0),
            p2=(bld_x - 0.5, bld_y),
            angle=90,
            text=metres_to_ftin(bld_y),
        )

    # Rear setback: building rear → plot rear (y=pl)
    rear_gap = pl - (bld_y + bld_d)
    if rear_gap > 0.05:
        _dim(
            base=(bld_x + bld_w + 1.5, bld_y + bld_d + rear_gap / 2),
            p1=(bld_x + bld_w + 0.5, bld_y + bld_d),
            p2=(bld_x + bld_w + 0.5, pl),
            angle=90,
            text=metres_to_ftin(rear_gap),
        )

    # Left setback: plot left (x=0) → building left (x=bld_x)
    if bld_x > 0.05:
        _dim(
            base=(bld_x / 2, bld_y - 1.5),
            p1=(0.0, bld_y - 0.5),
            p2=(bld_x, bld_y - 0.5),
            angle=0,
            text=metres_to_ftin(bld_x),
        )

    # Right setback: building right → plot right (x=pw)
    right_gap = pw - (bld_x + bld_w)
    if right_gap > 0.05:
        _dim(
            base=(bld_x + bld_w + right_gap / 2, bld_y + bld_d + 1.5),
            p1=(bld_x + bld_w, bld_y + bld_d + 0.5),
            p2=(pw, bld_y + bld_d + 0.5),
            angle=0,
            text=metres_to_ftin(right_gap),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Compound boundary wall
# ─────────────────────────────────────────────────────────────────────────────


def _draw_gate_post(
    msp, cx: float, cy: float, size: float, layer: str, z: float
) -> None:
    h = size / 2
    pts = [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]
    ent = msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
    ent.dxf.elevation = z


def _draw_wall_segment_poly(msp, pts_2d: list[tuple], layer: str, z: float) -> None:
    """Draw a buffered wall polygon (LWPOLYLINE + HATCH fill)."""
    if len(pts_2d) < 3:
        return
    ent = msp.add_lwpolyline(pts_2d, close=True, dxfattribs={"layer": layer})
    ent.dxf.elevation = z
    try:
        hatch = msp.add_hatch(dxfattribs={"layer": layer})
        hatch.dxf.elevation = z
        hatch.set_pattern_fill("ANSI31", scale=0.03)
        hatch.paths.add_polyline_path(pts_2d, is_closed=True)
    except Exception:
        pass


def draw_compound_wall(msp, site, layer: str, z: float) -> None:
    """
    Draw compound (boundary) wall around the plot perimeter.

    Projects ``FloorDrawing.site`` (Task 32): buffers each canonical
    centreline (``site.compound_wall_segments``, gate gap already cut and
    aligned to the main entrance at DRAWING build time) into a poché polygon,
    and strokes the canonical gate posts (``site.gate_posts``) around it.
    This is a projection, not a second derivation of wall/gate geometry.
    """
    from shapely.geometry import LineString

    from app.engine.geometry import COMPOUND_WALL_HALF_THICKNESS_M

    wall_t = COMPOUND_WALL_HALF_THICKNESS_M
    post_size = 0.3

    for x1, y1, x2, y2 in site.compound_wall_segments:
        buf = LineString([(x1, y1), (x2, y2)]).buffer(
            wall_t, cap_style="flat", join_style="mitre"
        )
        if not buf.is_empty and buf.geom_type == "Polygon":
            pts = [(x, y) for x, y in buf.exterior.coords[:-1]]
            _draw_wall_segment_poly(msp, pts, layer, z)

    for gx, gy in site.gate_posts:
        _draw_gate_post(msp, gx, gy, post_size, layer, z)


# ─────────────────────────────────────────────────────────────────────────────
# Open terrace / setback hatching
# ─────────────────────────────────────────────────────────────────────────────


def draw_open_terrace(msp, terrace, layer: str, z: float) -> None:
    """Hatch the canonical open terrace (FloorDrawing.site.open_terrace —
    plot minus the ground-floor footprint, Task 32) as open ground."""
    if terrace is None or terrace.is_empty:
        return

    _hatch_polygon(msp, terrace, "ANSI37", 0.08, layer, z)


# ─────────────────────────────────────────────────────────────────────────────
# Structural grid
# ─────────────────────────────────────────────────────────────────────────────


def draw_structural_grid(
    msp,
    rooms: list,
    bld_x: float,
    bld_y: float,
    bld_w: float,
    bld_d: float,
    layer: str,
    z: float,
) -> None:
    """
    Draw alphanumeric structural grid with dashed lines and circle bubble labels.

    Column lines (vertical) are labelled A, B, C, …
    Row lines (horizontal) are labelled 1, 2, 3, …
    Each grid line gets a bubble at both ends.
    """
    if not rooms:
        return

    xs = sorted(
        {round(r.x, 3) for r in rooms} | {round(r.x + r.width, 3) for r in rooms}
    )
    ys = sorted(
        {round(r.y, 3) for r in rooms} | {round(r.y + r.depth, 3) for r in rooms}
    )

    bubble_r = 0.35
    ext = 0.8  # extension beyond building for grid lines

    # Vertical lines — column labels A, B, C, …
    for i, x in enumerate(xs):
        col_label = string.ascii_uppercase[i % 26]
        y_lo = bld_y - ext - bubble_r * 2
        y_hi = bld_y + bld_d + ext + bubble_r * 2
        msp.add_line(
            (x, y_lo, z),
            (x, y_hi, z),
            dxfattribs={"layer": layer, "linetype": "DASHED"},
        )
        for cy in [bld_y - ext - bubble_r, bld_y + bld_d + ext + bubble_r]:
            msp.add_circle((x, cy), radius=bubble_r, dxfattribs={"layer": layer})
            msp.add_mtext(
                col_label,
                dxfattribs={
                    "layer": layer,
                    "char_height": 0.28,
                    "insert": (x, cy, z),
                    "attachment_point": 5,
                },
            )

    # Horizontal lines — row labels 1, 2, 3, …
    for j, y in enumerate(ys):
        row_label = str(j + 1)
        x_lo = bld_x - ext - bubble_r * 2
        x_hi = bld_x + bld_w + ext + bubble_r * 2
        msp.add_line(
            (x_lo, y, z),
            (x_hi, y, z),
            dxfattribs={"layer": layer, "linetype": "DASHED"},
        )
        for cx in [bld_x - ext - bubble_r, bld_x + bld_w + ext + bubble_r]:
            msp.add_circle((cx, y), radius=bubble_r, dxfattribs={"layer": layer})
            msp.add_mtext(
                row_label,
                dxfattribs={
                    "layer": layer,
                    "char_height": 0.28,
                    "insert": (cx, y, z),
                    "attachment_point": 5,
                },
            )


def _grid_column_class(idx: int, n: int, jdx: int, m: int) -> str:
    """corner/edge/interior classification matching structapi's own grid
    classification: extreme index on both axes = corner, one axis = edge."""
    x_extreme = idx in (0, n - 1)
    y_extreme = jdx in (0, m - 1)
    if x_extreme and y_extreme:
        return "corner"
    if x_extreme or y_extreme:
        return "edge"
    return "interior"


def draw_sized_columns(
    msp,
    columns: list,
    walls: list,
    columns_data: dict,
    layer: str,
    z: float,
) -> None:
    """S-COLUMNS-SIZED: designed column rectangles (b_mm x D_mm) at grid
    intersections, classified corner/edge/interior from wall centrelines and
    sized per structapi's ``data.columns`` (keyed by class)."""
    if not columns or not columns_data:
        return

    def _cluster(vals: list[float], tol: float = 0.3) -> list[float]:
        groups: list[list[float]] = []
        for v in sorted(vals):
            if groups and v - groups[-1][-1] < tol:
                groups[-1].append(v)
            else:
                groups.append([v])
        return [sum(g) / len(g) for g in groups]

    v_xs = _cluster([w.x1 for w in walls if abs(w.x1 - w.x2) < 1e-9])
    h_ys = _cluster([w.y1 for w in walls if abs(w.y1 - w.y2) < 1e-9])
    if not v_xs or not h_ys:
        return

    def _nearest(vals: list[float], v: float) -> int:
        return min(range(len(vals)), key=lambda i: abs(vals[i] - v))

    for col in columns:
        ci = _nearest(v_xs, col.cx)
        cj = _nearest(h_ys, col.cy)
        klass = _grid_column_class(ci, len(v_xs), cj, len(h_ys))
        info = columns_data.get(klass)
        if not info:
            continue
        b, d = info["b_mm"] / 1000, info["D_mm"] / 1000
        pts = [
            (col.cx - b / 2, col.cy - d / 2),
            (col.cx + b / 2, col.cy - d / 2),
            (col.cx + b / 2, col.cy + d / 2),
            (col.cx - b / 2, col.cy + d / 2),
        ]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer, "elevation": z})
        msp.add_mtext(
            f"{klass[0].upper()} {int(info['b_mm'])}x{int(info['D_mm'])}",
            dxfattribs={
                "layer": layer,
                "char_height": 0.12,
                "insert": (col.cx, col.cy + d / 2 + 0.15, z),
                "attachment_point": 5,
            },
        )


def draw_structural_schedule(
    msp,
    columns_data: dict,
    beams_data: dict,
    insert_x: float,
    insert_y: float,
    layer: str,
    z: float,
) -> None:
    """S-SCHEDULE: COLUMN SCHEDULE + BEAM SCHEDULE as one MTEXT block, from
    the persisted structural design's structapi ``data``."""
    if not columns_data and not beams_data:
        return
    lines = ["COLUMN SCHEDULE"]
    for cls, v in sorted(columns_data.items()):
        lines.append(
            f"{cls.upper()}: {int(v['b_mm'])}x{int(v['D_mm'])} mm — "
            f"{v.get('bars', '—')}"
        )
    lines.append("")
    lines.append("BEAM SCHEDULE")
    for key, v in sorted(beams_data.items()):
        direction = key.split("-")[0].upper()
        lines.append(
            f"{direction}: {int(v['b_mm'])}x{int(v['D_mm'])} mm — "
            f"span {v.get('span_m', 0):.1f} m"
        )
    msp.add_mtext(
        "\\P".join(lines),
        dxfattribs={
            "layer": layer,
            "char_height": 0.18,
            "insert": (insert_x, insert_y, z),
            "attachment_point": 7,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────# Furniture — the canonical Task-33 projector
# ─────────────────────────────────────────────────────────────────────────────


def draw_furniture(msp, room, fixtures, layer: str, z: float) -> None:
    """Project this room's canonical Fixture shapes onto A-FURNITURE.

    The geometry is derived once in app/engine/furniture.py (room-relative,
    carried on FloorDrawing.fixtures); here it is simply translated by the
    room's origin and emitted with EXACTLY the ezdxf attribute pattern the
    pre-migration renderers used — including its quirk that circles carry no
    explicit elevation while arcs/polylines/lines do (the streams are
    golden-pinned in tests/fixtures/furniture_dxf_golden.json, so fix that
    deliberately in a follow-up, not silently here). All errors silently
    suppressed, as before.
    """
    try:
        for fixture in fixtures or []:
            if fixture.room_id != room.id:
                continue
            for sh in fixture.shapes:
                x, y = sh.x + room.x, sh.y + room.y
                if sh.kind == "rect":
                    attribs = {"layer": layer}
                    if sh.dashed:
                        attribs["linetype"] = "DASHED"
                    ent = msp.add_lwpolyline(
                        [
                            (x, y),
                            (x + sh.width, y),
                            (x + sh.width, y + sh.depth),
                            (x, y + sh.depth),
                        ],
                        close=True,
                        dxfattribs=attribs,
                    )
                    ent.dxf.elevation = z
                elif sh.kind == "circle":
                    # pre-migration behaviour: circles are emitted WITHOUT an
                    # explicit elevation — replicated faithfully
                    msp.add_circle(
                        (x, y), radius=sh.radius, dxfattribs={"layer": layer}
                    )
                elif sh.kind == "arc":
                    msp.add_arc(
                        center=(x, y),
                        radius=sh.radius,
                        start_angle=sh.start_deg,
                        end_angle=sh.end_deg,
                        dxfattribs={"layer": layer, "elevation": z},
                    )
                elif sh.kind == "line":
                    msp.add_line(
                        (x, y, z),
                        (sh.x2 + room.x, sh.y2 + room.y, z),
                        dxfattribs={"layer": layer},
                    )
    except Exception:
        pass
