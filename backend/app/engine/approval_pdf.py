"""
Municipality Approval Drawing Package PDF generator.

Produces a 4-page A4 PDF formatted for Indian building plan submissions
(CMDA Chennai, BBMP Bangalore, GHMC Hyderabad, etc.).

Page 1 — Site Location Plan
Page 2 — Ground Floor Approval Plan
Page 3 — First Floor Approval Plan
Page 4 — Section View + Professional Title Block
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.cad_primitives import metres_to_ftin
from app.engine.models import FloorPlan, Layout, PlotConfig
from app.engine.pdf import (
    _pdf_draw_double_line_wall,
    _dedup_wall_coords,
    _draw_staircase_treads,
    _draw_windows,
    _draw_doors_in_gaps,
)

# ── Page geometry constants (points) ─────────────────────────────────────────
MARGIN = 40
TITLE_H = 120          # approval title block (taller than standard PDF)
TOP_PAD = 32
ROAD_H = 20
ROAD_GAP = 6

EXT_LW = 2.5           # external wall lineweight (IS code: heavier)
INT_LW = 1.0           # internal wall lineweight
DIM_LW = 0.5
COL_SZ = 5             # column marker half-size

# Municipality → building authority label mapping
_MUNICIPALITY_LABELS: dict[str, str] = {
    "Chennai": "CMDA",
    "Bangalore": "BBMP",
    "Hyderabad": "GHMC",
    "Mumbai": "MCGM",
    "Pune": "PMC",
}

# FAR limits per authority (simplified; actual values vary by zone)
_FAR_LIMITS: dict[str, float] = {
    "CMDA": 2.0,
    "BBMP": 2.5,
    "GHMC": 2.0,
    "MCGM": 1.33,
    "PMC": 1.5,
}


@dataclass
class OwnerInfo:
    owner_name: str
    survey_number: str
    locality: str
    engineer_name: str
    license_number: str
    municipality: str


# ── Public API ────────────────────────────────────────────────────────────────

def generate_approval_pdf(
    layout: Layout,
    plot_config: PlotConfig,
    owner_info: OwnerInfo,
    layout_id: str,
) -> bytes:
    """Return raw PDF bytes of the 4-page municipality approval drawing package."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # Page 1: Site Location Plan
    _draw_site_location_plan(c, plot_config, owner_info)
    c.showPage()

    # Page 2: Ground Floor Approval Plan
    _draw_approval_floor_plan(
        c, layout.ground_floor, layout, plot_config, owner_info, "Ground Floor"
    )
    c.showPage()

    # Page 3: First Floor Approval Plan
    _draw_approval_floor_plan(
        c, layout.first_floor, layout, plot_config, owner_info, "First Floor"
    )
    c.showPage()

    # Page 4: Section View + Title Block
    _draw_section_and_title_block(c, layout, plot_config, owner_info)
    c.showPage()

    c.save()
    return buf.getvalue()


# ── Page 1: Site Location Plan ────────────────────────────────────────────────

