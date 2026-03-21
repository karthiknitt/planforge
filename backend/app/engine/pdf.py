from __future__ import annotations

import math
from datetime import date
from io import BytesIO

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.cad_primitives import metres_to_ftin
from app.engine.models import FloorPlan, Layout, PlotConfig

# ---------------------------------------------------------------------------
# Internal CAD drawing helpers (ReportLab, not ezdxf)
# ---------------------------------------------------------------------------

def _pdf_draw_double_line_wall(
    c: canvas.Canvas,
    x1: float, y1: float, x2: float, y2: float,
    thickness_px: float,
    gaps_px: list[tuple[float, float]],
    lw: float,
) -> None:
    """
    Draw a double-line wall segment in PDF coordinates with optional opening gaps.

    Parameters
    ----------
    c           : ReportLab canvas
    x1,y1,x2,y2: wall endpoints in PDF points
    thickness_px: total wall thickness in points
    gaps_px     : list of (start, end) distances along the wall to leave open
    lw          : line width
    """
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 0.5:
        return

    # Unit vector along wall and perpendicular
    ux = dx / length
    uy = dy / length
    px = -uy   # perpendicular
    py = ux
    h = thickness_px / 2

    # Sort and clamp gaps
    gaps_sorted = sorted(gaps_px)
    # Build solid segments
    segments: list[tuple[float, float]] = []
    pos = 0.0
    for gs, ge in gaps_sorted:
        gs = max(gs, 0.0)
        ge = min(ge, length)
        if gs > pos + 0.5:
            segments.append((pos, gs))
        pos = max(pos, ge)
    if pos < length - 0.5:
        segments.append((pos, length))
    if not segments:
        return

    c.setLineWidth(lw)
    c.setDash()
    for seg_start, seg_end in segments:
        t0 = seg_start / length
        t1 = seg_end / length
        # Outer line (away from origin perpendicular)
        c.line(
            x1 + t0 * dx + h * px, y1 + t0 * dy + h * py,
            x1 + t1 * dx + h * px, y1 + t1 * dy + h * py,
        )
        # Inner line
        c.line(
            x1 + t0 * dx - h * px, y1 + t0 * dy - h * py,
            x1 + t1 * dx - h * px, y1 + t1 * dy - h * py,
        )


def _dedup_wall_coords(coords: list[float], tol: float = 0.125) -> list[float]:
    """Remove near-duplicate coordinates from adjacent room faces separated by wall thickness.

    When rooms are separated by an internal wall (0.115m), xs contains both the right
    face of room A and the left face of room B — two values ~0.115m apart.  Keeping
    both causes two overlapping double-line walls to be drawn at each internal position,
    producing 3-4 lines with varying apparent thickness.  We keep only the first of
    any pair closer than `tol` (default 0.125 m ~ iwt + 10mm clearance).
    """
    result: list[float] = []
    for c in coords:
        if not result or abs(c - result[-1]) >= tol:
            result.append(c)
    return result


def _pdf_draw_door_arc(
    c: canvas.Canvas,
    hinge_x: float, hinge_y: float,
    door_px: float,
    wall_is_horizontal: bool,
    swing_into_room: bool,
) -> None:
    """
    Draw door leaf line + quarter-circle swing arc in PDF coordinates.

    hinge_x/y   : hinge point in PDF points
    door_px     : door width in points
    wall_is_horizontal : True = door on horizontal wall (N/S), leaf goes up/down
                         False = door on vertical wall (E/W), leaf goes left/right
    swing_into_room : controls which side the arc swings toward
    """
    c.setDash()
    if wall_is_horizontal:
        # Door leaf goes vertically (into the room above the wall)
        direction = 1 if swing_into_room else -1
        leaf_end_x = hinge_x + door_px
        leaf_end_y = hinge_y
        c.line(hinge_x, hinge_y, leaf_end_x, leaf_end_y)
        # Quarter-circle arc centered at hinge, radius = door width
        # Arc from 0° to 90° (counterclockwise into room)
        if swing_into_room:
            c.arc(hinge_x, hinge_y, hinge_x + door_px * 2, hinge_y + door_px * 2, 90, 90)
        else:
            c.arc(hinge_x - door_px * 2, hinge_y - door_px * 2, hinge_x, hinge_y, 0, 90)
    else:
        # Door leaf goes horizontally (into the room to the right of the wall)
        leaf_end_x = hinge_x
        leaf_end_y = hinge_y + door_px
        c.line(hinge_x, hinge_y, leaf_end_x, leaf_end_y)
        if swing_into_room:
            c.arc(hinge_x, hinge_y, hinge_x + door_px * 2, hinge_y + door_px * 2, 0, 90)
        else:
            c.arc(hinge_x - door_px * 2, hinge_y - door_px * 2, hinge_x, hinge_y, 270, 90)

# ── Colour palette (fill, stroke) ────────────────────────────────────────────
PALETTE: dict[str, tuple[str, str]] = {
    "living":    ("#FFFFFF", "#000000"),
    "bedroom":   ("#FFFFFF", "#000000"),
    "kitchen":   ("#FFFFFF", "#000000"),
    "toilet":    ("#FFFFFF", "#000000"),
    "staircase": ("#FFFFFF", "#000000"),
    "parking":   ("#FFFFFF", "#000000"),
    "utility":   ("#FFFFFF", "#000000"),
    "pooja":     ("#FFFFFF", "#000000"),
    "study":     ("#FFFFFF", "#000000"),
    "balcony":   ("#FFFFFF", "#000000"),
    "dining":    ("#FFFFFF", "#000000"),
}

# ── Page constants (points) ───────────────────────────────────────────────────
TITLE_H  = 90   # title block height (larger to accommodate area schedule)
MARGIN   = 52   # page margins (larger for chain dimension zone)
ROAD_H   = 18   # road strip height
ROAD_GAP = 4    # gap between road strip top and plot boundary bottom
TOP_PAD  = 30   # padding above plot for north arrow / scale bar
COL_SZ   = 2.5  # column marker half-size (pt) — fits within wall thickness
EXT_LW   = 2.0  # external wall lineweight (pt)
INT_LW   = 1.0  # internal wall lineweight (pt)
DIM_LW   = 0.5  # dimension line lineweight (pt)
WIN_LW   = 0.75 # window line lineweight (pt)
MIN_DIM_SPAN = 0.5  # metres — filter out wall-thickness micro-gaps from chain dims


