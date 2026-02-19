from __future__ import annotations

from datetime import date
from io import BytesIO

from reportlab.lib.colors import HexColor, white
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
}

# ── Page constants (points) ───────────────────────────────────────────────────
TITLE_H  = 72   # title block height
MARGIN   = 36   # page margins
ROAD_H   = 18   # road strip height
ROAD_GAP = 4    # gap between road strip top and plot boundary bottom
TOP_PAD  = 28   # padding above plot for north arrow / scale bar
COL_SZ   = 3    # column marker half-size (pt)


# ── Public API ────────────────────────────────────────────────────────────────

def render_pdf(project_name: str, layout: Layout, cfg: PlotConfig, bhk: int) -> bytes:
    """Return raw PDF bytes containing ground floor and first floor pages."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for floor_plan in [layout.ground_floor, layout.first_floor]:
        floor_label = "Ground Floor" if floor_plan.floor == 0 else "First Floor"
        _draw_floor(c, floor_plan, layout, cfg, project_name, bhk, floor_label)
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

    scale = min(avail_w / cfg.plot_width, avail_h / cfg.plot_length)
    plot_px = cfg.plot_width * scale
    plot_py = cfg.plot_length * scale

    # Centre plot horizontally; road strip sits just below the plot.
    offset_x = MARGIN + (avail_w - plot_px) / 2
    # offset_y = y of the bottom edge of the plot in PDF coords
    offset_y = TITLE_H + MARGIN + ROAD_H + ROAD_GAP

    return scale, offset_x, offset_y, plot_px, plot_py


def _draw_floor(
    c: canvas.Canvas,
    floor_plan: FloorPlan,
    layout: Layout,
    cfg: PlotConfig,
    project_name: str,
    bhk: int,
    floor_label: str,
) -> None:
    page_w, page_h = A4
    scale, ox, oy, plot_px, plot_py = _compute_layout(cfg, page_w, page_h)

    # ── Background ────────────────────────────────────────────────────────────
    c.setFillColor(HexColor("#F8FAFC"))
    c.rect(0, TITLE_H, page_w, page_h - TITLE_H, fill=1, stroke=0)

    # ── Road strip (below plot, above title block margin) ─────────────────────
    road_y = TITLE_H + MARGIN  # bottom of road strip in PDF coords
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

    # ── Rooms ─────────────────────────────────────────────────────────────────
    c.setLineWidth(1.0)
    for room in floor_plan.rooms:
        fill_hex, stroke_hex = PALETTE.get(room.type, ("#F8FAFC", "#94A3B8"))
        rx = ox + room.x * scale
        ry = oy + room.y * scale
        rw = room.width * scale
        rh = room.depth * scale

        c.setFillColor(HexColor(fill_hex))
        c.setStrokeColor(HexColor(stroke_hex))
        c.setDash()
        c.rect(rx, ry, rw, rh, fill=1, stroke=1)

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

    # ── Column markers ────────────────────────────────────────────────────────
    c.setFillColor(HexColor("#1E293B"))
    c.setDash()
    for col in floor_plan.columns:
        cx = ox + col.x * scale
        cy = oy + col.y * scale
        c.rect(cx - COL_SZ, cy - COL_SZ, COL_SZ * 2, COL_SZ * 2, fill=1, stroke=0)

    # ── Dimension labels ──────────────────────────────────────────────────────
    # Width dimension: centred below the road strip (in bottom margin area)
    dim_y = TITLE_H + (MARGIN * 0.55)
    c.setFillColor(HexColor("#94A3B8"))
    c.setStrokeColor(HexColor("#94A3B8"))
    c.setLineWidth(0.5)
    c.setFont("Helvetica", 7)
    c.drawCentredString(ox + plot_px / 2, dim_y, f"{cfg.plot_width:.1f} m")
    c.line(ox, dim_y + 3, ox, dim_y + 8)
    c.line(ox + plot_px, dim_y + 3, ox + plot_px, dim_y + 8)
    c.line(ox, dim_y + 5, ox + plot_px, dim_y + 5)

    # Depth dimension: left of plot, rotated
    c.saveState()
    c.setFillColor(HexColor("#94A3B8"))
    c.setFont("Helvetica", 7)
    c.translate(ox - 14, oy + plot_py / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, f"{cfg.plot_length:.1f} m")
    c.restoreState()

    # ── Scale bar (bottom-left of plot area) ──────────────────────────────────
    _draw_scale_bar(c, ox + 4, oy + 16, scale)

    # ── North arrow (top-right of plot area) ──────────────────────────────────
    _draw_north_arrow(c, ox + plot_px - 16, oy + plot_py - 16, 12)

    # ── Title block ───────────────────────────────────────────────────────────
    _draw_title_block(c, project_name, layout.id, layout.name, floor_label, cfg, bhk, scale, page_w)


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

    # Upward-pointing filled triangle
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
    bhk: int,
    scale: float,
    page_w: float,
) -> None:
    # Horizontal ruling line separating drawing area from title block
    c.setStrokeColor(HexColor("#CBD5E1"))
    c.setLineWidth(0.75)
    c.line(0, TITLE_H, page_w, TITLE_H)

    # Scale ratio: 1 pt = 25.4/72 mm → ratio = 1000 / (scale * 25.4/72)
    scale_ratio = round(1000 / (scale * (25.4 / 72)))

    fields = [
        ("PROJECT",  project_name[:24] if len(project_name) > 24 else project_name),
        ("LAYOUT",   f"{layout_id} \u2013 {layout_name}"),
        ("FLOOR",    floor_label),
        ("PLOT",     f"{cfg.plot_width}\u00d7{cfg.plot_length} m"),
        ("CONFIG",   f"{bhk} BHK"),
        ("SCALE",    f"1:{scale_ratio}"),
        ("DATE",     date.today().strftime("%d %b %Y")),
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
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(cx, TITLE_H - 32, value)

    c.setFillColor(HexColor("#94A3B8"))
    c.setFont("Helvetica", 5)
    c.drawCentredString(page_w / 2, 8, "Generated by PlanForge")