def _draw_site_location_plan(
    c: canvas.Canvas,
    cfg: PlotConfig,
    owner: OwnerInfo,
) -> None:
    page_w, page_h = A4
    authority = _MUNICIPALITY_LABELS.get(owner.municipality, owner.municipality.upper()[:6])

    # Background
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # Page title bar
    c.setFillColor(HexColor("#000000"))
    c.rect(0, page_h - 48, page_w, 48, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(page_w / 2, page_h - 32, "SITE LOCATION PLAN")
    c.setFont("Helvetica", 9)
    c.drawCentredString(page_w / 2, page_h - 44, f"{owner.municipality} — {authority}")

    # Drawing area bounds
    draw_top = page_h - 60
    draw_bot = 100
    draw_h = draw_top - draw_bot
    draw_w = page_w - 2 * MARGIN

    # Scale to fit plot with setbacks
    total_w = cfg.plot_width + cfg.setback_left + cfg.setback_right + 4
    total_l = cfg.plot_length + cfg.setback_front + cfg.setback_rear + 4

    scale = min(draw_w / total_w, draw_h / total_l) * 0.75  # 75% of available for margins
    plot_px = cfg.plot_width * scale
    plot_py = cfg.plot_length * scale

    # Centre the compound in the drawing area
    compound_px = total_w * scale
    compound_py = total_l * scale
    ox = MARGIN + (draw_w - compound_px) / 2 + (cfg.setback_left + 2) * scale
    oy = draw_bot + (draw_h - compound_py) / 2 + (cfg.setback_front + 2) * scale

    # Compound boundary (site limit) — dashed green
    comp_x = ox - cfg.setback_left * scale
    comp_y = oy - cfg.setback_front * scale
    comp_w = (cfg.plot_width + cfg.setback_left + cfg.setback_right) * scale
    comp_h = (cfg.plot_length + cfg.setback_front + cfg.setback_rear) * scale

    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.75)
    c.setDash(6, 3)
    c.rect(comp_x, comp_y, comp_w, comp_h, fill=0, stroke=1)
    c.setDash()

    # Plot boundary — solid dark blue, thick
    c.setStrokeColor(HexColor("#000000"))
    c.setFillColor(HexColor("#FFFFFF"))
    c.setLineWidth(2.0)
    c.rect(ox, oy, plot_px, plot_py, fill=1, stroke=1)

    # Road strip — depends on road_side
    road_side = cfg.road_side.upper()
    c.setFillColor(HexColor("#CCCCCC"))
    if road_side == "S":
        c.rect(ox, oy - cfg.setback_front * scale - ROAD_H, plot_px, ROAD_H, fill=1, stroke=0)
        c.setFillColor(HexColor("#444444"))
        c.setFont("Helvetica", 7)
        c.drawCentredString(ox + plot_px / 2, oy - cfg.setback_front * scale - ROAD_H / 2 - 3,
                            "ROAD")
    elif road_side == "N":
        road_top = oy + plot_py + cfg.setback_rear * scale
        c.rect(ox, road_top, plot_px, ROAD_H, fill=1, stroke=0)
        c.setFillColor(HexColor("#444444"))
        c.setFont("Helvetica", 7)
        c.drawCentredString(ox + plot_px / 2, road_top + ROAD_H / 2 - 3, "ROAD")

    # Building footprint (setbacks applied)
    bldg_x = ox + cfg.setback_left * scale
    bldg_y = oy + cfg.setback_front * scale
    bldg_w = (cfg.plot_width - cfg.setback_left - cfg.setback_right) * scale
    bldg_h = (cfg.plot_length - cfg.setback_front - cfg.setback_rear) * scale

    c.setFillColor(HexColor("#E8E8E8"))
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(1.5)
    if bldg_w > 4 and bldg_h > 4:
        c.rect(bldg_x, bldg_y, bldg_w, bldg_h, fill=1, stroke=1)
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica-Bold", max(7, min(10, bldg_w / 6)))
        c.drawCentredString(bldg_x + bldg_w / 2, bldg_y + bldg_h / 2 - 4, "BUILDING")

    # Setback dimension callouts
    c.setFillColor(HexColor("#555555"))
    c.setStrokeColor(HexColor("#555555"))
    c.setLineWidth(DIM_LW)
    c.setFont("Helvetica", 7)

    # Front setback
    if cfg.setback_front > 0:
        sb_mid_x = ox + plot_px / 2
        sb_y_bot = oy
        sb_y_top = bldg_y
        _draw_setback_dim(c, sb_mid_x, sb_y_bot, sb_mid_x, sb_y_top,
                          f"Front: {cfg.setback_front:.1f}m", vertical=True)

    # Rear setback
    if cfg.setback_rear > 0:
        sb_top_y = oy + plot_py
        sb_bld_top = bldg_y + bldg_h
        _draw_setback_dim(c, ox + plot_px / 2, sb_bld_top, ox + plot_px / 2, sb_top_y,
                          f"Rear: {cfg.setback_rear:.1f}m", vertical=True)

    # Left setback
    if cfg.setback_left > 0:
        _draw_setback_dim(c, ox, oy + plot_py / 2, bldg_x, oy + plot_py / 2,
                          f"Left: {cfg.setback_left:.1f}m", vertical=False)

    # Right setback
    if cfg.setback_right > 0:
        _draw_setback_dim(c, bldg_x + bldg_w, oy + plot_py / 2, ox + plot_px, oy + plot_py / 2,
                          f"Right: {cfg.setback_right:.1f}m", vertical=False)

    # North arrow — prominent, upper-right
    _draw_large_north_arrow(c, ox + compound_px + 24, oy + compound_py - 10, 22, cfg.road_side)

    # Plot dimensions
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(ox + plot_px / 2, oy + plot_py + 10,
                        f"{cfg.plot_width:.2f} m \u00d7 {cfg.plot_length:.2f} m")

    # Survey number label inside plot
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(ox + plot_px / 2, oy + 8, f"S.No: {owner.survey_number}")

    # Locality + city label
    c.setFillColor(HexColor("#444444"))
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(ox + plot_px / 2, oy - cfg.setback_front * scale - ROAD_H - 14,
                        f"{owner.locality}, {owner.municipality}")

    # Bottom info bar
    c.setFillColor(HexColor("#000000"))
    c.rect(0, 0, page_w, 95, fill=1, stroke=0)
    info_fields = [
        ("PLOT SURVEY NO.", owner.survey_number),
        ("LOCALITY", owner.locality),
        ("CITY / ULB", owner.municipality),
        ("AUTHORITY", authority),
        ("PLOT AREA", f"{cfg.plot_width * cfg.plot_length:.1f} sqm"),
        ("DATE", date.today().strftime("%d/%m/%Y")),
    ]
    col_w = page_w / len(info_fields)
    for i, (label, value) in enumerate(info_fields):
        cx = col_w * i + col_w / 2
        c.setFillColor(HexColor("#808080"))
        c.setFont("Helvetica", 6)
        c.drawCentredString(cx, 78, label)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(cx, 62, value)
        if i > 0:
            c.setStrokeColor(HexColor("#333333"))
            c.setLineWidth(0.4)
            c.line(col_w * i, 10, col_w * i, 90)

    c.setFillColor(HexColor("#555555"))
    c.setFont("Helvetica", 5)
    c.drawCentredString(page_w / 2, 8, "Generated by PlanForge · For Municipality Submission")


def _draw_setback_dim(
    c: canvas.Canvas,
    x1: float, y1: float, x2: float, y2: float,
    label: str,
    vertical: bool,
) -> None:
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(0.6)
    c.setDash(3, 2)
    if vertical:
        c.line(x1, y1, x2, y2)
        mid_y = (y1 + y2) / 2
        c.setFillColor(HexColor("#333333"))
        c.setFont("Helvetica", 6)
        c.setDash()
        c.drawCentredString(x1 + 18, mid_y, label)
    else:
        c.line(x1, y1, x2, y2)
        mid_x = (x1 + x2) / 2
        c.setFillColor(HexColor("#333333"))
        c.setFont("Helvetica", 6)
        c.setDash()
        c.drawCentredString(mid_x, y1 + 8, label)
    c.setDash()


