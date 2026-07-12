"""
Municipality Approval Drawing Package PDF generator.

Produces a 5-page A4 PDF formatted for Indian building plan submissions
(CMDA Chennai, BBMP Bangalore, GHMC Hyderabad, etc.).

Page 1 — Site Location Plan
Page 2 — Ground Floor Approval Plan
Page 3 — First Floor Approval Plan
Page 4 — Section A-A + Professional Title Block
Page 5 — Front Elevation + Professional Title Block
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import BytesIO

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.geometry import buildable_polygon
from app.engine.models import FloorPlan, Layout, PlotConfig
from app.engine.section_geometry import (
    derive_elevation,
    derive_section,
    section_cut_line,
)
from app.engine.section_render import (
    draw_section_marker,
    render_elevation_view,
    render_section_view,
)
from app.engine.title_block import draw_title_block

# ── Page geometry constants (points) ─────────────────────────────────────────
MARGIN = 40
TITLE_H = 120  # approval title block (taller than standard PDF)
TOP_PAD = 32
ROAD_H = 20
ROAD_GAP = 6

EXT_LW = 2.5  # external wall lineweight (IS code: heavier)
INT_LW = 1.0  # internal wall lineweight
DIM_LW = 0.5

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
    """Return raw PDF bytes of the 5-page municipality approval drawing package."""
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

    # Page 5: Front Elevation + Title Block
    _draw_elevation_and_title_block(c, layout, plot_config, owner_info)
    c.showPage()

    c.save()
    return buf.getvalue()


# ── Page 1: Site Location Plan ────────────────────────────────────────────────


def _draw_site_location_plan(
    c: canvas.Canvas,
    cfg: PlotConfig,
    owner: OwnerInfo,
) -> None:
    from shapely.geometry import box as shapely_box

    page_w, page_h = A4
    authority = _MUNICIPALITY_LABELS.get(owner.municipality, owner.municipality.upper())

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

    # Drawing area bounds. SIDE_PAD reserves room on both sides for the
    # rotated Left/Right setback labels (and, when the road is E/W, the
    # road strip on that side) so neither ever clips at the page edge.
    SIDE_PAD = 46
    draw_top = page_h - 56
    draw_bot = 150  # room for road strip (worst case S) + caption + info bar
    draw_h = draw_top - draw_bot
    draw_w = page_w - 2 * MARGIN - 2 * SIDE_PAD

    # Scale to fit plot with setbacks
    total_w = cfg.plot_width + cfg.setback_left + cfg.setback_right + 4
    total_l = cfg.plot_length + cfg.setback_front + cfg.setback_rear + 4

    scale = min(draw_w / total_w, draw_h / total_l) * 0.94  # near-full fill
    plot_px = cfg.plot_width * scale
    plot_py = cfg.plot_length * scale

    # Centre the compound in the drawing area
    compound_px = total_w * scale
    compound_py = total_l * scale
    ox = MARGIN + SIDE_PAD + (draw_w - compound_px) / 2 + (cfg.setback_left + 2) * scale
    oy = draw_bot + (draw_h - compound_py) / 2 + (cfg.setback_front + 2) * scale

    # Compound boundary (site limit) — dashed
    comp_x = ox - cfg.setback_left * scale
    comp_y = oy - cfg.setback_front * scale
    comp_w = (cfg.plot_width + cfg.setback_left + cfg.setback_right) * scale
    comp_h = (cfg.plot_length + cfg.setback_front + cfg.setback_rear) * scale

    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.75)
    c.setDash(6, 3)
    c.rect(comp_x, comp_y, comp_w, comp_h, fill=0, stroke=1)
    c.setDash()

    # Plot boundary — solid black, thick
    c.setStrokeColor(HexColor("#000000"))
    c.setFillColor(HexColor("#FFFFFF"))
    c.setLineWidth(2.0)
    c.rect(ox, oy, plot_px, plot_py, fill=1, stroke=1)

    # Road strip — on whichever side the road actually is (S/N/E/W),
    # anchored to the compound (site-limit padding), not the bare plot.
    _draw_road_strip_for_side(c, cfg.road_side, comp_x, comp_y, comp_w, comp_h)

    # Building footprint (setbacks applied) — white + 45deg hatch, matching
    # the floor-plan pages' strict-B/W convention (no solid colour fills)
    bldg_x = ox + cfg.setback_left * scale
    bldg_y = oy + cfg.setback_front * scale
    bldg_w = (cfg.plot_width - cfg.setback_left - cfg.setback_right) * scale
    bldg_h = (cfg.plot_length - cfg.setback_front - cfg.setback_rear) * scale

    if bldg_w > 4 and bldg_h > 4:
        c.setFillColor(HexColor("#FFFFFF"))
        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(1.5)
        c.rect(bldg_x, bldg_y, bldg_w, bldg_h, fill=1, stroke=1)
        model_box = shapely_box(
            cfg.setback_left,
            cfg.setback_front,
            cfg.plot_width - cfg.setback_right,
            cfg.plot_length - cfg.setback_rear,
        )
        _hatch_polygons(c, model_box, scale, ox, oy, spacing=4.0)
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica-Bold", max(7, min(10, bldg_w / 6)))
        c.drawCentredString(bldg_x + bldg_w / 2, bldg_y + bldg_h / 2 - 4, "BUILDING")

    # Setback dimension callouts
    c.setFillColor(HexColor("#333333"))
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(DIM_LW)
    c.setFont("Helvetica", 6)

    # Front setback (vertical dim line inside the plot; label offset right)
    if cfg.setback_front > 0:
        sb_mid_x = ox + plot_px / 2
        _draw_setback_dim(
            c,
            sb_mid_x,
            oy,
            sb_mid_x,
            bldg_y,
            f"{cfg.setback_front:.1f}M FRONT SETBACK",
            vertical=True,
        )

    # Rear setback
    if cfg.setback_rear > 0:
        _draw_setback_dim(
            c,
            ox + plot_px / 2,
            bldg_y + bldg_h,
            ox + plot_px / 2,
            oy + plot_py,
            f"{cfg.setback_rear:.1f}M REAR SETBACK",
            vertical=True,
        )

    # Left/Right setbacks: short dashed tick inside the plot showing the
    # gap, label rotated 90 deg OUTSIDE the compound — a narrow footprint
    # that can never clip regardless of how tight the setback strip is.
    road_upper = cfg.road_side.upper()
    left_clear = 8 + (ROAD_GAP + ROAD_H if road_upper == "W" else 0)
    right_clear = 8 + (ROAD_GAP + ROAD_H if road_upper == "E" else 0)

    if cfg.setback_left > 0:
        c.setDash(3, 2)
        c.line(ox, oy + plot_py / 2, bldg_x, oy + plot_py / 2)
        c.setDash()
        c.saveState()
        c.translate(comp_x - left_clear, comp_y + comp_h / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, f"{cfg.setback_left:.1f}M LEFT SETBACK")
        c.restoreState()

    if cfg.setback_right > 0:
        c.setDash(3, 2)
        c.line(bldg_x + bldg_w, oy + plot_py / 2, ox + plot_px, oy + plot_py / 2)
        c.setDash()
        c.saveState()
        c.translate(comp_x + comp_w + right_clear, comp_y + comp_h / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, f"{cfg.setback_right:.1f}M RIGHT SETBACK")
        c.restoreState()

    # North arrow — prominent, upper-right, fully inside the page margin
    _draw_large_north_arrow(
        c, page_w - MARGIN - 24, page_h - 56 - 24, 20, cfg.road_side
    )

    # Plot dimensions \u2014 dual-unit (ft-in prominent, metric beneath)
    from app.engine.cad_primitives import metres_to_ftin

    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(
        ox + plot_px / 2,
        oy + plot_py + 19,
        f"{metres_to_ftin(cfg.plot_width)} \u00d7 {metres_to_ftin(cfg.plot_length)}",
    )
    c.setFont("Helvetica", 7)
    c.drawCentredString(
        ox + plot_px / 2,
        oy + plot_py + 9,
        f"({cfg.plot_width:.2f} m \u00d7 {cfg.plot_length:.2f} m)",
    )

    # Caption line below the compound (+ road strip, if on the south side):
    # survey no. + locality. Kept off the plot entirely — it used to sit
    # inside the plot and collide with the Front setback label.
    road_extra = ROAD_GAP + ROAD_H if cfg.road_side.upper() == "S" else 0
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(
        page_w / 2, comp_y - road_extra - 14, f"S.No: {owner.survey_number}"
    )
    c.setFillColor(HexColor("#444444"))
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(
        page_w / 2,
        comp_y - road_extra - 26,
        f"{owner.locality}, {owner.municipality}",
    )

    # Graphic scale bar (site-plan scale is fit-based, not a standard denom)
    from app.engine.pdf import _PT_PER_PAPER_M, _draw_scale_bar

    _draw_scale_bar(c, MARGIN, 104, scale, denom=round(_PT_PER_PAPER_M / scale))

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
    c.drawCentredString(
        page_w / 2, 8, "Generated by PlanForge · For Municipality Submission"
    )


def _draw_setback_dim(
    c: canvas.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
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


def _hatch_polygons(
    c: canvas.Canvas, geom, s: float, ox: float, oy: float, spacing: float = 3.0
) -> None:
    """45-degree hatch inside a shapely (Multi)Polygon (IS 962 brick convention)."""
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for poly in polys:
        if poly.is_empty:
            continue
        c.saveState()
        path = c.beginPath()
        for ring in [poly.exterior, *poly.interiors]:
            pts = [(ox + x * s, oy + y * s) for x, y in ring.coords]
            path.moveTo(*pts[0])
            for pt in pts[1:]:
                path.lineTo(*pt)
            path.close()
        c.clipPath(path, stroke=1, fill=0)
        minx, miny, maxx, maxy = poly.bounds
        x1p, y1p = ox + minx * s, oy + miny * s
        x2p, y2p = ox + maxx * s, oy + maxy * s
        c.setLineWidth(0.25)
        d = x2p - x1p + (y2p - y1p)
        t = -(y2p - y1p)
        while t < d:
            c.line(x1p + t, y1p, x1p + t + (y2p - y1p), y2p)
            t += spacing
        c.restoreState()


def _draw_far_strip(
    c: canvas.Canvas, layout: Layout, cfg: PlotConfig, authority: str, page_w: float
) -> None:
    """Single-line FAR summary in a reserved band above the title block."""
    plot_area = cfg.plot_width * cfg.plot_length
    gf = sum(r.area for r in layout.ground_floor.rooms)
    ff = sum(r.area for r in layout.first_floor.rooms)
    total = gf + ff
    achieved = total / plot_area if plot_area else 0.0
    allowed = _FAR_LIMITS.get(cfg.municipality or "", 2.0)
    text = (
        f"FAR CALCULATION — PLOT {plot_area:.1f} SQM | BUILT-UP GF {gf:.1f} | "
        f"FF {ff:.1f} | TOTAL {total:.1f} SQM | FAR ACHIEVED {achieved:.2f} | "
        f"ALLOWED ({authority}) {allowed:.2f}"
    )
    band_y = TITLE_H + 2
    c.setFillColor(HexColor("#FFFFFF"))
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.5)
    c.rect(0, band_y, page_w, 13, fill=1, stroke=1)
    c.setFillColor(HexColor("#000000"))
    font = 6.5
    from reportlab.pdfbase import pdfmetrics

    while (
        font > 4.5 and pdfmetrics.stringWidth(text, "Helvetica-Bold", font) > page_w - 8
    ):
        font -= 0.5
    c.setFont("Helvetica-Bold", font)
    c.drawCentredString(page_w / 2, band_y + 4, text)


def _draw_road_strip_for_side(
    c: canvas.Canvas,
    road_side: str,
    ox: float,
    oy: float,
    plot_px: float,
    plot_py: float,
) -> None:
    """Grey road band on whichever side the road actually is (S/N/E/W)."""
    c.setFillColor(HexColor("#DDDDDD"))
    if road_side == "S":
        c.rect(ox, oy - ROAD_GAP - ROAD_H, plot_px, ROAD_H, fill=1, stroke=0)
        tx, ty, rot = ox + plot_px / 2, oy - ROAD_GAP - ROAD_H + ROAD_H / 2 - 3, 0
    elif road_side == "N":
        c.rect(ox, oy + plot_py + ROAD_GAP, plot_px, ROAD_H, fill=1, stroke=0)
        tx, ty, rot = ox + plot_px / 2, oy + plot_py + ROAD_GAP + ROAD_H / 2 - 3, 0
    elif road_side == "W":
        c.rect(ox - ROAD_GAP - ROAD_H, oy, ROAD_H, plot_py, fill=1, stroke=0)
        tx, ty, rot = ox - ROAD_GAP - ROAD_H / 2, oy + plot_py / 2, 90
    else:  # E
        c.rect(ox + plot_px + ROAD_GAP, oy, ROAD_H, plot_py, fill=1, stroke=0)
        tx, ty, rot = ox + plot_px + ROAD_GAP + ROAD_H / 2, oy + plot_py / 2, 90
    c.setFillColor(HexColor("#444444"))
    c.setFont("Helvetica-Bold", 7)
    c.saveState()
    c.translate(tx, ty)
    if rot:
        c.rotate(rot)
    c.drawCentredString(0, 0, "ROAD")
    c.restoreState()


def _draw_approval_floor_plan(
    c: canvas.Canvas,
    floor_plan: FloorPlan,
    layout: Layout,
    cfg: PlotConfig,
    owner: OwnerInfo,
    floor_label: str,
) -> None:
    """Municipal floor plan projected from the canonical FloorDrawing:
    strict B/W, hatched walls, doors/windows/ventilators, full dimension
    chains (rooms + plot/setbacks), FAR strip clear of the plan."""
    from app.engine.pdf import (
        SCHED_PAD,
        SCHED_RESERVE,
        _area_schedule_height,
        _centered_plot_oy,
        _draw_area_schedule_table,
        _draw_dim_chains,
        _draw_labels,
        _draw_opening_symbol,
        _draw_opening_tags,
        _draw_openings_schedule_table,
        _draw_scale_bar,
        _draw_setback_callouts,
        _draw_stair_geometry,
        _openings_schedule_height,
        _opening_marks,
        _schedule_column_x,
        _shape_path,
        _standard_scale,
    )
    from app.engine.plan_geometry import (
        build_floor_drawing,
        opening_boxes,
        wall_polygons,
    )

    page_w, page_h = A4
    authority = _MUNICIPALITY_LABELS.get(owner.municipality, owner.municipality.upper())

    s, _denom = _standard_scale(cfg, page_w, page_h, reserve_w=SCHED_RESERVE)
    plot_px, plot_py = cfg.plot_width * s, cfg.plot_length * s
    # Centre the plot in the left region (reserved schedule column on the
    # right) and centre the plot+road group vertically as a unit — the road
    # sits below (S) or above (N) the plot on the actual road side.
    road_upper = cfg.road_side.upper()
    road_below = ROAD_H + ROAD_GAP if road_upper == "S" else 0.0
    road_above = ROAD_H + ROAD_GAP if road_upper == "N" else 0.0
    ox = MARGIN + (page_w - 2 * MARGIN - SCHED_RESERVE - plot_px) / 2
    oy = _centered_plot_oy(
        page_h,
        plot_py,
        title_h=TITLE_H,
        margin=MARGIN,
        road_below=road_below,
        road_above=road_above,
    )

    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(0, TITLE_H, page_w, page_h - TITLE_H, fill=1, stroke=0)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(HexColor("#000000"))
    c.drawCentredString(
        ox + plot_px / 2, oy + plot_py + road_above + 10, f"{floor_label.upper()} PLAN"
    )
    _draw_road_strip_for_side(c, cfg.road_side, ox, oy, plot_px, plot_py)

    c.setDash(5, 3)
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.5)
    c.rect(ox, oy, plot_px, plot_py, fill=0, stroke=1)
    c.setDash()

    if not floor_plan.rooms:
        _draw_approval_title_block(
            c, layout, cfg, owner, floor_label, authority, page_w
        )
        return

    drawing = build_floor_drawing(floor_plan, cfg)
    polys = wall_polygons(drawing.walls, openings=opening_boxes(drawing.openings))

    c.setStrokeColor(HexColor("#000000"))
    c.setFillColor(HexColor("#FFFFFF"))
    c.setLineWidth(0.7)
    _shape_path(c, polys["external"], s, ox, oy)
    _hatch_polygons(c, polys["external"], s, ox, oy)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setLineWidth(0.4)
    _shape_path(c, polys["internal"], s, ox, oy)
    _hatch_polygons(c, polys["internal"], s, ox, oy, spacing=2.5)

    # Section A-A cut marker
    line, _along_y = section_cut_line(floor_plan.rooms, buildable_polygon(cfg))
    (lx1, ly1), (lx2, ly2) = line.coords[0], line.coords[-1]
    draw_section_marker(c, ox + lx1 * s, oy + ly1 * s, ox + lx2 * s, oy + ly2 * s, "A")

    for o in drawing.openings:
        _draw_opening_symbol(c, o, s, ox, oy)
    half_col = 0.15 * s
    c.setFillColor(HexColor("#000000"))
    for col in drawing.columns:
        c.rect(
            ox + col.cx * s - half_col,
            oy + col.cy * s - half_col,
            2 * half_col,
            2 * half_col,
            fill=1,
            stroke=0,
        )
    _draw_stair_geometry(c, drawing, s, ox, oy)
    _draw_labels(c, drawing, s, ox, oy, _denom)
    _draw_dim_chains(
        c,
        drawing,
        s,
        ox,
        oy,
        plot_px,
        plot_py,
        bottom_lane_y=oy - ROAD_GAP - ROAD_H - 10,
    )
    _draw_setback_callouts(c, cfg, drawing.bounds, s, ox, oy)
    marks, opening_rows = _opening_marks(drawing)
    _draw_opening_tags(c, drawing, marks, s, ox, oy)
    # Schedule tables stacked bottom-right, above the FAR strip + title block.
    sched_x = _schedule_column_x(page_w, MARGIN)
    sched_base = TITLE_H + 18  # clear the full-width FAR strip band
    area_top = sched_base + SCHED_PAD + _area_schedule_height(floor_plan)
    _draw_area_schedule_table(c, floor_plan, sched_x, area_top)
    if opening_rows:
        openings_top = area_top + SCHED_PAD + _openings_schedule_height(opening_rows)
        _draw_openings_schedule_table(c, opening_rows, sched_x, openings_top)
    _draw_scale_bar(c, MARGIN, TITLE_H + 22, s, _denom)

    _draw_large_north_arrow(
        c, page_w - MARGIN - 20, page_h - MARGIN - 20, 18, cfg.road_side
    )
    _draw_far_strip(c, layout, cfg, authority, page_w)
    _draw_approval_title_block(c, layout, cfg, owner, floor_label, authority, page_w)


def _draw_setback_dims_on_plan(
    c: canvas.Canvas,
    cfg: PlotConfig,
    scale: float,
    ox: float,
    oy: float,
    plot_px: float,
    plot_py: float,
    bx: float,
    by: float,
    bw: float,
    bh: float,
    authority: str,
) -> None:
    """Draw dimension lines showing setbacks from plot boundary to building face."""
    c.setStrokeColor(HexColor("#333333"))
    c.setFillColor(HexColor("#333333"))
    c.setLineWidth(0.5)
    c.setFont("Helvetica", 6)

    # Front setback (bottom)
    sb_front = cfg.setback_front
    if sb_front > 0:
        y_plot = oy
        y_bldg = by
        mid_x = ox + plot_px / 2
        c.setDash(3, 2)
        c.line(mid_x, y_plot, mid_x, y_bldg)
        c.setDash()
        c.drawCentredString(
            mid_x + 22, (y_plot + y_bldg) / 2, f"F.S. {sb_front:.1f}m ({authority})"
        )

    # Rear setback (top)
    sb_rear = cfg.setback_rear
    if sb_rear > 0:
        y_plot_top = oy + plot_py
        y_bldg_top = by + bh
        mid_x = ox + plot_px / 2
        c.setDash(3, 2)
        c.line(mid_x, y_bldg_top, mid_x, y_plot_top)
        c.setDash()
        c.drawString(ox + 4, (y_bldg_top + y_plot_top) / 2, f"R.S. {sb_rear:.1f}m")

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
    right_x: float,
    bottom_y: float,
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
    authority = _MUNICIPALITY_LABELS.get(owner.municipality, owner.municipality.upper())

    # Title block occupies bottom quarter of the page
    tb_h = page_h * 0.27

    # Background
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(0, tb_h, page_w, page_h - tb_h, fill=1, stroke=0)

    # Page header
    c.setFillColor(HexColor("#000000"))
    c.rect(0, page_h - 36, page_w, 36, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(page_w / 2, page_h - 24, "SECTION AA — RESIDENTIAL BUILDING")

    # Convention-faithful section through the staircase
    sd = derive_section(layout, cfg)
    render_section_view(
        c, sd, (MARGIN, tb_h + 10, page_w - 2 * MARGIN, page_h - 36 - tb_h - 20)
    )

    # Professional title block
    _draw_professional_title_block(c, layout, cfg, owner, authority, page_w, tb_h)


def _draw_elevation_and_title_block(
    c: canvas.Canvas,
    layout: Layout,
    cfg: PlotConfig,
    owner: OwnerInfo,
) -> None:
    page_w, page_h = A4
    authority = _MUNICIPALITY_LABELS.get(owner.municipality, owner.municipality.upper())

    tb_h = page_h * 0.27

    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(0, tb_h, page_w, page_h - tb_h, fill=1, stroke=0)

    c.setFillColor(HexColor("#000000"))
    c.rect(0, page_h - 36, page_w, 36, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(
        page_w / 2, page_h - 24, "FRONT ELEVATION — RESIDENTIAL BUILDING"
    )

    ed = derive_elevation(layout, cfg)
    render_elevation_view(
        c, ed, (MARGIN, tb_h + 10, page_w - 2 * MARGIN, page_h - 36 - tb_h - 20)
    )

    _draw_professional_title_block(c, layout, cfg, owner, authority, page_w, tb_h)


def _draw_professional_title_block(
    c: canvas.Canvas,
    layout: Layout,
    cfg: PlotConfig,
    owner: OwnerInfo,
    authority: str,
    page_w: float,
    tb_h: float,
) -> None:
    """Full professional title block for municipality submission (shared look)."""
    gf = sum(r.area for r in layout.ground_floor.rooms)
    ff = sum(r.area for r in layout.first_floor.rooms)
    fields = [
        ("OWNER", owner.owner_name),
        ("SURVEY NO.", owner.survey_number),
        ("ULB", f"{owner.municipality} ({authority})"),
        ("SITE AREA", f"{cfg.plot_width * cfg.plot_length:.1f} SQM"),
        ("BUILT-UP GF", f"{gf:.1f} SQM"),
        ("BUILT-UP FF", f"{ff:.1f} SQM"),
        ("ENGINEER", owner.engineer_name),
        ("LICENSE NO.", owner.license_number),
        ("SCALE", "1:100"),
        ("LAYOUT", f"{layout.id} - {layout.name}"),
        ("DATE", date.today().strftime("%d/%m/%Y")),
    ]
    subtitle_lines = [
        f"Residential Building at {owner.locality}, {owner.municipality}",
    ]
    draw_title_block(
        c,
        page_w,
        tb_h,
        fields,
        subtitle_lines=subtitle_lines,
        signature=True,
        footer=(
            "Generated by PlanForge · NBC 2016 Compliant · "
            "For Municipality Submission Only"
        ),
    )


# ── Shared drawing helpers ────────────────────────────────────────────────────


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
    """Compact title block for floor plan pages (shared look)."""
    scale_ratio = 100  # Fixed 1:100

    gf_sqft = round(sum(r.area for r in layout.ground_floor.rooms) * 10.764)
    ff_sqft = round(sum(r.area for r in layout.first_floor.rooms) * 10.764)
    total_sqft = gf_sqft + ff_sqft
    far_allowed = _FAR_LIMITS.get(authority, 2.0)
    plot_area = cfg.plot_width * cfg.plot_length
    if far <= 0.0 and plot_area:
        far = (
            sum(r.area for r in layout.ground_floor.rooms)
            + sum(r.area for r in layout.first_floor.rooms)
        ) / plot_area

    fields = [
        ("PROJECT", owner.locality),
        ("LAYOUT", f"{layout.id} - {layout.name}"),
        ("FLOOR", floor_label),
        ("PLOT", f"{cfg.plot_width}x{cfg.plot_length}m"),
        ("SURVEY NO.", owner.survey_number),
        ("SCALE", f"1:{scale_ratio}"),
        ("AUTHORITY", authority),
        ("TOTAL AREA", f"{total_sqft} SQFT"),
        ("FAR", f"{far:.2f}/{far_allowed:.2f}"),
        ("DATE", date.today().strftime("%d/%m/%Y")),
        ("ENGINEER", owner.engineer_name or "-"),
    ]
    subtitle_lines = [
        f"Owner: {owner.owner_name}  |  Plot No.: {owner.survey_number}  |  "
        f"{owner.locality}, {owner.municipality}",
        f"Prepared by: {owner.engineer_name}  |  Lic. No.: {owner.license_number}"
        f"  |  {authority} Submission",
    ]
    draw_title_block(c, page_w, TITLE_H, fields, subtitle_lines=subtitle_lines)
