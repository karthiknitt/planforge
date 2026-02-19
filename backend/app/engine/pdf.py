from __future__ import annotations

import math
from datetime import date
from io import BytesIO

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.models import FloorPlan, Layout, PlotConfig

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
    """Return raw PDF bytes containing ground floor and first floor pages."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for floor_plan in [layout.ground_floor, layout.first_floor]:
        floor_label = "Ground Floor" if floor_plan.floor == 0 else "First Floor"
        _draw_floor(c, floor_plan, layout, cfg, project_name, num_bedrooms, floor_label)
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

    # ── Internal walls (double lines between rooms) ───────────────────────────
    iwt = 0.115
    ewt = 0.23
    rooms = floor_plan.rooms
    if rooms:
        xs = sorted({r.x for r in rooms} | {r.x + r.width for r in rooms})
        ys = sorted({r.y for r in rooms} | {r.y + r.depth for r in rooms})

        min_x = min(r.x for r in rooms)
        max_x = max(r.x + r.width for r in rooms)
        min_y = min(r.y for r in rooms)
        max_y = max(r.y + r.depth for r in rooms)

        c.setStrokeColor(HexColor("#334155"))
        c.setLineWidth(INT_LW)
        c.setDash()

        # Vertical interior dividers
        for x in xs[1:-1]:  # skip outer edges
            px1 = ox + x * scale
            py1 = oy + min_y * scale
            py2 = oy + max_y * scale
            c.line(px1 - (iwt * scale / 2), py1, px1 - (iwt * scale / 2), py2)
            c.line(px1 + (iwt * scale / 2), py1, px1 + (iwt * scale / 2), py2)

        # Horizontal interior dividers
        for y in ys[1:-1]:
            py1 = oy + y * scale
            px1 = ox + min_x * scale
            px2 = ox + max_x * scale
            c.line(px1, py1 - (iwt * scale / 2), px2, py1 - (iwt * scale / 2))
            c.line(px1, py1 + (iwt * scale / 2), px2, py1 + (iwt * scale / 2))

        # ── External wall boundary (thick) ────────────────────────────────────
        c.setLineWidth(EXT_LW)
        bx = ox + min_x * scale
        by = oy + min_y * scale
        bw = (max_x - min_x) * scale
        bh = (max_y - min_y) * scale
        half_ewt = ewt * scale / 2
        c.rect(bx - half_ewt, by - half_ewt,
               bw + 2 * half_ewt, bh + 2 * half_ewt, fill=0, stroke=1)
        c.setLineWidth(INT_LW)
        c.rect(bx + half_ewt, by + half_ewt,
               bw - 2 * half_ewt, bh - 2 * half_ewt, fill=0, stroke=1)

        # ── Window symbols on exterior walls ──────────────────────────────────
        _draw_windows(c, rooms, scale, ox, oy, min_x, max_x, min_y, max_y)

        # ── Door symbols ──────────────────────────────────────────────────────
        _draw_doors(c, rooms, scale, ox, oy)

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
    """Draw simplified door symbols (line + arc) on room entry walls."""
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
        # Swing arc (quarter circle)
        r_px = door_px
        c.arc(hx - r_px, hy - r_px, hx + r_px, hy + r_px, 0, 90)


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