def _draw_large_north_arrow(
    c: canvas.Canvas, cx: float, cy: float, r: float, road_side: str
) -> None:
    """Prominent north arrow for approval plans."""
    c.setFillColor(white)
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(1.5)
    c.circle(cx, cy, r, fill=1, stroke=1)

    # Arrow always points geographic N — road_side tells which edge faces road
    p = c.beginPath()
    p.moveTo(cx, cy + r * 0.85)
    p.lineTo(cx - r * 0.35, cy - r * 0.35)
    p.lineTo(cx, cy - r * 0.1)
    p.lineTo(cx + r * 0.35, cy - r * 0.35)
    p.close()
    c.setFillColor(HexColor("#000000"))
    c.drawPath(p, fill=1, stroke=0)

    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(cx, cy - r - 11, "NORTH")


# ── Page 2 & 3: Approval Floor Plan ──────────────────────────────────────────

def _draw_approval_floor_plan(
    c: canvas.Canvas,
    floor_plan: FloorPlan,
    layout: Layout,
    cfg: PlotConfig,
    owner: OwnerInfo,
    floor_label: str,
) -> None:
    page_w, page_h = A4
    authority = _MUNICIPALITY_LABELS.get(owner.municipality, owner.municipality.upper()[:6])

    # Available drawing area (above title block, below top padding)
    avail_w = page_w - 2 * MARGIN
    avail_h = page_h - TITLE_H - 2 * MARGIN - ROAD_H - ROAD_GAP - TOP_PAD

    scale = min(avail_w / cfg.plot_width, avail_h / cfg.plot_length)
    plot_px = cfg.plot_width * scale
    plot_py = cfg.plot_length * scale

    ox = MARGIN + (avail_w - plot_px) / 2
    oy = TITLE_H + MARGIN + ROAD_H + ROAD_GAP

    # Background
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(0, TITLE_H, page_w, page_h - TITLE_H, fill=1, stroke=0)

    # Road strip
    road_y = TITLE_H + MARGIN
    c.setFillColor(HexColor("#CCCCCC"))
    c.rect(ox, road_y, plot_px, ROAD_H, fill=1, stroke=0)
    c.setFillColor(HexColor("#444444"))
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(ox + plot_px / 2, road_y + ROAD_H / 2 - 3, "ROAD")

    # Plot boundary (dashed, light)
    c.setDash(5, 3)
    c.setStrokeColor(HexColor("#CCCCCC"))
    c.setLineWidth(0.75)
    c.rect(ox, oy, plot_px, plot_py, fill=0, stroke=1)
    c.setDash()

    rooms = floor_plan.rooms
    if not rooms:
        _draw_approval_title_block(c, layout, cfg, owner, floor_label, authority, page_w)
        return

    min_x = min(r.x for r in rooms)
    max_x = max(r.x + r.width for r in rooms)
    min_y = min(r.y for r in rooms)
    max_y = max(r.y + r.depth for r in rooms)

    # Room fills — white for B&W CAD / municipal submission standard
    APPROVAL_PALETTE: dict[str, str] = {
        "living":   "#FFFFFF",
        "bedroom":  "#FFFFFF",
        "master_bedroom": "#FFFFFF",
        "kitchen":  "#FFFFFF",
        "toilet":   "#FFFFFF",
        "staircase":"#FFFFFF",
        "parking":  "#FFFFFF",
        "utility":  "#FFFFFF",
        "pooja":    "#FFFFFF",
        "study":    "#FFFFFF",
        "balcony":  "#FFFFFF",
        "dining":   "#FFFFFF",
    }
    for room in rooms:
        fill_hex = APPROVAL_PALETTE.get(room.type, "#FFFFFF")
        rx = ox + room.x * scale
        ry = oy + room.y * scale
        rw = room.width * scale
        rh = room.depth * scale
        c.setFillColor(HexColor(fill_hex))
        c.rect(rx, ry, rw, rh, fill=1, stroke=0)

    # ── Door gaps (internal walls) ─────────────────────────────────────────────
    door_w_m = 0.9
    vertical_door_gaps: dict[float, list[tuple[float, float]]] = {}
    horizontal_door_gaps: dict[float, list[tuple[float, float]]] = {}
    habitable_door = {"living", "bedroom", "master_bedroom", "kitchen",
                      "study", "dining", "utility", "pooja"}

    for i, ra in enumerate(rooms):
        for j, rb in enumerate(rooms):
            if j <= i:
                continue
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

    # ── Window gaps (external walls of habitable rooms) ────────────────────────
    win_w_m = 1.2
    habitable_win = {"living", "bedroom", "master_bedroom", "kitchen", "study", "dining"}
    external_h_win_gaps: dict[float, list[tuple[float, float]]] = {}
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
            external_h_win_gaps.setdefault(round(min_y, 3), []).append(
                (rcx - ww_h / 2, rcx + ww_h / 2))
        if abs(room.y + room.depth - max_y) < tol:
            external_h_win_gaps.setdefault(round(max_y, 3), []).append(
                (rcx - ww_h / 2, rcx + ww_h / 2))
        if abs(room.x - min_x) < tol:
            external_v_win_gaps.setdefault(round(min_x, 3), []).append(
                (rcy - ww_v / 2, rcy + ww_v / 2))
        if abs(room.x + room.width - max_x) < tol:
            external_v_win_gaps.setdefault(round(max_x, 3), []).append(
                (rcy - ww_v / 2, rcy + ww_v / 2))

    # ── Double-line walls (IS code: external EXT_LW, internal INT_LW) ─────────
    iwt = 0.115
    ewt = 0.23
    xs = _dedup_wall_coords(sorted({r.x for r in rooms} | {r.x + r.width for r in rooms}))
    ys = _dedup_wall_coords(sorted({r.y for r in rooms} | {r.y + r.depth for r in rooms}))

    bx = ox + min_x * scale
    by = oy + min_y * scale
    bw = (max_x - min_x) * scale
    bh = (max_y - min_y) * scale
    ewt_px = ewt * scale
    iwt_px = iwt * scale

    c.setStrokeColor(HexColor("#000000"))

    # Internal walls
    py_lo = oy + min_y * scale + iwt_px
    py_hi = oy + max_y * scale - iwt_px
    px_lo = ox + min_x * scale + iwt_px
    px_hi = ox + max_x * scale - iwt_px

    for x in xs[1:-1]:
        px1 = ox + x * scale
        raw_gaps = vertical_door_gaps.get(round(x, 3), [])
        gaps_px = [
            ((g_s - min_y) * scale - iwt_px, (g_e - min_y) * scale - iwt_px)
            for g_s, g_e in raw_gaps
        ]
        _pdf_draw_double_line_wall(c, px1, py_lo, px1, py_hi, iwt_px, gaps_px, INT_LW)

    for y in ys[1:-1]:
        py1 = oy + y * scale
        raw_gaps = horizontal_door_gaps.get(round(y, 3), [])
        gaps_px = [
            ((g_s - min_x) * scale - iwt_px, (g_e - min_x) * scale - iwt_px)
            for g_s, g_e in raw_gaps
        ]
        _pdf_draw_double_line_wall(c, px_lo, py1, px_hi, py1, iwt_px, gaps_px, INT_LW)

    # External walls — solid (no gaps); window symbols drawn on top by _draw_windows()
    _pdf_draw_double_line_wall(c, bx, by, bx + bw, by, ewt_px, [], EXT_LW)
    _pdf_draw_double_line_wall(c, bx, by + bh, bx + bw, by + bh, ewt_px, [], EXT_LW)
    _pdf_draw_double_line_wall(c, bx, by, bx, by + bh, ewt_px, [], EXT_LW)
    _pdf_draw_double_line_wall(c, bx + bw, by, bx + bw, by + bh, ewt_px, [], EXT_LW)

    # Corner fills
    ch = ewt_px / 2
    c.setFillColor(HexColor("#000000"))
    c.setStrokeColor(HexColor("#000000"))
    for cx_c, cy_c in [(bx, by), (bx + bw, by), (bx, by + bh), (bx + bw, by + bh)]:
        c.rect(cx_c - ch, cy_c - ch, ewt_px, ewt_px, fill=1, stroke=0)

    # Setback dimension lines FROM plot boundary (mandatory for approval)
    _draw_setback_dims_on_plan(c, cfg, scale, ox, oy, plot_px, plot_py, bx, by, bw, bh, authority)

    # FAR: compute and draw table ABOVE the plot boundary (not on drawing)
    gf_area = sum(r.area for r in layout.ground_floor.rooms)
    ff_area = sum(r.area for r in layout.first_floor.rooms)
    plot_area = cfg.plot_width * cfg.plot_length
    far = (gf_area + ff_area) / plot_area if plot_area > 0 else 0.0
    far_allowed = _FAR_LIMITS.get(authority, 2.0)
    # Place FAR table above the plot top-right corner — ~144 pts available there
    _draw_far_table(
        c, ox + plot_px, oy + plot_py + 8,
        plot_area, gf_area, ff_area, far, far_allowed, authority,
    )

    # Room labels with dimensions in METRES (approval requirement)
    c.setLineWidth(1.0)
    for room in rooms:
        rx = ox + room.x * scale
        ry = oy + room.y * scale
        rw = room.width * scale
        rh = room.depth * scale
        if rw >= 55 and rh >= 28:
            # Only label rooms wide enough to avoid text bleeding into adjacent rooms
            cx_pt = rx + rw / 2
            cy_pt = ry + rh / 2
            fs = max(6, min(8, rw / 9, rh / 5))
            c.setFillColor(HexColor("#000000"))
            ftin_str = f"{metres_to_ftin(room.width)} x {metres_to_ftin(room.depth)}"
            sqft_str = f"{round(room.area * 10.764)} SQFT"
            if rh >= 46:
                # 3-line label (name + dimensions + sqft)
                c.setFont("Helvetica-Bold", fs)
                c.drawCentredString(cx_pt, cy_pt + fs * 1.2, room.name)
                c.setFont("Helvetica", fs - 1)
                c.drawCentredString(cx_pt, cy_pt + fs * 0.1, ftin_str)
                c.drawCentredString(cx_pt, cy_pt - fs * 0.9, sqft_str)
            else:
                c.setFont("Helvetica", fs)
                c.drawCentredString(
                    cx_pt, cy_pt - fs * 0.3,
                    f"{room.name} {ftin_str}"
                )

    # Staircase treads
    _draw_staircase_treads(c, rooms, scale, ox, oy)

    # Window symbols
    _draw_windows(c, rooms, scale, ox, oy, min_x, max_x, min_y, max_y)

    # Door symbols
    _draw_doors_in_gaps(c, rooms, scale, ox, oy, vertical_door_gaps, horizontal_door_gaps)

    # Column markers
    c.setFillColor(HexColor("#000000"))
    c.setDash()
    seen_cols: set[tuple[float, float]] = set()
    for col in floor_plan.columns:
        key = (round(col.x, 2), round(col.y, 2))
        if key in seen_cols:
            continue
        seen_cols.add(key)
        cx = ox + col.x * scale
        cy_c = oy + col.y * scale
        c.rect(cx - COL_SZ, cy_c - COL_SZ, COL_SZ * 2, COL_SZ * 2, fill=1, stroke=0)

    # Prominent NORTH arrow
    _draw_large_north_arrow(c, ox + plot_px - 24, oy + plot_py - 24, 18, cfg.road_side)

    # Scale bar
    _draw_scale_bar(c, ox + 4, oy + 18, scale)

    # Approval title block
    _draw_approval_title_block(c, layout, cfg, owner, floor_label, authority, page_w, far)


