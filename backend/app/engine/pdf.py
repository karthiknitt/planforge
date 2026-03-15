from __future__ import annotations

import math
from datetime import date
from io import BytesIO

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

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
    "living":    ("#FEF9C3", "#CA8A04"),
    "bedroom":   ("#EDE9FE", "#7C3AED"),
    "kitchen":   ("#DCFCE7", "#16A34A"),
    "toilet":    ("#E0F2FE", "#0284C7"),
    "staircase": ("#F1F5F9", "#64748B"),
    "parking":   ("#F8FAFC", "#94A3B8"),
    "utility":   ("#F8FAFC", "#94A3B8"),
    "pooja":     ("#FFF7ED", "#EA580C"),
    "study":     ("#F0FDF4", "#15803D"),
    "balcony":   ("#F0F9FF", "#0369A1"),
    "dining":    ("#FEFCE8", "#A16207"),
}

# ── Page constants (points) ───────────────────────────────────────────────────
TITLE_H  = 72   # title block height
MARGIN   = 36   # page margins
ROAD_H   = 18   # road strip height
ROAD_GAP = 4    # gap between road strip top and plot boundary bottom
TOP_PAD  = 28   # padding above plot for north arrow / scale bar
COL_SZ   = 4    # column marker half-size (pt) — larger for CAD feel
EXT_LW   = 2.0  # external wall lineweight (pt)
INT_LW   = 1.0  # internal wall lineweight (pt)
DIM_LW   = 0.5  # dimension line lineweight (pt)
WIN_LW   = 0.75 # window line lineweight (pt)


# ── Public API ────────────────────────────────────────────────────────────────

