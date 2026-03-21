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

import math
import string


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

    pw, pl = cfg.plot_width, cfg.plot_length

    def _dim(base, p1, p2, angle: int, text: str) -> None:
        try:
            dim = msp.add_linear_dim(
                base=base, p1=p1, p2=p2, angle=angle,
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

def _draw_gate_post(msp, cx: float, cy: float, size: float, layer: str, z: float) -> None:
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


def draw_compound_wall(msp, cfg, layer: str, z: float) -> None:
    """
    Draw compound (boundary) wall around the plot perimeter.

    Uses ``LineString.buffer(0.115)`` with mitered corners for each side.
    A 3.6 m gate gap is placed at the centre of the road-facing side,
    with 0.3 m square gate posts at the gap edges.
    """
    from shapely.geometry import LineString

    pw, pl = cfg.plot_width, cfg.plot_length
    road = (cfg.road_side or "S").upper()
    wall_t = 0.115
    gate_w = 3.6
    post_size = 0.3

    # Four sides: (start, end, side_id)
    sides: list[tuple] = [
        ((0.0, 0.0), (pw,  0.0), "S"),
        ((pw,  0.0), (pw,  pl),  "E"),
        ((pw,  pl),  (0.0, pl),  "N"),
        ((0.0, pl),  (0.0, 0.0), "W"),
    ]

    def _buf_and_draw(ls: "LineString") -> None:
        buf = ls.buffer(wall_t, cap_style="flat", join_style="mitre")
        if not buf.is_empty and buf.geom_type == "Polygon":
            pts = [(x, y) for x, y in buf.exterior.coords[:-1]]
            _draw_wall_segment_poly(msp, pts, layer, z)

    for p1, p2, side_id in sides:
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if length < 0.01:
            continue
        dx = (p2[0] - p1[0]) / length
        dy = (p2[1] - p1[1]) / length

        if side_id == road:
            gate_start_d = max(0.0, (length - gate_w) / 2)
            gate_end_d = min(length, gate_start_d + gate_w)

            # Wall segment before gate
            if gate_start_d > 0.1:
                sp = p1
                ep = (p1[0] + gate_start_d * dx, p1[1] + gate_start_d * dy)
                _buf_and_draw(LineString([sp, ep]))

            # Wall segment after gate
            if gate_end_d < length - 0.1:
                sp = (p1[0] + gate_end_d * dx, p1[1] + gate_end_d * dy)
                ep = p2
                _buf_and_draw(LineString([sp, ep]))

            # Gate posts
            gp1 = (p1[0] + gate_start_d * dx, p1[1] + gate_start_d * dy)
            gp2 = (p1[0] + gate_end_d * dx, p1[1] + gate_end_d * dy)
            _draw_gate_post(msp, gp1[0], gp1[1], post_size, layer, z)
            _draw_gate_post(msp, gp2[0], gp2[1], post_size, layer, z)
        else:
            _buf_and_draw(LineString([p1, p2]))


# ─────────────────────────────────────────────────────────────────────────────
# Open terrace / setback hatching
# ─────────────────────────────────────────────────────────────────────────────

def draw_open_terrace(msp, plot_poly, building_poly, layer: str, z: float) -> None:
    """Hatch the area between plot boundary and building footprint (terrace/setbacks)."""
    try:
        terrace = plot_poly.difference(building_poly)
    except Exception:
        return

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

    xs = sorted({round(r.x, 3) for r in rooms} | {round(r.x + r.width, 3) for r in rooms})
    ys = sorted({round(r.y, 3) for r in rooms} | {round(r.y + r.depth, 3) for r in rooms})

    bubble_r = 0.35
    ext = 0.8  # extension beyond building for grid lines

    # Vertical lines — column labels A, B, C, …
    for i, x in enumerate(xs):
        col_label = string.ascii_uppercase[i % 26]
        y_lo = bld_y - ext - bubble_r * 2
        y_hi = bld_y + bld_d + ext + bubble_r * 2
        msp.add_line(
            (x, y_lo, z), (x, y_hi, z),
            dxfattribs={"layer": layer, "linetype": "DASHED"},
        )
        for cy in [bld_y - ext - bubble_r, bld_y + bld_d + ext + bubble_r]:
            msp.add_circle((x, cy), radius=bubble_r, dxfattribs={"layer": layer})
            msp.add_mtext(
                col_label,
                dxfattribs={
                    "layer": layer, "char_height": 0.28,
                    "insert": (x, cy, z), "attachment_point": 5,
                },
            )

    # Horizontal lines — row labels 1, 2, 3, …
    for j, y in enumerate(ys):
        row_label = str(j + 1)
        x_lo = bld_x - ext - bubble_r * 2
        x_hi = bld_x + bld_w + ext + bubble_r * 2
        msp.add_line(
            (x_lo, y, z), (x_hi, y, z),
            dxfattribs={"layer": layer, "linetype": "DASHED"},
        )
        for cx in [bld_x - ext - bubble_r, bld_x + bld_w + ext + bubble_r]:
            msp.add_circle((cx, y), radius=bubble_r, dxfattribs={"layer": layer})
            msp.add_mtext(
                row_label,
                dxfattribs={
                    "layer": layer, "char_height": 0.28,
                    "insert": (cx, y, z), "attachment_point": 5,
                },
            )


# ─────────────────────────────────────────────────────────────────────────────
# Furniture symbols — one function per room type, strict context separation
# ─────────────────────────────────────────────────────────────────────────────
#
# Placement convention (y-axis increases away from road/entry):
#   "rear wall"  = room.y + room.depth  (far from door)
#   "front wall" = room.y               (near door / corridor side)
#   "left wall"  = room.x
#   "right wall" = room.x + room.width
#
# Rule: all furniture is pushed against a wall; nothing floats in the centre.
# ─────────────────────────────────────────────────────────────────────────────

def _rect(msp, x: float, y: float, w: float, d: float, layer: str, z: float) -> None:
    """Convenience: draw a closed rectangle."""
    ent = msp.add_lwpolyline(
        [(x, y), (x + w, y), (x + w, y + d), (x, y + d)],
        close=True, dxfattribs={"layer": layer},
    )
    ent.dxf.elevation = z


# ── Bedroom / Master Bedroom ──────────────────────────────────────────────────

def _furniture_bedroom(msp, room, layer: str, z: float) -> None:
    """
    Bed with headboard against the **rear wall** (far from door).
    For master bedroom: double bed (1.8 m); regular bedroom: single (1.2 m).
    Side table circle on the right.
    """
    margin = 0.15
    is_master = room.type == "master_bedroom"
    bed_w = min(1.8 if is_master else 1.2, room.width - 2 * margin)
    bed_d = min(2.0, room.depth - margin)
    if bed_w < 0.5 or bed_d < 0.5:
        return

    # Head against the rear wall — bed frame
    bx = room.x + (room.width - bed_w) / 2
    by = room.y + room.depth - margin - bed_d  # headboard at the top
    _rect(msp, bx, by, bed_w, bed_d, layer, z)

    # Headboard bar (10 cm strip at the top of bed)
    _rect(msp, bx, by + bed_d - 0.1, bed_w, 0.1, layer, z)

    # Pillow arc at the head (near rear wall)
    msp.add_arc(
        center=(bx + bed_w / 2, by + bed_d - 0.25),
        radius=min(0.35, bed_w / 3),
        start_angle=0, end_angle=180,
        dxfattribs={"layer": layer, "elevation": z},
    )

    # Side table (small circle on the right of the bed)
    st_r = 0.25
    if room.width - (bx - room.x + bed_w) > st_r + 0.1:
        msp.add_circle(
            (bx + bed_w + margin + st_r, by + bed_d - st_r - 0.1),
            radius=st_r,
            dxfattribs={"layer": layer},
        )


# ── Living Room ───────────────────────────────────────────────────────────────

def _furniture_living(msp, room, layer: str, z: float) -> None:
    """
    3-seater sofa against the **rear wall**, facing toward the entry.
    Coffee table rect in front of the sofa.
    TV unit (thin rect) against the **front wall**, opposite the sofa.
    No dining table here — that belongs in the dining room.
    """
    margin = 0.2
    sofa_w = min(2.4, room.width - 2 * margin)
    sofa_d = 0.9
    if sofa_w < 1.0:
        return

    # Sofa back against rear wall (high y), facing down
    sx = room.x + (room.width - sofa_w) / 2
    sy = room.y + room.depth - margin - sofa_d

    # Sofa back
    _rect(msp, sx, sy, sofa_w, sofa_d, layer, z)
    # Left armrest
    _rect(msp, sx, sy, 0.3, sofa_d, layer, z)
    # Right armrest
    _rect(msp, sx + sofa_w - 0.3, sy, 0.3, sofa_d, layer, z)

    # Coffee table in front of sofa (centred, 0.6 m gap from sofa)
    ct_w = min(1.2, sofa_w * 0.6)
    ct_d = 0.5
    ct_x = room.x + (room.width - ct_w) / 2
    ct_y = sy - 0.6 - ct_d
    if ct_y > room.y + margin:
        _rect(msp, ct_x, ct_y, ct_w, ct_d, layer, z)

    # TV unit against front wall (thin rect)
    tv_w = min(1.8, room.width - 2 * margin)
    tv_d = 0.4
    tv_x = room.x + (room.width - tv_w) / 2
    tv_y = room.y + margin
    _rect(msp, tv_x, tv_y, tv_w, tv_d, layer, z)


# ── Dining Room ───────────────────────────────────────────────────────────────

def _furniture_dining(msp, room, layer: str, z: float) -> None:
    """
    Rectangular dining table centred in the room.
    4 chairs for small tables, 6 chairs for large tables.
    Each chair is a small circle on each side.
    """
    margin = 0.4
    tbl_w = min(1.8, room.width - 2 * margin)
    tbl_d = min(0.9, room.depth - 2 * margin)
    if tbl_w < 0.8 or tbl_d < 0.5:
        return

    tx = room.x + (room.width - tbl_w) / 2
    ty = room.y + (room.depth - tbl_d) / 2
    _rect(msp, tx, ty, tbl_w, tbl_d, layer, z)

    # Chairs: circles along the long sides (top and bottom)
    chair_r = 0.22
    gap = 0.05
    num_side_chairs = 3 if tbl_w >= 1.5 else 2
    for i in range(num_side_chairs):
        cx = tx + tbl_w / (num_side_chairs + 1) * (i + 1)
        # Bottom chairs
        msp.add_circle((cx, ty - gap - chair_r), radius=chair_r,
                       dxfattribs={"layer": layer})
        # Top chairs
        msp.add_circle((cx, ty + tbl_d + gap + chair_r), radius=chair_r,
                       dxfattribs={"layer": layer})

    # One chair on each short side
    msp.add_circle((tx - gap - chair_r, ty + tbl_d / 2), radius=chair_r,
                   dxfattribs={"layer": layer})
    msp.add_circle((tx + tbl_w + gap + chair_r, ty + tbl_d / 2), radius=chair_r,
                   dxfattribs={"layer": layer})


# ── Kitchen ───────────────────────────────────────────────────────────────────

def _furniture_kitchen(msp, room, layer: str, z: float) -> None:
    """
    L-shaped counter along the **rear wall** and **left wall**
    (typical placement against solid/exterior walls with ventilation).
    Sink on the rear counter (right end, near window).
    Stove on the rear counter (left end).
    """
    margin = 0.05
    cw = 0.6   # counter depth/width
    if room.width < 1.2 or room.depth < 1.2:
        return

    rx, ry, rw, rd = room.x, room.y, room.width, room.depth

    # Rear counter (along the top/rear wall: y = ry + rd - margin - cw)
    rear_y = ry + rd - margin - cw
    rear_x0 = rx + margin
    rear_len = rw - 2 * margin
    _rect(msp, rear_x0, rear_y, rear_len, cw, layer, z)

    # Left counter (L-arm along left wall, from front up to rear counter)
    left_len = rd - 2 * margin - cw  # stop before rear counter
    if left_len > 0.5:
        _rect(msp, rx + margin, ry + margin, cw, left_len, layer, z)

    # Sink: on the rear counter, right end (near exterior/window wall)
    sink_x = rear_x0 + rear_len - 0.65
    sink_y = rear_y
    _rect(msp, sink_x, sink_y, 0.55, cw, layer, z)
    msp.add_circle((sink_x + 0.275, sink_y + cw / 2), radius=0.18,
                   dxfattribs={"layer": layer})

    # Stove: on the rear counter, left end
    stove_w = min(0.6, rear_len * 0.4)
    stove_x = rear_x0 + 0.1
    _rect(msp, stove_x, rear_y, stove_w, cw, layer, z)
    for bfx, bfy in [
        (stove_x + stove_w * 0.3, rear_y + cw * 0.3),
        (stove_x + stove_w * 0.7, rear_y + cw * 0.3),
        (stove_x + stove_w * 0.3, rear_y + cw * 0.7),
        (stove_x + stove_w * 0.7, rear_y + cw * 0.7),
    ]:
        msp.add_circle((bfx, bfy), radius=0.07, dxfattribs={"layer": layer})


# ── Toilet / Bathroom ─────────────────────────────────────────────────────────

def _furniture_toilet(msp, room, layer: str, z: float) -> None:
    """
    WC in the **rear-left** corner (far from door, against solid wall).
    Wash basin in the **front-right** corner (near door, easy access).
    Bathtub along the rear wall if room depth ≥ 1.5 m (bathroom type only).
    """
    margin = 0.08
    if room.width < 0.8 or room.depth < 0.8:
        return

    rx, ry, rw, rd = room.x, room.y, room.width, room.depth

    # WC — rear-left corner: tank against rear wall, bowl extending downward
    wc_cx = rx + margin + 0.2
    wc_cy = ry + rd - margin - 0.15  # tank base at the rear wall

    # Tank rect (against rear wall)
    _rect(msp, wc_cx - 0.175, wc_cy, 0.35, 0.15, layer, z)

    # Bowl arc — D-shape extending toward the room interior (downward)
    bowl_cy = wc_cy  # bowl centre at the tank bottom edge
    msp.add_arc(
        center=(wc_cx, bowl_cy),
        radius=0.18,
        start_angle=180, end_angle=360,
        dxfattribs={"layer": layer, "elevation": z},
    )
    msp.add_line(
        (wc_cx - 0.18, bowl_cy, z), (wc_cx + 0.18, bowl_cy, z),
        dxfattribs={"layer": layer},
    )

    # Wash basin — front-right corner (near the door)
    basin_cx = rx + rw - margin - 0.2
    basin_cy = ry + margin + 0.2
    msp.add_circle((basin_cx, basin_cy), radius=0.18,
                   dxfattribs={"layer": layer})

    # Bathtub — along rear wall if room is large enough (bathroom)
    if room.type == "bathroom" and rd >= 1.5 and rw >= 1.2:
        bt_w = min(1.5, rw - 2 * margin)
        bt_d = 0.7
        bt_x = rx + (rw - bt_w) / 2
        bt_y = ry + rd - margin - bt_d
        _rect(msp, bt_x, bt_y, bt_w, bt_d, layer, z)
        # Drain circle
        msp.add_circle((bt_x + bt_w / 2, bt_y + bt_d / 2), radius=0.07,
                       dxfattribs={"layer": layer})


# ── Study / Home Office ───────────────────────────────────────────────────────

def _furniture_study(msp, room, layer: str, z: float) -> None:
    """
    L-shaped desk against the **rear wall** and **right wall**.
    Office chair (circle) in front of the desk.
    Bookshelf (thin rect) along the **left wall**.
    """
    margin = 0.15
    if room.width < 1.5 or room.depth < 1.5:
        return

    rx, ry, rw, rd = room.x, room.y, room.width, room.depth
    desk_d = 0.6  # desk depth

    # Main desk along rear wall
    desk_w = min(1.8, rw - 2 * margin)
    desk_x = rx + (rw - desk_w) / 2
    desk_y = ry + rd - margin - desk_d
    _rect(msp, desk_x, desk_y, desk_w, desk_d, layer, z)

    # Return (L-arm) along right wall
    ret_w = desk_d
    ret_d = min(1.0, rd - 2 * margin - desk_d)
    if ret_d > 0.4:
        _rect(msp, rx + rw - margin - ret_w,
              desk_y - ret_d, ret_w, ret_d, layer, z)

    # Chair (circle) in front of desk
    chair_r = 0.3
    msp.add_circle(
        (desk_x + desk_w / 2, desk_y - chair_r - 0.1),
        radius=chair_r,
        dxfattribs={"layer": layer},
    )

    # Bookshelf along left wall (thin rect)
    shelf_d = 0.3
    shelf_h = min(1.2, rd - 2 * margin)
    _rect(msp, rx + margin, ry + margin, shelf_d, shelf_h, layer, z)


# ── Pooja Room ────────────────────────────────────────────────────────────────

def _furniture_pooja(msp, room, layer: str, z: float) -> None:
    """
    Altar platform against the **rear wall** (facing east per Vastu convention).
    Simple platform rect with a small pedestal circle for the idol.
    """
    margin = 0.1
    if room.width < 0.8 or room.depth < 0.6:
        return

    rx, ry, rw, rd = room.x, room.y, room.width, room.depth

    # Platform along rear wall
    plat_w = min(1.0, rw - 2 * margin)
    plat_d = 0.5
    plat_x = rx + (rw - plat_w) / 2
    plat_y = ry + rd - margin - plat_d
    _rect(msp, plat_x, plat_y, plat_w, plat_d, layer, z)

    # Pedestal (idol/lamp circle) centred on the platform
    msp.add_circle(
        (plat_x + plat_w / 2, plat_y + plat_d / 2),
        radius=min(0.15, plat_w / 4),
        dxfattribs={"layer": layer},
    )


# ── Balcony ───────────────────────────────────────────────────────────────────

def _furniture_balcony(msp, room, layer: str, z: float) -> None:
    """
    Two patio chairs (circles) along the rear wall and a small table (circle) between them.
    """
    margin = 0.2
    if room.width < 1.0 or room.depth < 1.0:
        return

    rx, ry, rw, rd = room.x, room.y, room.width, room.depth
    chair_r = 0.3

    # Place chairs near the rear wall, evenly spaced
    cy = ry + rd - margin - chair_r
    if rw >= 2.0:
        c1x = rx + rw * 0.25
        c2x = rx + rw * 0.75
        msp.add_circle((c1x, cy), radius=chair_r, dxfattribs={"layer": layer})
        msp.add_circle((c2x, cy), radius=chair_r, dxfattribs={"layer": layer})
        # Small table between the chairs
        msp.add_circle((rx + rw / 2, cy), radius=0.2, dxfattribs={"layer": layer})
    else:
        msp.add_circle((rx + rw / 2, cy), radius=chair_r, dxfattribs={"layer": layer})


# ── Utility / Laundry ────────────────────────────────────────────────────────

def _furniture_utility(msp, room, layer: str, z: float) -> None:
    """
    Washing machine (rect + concentric circles) against the **rear wall**.
    Optional overhead storage shelf (thin rect) along the side wall.
    """
    margin = 0.1
    if room.width < 0.8 or room.depth < 0.8:
        return

    rx, ry, rw, rd = room.x, room.y, room.width, room.depth
    wm_size = 0.6  # washing machine footprint

    # Washing machine against the rear wall
    wm_x = rx + (rw - wm_size) / 2
    wm_y = ry + rd - margin - wm_size
    _rect(msp, wm_x, wm_y, wm_size, wm_size, layer, z)
    # Drum circles (outer + inner)
    cx, cy = wm_x + wm_size / 2, wm_y + wm_size / 2
    msp.add_circle((cx, cy), radius=wm_size * 0.38, dxfattribs={"layer": layer})
    msp.add_circle((cx, cy), radius=wm_size * 0.18, dxfattribs={"layer": layer})

    # Shelf along left wall (thin rect)
    shelf_h = min(1.0, rd - 2 * margin)
    if rw > 1.2:
        _rect(msp, rx + margin, ry + margin, 0.3, shelf_h, layer, z)


# ── Servant Quarter ───────────────────────────────────────────────────────────

def _furniture_servant_quarter(msp, room, layer: str, z: float) -> None:
    """
    Single bed (1.0 m wide) against the rear wall.
    Small wardrobe rect along the side wall.
    """
    margin = 0.1
    bed_w = min(1.0, room.width - 2 * margin)
    bed_d = min(1.9, room.depth - margin)
    if bed_w < 0.5 or bed_d < 0.5:
        return

    rx, ry, rw, rd = room.x, room.y, room.width, room.depth

    bx = rx + (rw - bed_w) / 2
    by = ry + rd - margin - bed_d
    _rect(msp, bx, by, bed_w, bed_d, layer, z)
    # Headboard
    _rect(msp, bx, by + bed_d - 0.08, bed_w, 0.08, layer, z)

    # Wardrobe along left wall
    wardrobe_w = 0.55
    wardrobe_h = min(1.2, rd - 2 * margin - bed_d - 0.3)
    if wardrobe_h > 0.4 and rw > 1.3:
        _rect(msp, rx + margin, ry + margin, wardrobe_w, wardrobe_h, layer, z)


# ── Parking / Garage ─────────────────────────────────────────────────────────

def _furniture_parking(msp, room, layer: str, z: float) -> None:
    """
    Dashed stall outline marking the parking bay.
    Car silhouette (rect) centred in the stall.
    """
    # Dashed stall outline
    ent = msp.add_lwpolyline(
        [(room.x, room.y), (room.x + room.width, room.y),
         (room.x + room.width, room.y + room.depth), (room.x, room.y + room.depth)],
        close=True,
        dxfattribs={"layer": layer, "linetype": "DASHED"},
    )
    ent.dxf.elevation = z

    margin = 0.3
    car_w = min(2.0, room.width - 2 * margin)
    car_d = min(4.5, room.depth - 2 * margin)
    if car_w < 0.5 or car_d < 0.5:
        return

    cx_off = room.x + (room.width - car_w) / 2
    cy_off = room.y + (room.depth - car_d) / 2
    _rect(msp, cx_off, cy_off, car_w, car_d, layer, z)


def _furniture_gym(msp, room, layer: str, z: float) -> None:
    """
    Treadmill (rect) against the rear wall.
    Dumbbell rack (thin rect) along the left wall.
    Open exercise mat area indicated by a dashed rect in the centre.
    """
    margin = 0.15
    if room.width < 2.0 or room.depth < 2.0:
        return

    rx, ry, rw, rd = room.x, room.y, room.width, room.depth

    # Treadmill against rear wall (1.8 × 0.8)
    tm_w = min(1.8, rw - 2 * margin)
    tm_x = rx + (rw - tm_w) / 2
    tm_y = ry + rd - margin - 0.8
    _rect(msp, tm_x, tm_y, tm_w, 0.8, layer, z)

    # Dumbbell rack along left wall (narrow tall rect)
    rack_h = min(1.0, rd - 2 * margin - 0.8 - 0.3)
    if rack_h > 0.4:
        _rect(msp, rx + margin, ry + margin, 0.4, rack_h, layer, z)

    # Exercise mat (dashed outline) in the remaining floor area
    mat_x = rx + margin
    mat_y = ry + margin + rack_h + 0.2
    mat_w = rw - 2 * margin
    mat_d = max(0.5, tm_y - mat_y - 0.3)
    if mat_d > 0.5:
        ent = msp.add_lwpolyline(
            [(mat_x, mat_y), (mat_x + mat_w, mat_y),
             (mat_x + mat_w, mat_y + mat_d), (mat_x, mat_y + mat_d)],
            close=True,
            dxfattribs={"layer": layer, "linetype": "DASHED"},
        )
        ent.dxf.elevation = z


# ── Dispatch table ────────────────────────────────────────────────────────────

_FURNITURE_DISPATCH = {
    "bedroom":          _furniture_bedroom,
    "master_bedroom":   _furniture_bedroom,
    "living":           _furniture_living,
    "dining":           _furniture_dining,
    "kitchen":          _furniture_kitchen,
    "toilet":           _furniture_toilet,
    "bathroom":         _furniture_toilet,
    "study":            _furniture_study,
    "home_office":      _furniture_study,
    "pooja":            _furniture_pooja,
    "balcony":          _furniture_balcony,
    "utility":          _furniture_utility,
    "servant_quarter":  _furniture_servant_quarter,
    "parking":          _furniture_parking,
    "garage":           _furniture_parking,
    "gym":              _furniture_gym,
    # No furniture: staircase, passage, store_room (empty by design)
}


def draw_furniture(msp, room, layer: str, z: float) -> None:
    """Dispatch to room-type-specific furniture drawing. All errors silently suppressed."""
    try:
        fn = _FURNITURE_DISPATCH.get(room.type)
        if fn:
            fn(msp, room, layer, z)
    except Exception:
        pass