def _draw_setback_dims_on_plan(
    c: canvas.Canvas,
    cfg: PlotConfig,
    scale: float,
    ox: float, oy: float,
    plot_px: float, plot_py: float,
    bx: float, by: float, bw: float, bh: float,
    authority: str,
) -> None:
    """Draw dimension lines showing setbacks from plot boundary to building face."""
    c.setStrokeColor(HexColor("#333333"))
    c.setFillColor(HexColor("#333333"))
    c.setLineWidth(0.5)
    c.setFont("Helvetica", 6)

    dim_ext = 8  # pt extension outside building for dim line

    # Front setback (bottom)
    sb_front = cfg.setback_front
    if sb_front > 0:
        y_plot = oy
        y_bldg = by
        mid_x = ox + plot_px / 2
        c.setDash(3, 2)
        c.line(mid_x, y_plot, mid_x, y_bldg)
        c.setDash()
        c.drawCentredString(mid_x + 22, (y_plot + y_bldg) / 2,
                            f"F.S. {sb_front:.1f}m ({authority})")

    # Rear setback (top)
    sb_rear = cfg.setback_rear
    if sb_rear > 0:
        y_plot_top = oy + plot_py
        y_bldg_top = by + bh
        mid_x = ox + plot_px / 2
        c.setDash(3, 2)
        c.line(mid_x, y_bldg_top, mid_x, y_plot_top)
        c.setDash()
        c.drawString(ox + 4, (y_bldg_top + y_plot_top) / 2,
                     f"R.S. {sb_rear:.1f}m")

    # Left setback
    sb_left = cfg.setback_left
    if sb_left > 0:
        x_plot = ox
        x_bldg = bx
        mid_y = oy + plot_py / 2
        c.setDash(3, 2)
        c.line(x_plot, mid_y, x_bldg, mid_y)
        c.setDash()
        c.saveState()
        c.translate((x_plot + x_bldg) / 2, mid_y + 10)
        c.rotate(90)
        c.drawCentredString(0, 0, f"L.S. {sb_left:.1f}m")
        c.restoreState()

    # Right setback
    sb_right = cfg.setback_right
    if sb_right > 0:
        x_bldg_right = bx + bw
        x_plot_right = ox + plot_px
        mid_y = oy + plot_py / 2
        c.setDash(3, 2)
        c.line(x_bldg_right, mid_y, x_plot_right, mid_y)
        c.setDash()
        c.saveState()
        c.translate((x_bldg_right + x_plot_right) / 2, mid_y + 10)
        c.rotate(90)
        c.drawCentredString(0, 0, f"R.S. {sb_right:.1f}m")
        c.restoreState()