# ── Public API ────────────────────────────────────────────────────────────────

def render_pdf(
    project_name: str,
    layout: Layout,
    cfg: PlotConfig,
    num_bedrooms: int,
    annotations: dict | None = None,
) -> bytes:
    """Return raw PDF bytes.

    Page order:
      1. Ground Floor architectural plan
      2. First Floor architectural plan
      3. Ground Floor structural (beam & column) layout
      4. First Floor structural (beam & column) layout
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # ── Architectural pages ────────────────────────────────────────────────────
    for floor_plan in [layout.ground_floor, layout.first_floor]:
        floor_label = "Ground Floor" if floor_plan.floor == 0 else "First Floor"
        _draw_floor(c, floor_plan, layout, cfg, project_name, num_bedrooms, floor_label,
                    annotations=annotations)
        c.showPage()

    # ── Structural pages ───────────────────────────────────────────────────────
    for floor_plan in [layout.ground_floor, layout.first_floor]:
        floor_label = "Ground Floor" if floor_plan.floor == 0 else "First Floor"
        _draw_structural_floor(c, floor_plan, layout, cfg, project_name, num_bedrooms, floor_label)
        c.showPage()

    c.save()
    return buf.getvalue()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _compute_layout(
    cfg: PlotConfig, page_w: float, page_h: float
) -> tuple[float, float, float, float, float]:
    """Return (scale pt/m, offset_x, offset_y, plot_px, plot_py)."""
    avail_w = page_w - 2 * MARGIN
    avail_h = page_h - TITLE_H - 2 * MARGIN - ROAD_H - ROAD_GAP - TOP_PAD

    scale   = min(avail_w / cfg.plot_width, avail_h / cfg.plot_length)
    plot_px = cfg.plot_width  * scale
    plot_py = cfg.plot_length * scale

    offset_x = MARGIN + (avail_w - plot_px) / 2
    offset_y = TITLE_H + MARGIN + ROAD_H + ROAD_GAP

    return scale, offset_x, offset_y, plot_px, plot_py


def _draw_floor(
    c: canvas.Canvas,
    floor_plan: FloorPlan,
    layout: Layout,
    cfg: PlotConfig,
    project_name: str,
    num_bedrooms: int,
    floor_label: str,
    annotations: dict | None = None,
) -> None:
    page_w, page_h = A4
    scale, ox, oy, plot_px, plot_py = _compute_layout(cfg, page_w, page_h)

    # ── Road strip ────────────────────────────────────────────────────────────
    road_y = TITLE_H + MARGIN
    # Road strip: two lines — floor plan label (top) + road direction (bottom)
    c.setFillColor(HexColor("#CCCCCC"))
    c.rect(ox, road_y, plot_px, ROAD_H, fill=1, stroke=0)
    road_side_name = {"S": "SOUTH", "N": "NORTH", "E": "EAST", "W": "WEST"}.get(cfg.road_side, "")
    cx_road = ox + plot_px / 2
    # Floor plan label — upper line (bold, black)
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(cx_road, road_y + ROAD_H - 7, floor_label.upper() + " PLAN")
    # Road direction — lower line (smaller, gray)
    c.setFillColor(HexColor("#444444"))
    c.setFont("Helvetica", 5.5)
    road_text = f"ROAD  ({road_side_name})" if road_side_name else "ROAD"
    c.drawCentredString(cx_road, road_y + 3, road_text)

    # ── Plot boundary (dashed) — thin black dashed rectangle, CAD convention ──
    c.setDash(5, 3)
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(0.5)
    if cfg.plot_shape == "quadrilateral" and cfg.plot_corners and len(cfg.plot_corners) == 4:
        pts = [(ox + cx * scale, oy + cy * scale) for cx, cy in cfg.plot_corners]
        p = c.beginPath()
        p.moveTo(*pts[0])
        for pt in pts[1:]:
            p.lineTo(*pt)
        p.close()
        c.drawPath(p, stroke=1, fill=0)
    else:
        c.rect(ox, oy, plot_px, plot_py, fill=0, stroke=1)
    c.setDash()

    # ── Room fills (coloured backgrounds) ─────────────────────────────────────
    for room in floor_plan.rooms:
        fill_hex, _ = PALETTE.get(room.type, ("#F8FAFC", "#94A3B8"))
        rx = ox + room.x * scale
        ry = oy + room.y * scale
        rw = room.width * scale
        rh = room.depth * scale
        c.setFillColor(HexColor(fill_hex))
        c.setStrokeColor(HexColor("#00000000"))  # transparent stroke
        c.setDash()
        c.rect(rx, ry, rw, rh, fill=1, stroke=0)

    # ── Walls, doors, windows (CAD-accurate) ─────────────────────────────────
    iwt = 0.115   # internal wall thickness (m)
    ewt = 0.23    # external wall thickness (m)
    rooms = floor_plan.rooms
    if rooms:
        xs = _dedup_wall_coords(sorted({r.x for r in rooms} | {r.x + r.width for r in rooms}))
        ys = _dedup_wall_coords(sorted({r.y for r in rooms} | {r.y + r.depth for r in rooms}))

        min_x = min(r.x for r in rooms)
        max_x = max(r.x + r.width for r in rooms)
        min_y = min(r.y for r in rooms)
        max_y = max(r.y + r.depth for r in rooms)

        # Build door-gap information: for each shared internal wall, mark a
        # 0.9 m door opening at the centre of the shared segment.
        door_w_m = 0.9
        # vertical_gaps[x_coord] = list of (y_start, y_end) openings in metres
        vertical_door_gaps: dict[float, list[tuple[float, float]]] = {}
        # horizontal_gaps[y_coord] = list of (x_start, x_end)
        horizontal_door_gaps: dict[float, list[tuple[float, float]]] = {}
        habitable_door = {"living", "bedroom", "master_bedroom", "kitchen",
                          "study", "dining", "utility", "pooja"}

        for i, ra in enumerate(rooms):
            for j, rb in enumerate(rooms):
                if j <= i:
                    continue
                # Vertical shared wall (ra right ≈ rb left)
                # Tolerance 0.15 covers rooms separated by internal wall thickness (~0.115m)
                if abs(ra.x + ra.width - rb.x) < 0.15:
                    if ra.type in habitable_door or rb.type in habitable_door:
                        y_lo = max(ra.y, rb.y)
                        y_hi = min(ra.y + ra.depth, rb.y + rb.depth)
                        if y_hi - y_lo > door_w_m + 0.1:
                            mid = (y_lo + y_hi) / 2
                            gap = (mid - door_w_m / 2, mid + door_w_m / 2)
                            vertical_door_gaps.setdefault(round(ra.x + ra.width, 3), []).append(gap)
                elif abs(rb.x + rb.width - ra.x) < 0.15:
                    if ra.type in habitable_door or rb.type in habitable_door:
                        y_lo = max(ra.y, rb.y)
                        y_hi = min(ra.y + ra.depth, rb.y + rb.depth)
                        if y_hi - y_lo > door_w_m + 0.1:
                            mid = (y_lo + y_hi) / 2
                            gap = (mid - door_w_m / 2, mid + door_w_m / 2)
                            vertical_door_gaps.setdefault(round(rb.x + rb.width, 3), []).append(gap)
                # Horizontal shared wall (ra top ≈ rb bottom)
                if abs(ra.y + ra.depth - rb.y) < 0.15:
                    if ra.type in habitable_door or rb.type in habitable_door:
                        x_lo = max(ra.x, rb.x)
                        x_hi = min(ra.x + ra.width, rb.x + rb.width)
                        if x_hi - x_lo > door_w_m + 0.1:
                            mid = (x_lo + x_hi) / 2
                            gap = (mid - door_w_m / 2, mid + door_w_m / 2)
                            horizontal_door_gaps.setdefault(round(ra.y + ra.depth, 3), []).append(gap)
                elif abs(rb.y + rb.depth - ra.y) < 0.15:
                    if ra.type in habitable_door or rb.type in habitable_door:
                        x_lo = max(ra.x, rb.x)
                        x_hi = min(ra.x + ra.width, rb.x + rb.width)
                        if x_hi - x_lo > door_w_m + 0.1:
                            mid = (x_lo + x_hi) / 2
                            gap = (mid - door_w_m / 2, mid + door_w_m / 2)
                            horizontal_door_gaps.setdefault(round(rb.y + rb.depth, 3), []).append(gap)

        # Build window-gap information for external walls: 1.2 m window at room centre
        win_w_m = 1.2
        habitable_win = {"living", "bedroom", "master_bedroom", "kitchen", "study", "dining"}
        # external_h_gaps[y_coord] = list of (x_start, x_end) for horizontal walls
        external_h_win_gaps: dict[float, list[tuple[float, float]]] = {}
        # external_v_gaps[x_coord] = list of (y_start, y_end) for vertical walls
        external_v_win_gaps: dict[float, list[tuple[float, float]]] = {}

        for room in rooms:
            if room.type not in habitable_win:
                continue
            rcx = room.x + room.width / 2
            rcy = room.y + room.depth / 2
            ww_h = min(win_w_m, room.width * 0.6)
            ww_v = min(win_w_m, room.depth * 0.6)
            tol = 0.05
            if abs(room.y - min_y) < tol:
                wy = round(min_y, 3)
                external_h_win_gaps.setdefault(wy, []).append(
                    (rcx - ww_h / 2, rcx + ww_h / 2)
                )
            if abs(room.y + room.depth - max_y) < tol:
                wy = round(max_y, 3)
                external_h_win_gaps.setdefault(wy, []).append(
                    (rcx - ww_h / 2, rcx + ww_h / 2)
                )
            if abs(room.x - min_x) < tol:
                wx = round(min_x, 3)
                external_v_win_gaps.setdefault(wx, []).append(
                    (rcy - ww_v / 2, rcy + ww_v / 2)
                )
            if abs(room.x + room.width - max_x) < tol:
                wx = round(max_x, 3)
                external_v_win_gaps.setdefault(wx, []).append(
                    (rcy - ww_v / 2, rcy + ww_v / 2)
                )

        c.setStrokeColor(HexColor("#000000"))

        # ── Internal double-line walls with door gaps ──────────────────────────
        iwt_px = iwt * scale
        # Internal walls start/end at inner face of external wall (not at wall centre).
        # ewt/2 = 0.115m = iwt, so offset is exactly iwt_px.
        py_lo = oy + min_y * scale + iwt_px   # inner face of front external wall
        py_hi = oy + max_y * scale - iwt_px   # inner face of rear external wall
        px_lo = ox + min_x * scale + iwt_px   # inner face of left external wall
        px_hi = ox + max_x * scale - iwt_px   # inner face of right external wall

        for x in xs[1:-1]:  # skip outer edges
            px1 = ox + x * scale
            # Gap offset is from py_lo, not from raw min_y
            raw_gaps = vertical_door_gaps.get(round(x, 3), [])
            gaps_px = [
                ((g_s - min_y) * scale - iwt_px, (g_e - min_y) * scale - iwt_px)
                for g_s, g_e in raw_gaps
            ]
            _pdf_draw_double_line_wall(
                c, px1, py_lo, px1, py_hi,
                iwt_px, gaps_px, INT_LW,
            )

        for y in ys[1:-1]:
            py1 = oy + y * scale
            raw_gaps = horizontal_door_gaps.get(round(y, 3), [])
            gaps_px = [
                ((g_s - min_x) * scale - iwt_px, (g_e - min_x) * scale - iwt_px)
                for g_s, g_e in raw_gaps
            ]
            _pdf_draw_double_line_wall(
                c, px_lo, py1, px_hi, py1,
                iwt_px, gaps_px, INT_LW,
            )

        # ── External wall boundary (thick double lines with window gaps) ───────
        bx = ox + min_x * scale
        by = oy + min_y * scale
        bw = (max_x - min_x) * scale
        bh = (max_y - min_y) * scale
        ewt_px = ewt * scale

        # External walls — solid (no gaps); window symbols drawn on top by _draw_windows()
        _pdf_draw_double_line_wall(c, bx, by, bx + bw, by, ewt_px, [], EXT_LW)
        _pdf_draw_double_line_wall(c, bx, by + bh, bx + bw, by + bh, ewt_px, [], EXT_LW)
        _pdf_draw_double_line_wall(c, bx, by, bx, by + bh, ewt_px, [], EXT_LW)
        _pdf_draw_double_line_wall(c, bx + bw, by, bx + bw, by + bh, ewt_px, [], EXT_LW)

        # ── Corner junction fills — tight fill to close wall gap at outer corners ─
        # Size = half wall thickness (fills gap without over-extending outside wall)
        ch = ewt_px / 2  # half wall thickness
        jf = ch * 0.7    # junction fill size: 70% of half-wall — keeps corners clean
        c.setFillColor(HexColor("#000000"))
        c.setStrokeColor(HexColor("#000000"))
        for cx_c, cy_c in [(bx, by), (bx + bw, by), (bx, by + bh), (bx + bw, by + bh)]:
            c.rect(cx_c - jf, cy_c - jf, jf * 2, jf * 2, fill=1, stroke=0)

        # ── Staircase treads ──────────────────────────────────────────────────
        _draw_staircase_treads(c, rooms, scale, ox, oy)

        # ── Window symbols in exterior wall gaps ──────────────────────────────
        _draw_windows(c, rooms, scale, ox, oy, min_x, max_x, min_y, max_y)

        # ── Door leaf + arc in interior wall gaps ─────────────────────────────
        _draw_doors_in_gaps(c, rooms, scale, ox, oy, vertical_door_gaps, horizontal_door_gaps)

    # ── Column markers (filled dark squares) ─────────────────────────────────
    c.setFillColor(HexColor("#000000"))
    c.setDash()
    seen_cols: set[tuple[float, float]] = set()
    for col in floor_plan.columns:
        key = (round(col.x, 2), round(col.y, 2))
        if key in seen_cols:
            continue
        seen_cols.add(key)
        cx = ox + col.x * scale
        cy = oy + col.y * scale
        c.rect(cx - COL_SZ, cy - COL_SZ, COL_SZ * 2, COL_SZ * 2, fill=1, stroke=0)

    # ── Room labels ───────────────────────────────────────────────────────────
    c.setLineWidth(1.0)
    for room in floor_plan.rooms:
        rx = ox + room.x * scale
        ry = oy + room.y * scale
        rw = room.width * scale
        rh = room.depth * scale
        # Skip labels in rooms too small to show anything readable
        if rw < 22 or rh < 16:
            continue
        cx_pt = rx + rw / 2
        cy_pt = ry + rh / 2
        # Font size: bounded by room size, never too large
        fs = max(6.0, min(12.0, rw / 7.5, rh / 4.0))
        c.setFillColor(HexColor("#000000"))
        ftin_label = f"{metres_to_ftin(room.width)} x {metres_to_ftin(room.depth)}"
        # Show name + dimensions only when room is wide enough to display cleanly.
        # Narrow rooms (staircase, toilet) are identified by geometry + area schedule.
        name_upper = room.name.upper()
        if rh >= 36 and rw >= 55:
            c.setFont("Helvetica-Bold", fs)
            c.drawCentredString(cx_pt, cy_pt + fs * 0.6, name_upper)
            c.setFont("Helvetica", fs)
            c.drawCentredString(cx_pt, cy_pt - fs * 0.9, ftin_label)
        elif rw >= 55:
            c.setFont("Helvetica-Bold", fs)
            c.drawCentredString(cx_pt, cy_pt - fs * 0.3, name_upper)
        # Narrow rooms (rw < 55pt ≈ < 1.3m): skip label — avoids bleed into adjacent rooms

    # ── Annotation notes ──────────────────────────────────────────────────────
    if annotations:
        _draw_annotations(c, floor_plan.rooms, annotations, scale, ox, oy)

    # ── Dimension lines ───────────────────────────────────────────────────────
    _draw_dimension_lines(c, cfg, scale, ox, oy, plot_px, plot_py, floor_plan)

    # ── Scale bar (placed in the margin zone, left of chain dims) ─────────────
    _draw_scale_bar(c, ox + 4, TITLE_H + MARGIN // 2 - 4, scale)

    # ── North arrow (placed in top-right margin, away from plot boundary) ─────
    _draw_north_arrow(c, ox + plot_px - 22, oy + plot_py + TOP_PAD * 0.45, 16)

    # ── Title block ───────────────────────────────────────────────────────────
    _draw_title_block(c, project_name, layout.id, layout.name, floor_label, cfg,
                      num_bedrooms, scale, page_w, floor_plan=floor_plan)


def _draw_staircase_treads(c, rooms, scale, ox, oy):
    """Draw staircase: floor-level indicator, tread lines, break line, UP arrow + label."""
    c.setDash()

    for room in rooms:
        if room.type != "staircase":
            continue
        rx = ox + room.x * scale
        ry = oy + room.y * scale
        rw = room.width * scale
        rh = room.depth * scale
        inset = 0.115 * scale / 2  # stop at inner wall face

        # ── Floor-level indicator (thick first tread at stair entry / bottom) ──
        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(1.8)
        c.line(rx + inset, ry, rx + rw - inset, ry)

        # ── Tread lines — evenly spaced, using target 270mm tread depth ─────────
        tread_depth_m = 0.27  # standard residential tread depth
        num_treads = max(3, min(16, int((room.depth * 0.5) / tread_depth_m)))
        lower_half = rh / 2  # draw treads in lower half only (above break line)
        step = lower_half / (num_treads + 1) if num_treads > 0 else lower_half / 4
        c.setStrokeColor(HexColor("#333333"))
        c.setLineWidth(0.5)
        for i in range(1, num_treads + 1):
            ly = ry + i * step
            c.line(rx + inset, ly, rx + rw - inset, ly)

        # ── Break line (dashed zigzag, mid-height) ───────────────────────────────
        mid_y = ry + rh / 2
        c.setDash(4, 2)
        c.setLineWidth(0.75)
        c.setStrokeColor(HexColor("#000000"))
        c.line(rx + inset, mid_y, rx + rw - inset, mid_y)
        c.setDash()

        # ── UP label + arrow (upper tread zone, above break line) ────────────────
        if rw >= 18:
            lbl_fs = max(8, min(12, rw * 0.30))
            cx_s = rx + rw / 2
            # Arrow stem + head pointing up, positioned in upper zone
            arrow_base_y = ry + rh * 0.58
            arrow_tip_y  = ry + rh * 0.80
            stem_x = cx_s
            c.setStrokeColor(HexColor("#000000"))
            c.setLineWidth(1.0)
            c.line(stem_x, arrow_base_y, stem_x, arrow_tip_y)  # vertical stem
            arrow_w = min(rw * 0.28, 7)
            p = c.beginPath()
            p.moveTo(stem_x, arrow_tip_y + arrow_w)              # tip
            p.lineTo(stem_x - arrow_w / 2, arrow_tip_y)          # left wing
            p.lineTo(stem_x + arrow_w / 2, arrow_tip_y)          # right wing
            p.close()
            c.setFillColor(HexColor("#000000"))
            c.drawPath(p, fill=1, stroke=0)
            # "UP" text above the arrow tip
            c.setFillColor(HexColor("#000000"))
            c.setFont("Helvetica-Bold", lbl_fs)
            c.drawCentredString(cx_s, arrow_tip_y + arrow_w + 2, "UP")


def _draw_windows(c, rooms, scale, ox, oy, min_x, max_x, min_y, max_y):
    """Draw window symbols on exterior-facing walls of habitable rooms."""
    habitable = {"living", "bedroom", "kitchen", "study", "dining"}
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(WIN_LW)
    win_w_m = 1.2  # window width in metres

    for room in rooms:
        if room.type not in habitable:
            continue
        cx_m = room.x + room.width / 2
        cy_m = room.y + room.depth / 2
        win_px = min(win_w_m, room.width * 0.6) * scale
        tol = 0.05

        if abs(room.y - min_y) < tol:  # front exterior wall
            wy = oy + room.y * scale
            wx = ox + cx_m * scale
            _draw_window_symbol(c, wx, wy, win_px, horizontal=True)
        if abs(room.y + room.depth - max_y) < tol:  # rear exterior wall
            wy = oy + (room.y + room.depth) * scale
            wx = ox + cx_m * scale
            _draw_window_symbol(c, wx, wy, win_px, horizontal=True)
        if abs(room.x - min_x) < tol:  # left exterior wall
            wxy = oy + cy_m * scale
            wxw = ox + room.x * scale
            _draw_window_symbol(c, wxw, wxy, win_px, horizontal=False)
        if abs(room.x + room.width - max_x) < tol:  # right exterior wall
            wxy = oy + cy_m * scale
            wxw = ox + (room.x + room.width) * scale
            _draw_window_symbol(c, wxw, wxy, win_px, horizontal=False)


def _draw_window_symbol(c, cx, cy, width_px, horizontal: bool):
    """Three parallel lines + perpendicular jamb caps: architectural window-in-wall box symbol."""
    gap = 3  # pt gap between parallel lines (fits within ewt_px ≈ 9.4pt)
    hw = width_px / 2
    if horizontal:
        # 3 horizontal lines spanning the window width
        c.line(cx - hw, cy - gap, cx + hw, cy - gap)
        c.line(cx - hw, cy,       cx + hw, cy)
        c.line(cx - hw, cy + gap, cx + hw, cy + gap)
        # Perpendicular jamb caps at left and right ends (close the box)
        c.line(cx - hw, cy - gap, cx - hw, cy + gap)
        c.line(cx + hw, cy - gap, cx + hw, cy + gap)
    else:
        # 3 vertical lines spanning the window height
        c.line(cx - gap, cy - hw, cx - gap, cy + hw)
        c.line(cx,       cy - hw, cx,       cy + hw)
        c.line(cx + gap, cy - hw, cx + gap, cy + hw)
        # Perpendicular jamb caps at bottom and top ends (close the box)
        c.line(cx - gap, cy - hw, cx + gap, cy - hw)
        c.line(cx - gap, cy + hw, cx + gap, cy + hw)


def _draw_doors(c, rooms, scale, ox, oy):
    """Draw simplified door symbols (line + arc) on room entry walls.

    Kept for structural page and fallback use; main architectural page uses
    _draw_doors_in_gaps which places doors at actual shared-wall openings.
    """
    door_w_m = 0.9
    habitable = {"living", "bedroom", "kitchen", "study", "dining", "utility", "pooja"}
    c.setStrokeColor(HexColor("#555555"))
    c.setLineWidth(0.75)

    for room in rooms:
        if room.type not in habitable:
            continue
        door_px = door_w_m * scale
        # Place door at bottom-centre of room (heuristic — front-facing)
        hx = ox + (room.x + room.width / 2) * scale
        hy = oy + room.y * scale
        # Door leaf
        c.line(hx, hy, hx + door_px, hy)
        # Swing arc (quarter circle): bounding box centred on hinge at (hx, hy)
        c.arc(hx, hy, hx + door_px, hy + door_px, 90, 90)


def _draw_doors_in_gaps(
    c: canvas.Canvas,
    rooms,
    scale: float,
    ox: float,
    oy: float,
    vertical_door_gaps: dict[float, list[tuple[float, float]]],
    horizontal_door_gaps: dict[float, list[tuple[float, float]]],
) -> None:
    """
    Draw door leaf (line) + quarter-circle swing arc at each computed door gap.

    vertical_door_gaps  : {x_coord_m: [(y_start_m, y_end_m), ...]}
    horizontal_door_gaps: {y_coord_m: [(x_start_m, x_end_m), ...]}
    """
    c.setStrokeColor(HexColor("#000000"))
    c.setDash()

    LEAF_LW = INT_LW   # door leaf = same weight as internal wall
    ARC_LW  = 0.4      # door swing arc = thin pen (architectural convention)

    # Doors on vertical walls (wall runs N-S at fixed x)
    for x_m, gaps in vertical_door_gaps.items():
        wx = ox + x_m * scale
        for y_s, y_e in gaps:
            door_px = (y_e - y_s) * scale
            hy = oy + y_s * scale  # hinge at start of gap
            # Door leaf: horizontal line from hinge into room (rightward)
            c.setLineWidth(LEAF_LW)
            c.line(wx, hy, wx + door_px, hy)
            # Swing arc: thin pen (architectural convention)
            c.setLineWidth(ARC_LW)
            c.arc(wx - door_px, hy - door_px, wx + door_px, hy + door_px, 0, 90)

    # Doors on horizontal walls (wall runs E-W at fixed y)
    for y_m, gaps in horizontal_door_gaps.items():
        wy = oy + y_m * scale
        for x_s, x_e in gaps:
            door_px = (x_e - x_s) * scale
            hx = ox + x_s * scale  # hinge at start of gap
            # Door leaf: vertical line from hinge into room (upward)
            c.setLineWidth(LEAF_LW)
            c.line(hx, wy, hx, wy + door_px)
            # Swing arc: thin pen
            c.setLineWidth(ARC_LW)
            c.arc(hx - door_px, wy - door_px, hx + door_px, wy + door_px, 0, 90)


def _draw_annotations(c: canvas.Canvas, rooms, annotations: dict, scale: float, ox: float, oy: float) -> None:
    """Render engineer annotation notes near room centres in the PDF."""
    room_map = {r.id: r for r in rooms}
    for room_id, ann in annotations.items():
        note = ann.get("note", "")
        if not note:
            continue
        room = room_map.get(room_id)
        if room is None:
            continue
        cx = ox + (room.x + room.width / 2) * scale
        cy = oy + (room.y + room.depth / 2) * scale
        # Offset slightly below room centre so it doesn't overlap the room name
        note_y = cy - 8
        truncated = (note[:40] + "…") if len(note) > 40 else note
        label = f"Note: {truncated}"
        fs = 5
        c.setFont("Helvetica", fs)
        text_w = c.stringWidth(label, "Helvetica", fs)
        pad = 3
        rect_w = text_w + 2 * pad
        rect_h = fs + 2 * pad
        # Light grey background rectangle
        c.setFillColor(HexColor("#F1F5F9"))
        c.setStrokeColor(HexColor("#808080"))
        c.setLineWidth(0.4)
        c.rect(cx - rect_w / 2, note_y - pad, rect_w, rect_h, fill=1, stroke=1)
        # Text
        c.setFillColor(HexColor("#444444"))
        c.drawCentredString(cx, note_y + 1, label)


def _filter_dim_positions(positions: list[float]) -> list[float]:
    """Remove positions that create spans < MIN_DIM_SPAN (wall thickness noise)."""
    if len(positions) <= 2:
        return list(positions)
    kept = [positions[0]]
    for p in positions[1:]:
        if p - kept[-1] >= MIN_DIM_SPAN:
            kept.append(p)
    # Ensure last position is always included
    if kept[-1] < positions[-1] - 0.01:
        if positions[-1] - kept[-1] < MIN_DIM_SPAN:
            kept[-1] = positions[-1]
        else:
            kept.append(positions[-1])
    return kept


def _draw_dimension_lines(c, cfg, scale, ox, oy, plot_px, plot_py, floor_plan=None):
    """
    Draw IS-style chain dimension lines in feet-inches.

    Layout (MARGIN = 52 pts between title block top and road strip bottom):
      Bottom: 2 rows — inner room spans at y≈TITLE_H+38, outer total at y≈TITLE_H+16
      Right:  2 rows — inner room spans at x≈right_edge+14, outer total at x≈right_edge+36
    """
    c.setFillColor(HexColor("#000000"))
    c.setStrokeColor(HexColor("#000000"))

    rooms = floor_plan.rooms if floor_plan else []

    # Collect and filter room boundary positions
    if rooms:
        raw_x = sorted({round(r.x, 3) for r in rooms} | {round(r.x + r.width, 3) for r in rooms})
        raw_y = sorted({round(r.y, 3) for r in rooms} | {round(r.y + r.depth, 3) for r in rooms})
    else:
        raw_x = [0.0, cfg.plot_width]
        raw_y = [0.0, cfg.plot_length]

    x_pos = _filter_dim_positions(raw_x)
    y_pos = _filter_dim_positions(raw_y)

    # ── BOTTOM HORIZONTAL CHAIN ───────────────────────────────────────────────
    # MARGIN zone: y = TITLE_H to y = TITLE_H + MARGIN (road strip)
    # Inner row: bar at TITLE_H + MARGIN - 12 (just below road strip start)
    # Outer row: bar at TITLE_H + MARGIN - 36 (middle of margin)
    inner_y = TITLE_H + MARGIN - 12   # ≈ 130
    outer_y = TITLE_H + MARGIN - 36   # ≈ 106

    # Inner chain — room span segments
    # 45° diagonal tick marks (architectural standard: slash at each dim endpoint)
    c.setLineWidth(DIM_LW)
    c.setStrokeColor(HexColor("#000000"))
    for xm in x_pos:
        px = ox + xm * scale
        c.line(px - 3.5, inner_y - 3.5, px + 3.5, inner_y + 3.5)  # 45° tick
    c.line(ox + x_pos[0] * scale, inner_y, ox + x_pos[-1] * scale, inner_y)  # bar

    c.setFont("Helvetica", 5.5)
    c.setFillColor(HexColor("#000000"))
    for i in range(len(x_pos) - 1):
        span = x_pos[i + 1] - x_pos[i]
        mid_px = ox + (x_pos[i] + span / 2) * scale
        c.drawCentredString(mid_px, inner_y + 7, metres_to_ftin(span))

    # Outer chain — overall plot width
    c.setLineWidth(DIM_LW + 0.3)
    c.line(ox, outer_y, ox + plot_px, outer_y)
    c.line(ox - 4, outer_y - 4, ox + 4, outer_y + 4)        # 45° tick at start
    c.line(ox + plot_px - 4, outer_y - 4, ox + plot_px + 4, outer_y + 4)  # 45° tick at end
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(ox + plot_px / 2, outer_y + 8, metres_to_ftin(cfg.plot_width))

    # ── RIGHT VERTICAL CHAIN ──────────────────────────────────────────────────
    right_x = ox + plot_px
    inner_x = right_x + 30   # wider gap from building edge for clean dimension clearance
    outer_x = right_x + 54   # proportionally wider for outer overall dim

    # Inner chain — room span segments (45° diagonal ticks)
    c.setLineWidth(DIM_LW)
    for ym in y_pos:
        py = oy + ym * scale
        c.line(inner_x - 3.5, py - 3.5, inner_x + 3.5, py + 3.5)  # 45° tick
    c.line(inner_x, oy + y_pos[0] * scale, inner_x, oy + y_pos[-1] * scale)  # bar

    c.setFont("Helvetica", 5.5)
    for i in range(len(y_pos) - 1):
        span = y_pos[i + 1] - y_pos[i]
        mid_py = oy + (y_pos[i] + span / 2) * scale
        c.saveState()
        c.translate(inner_x + 8, mid_py)
        c.rotate(90)
        c.drawCentredString(0, 0, metres_to_ftin(span))
        c.restoreState()

    # Outer chain — overall plot length (45° ticks)
    c.setLineWidth(DIM_LW + 0.3)
    c.line(outer_x, oy, outer_x, oy + plot_py)
    c.line(outer_x - 4, oy - 4, outer_x + 4, oy + 4)               # 45° tick at bottom
    c.line(outer_x - 4, oy + plot_py - 4, outer_x + 4, oy + plot_py + 4)  # 45° tick at top
    c.saveState()
    c.translate(outer_x + 8, oy + plot_py / 2)
    c.rotate(90)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(0, 0, metres_to_ftin(cfg.plot_length))
    c.restoreState()


def _draw_arrow(c, x, y, right: bool):
    sz = 4
    dx = sz if right else -sz
    c.setFillColor(HexColor("#555555"))
    p = c.beginPath()
    p.moveTo(x, y)
    p.lineTo(x + dx, y + sz / 2)
    p.lineTo(x + dx, y - sz / 2)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def _draw_scale_bar(c: canvas.Canvas, x: float, y: float, scale: float) -> None:
    bar_pt = 3.0 * scale
    c.setStrokeColor(HexColor("#555555"))
    c.setLineWidth(1.5)
    c.line(x, y, x + bar_pt, y)
    c.setLineWidth(1.0)
    c.line(x, y - 3, x, y + 3)
    c.line(x + bar_pt, y - 3, x + bar_pt, y + 3)
    c.setFillColor(HexColor("#555555"))
    c.setFont("Helvetica", 6)
    c.drawCentredString(x + bar_pt / 2, y - 10, "3 m")


def _draw_north_arrow(c: canvas.Canvas, cx: float, cy: float, r: float) -> None:
    c.setFillColor(white)
    c.setStrokeColor(HexColor("#808080"))
    c.setLineWidth(0.75)
    c.circle(cx, cy, r, fill=1, stroke=1)

    p = c.beginPath()
    p.moveTo(cx, cy + r * 0.8)
    p.lineTo(cx - r * 0.3, cy - r * 0.3)
    p.lineTo(cx, cy - r * 0.1)
    p.lineTo(cx + r * 0.3, cy - r * 0.3)
    p.close()
    c.setFillColor(HexColor("#000000"))
    c.drawPath(p, fill=1, stroke=0)

    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(cx, cy - r - 7, "NORTH")


def _draw_structural_floor(
    c: canvas.Canvas,
    floor_plan: FloorPlan,
    layout: Layout,
    cfg: PlotConfig,
    project_name: str,
    num_bedrooms: int,
    floor_label: str,
) -> None:
    """Render a separate structural (beam & column) layout page."""
    page_w, page_h = A4
    scale, ox, oy, plot_px, plot_py = _compute_layout(cfg, page_w, page_h)

    # Background
    c.setFillColor(HexColor("#F8FAFC"))
    c.rect(0, TITLE_H, page_w, page_h - TITLE_H, fill=1, stroke=0)

    # Road strip
    road_y = TITLE_H + MARGIN
    c.setFillColor(HexColor("#E2E8F0"))
    c.rect(ox, road_y, plot_px, ROAD_H, fill=1, stroke=0)
    c.setFillColor(HexColor("#808080"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(ox + plot_px / 2, road_y + ROAD_H / 2 - 3, "ROAD")

    # Plot boundary
    c.setDash(5, 3)
    c.setStrokeColor(HexColor("#CCCCCC"))
    c.setLineWidth(0.75)
    c.rect(ox, oy, plot_px, plot_py, fill=0, stroke=1)
    c.setDash()

    rooms = floor_plan.rooms
    if not rooms:
        _draw_title_block(
            c, project_name, layout.id, layout.name,
            f"{floor_label} — Structural", cfg, num_bedrooms, scale, page_w,
        )
        return

    min_x = min(r.x for r in rooms)
    max_x = max(r.x + r.width for r in rooms)
    min_y = min(r.y for r in rooms)
    max_y = max(r.y + r.depth for r in rooms)

    # Room outlines — light gray, no fill
    c.setStrokeColor(HexColor("#CCCCCC"))
    c.setLineWidth(0.5)
    c.setDash()
    for room in rooms:
        rx = ox + room.x * scale
        ry = oy + room.y * scale
        rw = room.width * scale
        rh = room.depth * scale
        c.rect(rx, ry, rw, rh, fill=0, stroke=1)

    # Structural grid dashed lines
    xs = sorted({round(r.x, 3) for r in rooms} | {round(r.x + r.width, 3) for r in rooms})
    ys = sorted({round(r.y, 3) for r in rooms} | {round(r.y + r.depth, 3) for r in rooms})

    c.setStrokeColor(HexColor("#808080"))
    c.setLineWidth(0.4)
    c.setDash(4, 3)
    bx_lo = ox + min_x * scale
    bx_hi = ox + max_x * scale
    by_lo = oy + min_y * scale
    by_hi = oy + max_y * scale
    ext = 8  # pt extension past building

    for x in xs:
        px_x = ox + x * scale
        c.line(px_x, by_lo - ext, px_x, by_hi + ext)
    for y in ys:
        px_y = oy + y * scale
        c.line(bx_lo - ext, px_y, bx_hi + ext, px_y)
    c.setDash()

    # Grid bubble labels (A, B, C… / 1, 2, 3…)
    import string as _string
    bubble_r = 6  # pt
    c.setStrokeColor(HexColor("#555555"))
    c.setFillColor(HexColor("#FFFFFF"))
    c.setLineWidth(0.6)

    for i, x in enumerate(xs):
        lbl = _string.ascii_uppercase[i % 26]
        px_x = ox + x * scale
        for bubble_y in [by_lo - ext - bubble_r - 2, by_hi + ext + bubble_r + 2]:
            c.circle(px_x, bubble_y, bubble_r, fill=1, stroke=1)
            c.setFillColor(HexColor("#333333"))
            c.setFont("Helvetica-Bold", 6)
            c.drawCentredString(px_x, bubble_y - 2.5, lbl)
            c.setFillColor(HexColor("#FFFFFF"))

    for j, y in enumerate(ys):
        lbl = str(j + 1)
        px_y = oy + y * scale
        for bubble_x in [bx_lo - ext - bubble_r - 2, bx_hi + ext + bubble_r + 2]:
            c.circle(bubble_x, px_y, bubble_r, fill=1, stroke=1)
            c.setFillColor(HexColor("#333333"))
            c.setFont("Helvetica-Bold", 6)
            c.drawCentredString(bubble_x, px_y - 2.5, lbl)
            c.setFillColor(HexColor("#FFFFFF"))

    # Beam lines — connect columns that share the same X or Y
    cols = floor_plan.columns
    if cols:
        seen: set[tuple] = set()
        col_xs: dict[float, list] = {}
        col_ys: dict[float, list] = {}
        unique_cols = []
        for col in cols:
            key = (round(col.x, 2), round(col.y, 2))
            if key in seen:
                continue
            seen.add(key)
            unique_cols.append(col)
            col_xs.setdefault(round(col.x, 2), []).append(col)
            col_ys.setdefault(round(col.y, 2), []).append(col)

        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(1.5)
        c.setDash()

        # Vertical beams (same X, different Y — sort by Y, connect pairs)
        for _x, col_list in col_xs.items():
            if len(col_list) < 2:
                continue
            sorted_cols = sorted(col_list, key=lambda col: col.y)
            for k in range(len(sorted_cols) - 1):
                c1, c2 = sorted_cols[k], sorted_cols[k + 1]
                c.line(ox + c1.x * scale, oy + c1.y * scale,
                       ox + c2.x * scale, oy + c2.y * scale)

        # Horizontal beams (same Y, different X)
        for _y, col_list in col_ys.items():
            if len(col_list) < 2:
                continue
            sorted_cols = sorted(col_list, key=lambda col: col.x)
            for k in range(len(sorted_cols) - 1):
                c1, c2 = sorted_cols[k], sorted_cols[k + 1]
                c.line(ox + c1.x * scale, oy + c1.y * scale,
                       ox + c2.x * scale, oy + c2.y * scale)

        # Column squares with numbers
        col_sz = max(5, 0.3 * scale)
        c.setFillColor(HexColor("#000000"))
        for idx, col in enumerate(unique_cols):
            cx = ox + col.x * scale
            cy = oy + col.y * scale
            c.rect(cx - col_sz / 2, cy - col_sz / 2, col_sz, col_sz, fill=1, stroke=0)
            # Column label
            c.setFillColor(HexColor("#FFFFFF"))
            c.setFont("Helvetica-Bold", max(4, col_sz * 0.55))
            c.drawCentredString(cx, cy - col_sz * 0.2, f"C{idx + 1}")
            c.setFillColor(HexColor("#000000"))

    # Scale bar + north arrow
    _draw_scale_bar(c, ox + 4, oy + 16, scale)
    _draw_north_arrow(c, ox + plot_px - 22, oy + plot_py + TOP_PAD * 0.45, 16)

    # Structural title block
    _draw_title_block(
        c, project_name, layout.id, layout.name,
        f"{floor_label} — Beam/Column Layout", cfg, num_bedrooms, scale, page_w,
    )


def _draw_title_block(
    c: canvas.Canvas,
    project_name: str,
    layout_id: str,
    layout_name: str,
    floor_label: str,
    cfg: PlotConfig,
    num_bedrooms: int,
    scale: float,
    page_w: float,
    floor_plan: "FloorPlan | None" = None,
) -> None:
    # Outer border around entire title block
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(1.0)
    c.rect(0, 0, page_w, TITLE_H, fill=0, stroke=1)
    # Heavy top border line separating title block from drawing
    c.setLineWidth(1.5)
    c.line(0, TITLE_H, page_w, TITLE_H)

    scale_ratio = round(1000 / (scale * (25.4 / 72)))

    # Compute area total in sqft when floor plan is available
    sqm_total = sum(r.area for r in floor_plan.rooms) if floor_plan else 0.0
    sqft_total = round(sqm_total * 10.764)

    city_label = cfg.city.title() if cfg.city != "other" else "NBC Defaults"
    fields = [
        ("PROJECT",  (project_name[:22] + "…") if len(project_name) > 24 else project_name),
        ("LAYOUT",   f"{layout_id} - {layout_name}"),
        ("FLOOR",    floor_label),
        ("PLOT",     f"{cfg.plot_width}x{cfg.plot_length} m"),
        ("CONFIG",   f"{num_bedrooms} BHK · {cfg.city.title()}"),
        ("SCALE",    f"1:{scale_ratio}"),
        ("TOTAL AREA", f"{sqft_total} SQFT" if floor_plan else "—"),
        ("DATE",     date.today().strftime("%d %b %Y")),
    ]

    # Field cells — upper 40pt for fields, lower zone for area schedule
    FIELD_H = 40  # height of the field row
    col_w = page_w / len(fields)
    for i, (label, value) in enumerate(fields):
        cx = col_w * i + col_w / 2
        cell_x = col_w * i
        # Dark header band for each field label
        c.setFillColor(HexColor("#222222"))
        c.rect(cell_x, TITLE_H - 18, col_w, 18, fill=1, stroke=0)
        # Field label in white on dark background
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(cx, TITLE_H - 12, label)
        # Value in black below
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString(cx, TITLE_H - 34, value)
        # Vertical divider between cells
        if i > 0:
            c.setStrokeColor(HexColor("#000000"))
            c.setLineWidth(0.5)
            c.line(cell_x, 0, cell_x, TITLE_H)
    # Horizontal separator between fields and area schedule zone
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.5)
    c.line(0, TITLE_H - FIELD_H, page_w, TITLE_H - FIELD_H)

    # Area schedule: list room names and sizes in the lower zone
    if floor_plan and floor_plan.rooms:
        sched_y_top = TITLE_H - FIELD_H - 4
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica-Bold", 5.5)
        c.drawString(4, sched_y_top, "AREA SCHEDULE:")
        c.setFont("Helvetica", 5)
        schedule_parts = [
            f"{r.name.upper()}: {round(r.area * 10.764)} SQFT"
            for r in floor_plan.rooms
            if r.type not in {"staircase", "parking", "parking_4w", "parking_2w"}
        ]
        schedule_line = "   |   ".join(schedule_parts[:8])
        c.drawString(4, sched_y_top - 10, schedule_line[:190])
        c.setFont("Helvetica-Bold", 5.5)
        c.drawString(4, sched_y_top - 20, f"TOTAL BUILT-UP AREA: {sqft_total} SQFT  ({sqm_total:.1f} SQ.M)")

    # Branding
    c.setFillColor(HexColor("#888888"))
    c.setFont("Helvetica", 5)
    c.drawRightString(page_w - 4, 8, "Generated by PlanForge · NBC 2016 Compliant")