def render_pdf(project_name: str, layout: Layout, cfg: PlotConfig, num_bedrooms: int) -> bytes:
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
        _draw_floor(c, floor_plan, layout, cfg, project_name, num_bedrooms, floor_label)
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
) -> None:
    page_w, page_h = A4
    scale, ox, oy, plot_px, plot_py = _compute_layout(cfg, page_w, page_h)

    # ── Background ────────────────────────────────────────────────────────────
    c.setFillColor(HexColor("#F8FAFC"))
    c.rect(0, TITLE_H, page_w, page_h - TITLE_H, fill=1, stroke=0)

    # ── Road strip ────────────────────────────────────────────────────────────
    road_y = TITLE_H + MARGIN
    c.setFillColor(HexColor("#CBD5E1"))
    c.rect(ox, road_y, plot_px, ROAD_H, fill=1, stroke=0)
    c.setFillColor(HexColor("#475569"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(ox + plot_px / 2, road_y + ROAD_H / 2 - 3, "ROAD")

    # ── Plot boundary (dashed) ────────────────────────────────────────────────
    c.setDash(5, 3)
    c.setStrokeColor(HexColor("#CBD5E1"))
    c.setLineWidth(0.75)
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
        xs = sorted({r.x for r in rooms} | {r.x + r.width for r in rooms})
        ys = sorted({r.y for r in rooms} | {r.y + r.depth for r in rooms})

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
                if abs(ra.x + ra.width - rb.x) < 0.05:
                    if ra.type in habitable_door or rb.type in habitable_door:
                        y_lo = max(ra.y, rb.y)
                        y_hi = min(ra.y + ra.depth, rb.y + rb.depth)
                        if y_hi - y_lo > door_w_m + 0.1:
                            mid = (y_lo + y_hi) / 2
                            wx = round(ra.x + ra.width, 3)
                            vertical_door_gaps.setdefault(wx, []).append(
                                (mid - door_w_m / 2, mid + door_w_m / 2)
                            )
                elif abs(rb.x + rb.width - ra.x) < 0.05:
                    if ra.type in habitable_door or rb.type in habitable_door:
                        y_lo = max(ra.y, rb.y)
                        y_hi = min(ra.y + ra.depth, rb.y + rb.depth)
                        if y_hi - y_lo > door_w_m + 0.1:
                            mid = (y_lo + y_hi) / 2
                            wx = round(rb.x + rb.width, 3)
                            vertical_door_gaps.setdefault(wx, []).append(
                                (mid - door_w_m / 2, mid + door_w_m / 2)
                            )
                # Horizontal shared wall (ra top ≈ rb bottom)
                if abs(ra.y + ra.depth - rb.y) < 0.05:
                    if ra.type in habitable_door or rb.type in habitable_door:
                        x_lo = max(ra.x, rb.x)
                        x_hi = min(ra.x + ra.width, rb.x + rb.width)
                        if x_hi - x_lo > door_w_m + 0.1:
                            mid = (x_lo + x_hi) / 2
                            wy = round(ra.y + ra.depth, 3)
                            horizontal_door_gaps.setdefault(wy, []).append(
                                (mid - door_w_m / 2, mid + door_w_m / 2)
                            )
                elif abs(rb.y + rb.depth - ra.y) < 0.05:
                    if ra.type in habitable_door or rb.type in habitable_door:
                        x_lo = max(ra.x, rb.x)
                        x_hi = min(ra.x + ra.width, rb.x + rb.width)
                        if x_hi - x_lo > door_w_m + 0.1:
                            mid = (x_lo + x_hi) / 2
                            wy = round(rb.y + rb.depth, 3)
                            horizontal_door_gaps.setdefault(wy, []).append(
                                (mid - door_w_m / 2, mid + door_w_m / 2)
                            )

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
                    (rcx - ww_h / 2, rcx + ww_h / 2)
                )

        c.setStrokeColor(HexColor("#334155"))

        # ── Internal double-line walls with door gaps ──────────────────────────
        iwt_px = iwt * scale
        for x in xs[1:-1]:  # skip outer edges
            px1 = ox + x * scale
            py1 = oy + min_y * scale
            py2 = oy + max_y * scale
            wall_len_px = py2 - py1
            # Convert door gaps from metres to px offsets along wall
            raw_gaps = vertical_door_gaps.get(round(x, 3), [])
            gaps_px = [
                ((g_s - min_y) * scale, (g_e - min_y) * scale)
                for g_s, g_e in raw_gaps
            ]
            _pdf_draw_double_line_wall(
                c, px1, py1, px1, py2,
                iwt_px, gaps_px, INT_LW,
            )

        for y in ys[1:-1]:
            py1 = oy + y * scale
            px1 = ox + min_x * scale
            px2 = ox + max_x * scale
            raw_gaps = horizontal_door_gaps.get(round(y, 3), [])
            gaps_px = [
                ((g_s - min_x) * scale, (g_e - min_x) * scale)
                for g_s, g_e in raw_gaps
            ]
            _pdf_draw_double_line_wall(
                c, px1, py1, px2, py1,
                iwt_px, gaps_px, INT_LW,
            )

        # ── External wall boundary (thick double lines with window gaps) ───────
        bx = ox + min_x * scale
        by = oy + min_y * scale
        bw = (max_x - min_x) * scale
        bh = (max_y - min_y) * scale
        ewt_px = ewt * scale

        # Front wall (bottom, horizontal, y=min_y)
        raw_gaps_front = external_h_win_gaps.get(round(min_y, 3), [])
        gaps_px_front = [
            ((g_s - min_x) * scale, (g_e - min_x) * scale)
            for g_s, g_e in raw_gaps_front
        ]
        _pdf_draw_double_line_wall(c, bx, by, bx + bw, by, ewt_px, gaps_px_front, EXT_LW)

        # Rear wall (top, horizontal, y=max_y)
        raw_gaps_rear = external_h_win_gaps.get(round(max_y, 3), [])
        gaps_px_rear = [
            ((g_s - min_x) * scale, (g_e - min_x) * scale)
            for g_s, g_e in raw_gaps_rear
        ]
        _pdf_draw_double_line_wall(c, bx, by + bh, bx + bw, by + bh, ewt_px, gaps_px_rear, EXT_LW)

        # Left wall (vertical, x=min_x)
        raw_gaps_left = external_v_win_gaps.get(round(min_x, 3), [])
        gaps_px_left = [
            ((g_s - min_y) * scale, (g_e - min_y) * scale)
            for g_s, g_e in raw_gaps_left
        ]
        _pdf_draw_double_line_wall(c, bx, by, bx, by + bh, ewt_px, gaps_px_left, EXT_LW)

        # Right wall (vertical, x=max_x)
        raw_gaps_right = external_v_win_gaps.get(round(max_x, 3), [])
        gaps_px_right = [
            ((g_s - min_y) * scale, (g_e - min_y) * scale)
            for g_s, g_e in raw_gaps_right
        ]
        _pdf_draw_double_line_wall(c, bx + bw, by, bx + bw, by + bh, ewt_px, gaps_px_right, EXT_LW)

        # ── Staircase treads ──────────────────────────────────────────────────
        _draw_staircase_treads(c, rooms, scale, ox, oy)

        # ── Window symbols in exterior wall gaps ──────────────────────────────
        _draw_windows(c, rooms, scale, ox, oy, min_x, max_x, min_y, max_y)

        # ── Door leaf + arc in interior wall gaps ─────────────────────────────
        _draw_doors_in_gaps(c, rooms, scale, ox, oy, vertical_door_gaps, horizontal_door_gaps)

    # ── Column markers (filled dark squares) ─────────────────────────────────
    c.setFillColor(HexColor("#1E293B"))
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
        if rw >= 30 and rh >= 22:
            cx_pt = rx + rw / 2
            cy_pt = ry + rh / 2
            fs = max(6, min(9, rw / 8, rh / 4))
            c.setFillColor(HexColor("#1E293B"))
            if rh >= 38:
                c.setFont("Helvetica-Bold", fs)
                c.drawCentredString(cx_pt, cy_pt + fs * 0.6, room.name)
                c.setFont("Helvetica", fs - 1)
                c.drawCentredString(cx_pt, cy_pt - fs * 0.8, f"{room.area} m\u00b2")
            else:
                c.setFont("Helvetica", fs)
                c.drawCentredString(cx_pt, cy_pt - fs * 0.3, f"{room.name} \u00b7 {room.area}m\u00b2")

    # ── Dimension lines ───────────────────────────────────────────────────────
    _draw_dimension_lines(c, cfg, scale, ox, oy, plot_px, plot_py)

    # ── Scale bar ─────────────────────────────────────────────────────────────
    _draw_scale_bar(c, ox + 4, oy + 16, scale)

    # ── North arrow ───────────────────────────────────────────────────────────
    _draw_north_arrow(c, ox + plot_px - 16, oy + plot_py - 16, 12)

    # ── Title block ───────────────────────────────────────────────────────────
    _draw_title_block(c, project_name, layout.id, layout.name, floor_label, cfg,
                      num_bedrooms, scale, page_w)


def _draw_staircase_treads(c, rooms, scale, ox, oy):
    """Draw horizontal tread lines + mid cut-line + UP label for staircase rooms."""
    c.setStrokeColor(HexColor("#94A3B8"))
    c.setLineWidth(0.5)
    c.setDash()

    for room in rooms:
        if room.type != "staircase":
            continue
        rx = ox + room.x * scale
        ry = oy + room.y * scale
        rw = room.width * scale
        rh = room.depth * scale

        tread_h = max(4, min(10, scale * 0.3))
        num_treads = max(3, int(rh / tread_h))
        step = rh / num_treads

        for i in range(1, num_treads):
            ly = ry + i * step
            c.line(rx, ly, rx + rw, ly)

        # Cut line (dashed, mid-height)
        mid_y = ry + rh / 2
        c.setDash(4, 2)
        c.setLineWidth(1.0)
        c.setStrokeColor(HexColor("#64748B"))
        c.line(rx, mid_y, rx + rw, mid_y)
        c.setDash()
        c.setLineWidth(0.5)
        c.setStrokeColor(HexColor("#94A3B8"))

        # UP label
        c.setFillColor(HexColor("#64748B"))
        c.setFont("Helvetica-Bold", max(5, scale * 0.12))
        c.drawCentredString(rx + rw / 2, mid_y + 4, "UP")


def _draw_windows(c, rooms, scale, ox, oy, min_x, max_x, min_y, max_y):
    """Draw window symbols on exterior-facing walls of habitable rooms."""
    habitable = {"living", "bedroom", "kitchen", "study", "dining"}
    c.setStrokeColor(HexColor("#0369A1"))
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
    """Three parallel lines: the architectural window symbol."""
    gap = 3  # pt gap between lines
    if horizontal:
        c.line(cx - width_px / 2, cy - gap, cx + width_px / 2, cy - gap)
        c.line(cx - width_px / 2, cy,       cx + width_px / 2, cy)
        c.line(cx - width_px / 2, cy + gap, cx + width_px / 2, cy + gap)
    else:
        c.line(cx - gap, cy - width_px / 2, cx - gap, cy + width_px / 2)
        c.line(cx,       cy - width_px / 2, cx,       cy + width_px / 2)
        c.line(cx + gap, cy - width_px / 2, cx + gap, cy + width_px / 2)


def _draw_doors(c, rooms, scale, ox, oy):
    """Draw simplified door symbols (line + arc) on room entry walls.

    Kept for structural page and fallback use; main architectural page uses
    _draw_doors_in_gaps which places doors at actual shared-wall openings.
    """
    door_w_m = 0.9
    habitable = {"living", "bedroom", "kitchen", "study", "dining", "utility", "pooja"}
    c.setStrokeColor(HexColor("#64748B"))
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
    c.setStrokeColor(HexColor("#475569"))
    c.setLineWidth(0.75)
    c.setDash()

    # Doors on vertical walls (wall runs N-S at fixed x)
    for x_m, gaps in vertical_door_gaps.items():
        wx = ox + x_m * scale
        for y_s, y_e in gaps:
            door_px = (y_e - y_s) * scale
            hy = oy + y_s * scale  # hinge at start of gap
            # Door leaf: horizontal line from hinge into room (rightward)
            c.line(wx, hy, wx + door_px, hy)
            # Quarter-circle arc: centred on hinge, sweeping 90° into room
            c.arc(wx, hy, wx + door_px, hy + door_px, 90, 90)

    # Doors on horizontal walls (wall runs E-W at fixed y)
    for y_m, gaps in horizontal_door_gaps.items():
        wy = oy + y_m * scale
        for x_s, x_e in gaps:
            door_px = (x_e - x_s) * scale
            hx = ox + x_s * scale  # hinge at start of gap
            # Door leaf: vertical line from hinge into room (upward)
            c.line(hx, wy, hx, wy + door_px)
            # Quarter-circle arc: centred on hinge, sweeping 90° into room
            c.arc(hx, wy, hx + door_px, wy + door_px, 90, 90)


def _draw_dimension_lines(c, cfg, scale, ox, oy, plot_px, plot_py):
    """Draw IS-compliant overall dimension chains."""
    c.setFillColor(HexColor("#64748B"))
    c.setStrokeColor(HexColor("#64748B"))
    c.setLineWidth(DIM_LW)
    c.setFont("Helvetica", 7)

    # Width dimension (bottom, below road strip)
    dim_y = TITLE_H + (MARGIN * 0.55)
    c.drawCentredString(ox + plot_px / 2, dim_y, f"{cfg.plot_width:.2f} m")
    c.line(ox, dim_y + 3, ox, dim_y + 8)
    c.line(ox + plot_px, dim_y + 3, ox + plot_px, dim_y + 8)
    c.line(ox, dim_y + 5.5, ox + plot_px, dim_y + 5.5)
    # Arrows
    _draw_arrow(c, ox, dim_y + 5.5, right=True)
    _draw_arrow(c, ox + plot_px, dim_y + 5.5, right=False)

    # Depth dimension (left side, rotated)
    c.saveState()
    c.setFillColor(HexColor("#64748B"))
    c.setFont("Helvetica", 7)
    c.translate(ox - 18, oy + plot_py / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, f"{cfg.plot_length:.2f} m")
    c.restoreState()
    c.setStrokeColor(HexColor("#64748B"))
    c.setLineWidth(DIM_LW)
    c.line(ox - 12, oy, ox - 8, oy)
    c.line(ox - 12, oy + plot_py, ox - 8, oy + plot_py)
    c.line(ox - 10, oy, ox - 10, oy + plot_py)


def _draw_arrow(c, x, y, right: bool):
    sz = 4
    dx = sz if right else -sz
    c.setFillColor(HexColor("#64748B"))
    p = c.beginPath()
    p.moveTo(x, y)
    p.lineTo(x + dx, y + sz / 2)
    p.lineTo(x + dx, y - sz / 2)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def _draw_scale_bar(c: canvas.Canvas, x: float, y: float, scale: float) -> None:
    bar_pt = 3.0 * scale
    c.setStrokeColor(HexColor("#64748B"))
    c.setLineWidth(1.5)
    c.line(x, y, x + bar_pt, y)
    c.setLineWidth(1.0)
    c.line(x, y - 3, x, y + 3)
    c.line(x + bar_pt, y - 3, x + bar_pt, y + 3)
    c.setFillColor(HexColor("#64748B"))
    c.setFont("Helvetica", 6)
    c.drawCentredString(x + bar_pt / 2, y - 10, "3 m")


def _draw_north_arrow(c: canvas.Canvas, cx: float, cy: float, r: float) -> None:
    c.setFillColor(white)
    c.setStrokeColor(HexColor("#94A3B8"))
    c.setLineWidth(0.75)
    c.circle(cx, cy, r, fill=1, stroke=1)

    p = c.beginPath()
    p.moveTo(cx, cy + r * 0.8)
    p.lineTo(cx - r * 0.3, cy - r * 0.3)
    p.lineTo(cx, cy - r * 0.1)
    p.lineTo(cx + r * 0.3, cy - r * 0.3)
    p.close()
    c.setFillColor(HexColor("#1E293B"))
    c.drawPath(p, fill=1, stroke=0)

    c.setFillColor(HexColor("#64748B"))
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(cx, cy - r - 7, "N")


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
    c.setFillColor(HexColor("#94A3B8"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(ox + plot_px / 2, road_y + ROAD_H / 2 - 3, "ROAD")

    # Plot boundary
    c.setDash(5, 3)
    c.setStrokeColor(HexColor("#CBD5E1"))
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
    c.setStrokeColor(HexColor("#CBD5E1"))
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

    c.setStrokeColor(HexColor("#94A3B8"))
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
    c.setStrokeColor(HexColor("#64748B"))
    c.setFillColor(HexColor("#FFFFFF"))
    c.setLineWidth(0.6)

    for i, x in enumerate(xs):
        lbl = _string.ascii_uppercase[i % 26]
        px_x = ox + x * scale
        for bubble_y in [by_lo - ext - bubble_r - 2, by_hi + ext + bubble_r + 2]:
            c.circle(px_x, bubble_y, bubble_r, fill=1, stroke=1)
            c.setFillColor(HexColor("#334155"))
            c.setFont("Helvetica-Bold", 6)
            c.drawCentredString(px_x, bubble_y - 2.5, lbl)
            c.setFillColor(HexColor("#FFFFFF"))

    for j, y in enumerate(ys):
        lbl = str(j + 1)
        px_y = oy + y * scale
        for bubble_x in [bx_lo - ext - bubble_r - 2, bx_hi + ext + bubble_r + 2]:
            c.circle(bubble_x, px_y, bubble_r, fill=1, stroke=1)
            c.setFillColor(HexColor("#334155"))
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

        c.setStrokeColor(HexColor("#1E293B"))
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
        c.setFillColor(HexColor("#1E293B"))
        for idx, col in enumerate(unique_cols):
            cx = ox + col.x * scale
            cy = oy + col.y * scale
            c.rect(cx - col_sz / 2, cy - col_sz / 2, col_sz, col_sz, fill=1, stroke=0)
            # Column label
            c.setFillColor(HexColor("#FFFFFF"))
            c.setFont("Helvetica-Bold", max(4, col_sz * 0.55))
            c.drawCentredString(cx, cy - col_sz * 0.2, f"C{idx + 1}")
            c.setFillColor(HexColor("#1E293B"))

    # Scale bar + north arrow
    _draw_scale_bar(c, ox + 4, oy + 16, scale)
    _draw_north_arrow(c, ox + plot_px - 16, oy + plot_py - 16, 12)

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
) -> None:
    c.setStrokeColor(HexColor("#CBD5E1"))
    c.setLineWidth(0.75)
    c.line(0, TITLE_H, page_w, TITLE_H)

    scale_ratio = round(1000 / (scale * (25.4 / 72)))

    city_label = cfg.city.title() if cfg.city != "other" else "NBC Defaults"
    fields = [
        ("PROJECT",  (project_name[:22] + "…") if len(project_name) > 24 else project_name),
        ("LAYOUT",   f"{layout_id} \u2013 {layout_name}"),
        ("FLOOR",    floor_label),
        ("PLOT",     f"{cfg.plot_width}\u00d7{cfg.plot_length} m"),
        ("CONFIG",   f"{num_bedrooms} BHK · {cfg.city.title()}"),
        ("SCALE",    f"1:{scale_ratio}"),
        ("DATE",     date.today().strftime("%d %b %Y")),
        ("DRAWN BY", "PlanForge"),
    ]

    col_w = page_w / len(fields)
    for i, (label, value) in enumerate(fields):
        cx = col_w * i + col_w / 2
        if i > 0:
            c.setStrokeColor(HexColor("#E2E8F0"))
            c.setLineWidth(0.5)
            c.line(col_w * i, 0, col_w * i, TITLE_H)

        c.setFillColor(HexColor("#94A3B8"))
        c.setFont("Helvetica", 6)
        c.drawCentredString(cx, TITLE_H - 16, label)

        c.setFillColor(HexColor("#1E293B"))
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(cx, TITLE_H - 32, value)

    # PlanForge branding line
    c.setFillColor(HexColor("#94A3B8"))
    c.setFont("Helvetica", 5)
    c.drawCentredString(page_w / 2, 8, "Generated by PlanForge · NBC 2016 Compliant")