def _draw_far_table(
    c: canvas.Canvas,
    right_x: float, bottom_y: float,
    plot_area: float,
    gf_area: float,
    ff_area: float,
    far: float,
    far_allowed: float,
    authority: str,
) -> None:
    """FAR calculation table — bottom-right of drawing area."""
    table_w = 118
    row_h = 12
    rows = [
        ("Plot Area", f"{plot_area:.1f} sqm"),
        ("Built-up (GF)", f"{gf_area:.1f} sqm"),
        ("Built-up (FF)", f"{ff_area:.1f} sqm"),
        ("Total Built-up", f"{gf_area + ff_area:.1f} sqm"),
        ("FAR Achieved", f"{far:.2f}"),
        (f"FAR Allowed ({authority})", f"{far_allowed:.2f}"),
    ]
    table_h = len(rows) * row_h + 16
    tx = right_x - table_w
    ty = bottom_y

    c.setFillColor(HexColor("#FFFFFF"))
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(0.6)
    c.rect(tx, ty, table_w, table_h, fill=1, stroke=1)

    # Header
    c.setFillColor(HexColor("#000000"))
    c.rect(tx, ty + table_h - 16, table_w, 16, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(tx + table_w / 2, ty + table_h - 11, "FAR CALCULATION")

    for i, (label, value) in enumerate(rows):
        row_y = ty + table_h - 16 - (i + 1) * row_h
        if far > far_allowed and label.startswith("FAR Achieved"):
            c.setFillColor(HexColor("#FFEEEE"))
            c.rect(tx + 0.3, row_y, table_w - 0.6, row_h, fill=1, stroke=0)
        c.setFillColor(HexColor("#333333"))
        c.setFont("Helvetica", 6)
        c.drawString(tx + 4, row_y + 3.5, label)
        c.setFont("Helvetica-Bold", 6)
        c.drawRightString(tx + table_w - 4, row_y + 3.5, value)
        c.setStrokeColor(HexColor("#EBEBEB"))
        c.setLineWidth(0.3)
        c.line(tx, row_y, tx + table_w, row_y)


# ── Page 4: Section View + Professional Title Block ───────────────────────────

def _draw_section_and_title_block(
    c: canvas.Canvas,
    layout: Layout,
    cfg: PlotConfig,
    owner: OwnerInfo,
) -> None:
    page_w, page_h = A4
    authority = _MUNICIPALITY_LABELS.get(owner.municipality, owner.municipality.upper()[:6])

    # Title block occupies bottom quarter of the page
    tb_h = page_h * 0.27
    tb_y = 0
    section_h = page_h - tb_h - 20

    # Background
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(0, tb_h, page_w, page_h - tb_h, fill=1, stroke=0)

    # Page header
    c.setFillColor(HexColor("#000000"))
    c.rect(0, page_h - 36, page_w, 36, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(page_w / 2, page_h - 24, "SECTION AA — RESIDENTIAL BUILDING")

    # Parametric section view
    _draw_section_view(c, cfg, page_w, tb_h, section_h)

    # Professional title block
    _draw_professional_title_block(c, layout, cfg, owner, authority, page_w, tb_h)


def _draw_section_view(
    c: canvas.Canvas,
    cfg: PlotConfig,
    page_w: float,
    tb_h: float,
    section_h: float,
) -> None:
    """Parametric building section (GF + FF + slab + parapet)."""
    bldg_w_m = cfg.plot_width - cfg.setback_left - cfg.setback_right
    floor_h_m = 3.0      # floor-to-floor height (m)
    slab_t_m = 0.15      # slab thickness (m)
    parapet_h_m = 1.0
    found_d_m = 0.6      # foundation depth below GL
    ewt_m = 0.23

    num_floors = getattr(cfg, "num_floors", 2)
    total_above_gl = num_floors * floor_h_m + slab_t_m + parapet_h_m
    total_h_m = total_above_gl + found_d_m

    avail_w = page_w - 2 * MARGIN - 40
    avail_h = section_h - tb_h - 50

    scale = min(avail_w / (bldg_w_m + 4), avail_h / (total_h_m + 0.5))
    sx = MARGIN + 20 + (avail_w - bldg_w_m * scale) / 2
    gl_y = tb_h + 20 + found_d_m * scale

    # GL line (ground level)
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(1.0)
    c.setDash(4, 2)
    c.line(MARGIN, gl_y, page_w - MARGIN, gl_y)
    c.setDash()
    c.setFillColor(HexColor("#555555"))
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN + 2, gl_y + 3, "G.L.")

    # Foundation
    c.setFillColor(HexColor("#D1D5DB"))
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(0.5)
    found_w_px = bldg_w_m * scale + ewt_m * 2 * scale + 0.3 * scale
    found_h_px = found_d_m * scale
    c.rect(sx - ewt_m * scale, gl_y - found_h_px, found_w_px, found_h_px, fill=1, stroke=1)
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", 6)
    c.drawCentredString(sx + bldg_w_m * scale / 2, gl_y - found_h_px / 2 - 3, "FOUNDATION")

    # Floors
    floor_colors = ["#E8E8E8", "#EEEEEE"]
    for floor_idx in range(num_floors):
        floor_y = gl_y + floor_idx * floor_h_m * scale
        floor_py = floor_h_m * scale - slab_t_m * scale

        # Wall fill
        c.setFillColor(HexColor(floor_colors[floor_idx % len(floor_colors)]))
        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(EXT_LW)
        c.rect(sx, floor_y, bldg_w_m * scale, floor_py, fill=1, stroke=1)

        # Slab
        slab_y = floor_y + floor_py
        c.setFillColor(HexColor("#808080"))
        c.setStrokeColor(HexColor("#444444"))
        c.setLineWidth(1.0)
        c.rect(sx, slab_y, bldg_w_m * scale, slab_t_m * scale, fill=1, stroke=1)

        # Floor label
        label = "GROUND FLOOR" if floor_idx == 0 else "FIRST FLOOR"
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(sx + bldg_w_m * scale / 2, floor_y + floor_py / 2 - 3, label)
        c.setFont("Helvetica", 6)
        c.drawCentredString(sx + bldg_w_m * scale / 2, floor_y + floor_py / 2 - 12,
                            f"Ht: {floor_h_m:.1f}m")

        # Height dimension line (right side)
        dim_x = sx + bldg_w_m * scale + 20
        c.setStrokeColor(HexColor("#555555"))
        c.setLineWidth(DIM_LW)
        c.line(dim_x, floor_y, dim_x, floor_y + floor_py)
        c.line(dim_x - 4, floor_y, dim_x + 4, floor_y)
        c.line(dim_x - 4, floor_y + floor_py, dim_x + 4, floor_y + floor_py)
        c.setFillColor(HexColor("#555555"))
        c.setFont("Helvetica", 6)
        c.drawString(dim_x + 5, floor_y + floor_py / 2 - 3, f"{floor_h_m:.1f}m")

    # Parapet
    parapet_y = gl_y + num_floors * floor_h_m * scale
    c.setFillColor(HexColor("#EBEBEB"))
    c.setStrokeColor(HexColor("#444444"))
    c.setLineWidth(1.0)
    # Left parapet wall
    c.rect(sx, parapet_y, ewt_m * scale * 1.5, parapet_h_m * scale, fill=1, stroke=1)
    # Right parapet wall
    c.rect(sx + bldg_w_m * scale - ewt_m * scale * 1.5, parapet_y,
           ewt_m * scale * 1.5, parapet_h_m * scale, fill=1, stroke=1)
    c.setFillColor(HexColor("#555555"))
    c.setFont("Helvetica", 6)
    c.drawCentredString(sx + bldg_w_m * scale / 2, parapet_y + parapet_h_m * scale / 2,
                        f"PARAPET {parapet_h_m:.1f}m")

    # Building width dimension at top
    top_y = parapet_y + parapet_h_m * scale + 8
    c.setStrokeColor(HexColor("#555555"))
    c.setLineWidth(DIM_LW)
    c.line(sx, top_y, sx + bldg_w_m * scale, top_y)
    c.line(sx, top_y - 4, sx, top_y + 4)
    c.line(sx + bldg_w_m * scale, top_y - 4, sx + bldg_w_m * scale, top_y + 4)
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(sx + bldg_w_m * scale / 2, top_y + 5, f"{bldg_w_m:.2f}m")

    # Total height annotation
    total_h_px = total_above_gl * scale
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.5)
    left_dim_x = sx - 28
    c.line(left_dim_x, gl_y, left_dim_x, gl_y + total_h_px)
    c.line(left_dim_x - 4, gl_y, left_dim_x + 4, gl_y)
    c.line(left_dim_x - 4, gl_y + total_h_px, left_dim_x + 4, gl_y + total_h_px)
    c.saveState()
    c.translate(left_dim_x - 8, gl_y + total_h_px / 2)
    c.rotate(90)
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(0, 0, f"Total Ht: {total_above_gl:.2f}m")
    c.restoreState()

    # Slab label
    c.setFillColor(HexColor("#444444"))
    c.setFont("Helvetica", 6)
    c.drawString(sx + bldg_w_m * scale + 5, gl_y + num_floors * floor_h_m * scale - slab_t_m * scale / 2 - 3,
                 "150mm slab")

    # Section cut symbol header
    c.setFillColor(HexColor("#555555"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(sx - 20, gl_y + total_h_px + 20, "A")
    c.drawString(sx + bldg_w_m * scale + 5, gl_y + total_h_px + 20, "A")


def _draw_professional_title_block(
    c: canvas.Canvas,
    layout: Layout,
    cfg: PlotConfig,
    owner: OwnerInfo,
    authority: str,
    page_w: float,
    tb_h: float,
) -> None:
    """Full professional title block for municipality submission."""
    # Outer border
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(2.0)
    c.rect(MARGIN, 8, page_w - 2 * MARGIN, tb_h - 12, fill=0, stroke=1)

    # Inner header band
    c.setFillColor(HexColor("#000000"))
    c.rect(MARGIN, tb_h - 12 - 28, page_w - 2 * MARGIN, 28, fill=1, stroke=0)

    project_title = f"Residential Building at {owner.locality}, {owner.municipality}"
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(page_w / 2, tb_h - 12 - 28 + 9, project_title)

    # Grid of fields — 3 columns × 5 rows
    col_w = (page_w - 2 * MARGIN) / 3
    row_h = 20
    fields_grid = [
        # Row 1
        ("Owner", owner.owner_name),
        ("Plot No. / Survey No.", owner.survey_number),
        ("Municipality / ULB", f"{owner.municipality} ({authority})"),
        # Row 2
        ("Site Area", f"{cfg.plot_width * cfg.plot_length:.1f} sqm"),
        ("Built-up Area (GF)", f"{sum(r.area for r in layout.ground_floor.rooms):.1f} sqm"),
        ("Built-up Area (FF)", f"{sum(r.area for r in layout.first_floor.rooms):.1f} sqm"),
        # Row 3
        ("Architect / Engineer", owner.engineer_name),
        ("License No.", owner.license_number),
        ("Date of Submission", date.today().strftime("%d/%m/%Y")),
        # Row 4
        ("Scale", "1:100"),
        ("Drawing Reference", f"Layout {layout.id} — {layout.name}"),
        ("Software", "PlanForge"),
    ]

    tb_content_top = tb_h - 12 - 28  # bottom of header band

    for i, (label, value) in enumerate(fields_grid):
        row = i // 3
        col = i % 3
        fx = MARGIN + col * col_w
        fy = tb_content_top - (row + 1) * row_h

        # Cell border
        c.setStrokeColor(HexColor("#CCCCCC"))
        c.setLineWidth(0.4)
        c.rect(fx, fy, col_w, row_h, fill=0, stroke=1)

        # Label
        c.setFillColor(HexColor("#555555"))
        c.setFont("Helvetica", 6)
        c.drawString(fx + 4, fy + row_h - 9, label)

        # Value
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(fx + 4, fy + 4, value[:35] if len(value) > 35 else value)

    # Signature + Seal row at bottom
    sig_y = 8
    sig_h = tb_content_top - 4 * row_h - 8 - sig_y
    sig_w = (page_w - 2 * MARGIN) / 2

    # Signature box (left half)
    c.setStrokeColor(HexColor("#CCCCCC"))
    c.setLineWidth(0.5)
    c.rect(MARGIN, sig_y, sig_w, sig_h, fill=0, stroke=1)
    c.setFillColor(HexColor("#555555"))
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN + 6, sig_y + sig_h - 12, "Signature of Architect/Engineer:")
    c.setStrokeColor(HexColor("#808080"))
    c.setLineWidth(0.5)
    sig_line_y = sig_y + sig_h * 0.4
    c.line(MARGIN + 8, sig_line_y, MARGIN + sig_w - 8, sig_line_y)
    c.setFillColor(HexColor("#808080"))
    c.setFont("Helvetica-Oblique", 6)
    c.drawCentredString(MARGIN + sig_w / 2, sig_line_y - 9, "(Authorised Signatory)")

    # Seal box (right half)
    c.setStrokeColor(HexColor("#CCCCCC"))
    c.setLineWidth(0.5)
    c.rect(MARGIN + sig_w, sig_y, sig_w, sig_h, fill=0, stroke=1)
    seal_cx = MARGIN + sig_w + sig_w / 2
    seal_cy = sig_y + sig_h / 2
    seal_r = min(sig_h / 2 - 4, sig_w / 3)
    c.setStrokeColor(HexColor("#CCCCCC"))
    c.setLineWidth(0.75)
    c.circle(seal_cx, seal_cy, seal_r, fill=0, stroke=1)
    c.setStrokeColor(HexColor("#EBEBEB"))
    c.circle(seal_cx, seal_cy, seal_r * 0.8, fill=0, stroke=1)
    c.setFillColor(HexColor("#CCCCCC"))
    c.setFont("Helvetica", 6)
    c.drawCentredString(seal_cx, seal_cy + 3, "SEAL")
    c.drawCentredString(seal_cx, seal_cy - 6, "(Office Stamp)")
    c.setFillColor(HexColor("#555555"))
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN + sig_w + 6, sig_y + sig_h - 12, "Official Seal:")

    # Footer
    c.setFillColor(HexColor("#808080"))
    c.setFont("Helvetica", 5)
    c.drawCentredString(page_w / 2, 2,
                        "Generated by PlanForge · NBC 2016 Compliant · For Municipality Submission Only")


# ── Shared drawing helpers ────────────────────────────────────────────────────

def _draw_scale_bar(c: canvas.Canvas, x: float, y: float, scale: float) -> None:
    bar_pt = 3.0 * scale
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(1.5)
    c.line(x, y, x + bar_pt, y)
    c.setLineWidth(1.0)
    c.line(x, y - 3, x, y + 3)
    c.line(x + bar_pt, y - 3, x + bar_pt, y + 3)
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", 6)
    c.drawCentredString(x + bar_pt / 2, y - 11, "3 m")
    c.setFont("Helvetica", 5)
    c.drawCentredString(x + bar_pt / 2, y - 19, "SCALE 1:100")


def _draw_approval_title_block(
    c: canvas.Canvas,
    layout: Layout,
    cfg: PlotConfig,
    owner: OwnerInfo,
    floor_label: str,
    authority: str,
    page_w: float,
    far: float = 0.0,
) -> None:
    """Compact title block for floor plan pages."""
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(1.0)
    c.line(0, TITLE_H, page_w, TITLE_H)
    c.setStrokeColor(HexColor("#EBEBEB"))
    c.setLineWidth(0.3)
    c.line(0, TITLE_H - 36, page_w, TITLE_H - 36)

    scale_ratio = 100  # Fixed 1:100

    # Compute built-up area in SQFT for title block
    gf_sqft = round(sum(r.area for r in layout.ground_floor.rooms) * 10.764)
    ff_sqft = round(sum(r.area for r in layout.first_floor.rooms) * 10.764)
    total_sqft = gf_sqft + ff_sqft
    far_allowed = _FAR_LIMITS.get(authority, 2.0)

    fields = [
        ("PROJECT", (owner.locality + ", " + owner.municipality)[:28]),
        ("LAYOUT", f"{layout.id} - {layout.name}"),
        ("FLOOR", floor_label),
        ("PLOT", f"{cfg.plot_width}x{cfg.plot_length}m"),
        ("SURVEY NO.", owner.survey_number),
        ("SCALE", f"1:{scale_ratio}"),
        ("AUTHORITY", authority),
        ("TOTAL AREA", f"{total_sqft} SQFT"),
        ("FAR", f"{far:.2f}/{far_allowed:.2f}"),
        ("DATE", date.today().strftime("%d/%m/%Y")),
        ("ENGINEER", owner.engineer_name[:18] if owner.engineer_name else "-"),
    ]

    col_w = page_w / len(fields)
    for i, (label, value) in enumerate(fields):
        cx = col_w * i + col_w / 2
        if i > 0:
            c.setStrokeColor(HexColor("#EBEBEB"))
            c.setLineWidth(0.4)
            c.line(col_w * i, 0, col_w * i, TITLE_H)

        c.setFillColor(HexColor("#555555"))
        c.setFont("Helvetica", 5.5)
        c.drawCentredString(cx, TITLE_H - 14, label)

        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(cx, TITLE_H - 27, value)

    # Bottom sub-row: owner details
    c.setFillColor(HexColor("#F0F0F0"))
    c.rect(0, 0, page_w, 36, fill=1, stroke=0)
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", 7)
    owner_line = f"Owner: {owner.owner_name}  |  Plot No.: {owner.survey_number}  |  {owner.locality}, {owner.municipality}"
    c.drawCentredString(page_w / 2, 26, owner_line)
    c.setFont("Helvetica-Oblique", 6.5)
    c.drawCentredString(
        page_w / 2, 13,
        f"Prepared by: {owner.engineer_name}  |  Lic. No.: {owner.license_number}  |  {authority} Submission"
    )
    c.setFillColor(HexColor("#808080"))
    c.setFont("Helvetica", 5)
    c.drawCentredString(page_w / 2, 3, "Generated by PlanForge · NBC 2016 Compliant")
