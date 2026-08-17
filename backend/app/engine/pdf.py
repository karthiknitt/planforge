from __future__ import annotations

import math
from datetime import date
from io import BytesIO

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.cad_primitives import metres_to_ftin
from app.engine.geometry import buildable_polygon
from app.engine.models import FloorPlan, Layout, PlotConfig, Room
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

# ---------------------------------------------------------------------------
# Internal CAD drawing helpers (ReportLab, not ezdxf)
# ---------------------------------------------------------------------------


def _pdf_draw_double_line_wall(
    c: canvas.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
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
    px = -uy  # perpendicular
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
            x1 + t0 * dx + h * px,
            y1 + t0 * dy + h * py,
            x1 + t1 * dx + h * px,
            y1 + t1 * dy + h * py,
        )
        # Inner line
        c.line(
            x1 + t0 * dx - h * px,
            y1 + t0 * dy - h * py,
            x1 + t1 * dx - h * px,
            y1 + t1 * dy - h * py,
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
    hinge_x: float,
    hinge_y: float,
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
        leaf_end_x = hinge_x + door_px
        leaf_end_y = hinge_y
        c.line(hinge_x, hinge_y, leaf_end_x, leaf_end_y)
        # Quarter-circle arc centered at hinge, radius = door width
        # Arc from 0° to 90° (counterclockwise into room)
        if swing_into_room:
            c.arc(
                hinge_x, hinge_y, hinge_x + door_px * 2, hinge_y + door_px * 2, 90, 90
            )
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
            c.arc(
                hinge_x - door_px * 2, hinge_y - door_px * 2, hinge_x, hinge_y, 270, 90
            )


# ── Colour palette (fill, stroke) ────────────────────────────────────────────
PALETTE: dict[str, tuple[str, str]] = {
    "living": ("#FFFFFF", "#000000"),
    "bedroom": ("#FFFFFF", "#000000"),
    "kitchen": ("#FFFFFF", "#000000"),
    "toilet": ("#FFFFFF", "#000000"),
    "staircase": ("#FFFFFF", "#000000"),
    "parking": ("#FFFFFF", "#000000"),
    "utility": ("#FFFFFF", "#000000"),
    "pooja": ("#FFFFFF", "#000000"),
    "study": ("#FFFFFF", "#000000"),
    "balcony": ("#FFFFFF", "#000000"),
    "dining": ("#FFFFFF", "#000000"),
    "foyer": ("#FFFFFF", "#000000"),
    "courtyard": ("#FFFFFF", "#000000"),
    "wardrobe": ("#FFFFFF", "#000000"),
}

# ── Page constants (points) ───────────────────────────────────────────────────
TITLE_H = 90  # title block height (larger to accommodate area schedule)
MARGIN = 52  # page margins (larger for chain dimension zone)
ROAD_H = 18  # road strip height
ROAD_GAP = 4  # gap between road strip top and plot boundary bottom
TOP_PAD = 30  # padding above plot for north arrow / scale bar
EXT_LW = 2.0  # external wall lineweight (pt)
INT_LW = 1.0  # internal wall lineweight (pt)
DIM_LW = 0.5  # dimension line lineweight (pt)
WIN_LW = 0.75  # window line lineweight (pt)
MIN_DIM_SPAN = 0.5  # metres — filter out wall-thickness micro-gaps from chain dims

# ── Schedule-table column (points) ────────────────────────────────────────────
# The AREA / OPENINGS schedule tables live in a reserved right-hand column,
# stacked just above the title block.  The plot is scaled + centred in the
# remaining left region so it never overlaps the tables for any aspect ratio.
SCHED_W = 148  # width of both schedule tables (they share this width)
SCHED_PAD = 12  # gap between the plot region and the schedule column
SCHED_RESERVE = SCHED_W + SCHED_PAD  # width withheld from the plot's available width
SCHED_ROW_H = 9.0  # schedule table row height
SCHED_BAND_H = 11.0  # schedule table title-band height


def _centered_plot_oy(
    page_h: float,
    plot_py: float,
    *,
    title_h: float,
    margin: float,
    road_below: float = 0.0,
    road_above: float = 0.0,
) -> float:
    """Return ``oy`` (plot-origin Y in points) that vertically centres the
    plot — together with any road strip drawn directly below/above it — in the
    band between the title block top (``title_h``) and the top page margin.

    ``road_below`` / ``road_above`` are the total heights (strip + gap) the road
    adds under / over the plot, so the whole plot+road group centres as a unit.
    """
    band_bottom = title_h
    band_top = page_h - margin
    group_h = plot_py + road_below + road_above
    slack = max(0.0, (band_top - band_bottom - group_h) / 2)
    return band_bottom + road_below + slack


def _area_schedule_height(floor_plan: FloorPlan) -> float:
    """Height (points) of the AREA SCHEDULE table for ``floor_plan``.

    Mirrors the row math in :func:`_draw_area_schedule_table` so callers can
    stack tables without first drawing them."""
    return SCHED_BAND_H + SCHED_ROW_H * (len(floor_plan.rooms) + 2)


def _openings_schedule_height(rows: list[tuple]) -> float:
    """Height (points) of the SCHEDULE OF OPENINGS table for ``rows``.

    Mirrors the row math in :func:`_draw_openings_schedule_table`."""
    return SCHED_BAND_H + SCHED_ROW_H * (len(rows) + 1)


def _schedule_column_x(page_w: float, margin: float) -> float:
    """X of the left edge of the reserved schedule column."""
    return page_w - margin - SCHED_W


_FLOOR_LABELS = {-1: "Basement", 0: "Ground Floor", 1: "First Floor", 2: "Second Floor"}

_FLOOR_NUM_BY_KEY = {
    "basement_floor": -1,
    "ground_floor": 0,
    "first_floor": 1,
    "second_floor": 2,
}


def _floor_label(floor_plan: FloorPlan) -> str:
    """Display label for a floor number (Basement/Ground/First/Second Floor)."""
    return _FLOOR_LABELS.get(floor_plan.floor, f"Floor {floor_plan.floor}")


def ordered_floors(layout: Layout) -> list[FloorPlan]:
    """All populated floors in build order (basement first)."""
    return [
        fp
        for fp in (
            layout.basement_floor,
            layout.ground_floor,
            layout.first_floor,
            layout.second_floor,
        )
        if fp is not None
    ]


def arch_page_index(layout: Layout, floor_key: str) -> int:
    """Architectural-page index (0-based) of ``floor_key`` in render_pdf()'s page order."""
    want = _FLOOR_NUM_BY_KEY.get(floor_key)
    if want is None:
        return 0
    return next(
        (i for i, fp in enumerate(ordered_floors(layout)) if fp.floor == want),
        0,
    )


def _has_floor_above(layout: Layout, floor_plan: FloorPlan) -> bool:
    """True if any populated floor (with rooms) sits above ``floor_plan``."""
    floors = {
        fp.floor: fp
        for fp in (
            layout.basement_floor,
            layout.ground_floor,
            layout.first_floor,
            layout.second_floor,
        )
        if fp
    }
    return any(f > floor_plan.floor and fp.rooms for f, fp in floors.items())


# ── Public API ────────────────────────────────────────────────────────────────


def render_pdf(
    project_name: str,
    layout: Layout,
    cfg: PlotConfig,
    num_bedrooms: int,
    annotations: dict | None = None,
    structural_design: dict | None = None,
    watermark_preliminary: bool = False,
) -> bytes:
    """Return raw PDF bytes.

    Page order:
      1..N. Architectural pages, one per populated floor, basement first
      N+1..2N. Structural pages (beam & column layout), same order
      then Section A-A
      then Front Elevation

    ``structural_design`` (optional): the persisted StructuralDesign surface
    -- {status, revision_id, changelog, structapi: {data, disclaimer}} --
    from ``GET /structural/design``. When present, structural pages draw
    designed member sizes + schedule tables instead of the typ. defaults,
    and the architectural watermark is suppressed (a design supersedes
    "preliminary"). When absent and ``watermark_preliminary`` is True, the
    architectural pages carry a "PRELIMINARY — FOR PLANNING ONLY" watermark.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    show_watermark = watermark_preliminary and structural_design is None

    # ── Architectural pages ────────────────────────────────────────────────────
    for floor_plan in ordered_floors(layout):
        _draw_floor_projected(
            c,
            floor_plan,
            layout,
            cfg,
            project_name,
            num_bedrooms,
            _floor_label(floor_plan),
            annotations=annotations,
            watermark_preliminary=show_watermark,
        )
        c.showPage()

    # ── Structural pages ───────────────────────────────────────────────────────
    for floor_plan in ordered_floors(layout):
        _draw_structural_floor(
            c,
            floor_plan,
            layout,
            cfg,
            project_name,
            num_bedrooms,
            _floor_label(floor_plan),
            structural_design=structural_design,
        )
        c.showPage()

    # ── Section & elevation pages ─────────────────────────────────────────────
    page_w, page_h = A4
    region = (MARGIN, TITLE_H + 30, page_w - 2 * MARGIN, page_h - TITLE_H - 60)

    sd = derive_section(layout, cfg, structural_design=structural_design)
    sd_scale = render_section_view(c, sd, region)
    _draw_title_block(
        c,
        project_name,
        layout.id,
        layout.name,
        sd.title,
        cfg,
        num_bedrooms,
        sd_scale,
        page_w,
    )
    c.showPage()

    ed = derive_elevation(layout, cfg)
    ed_scale = render_elevation_view(c, ed, region)
    _draw_title_block(
        c,
        project_name,
        layout.id,
        layout.name,
        ed.title,
        cfg,
        num_bedrooms,
        ed_scale,
        page_w,
    )
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

    offset_x = MARGIN + (avail_w - plot_px) / 2
    offset_y = TITLE_H + MARGIN + ROAD_H + ROAD_GAP

    return scale, offset_x, offset_y, plot_px, plot_py


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

    LEAF_LW = INT_LW  # door leaf = same weight as internal wall
    ARC_LW = 0.4  # door swing arc = thin pen (architectural convention)

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


def _draw_annotations(
    c: canvas.Canvas, rooms, annotations: dict, scale: float, ox: float, oy: float
) -> None:
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
        raw_x = sorted(
            {round(r.x, 3) for r in rooms} | {round(r.x + r.width, 3) for r in rooms}
        )
        raw_y = sorted(
            {round(r.y, 3) for r in rooms} | {round(r.y + r.depth, 3) for r in rooms}
        )
    else:
        raw_x = [0.0, cfg.plot_width]
        raw_y = [0.0, cfg.plot_length]

    x_pos = _filter_dim_positions(raw_x)
    y_pos = _filter_dim_positions(raw_y)

    # ── BOTTOM HORIZONTAL CHAIN ───────────────────────────────────────────────
    # MARGIN zone: y = TITLE_H to y = TITLE_H + MARGIN (road strip)
    # Inner row: bar at TITLE_H + MARGIN - 12 (just below road strip start)
    # Outer row: bar at TITLE_H + MARGIN - 36 (middle of margin)
    inner_y = TITLE_H + MARGIN - 12  # ≈ 130
    outer_y = TITLE_H + MARGIN - 36  # ≈ 106

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
    c.line(ox - 4, outer_y - 4, ox + 4, outer_y + 4)  # 45° tick at start
    c.line(
        ox + plot_px - 4, outer_y - 4, ox + plot_px + 4, outer_y + 4
    )  # 45° tick at end
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(ox + plot_px / 2, outer_y + 8, metres_to_ftin(cfg.plot_width))

    # ── RIGHT VERTICAL CHAIN ──────────────────────────────────────────────────
    right_x = ox + plot_px
    inner_x = right_x + 30  # wider gap from building edge for clean dimension clearance
    outer_x = right_x + 54  # proportionally wider for outer overall dim

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
    c.line(outer_x - 4, oy - 4, outer_x + 4, oy + 4)  # 45° tick at bottom
    c.line(
        outer_x - 4, oy + plot_py - 4, outer_x + 4, oy + plot_py + 4
    )  # 45° tick at top
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


def _draw_scale_bar(
    c: canvas.Canvas,
    x: float,
    y: float,
    scale: float,
    denom: int | None = None,
    metres: int = 4,
) -> None:
    """IS-style graphic scale bar: alternating filled 1 m segments with
    0/1M/2M… tick labels and the numeric scale above. Shared by every page
    of both the standard and approval PDFs."""
    seg = scale  # 1 model-metre in points
    h = 4.0
    c.setLineWidth(0.6)
    c.setStrokeColor(HexColor("#000000"))
    for i in range(metres):
        c.setFillColor(HexColor("#000000") if i % 2 == 0 else HexColor("#FFFFFF"))
        c.rect(x + i * seg, y, seg, h, fill=1, stroke=1)
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 5)
    for i in range(metres + 1):
        c.drawCentredString(x + i * seg, y + h + 2, "0" if i == 0 else f"{i}M")
    if denom:
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(x + metres * seg / 2, y + h + 9, f"SCALE 1:{denom}")


def _draw_area_schedule_table(
    c: canvas.Canvas, floor_plan: FloorPlan, x: float, y_top: float
) -> float:
    """Bordered ROOM | AREA (SQFT) table with a TOTAL row (reference-drawing
    convention, replaces the old inline pipe-separated text). Returns height."""
    # Voids (`Room.is_void`) are a hole in the slab, not floor area — they get
    # their own "OPEN TO BELOW" annotation via `_draw_voids`, so they must not
    # double up as an area-schedule row or add their footprint to TOTAL.
    rows = [
        (r.name.upper(), f"{round(r.area * 10.764)}")
        for r in sorted(floor_plan.rooms, key=lambda r: r.id)
        if not r.is_void
    ]
    total = round(sum(r.area for r in floor_plan.rooms if not r.is_void) * 10.764)
    w_room, w_area = 96, 52
    w = w_room + w_area
    row_h, band_h = SCHED_ROW_H, SCHED_BAND_H
    height = _area_schedule_height(floor_plan)
    y = y_top - height

    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.7)
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(x, y, w, height, fill=1, stroke=1)
    # Title band
    c.setFillColor(HexColor("#000000"))
    c.rect(x, y_top - band_h, w, band_h, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(x + w / 2, y_top - band_h + 3.5, "AREA SCHEDULE")
    # Column headers
    hdr_y = y_top - band_h - row_h
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 5.5)
    c.drawString(x + 3, hdr_y + 2.5, "ROOM")
    c.drawRightString(x + w - 3, hdr_y + 2.5, "AREA (SQFT)")
    c.setLineWidth(0.4)
    c.line(x, hdr_y, x + w, hdr_y)
    c.line(x + w_room, y, x + w_room, y_top - band_h)
    # Rows
    c.setFont("Helvetica", 5.5)
    for i, (name, area) in enumerate(rows):
        ry = hdr_y - (i + 1) * row_h
        c.drawString(x + 3, ry + 2.5, name)
        c.drawRightString(x + w - 3, ry + 2.5, area)
        c.setLineWidth(0.25)
        c.line(x, ry, x + w, ry)
    # Total row
    ty = hdr_y - (len(rows) + 1) * row_h
    c.setFont("Helvetica-Bold", 5.5)
    c.drawString(x + 3, ty + 2.5, "TOTAL AREA")
    c.drawRightString(x + w - 3, ty + 2.5, str(total))
    c.setLineWidth(0.7)
    c.line(x, ty + row_h, x + w, ty + row_h)
    return height


_OPENING_HEIGHT_MM = {"door": 2100, "window": 1200, "ventilator": 600}
_OPENING_PREFIX = {"door": "D", "window": "W", "ventilator": "V"}


def _opening_marks(drawing) -> tuple[dict[int, str], list[tuple]]:
    """IS 962 practice: same-kind, same-width openings share one mark
    (D1 = all 900 mm doors, D2 = 750 mm wet-room doors, W1, V1 …).
    The main entrance door is tagged "MD" and kept out of the D-series.
    Returns ({opening index: mark}, schedule rows (mark, type, w_mm, h_mm, nos))."""
    groups: dict[tuple[str, int], list[int]] = {}
    main_idx: list[int] = []
    for i, o in enumerate(drawing.openings):
        if getattr(o, "is_main", False):
            main_idx.append(i)
            continue
        # snap to 50 mm modules so near-identical computed widths (1180 vs
        # 1200) share one mark, as they would on a real drawing
        groups.setdefault((o.kind, round(o.width * 1000 / 50) * 50), []).append(i)
    counters = dict.fromkeys(_OPENING_PREFIX, 0)
    marks: dict[int, str] = {}
    rows: list[tuple] = []
    for (kind, width_mm), idxs in sorted(
        groups.items(), key=lambda kv: (kv[0][0], -kv[0][1])
    ):
        counters[kind] += 1
        mark = f"{_OPENING_PREFIX[kind]}{counters[kind]}"
        for i in idxs:
            marks[i] = mark
        rows.append((mark, kind.upper(), width_mm, _OPENING_HEIGHT_MM[kind], len(idxs)))
    if main_idx:
        width_mm = round(drawing.openings[main_idx[0]].width * 1000 / 50) * 50
        for i in main_idx:
            marks[i] = "MD"
        rows.insert(
            0, ("MD", "MAIN DOOR", width_mm, _OPENING_HEIGHT_MM["door"], len(main_idx))
        )
    return marks, rows


def _draw_opening_tags(
    c: canvas.Canvas, drawing, marks: dict[int, str], s: float, ox: float, oy: float
) -> None:
    """Tiny D1/W1/V1 tags beside each opening, offset away from the building
    centre so window/ventilator tags land in the (empty) setback strip."""
    bx1, by1, bx2, by2 = drawing.bounds
    ccx, ccy = (bx1 + bx2) / 2, (by1 + by2) / 2
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 4.5)
    for i, o in enumerate(drawing.openings):
        off = o.wall_thickness * s / 2 + 3.5
        if o.is_horizontal:
            yp = oy + o.cy * s + (off if o.cy >= ccy else -off - 4)
            c.drawCentredString(ox + o.cx * s, yp, marks[i])
        else:
            xp = ox + o.cx * s + (off + 1.5 if o.cx >= ccx else -off - 1.5)
            c.saveState()
            c.translate(xp, oy + o.cy * s)
            c.rotate(90)
            c.drawCentredString(0, -1.5, marks[i])
            c.restoreState()


def _draw_openings_schedule_table(
    c: canvas.Canvas, rows: list[tuple], x: float, y_top: float
) -> float:
    """SCHEDULE OF OPENINGS table (municipal submission requirement).
    Same visual style as the area schedule table. Returns height."""
    col_ws = (22, 44, 28, 28, 26)
    headers = ("MARK", "TYPE", "W (MM)", "H (MM)", "NOS")
    w = sum(col_ws)
    row_h, band_h = SCHED_ROW_H, SCHED_BAND_H
    height = _openings_schedule_height(rows)
    y = y_top - height

    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.7)
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(x, y, w, height, fill=1, stroke=1)
    c.setFillColor(HexColor("#000000"))
    c.rect(x, y_top - band_h, w, band_h, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(x + w / 2, y_top - band_h + 3.5, "SCHEDULE OF OPENINGS")

    hdr_y = y_top - band_h - row_h
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 5)
    cx_acc = x
    for cw, hdr in zip(col_ws, headers):
        c.drawCentredString(cx_acc + cw / 2, hdr_y + 2.5, hdr)
        cx_acc += cw
    c.setLineWidth(0.4)
    c.line(x, hdr_y, x + w, hdr_y)
    cx_acc = x
    for cw in col_ws[:-1]:
        cx_acc += cw
        c.line(cx_acc, y, cx_acc, y_top - band_h)

    c.setFont("Helvetica", 5)
    for i, row in enumerate(rows):
        ry = hdr_y - (i + 1) * row_h
        cx_acc = x
        for cw, val in zip(col_ws, row):
            c.drawCentredString(cx_acc + cw / 2, ry + 2.5, str(val))
            cx_acc += cw
        c.setLineWidth(0.25)
        c.line(x, ry, x + w, ry)
    return height


def _draw_compound_wall(
    c: canvas.Canvas, cfg: PlotConfig, ox: float, oy: float, s: float
) -> None:
    """Boundary wall ring with a road-side gate gap.

    Strokes the same centrelines the DXF path buffers into a poché polygon
    (`app.engine.geometry.compound_wall_segments`) — this is a thin ReportLab
    wrapper, not a second derivation of the wall/gate geometry. Unlike the DXF
    path this doesn't align the gate to the main-entrance x position (no door
    position is passed in); it's always centred on the road-side edge.
    """
    from app.engine.geometry import COMPOUND_WALL_THICKNESS_M, compound_wall_segments

    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(COMPOUND_WALL_THICKNESS_M * s)
    for x1, y1, x2, y2 in compound_wall_segments(cfg):
        c.line(ox + x1 * s, oy + y1 * s, ox + x2 * s, oy + y2 * s)


def _draw_setback_callouts(
    c: canvas.Canvas,
    cfg: PlotConfig,
    bounds: tuple[float, float, float, float],
    s: float,
    ox: float,
    oy: float,
) -> None:
    """Text callouts ("1.5M FRONT SETBACK") centred in each setback strip."""
    from app.engine.plan_geometry import setback_callouts

    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 5.5)
    for text, xm, ym, rotated in setback_callouts(cfg, bounds):
        xp, yp = ox + xm * s, oy + ym * s
        if rotated:
            c.saveState()
            c.translate(xp, yp)
            c.rotate(90)
            c.drawCentredString(0, 0, text)
            c.restoreState()
        else:
            c.drawCentredString(xp, yp - 2, text)


def _draw_preliminary_watermark(c: canvas.Canvas, page_w: float, page_h: float) -> None:
    """Subtle diagonal watermark for architectural pages that have no
    designed structural set backing them yet."""
    c.saveState()
    c.translate(page_w / 2, page_h / 2)
    c.rotate(35)
    c.setFillColor(HexColor("#C8C8C8"))
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(0, 0, "PRELIMINARY — FOR PLANNING ONLY")
    c.restoreState()


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


def _cluster(vals: list[float], tol: float = 0.3) -> list[float]:
    groups: list[list[float]] = []
    for v in sorted(vals):
        if groups and v - groups[-1][-1] < tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def _column_class(idx: int, xs_len: int, jdx: int, ys_len: int) -> str:
    """corner/edge/interior classification matching structapi's own grid
    classification (extreme index on both axes = corner, one axis = edge)."""
    x_extreme = idx in (0, xs_len - 1)
    y_extreme = jdx in (0, ys_len - 1)
    if x_extreme and y_extreme:
        return "corner"
    if x_extreme or y_extreme:
        return "edge"
    return "interior"


def _nearest_index(vals: list[float], v: float) -> int:
    return min(range(len(vals)), key=lambda i: abs(vals[i] - v))


def _draw_column_schedule_table(
    c: canvas.Canvas, columns_data: dict, x: float, y_top: float
) -> float:
    """COLUMN SCHEDULE: class -> size + bars, from structapi ``data.columns``."""
    col_ws = (44, 44, 60)
    headers = ("CLASS", "SIZE (MM)", "BARS")
    rows = [
        (cls.upper(), f"{int(v['b_mm'])}x{int(v['D_mm'])}", v.get("bars", "—"))
        for cls, v in sorted(columns_data.items())
    ]
    return _draw_generic_schedule_table(
        c, "COLUMN SCHEDULE", headers, col_ws, rows, x, y_top
    )


def _draw_beam_schedule_table(
    c: canvas.Canvas, beams_data: dict, x: float, y_top: float
) -> float:
    """BEAM SCHEDULE: unique beam design entries -> size + span/tributary,
    from structapi ``data.beams`` (worst-span-governed, per direction)."""
    col_ws = (30, 44, 40, 34)
    headers = ("DIR", "SIZE (MM)", "SPAN (M)", "SPANS")
    rows = [
        (
            key.split("-")[0].upper(),
            f"{int(v['b_mm'])}x{int(v['D_mm'])}",
            f"{v.get('span_m', 0):.1f}",
            str(v.get("n_spans", "—")),
        )
        for key, v in sorted(beams_data.items())
    ]
    return _draw_generic_schedule_table(
        c, "BEAM SCHEDULE", headers, col_ws, rows, x, y_top
    )


def _generic_schedule_height(n_rows: int) -> float:
    return SCHED_BAND_H + SCHED_ROW_H * (n_rows + 1)


def _draw_generic_schedule_table(
    c: canvas.Canvas,
    title: str,
    headers: tuple[str, ...],
    col_ws: tuple[float, ...],
    rows: list[tuple],
    x: float,
    y_top: float,
) -> float:
    """Bordered schedule table, same visual style as the openings/area
    schedules (title band + header row + data rows). Returns height."""
    w = sum(col_ws)
    row_h, band_h = SCHED_ROW_H, SCHED_BAND_H
    height = _generic_schedule_height(len(rows))
    y = y_top - height

    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.7)
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(x, y, w, height, fill=1, stroke=1)
    c.setFillColor(HexColor("#000000"))
    c.rect(x, y_top - band_h, w, band_h, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(x + w / 2, y_top - band_h + 3.5, title)

    hdr_y = y_top - band_h - row_h
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 5)
    cx_acc = x
    for cw, hdr in zip(col_ws, headers):
        c.drawCentredString(cx_acc + cw / 2, hdr_y + 2.5, hdr)
        cx_acc += cw
    c.setLineWidth(0.4)
    c.line(x, hdr_y, x + w, hdr_y)
    cx_acc = x
    for cw in col_ws[:-1]:
        cx_acc += cw
        c.line(cx_acc, y, cx_acc, y_top - band_h)

    c.setFont("Helvetica", 5)
    for i, row in enumerate(rows):
        ry = hdr_y - (i + 1) * row_h
        cx_acc = x
        for cw, val in zip(col_ws, row):
            c.drawCentredString(cx_acc + cw / 2, ry + 2.5, str(val))
            cx_acc += cw
        c.setLineWidth(0.25)
        c.line(x, ry, x + w, ry)
    return height


def _draw_structural_floor(
    c: canvas.Canvas,
    floor_plan: FloorPlan,
    layout: Layout,
    cfg: PlotConfig,
    project_name: str,
    num_bedrooms: int,
    floor_label: str,
    structural_design: dict | None = None,
) -> tuple[float, float, float, int]:
    """Beam & column layout projected from the canonical FloorDrawing — the
    same scale, grid derivation (wall centrelines), and page furniture as
    the architectural pages, so all four sheets read as one set.

    Returns the computed ``(ox, oy, s, denom)`` frame (plot-origin X/Y in
    points, scale, scale denominator) so callers that need to overlay
    additional content in the same coordinate space (e.g.
    `structural_drawing_set.render_roof_beam_slab_plan`) don't have to
    reimplement this scale/offset math themselves — this function is the
    single source of truth for it."""
    from app.engine.plan_geometry import build_floor_drawing

    page_w, page_h = A4
    # Same scale + centring as the architectural pages (incl. the reserved
    # schedule column) so all four sheets read as one set.
    s, denom = _standard_scale(cfg, page_w, page_h, reserve_w=SCHED_RESERVE)
    plot_px, plot_py = cfg.plot_width * s, cfg.plot_length * s
    ox = MARGIN + (page_w - 2 * MARGIN - SCHED_RESERVE - plot_px) / 2
    oy = _centered_plot_oy(
        page_h, plot_py, title_h=TITLE_H, margin=MARGIN, road_below=ROAD_H + ROAD_GAP
    )

    # Road strip + page label — identical furniture to architectural pages
    road_y = oy - ROAD_GAP - ROAD_H
    c.setFillColor(HexColor("#DDDDDD"))
    c.rect(ox, road_y, plot_px, ROAD_H, fill=1, stroke=0)
    road_side_name = {"S": "SOUTH", "N": "NORTH", "E": "EAST", "W": "WEST"}.get(
        cfg.road_side, ""
    )
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(
        ox + plot_px / 2,
        road_y + ROAD_H - 7,
        f"{floor_label.upper()} — BEAM/COLUMN LAYOUT",
    )
    c.setFillColor(HexColor("#444444"))
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(
        ox + plot_px / 2,
        road_y + 3,
        f"ROAD  ({road_side_name})" if road_side_name else "ROAD",
    )

    # Plot boundary (dashed) — same as architectural pages
    c.setDash(5, 3)
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(0.5)
    c.rect(ox, oy, plot_px, plot_py, fill=0, stroke=1)
    c.setDash()

    if not floor_plan.rooms:
        _draw_title_block(
            c,
            project_name,
            layout.id,
            layout.name,
            f"{floor_label} — Beam/Column Layout",
            cfg,
            num_bedrooms,
            s,
            page_w,
            scale_denom=denom,
        )
        return ox, oy, s, denom

    drawing = build_floor_drawing(floor_plan, cfg)
    bx1, by1, bx2, by2 = drawing.bounds

    # Room outlines for context — light gray
    c.setStrokeColor(HexColor("#CCCCCC"))
    c.setLineWidth(0.5)
    for room in floor_plan.rooms:
        c.rect(
            ox + room.x * s,
            oy + room.y * s,
            room.width * s,
            room.depth * s,
            fill=0,
            stroke=1,
        )

    # Structural grid at wall CENTRELINES, clustered so closely spaced lines
    # share one grid line and one bubble (fixes the overlapping-bubble mess
    # the raw room-edge grid produced). _cluster is module-level (shared
    # with app.engine.footing_placement).
    v_xs = _cluster([w.x1 for w in drawing.walls if abs(w.x1 - w.x2) < 1e-9])
    h_ys = _cluster([w.y1 for w in drawing.walls if abs(w.y1 - w.y2) < 1e-9])

    bx_lo, bx_hi = ox + bx1 * s, ox + bx2 * s
    by_lo, by_hi = oy + by1 * s, oy + by2 * s
    ext = 10  # pt extension past building
    bubble_r = 6

    c.setStrokeColor(HexColor("#808080"))
    c.setLineWidth(0.4)
    c.setDash(4, 3)
    for x in v_xs:
        px = ox + x * s
        c.line(px, by_lo - ext - 2, px, by_hi + ext + 2)
    for y in h_ys:
        py = oy + y * s
        c.line(bx_lo - ext - 2, py, bx_hi + ext + 2, py)
    c.setDash()

    import string as _string

    def _bubble(px: float, py: float, lbl: str) -> None:
        c.setStrokeColor(HexColor("#555555"))
        c.setFillColor(HexColor("#FFFFFF"))
        c.setLineWidth(0.6)
        c.circle(px, py, bubble_r, fill=1, stroke=1)
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(px, py - 2.2, lbl)

    for i, x in enumerate(v_xs):
        px = ox + x * s
        for by_b in (by_lo - ext - bubble_r - 4, by_hi + ext + bubble_r + 4):
            _bubble(px, by_b, _string.ascii_uppercase[i % 26])
    for j, y in enumerate(h_ys):
        py = oy + y * s
        for bx_b in (bx_lo - ext - bubble_r - 4, bx_hi + ext + bubble_r + 4):
            _bubble(bx_b, py, str(j + 1))

    # Beams: connect canonical junction columns sharing a grid ordinate
    cols = drawing.columns
    col_groups_x: dict[float, list] = {}
    col_groups_y: dict[float, list] = {}
    for col in cols:
        col_groups_x.setdefault(round(col.cx, 2), []).append(col)
        col_groups_y.setdefault(round(col.cy, 2), []).append(col)
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(1.3)
    for group, key in ((col_groups_x, "cy"), (col_groups_y, "cx")):
        for col_list in group.values():
            if len(col_list) < 2:
                continue
            ordered = sorted(col_list, key=lambda cc: getattr(cc, key))
            for a, b in zip(ordered, ordered[1:]):
                c.line(ox + a.cx * s, oy + a.cy * s, ox + b.cx * s, oy + b.cy * s)

    # Designed column sizes from the persisted structural design (when one
    # exists): classify each drawn column corner/edge/interior by its grid
    # position and size it to structapi's data.columns[class].b_mm/D_mm.
    design_data = None
    if structural_design and structural_design.get("status") not in (None, "stale"):
        design_data = (structural_design.get("structapi") or {}).get("data") or {}
    columns_data = (design_data or {}).get("columns") or {}
    col_class_by_idx: dict[int, str] = {}
    if columns_data and v_xs and h_ys:
        for idx, col in enumerate(cols):
            ci = _nearest_index(v_xs, col.cx)
            cj = _nearest_index(h_ys, col.cy)
            col_class_by_idx[idx] = _column_class(ci, len(v_xs), cj, len(h_ys))

    # Column markers with side tags (tags beside the marker, not inside —
    # a 300 mm square at 1:100 is too small for legible inset text)
    default_col_sz = max(5.0, 0.3 * s)
    c.setFillColor(HexColor("#000000"))
    for idx, col in enumerate(cols):
        cls = col_class_by_idx.get(idx)
        if cls and cls in columns_data:
            b_mm, d_mm = columns_data[cls]["b_mm"], columns_data[cls]["D_mm"]
            col_w, col_h = max(3.0, b_mm / 1000 * s), max(3.0, d_mm / 1000 * s)
        else:
            col_w = col_h = default_col_sz
        c.rect(
            ox + col.cx * s - col_w / 2,
            oy + col.cy * s - col_h / 2,
            col_w,
            col_h,
            fill=1,
            stroke=0,
        )
    c.setFont("Helvetica", 4.5)
    placed_tags: list[tuple[float, float]] = []
    for idx, col in enumerate(cols):
        cls = col_class_by_idx.get(idx)
        tag = f"C{idx + 1}" if not cls else f"C{idx + 1} ({cls[0].upper()})"
        tx = ox + col.cx * s + default_col_sz / 2 + 1.5
        ty = oy + col.cy * s + default_col_sz / 2 - 2
        if any(abs(tx - px) < 16 and abs(ty - py) < 7 for px, py in placed_tags):
            # neighbour tag would overlap: drop to the lower-left corner
            tx = ox + col.cx * s - default_col_sz / 2 - 12
            ty = oy + col.cy * s - default_col_sz / 2 - 3
        placed_tags.append((tx, ty))
        c.drawString(tx, ty, tag)

    # Structural notes — same top-left slot the area schedule table uses on
    # the architectural pages
    if design_data:
        beams_typ = design_data.get("beams") or {}
        beam_D_typ = max((v["D_mm"] for v in beams_typ.values()), default=380)
        notes = [
            "STRUCTURAL NOTES (IS-CODE DESIGNED):",
            f"1. COLUMNS SIZED PER DESIGN — {len(cols)} NOS — MARKED C1..C{len(cols)}",
            f"2. BEAMS UP TO {int(beam_D_typ)} MM DEEP — SEE BEAM SCHEDULE",
            "3. GRID LINES AT WALL CENTRELINES",
            "4. SEE COLUMN/BEAM SCHEDULE TABLES FOR MEMBER SIZES + REINFORCEMENT",
        ]
    else:
        notes = [
            "STRUCTURAL NOTES:",
            f"1. COLUMNS 300 x 300 MM (TYP.), {len(cols)} NOS — MARKED C1..C{len(cols)}",
            "2. BEAMS 230 x 380 MM (TYP.) ALONG GRID LINES",
            "3. GRID LINES AT WALL CENTRELINES",
            "4. MAX CLEAR BEAM SPAN 4.5 M — VERIFY BEFORE EXECUTION",
        ]
    c.setFillColor(HexColor("#000000"))
    for i, note in enumerate(notes):
        c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 6 if i == 0 else 5.5)
        c.drawString(MARGIN, page_h - MARGIN - 9 * i, note)

    # Column/beam schedule tables + revision notes + disclaimer — reserved
    # schedule column, same slot the AREA/OPENINGS tables use on the
    # architectural pages (unused here otherwise)
    if design_data:
        sched_x = _schedule_column_x(page_w, MARGIN)
        top = TITLE_H + SCHED_PAD
        if columns_data:
            h = _draw_column_schedule_table(c, columns_data, sched_x, top + 0)
            top += h + SCHED_PAD
        beams_data = design_data.get("beams") or {}
        if beams_data:
            h = _draw_beam_schedule_table(c, beams_data, sched_x, top)
            top += h + SCHED_PAD

        rev_id = structural_design.get("revision_id")
        status_txt = (structural_design.get("status") or "").upper()
        changelog = structural_design.get("changelog") or []
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica-Bold", 5.5)
        rev_y = page_h - MARGIN - 9 * 5 - 6
        c.drawString(MARGIN, rev_y, "REVISION NOTES:")
        c.setFont("Helvetica", 5)
        rev_y -= 8
        c.drawString(
            MARGIN, rev_y, f"REVISION {rev_id or '—'} — STATUS: {status_txt or '—'}"
        )
        for note in changelog[:6]:
            rev_y -= 7
            c.drawString(MARGIN, rev_y, f"- {note}"[:110])
        disclaimer = (structural_design.get("structapi") or {}).get("disclaimer")
        if disclaimer:
            rev_y -= 9
            c.setFont("Helvetica-Oblique", 4.5)
            c.setFillColor(HexColor("#555555"))
            c.drawString(MARGIN, rev_y, disclaimer[:130])

    # Scale bar + north arrow + title block — shared furniture
    _draw_scale_bar(c, MARGIN, TITLE_H + 2, s, denom)
    _draw_north_arrow(c, page_w - MARGIN - 14, page_h - MARGIN - 16, 16)
    _draw_title_block(
        c,
        project_name,
        layout.id,
        layout.name,
        f"{floor_label} — Beam/Column Layout",
        cfg,
        num_bedrooms,
        s,
        page_w,
        floor_plan=floor_plan,
        scale_denom=denom,
        far_text=_far_text(layout, cfg),
    )

    return ox, oy, s, denom


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
    scale_denom: int | None = None,
    far_text: str | None = None,
) -> None:
    scale_ratio = scale_denom if scale_denom else round(1000 / (scale * (25.4 / 72)))

    # Compute area total in sqft when floor plan is available. Voids
    # (`Room.is_void`) have no slab and must not count toward built-up area.
    sqm_total = (
        sum(r.area for r in floor_plan.rooms if not r.is_void) if floor_plan else 0.0
    )
    sqft_total = round(sqm_total * 10.764)

    fields = [
        ("PROJECT", project_name),
        ("LAYOUT", f"{layout_id} - {layout_name}"),
        ("FLOOR", floor_label),
        ("PLOT", f"{cfg.plot_width}x{cfg.plot_length} m"),
        ("CONFIG", f"{num_bedrooms} BHK · {cfg.city.title()}"),
        ("SCALE", f"1:{scale_ratio}"),
        ("TOTAL AREA", f"{sqft_total} SQFT" if floor_plan else "—"),
        ("DATE", date.today().strftime("%d %b %Y")),
    ]
    if far_text:
        fields.insert(7, ("FAR", far_text))

    subtitle_lines = None
    if floor_plan and floor_plan.rooms:
        subtitle_lines = [
            f"TOTAL BUILT-UP AREA: {sqft_total} SQFT  ({sqm_total:.1f} SQ.M)"
            "   —   ROOM-WISE AREA: SEE AREA SCHEDULE TABLE ON PLAN"
        ]

    draw_title_block(c, page_w, TITLE_H, fields, subtitle_lines=subtitle_lines)


# ── FloorDrawing projection renderer (Sprint 5.1) ────────────────────────────

_PT_PER_PAPER_M = 72 / 0.0254  # points per paper metre


def _far_text(layout: Layout, cfg: PlotConfig) -> str:
    plot_area = cfg.plot_width * cfg.plot_length
    if not plot_area:
        return "0.00"
    built = sum(r.area for r in layout.ground_floor.rooms if not r.is_void) + sum(
        r.area for r in layout.first_floor.rooms if not r.is_void
    )
    return f"{built / plot_area:.2f}"


def _standard_scale(
    cfg: PlotConfig, page_w: float, page_h: float, reserve_w: float = 0.0
) -> tuple[float, int]:
    """Largest standard scale (1:50/1:100/1:200) that fits the plot on A4.

    Returns (points per model metre, scale denominator). Falls back to the
    next 50-multiple denominator when even 1:200 does not fit.

    ``reserve_w`` withholds horizontal space (e.g. for the schedule-table
    column) so the plot is scaled to fit the *remaining* width — this is how
    the plot shrinks just enough to keep clear of the bottom-right tables.
    """
    avail_w = page_w - 2 * MARGIN - reserve_w
    avail_h = page_h - TITLE_H - 2 * MARGIN - ROAD_H - ROAD_GAP - TOP_PAD
    for denom in (50, 100, 200):
        s = _PT_PER_PAPER_M / denom
        if cfg.plot_width * s <= avail_w and cfg.plot_length * s <= avail_h:
            return s, denom
    fit = min(avail_w / cfg.plot_width, avail_h / cfg.plot_length)
    denom = math.ceil(_PT_PER_PAPER_M / fit / 50) * 50
    return _PT_PER_PAPER_M / denom, denom


def _draw_voids(
    c: canvas.Canvas, rooms: list[Room], s: float, ox: float, oy: float
) -> None:
    """Void rooms (`Room.is_void`, Task 10) are holes, not slabs: no fill (the
    architectural page never hatches room floors to begin with, so there is
    no slab hatch to skip), a dashed boundary over the room's footprint
    instead of the solid wall poché a real room's edge implies, and an
    "OPEN TO BELOW" label under the room name.
    """
    void_rooms = [r for r in rooms if r.is_void]
    if not void_rooms:
        return
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.4)
    c.setDash(3, 2)
    for r in void_rooms:
        for p in r.rects:
            c.rect(
                ox + p.x * s, oy + p.y * s, p.width * s, p.depth * s, fill=0, stroke=1
            )
    c.setDash()
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Oblique", 6)
    for r in void_rooms:
        cx = ox + (r.x + r.width / 2) * s
        cy = oy + (r.y + r.depth / 2) * s
        c.drawCentredString(cx, cy - 8, "OPEN TO BELOW")


def _shape_path(c: canvas.Canvas, geom, s: float, ox: float, oy: float):
    """Fill+outline a shapely (Multi)Polygon with even-odd holes."""
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for poly in polys:
        if poly.is_empty:
            continue
        p = c.beginPath()
        rings = [poly.exterior, *poly.interiors]
        for ring in rings:
            pts = [(ox + x * s, oy + y * s) for x, y in ring.coords]
            p.moveTo(*pts[0])
            for pt in pts[1:]:
                p.lineTo(*pt)
            p.close()
        c.drawPath(p, stroke=1, fill=1, fillMode=1)


def _draw_opening_symbol(c: canvas.Canvas, o, s: float, ox: float, oy: float) -> None:
    t = o.wall_thickness * s
    if o.kind == "door":
        hx, hy = ox + o.hinge_x * s, oy + o.hinge_y * s
        jx, jy = ox + (2 * o.cx - o.hinge_x) * s, oy + (2 * o.cy - o.hinge_y) * s
        r = o.width * s
        ang0 = math.degrees(math.atan2(jy - hy, jx - hx))
        sweep = -90.0 if o.swing_cw else 90.0
        a1 = math.radians(ang0 + sweep)
        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(0.8)
        c.line(hx, hy, hx + r * math.cos(a1), hy + r * math.sin(a1))
        c.setLineWidth(0.35)
        c.arc(hx - r, hy - r, hx + r, hy + r, min(ang0, ang0 + sweep), 90)
        return
    # window / ventilator: parallel lines across the gap + jamb caps
    cxp, cyp = ox + o.cx * s, oy + o.cy * s
    half = o.width * s / 2
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(WIN_LW if o.kind == "window" else 0.5)
    offsets = (-t / 3, 0.0, t / 3) if o.kind == "window" else (-t / 4, t / 4)
    for off in offsets:
        if o.is_horizontal:
            c.line(cxp - half, cyp + off, cxp + half, cyp + off)
        else:
            c.line(cxp + off, cyp - half, cxp + off, cyp + half)
    c.setLineWidth(0.8)
    if o.is_horizontal:
        c.line(cxp - half, cyp - t / 2, cxp - half, cyp + t / 2)
        c.line(cxp + half, cyp - t / 2, cxp + half, cyp + t / 2)
    else:
        c.line(cxp - t / 2, cyp - half, cxp + t / 2, cyp - half)
        c.line(cxp - t / 2, cyp + half, cxp + t / 2, cyp + half)


def _draw_dim_chains(
    c: canvas.Canvas,
    drawing,
    s: float,
    ox: float,
    oy: float,
    plot_px: float,
    plot_py: float,
    bottom_lane_y: float | None = None,
) -> None:
    """Render chains in fixed paper-space lanes per side/level."""
    lane_step = 14.0
    road_y = TITLE_H + MARGIN
    base = {
        "bottom": (
            bottom_lane_y if bottom_lane_y is not None else road_y - 8.0
        ),  # below the road strip, inside the margin zone
        "top": oy + plot_py + 12.0,
        "left": ox - 12.0,
        "right": ox + plot_px + 12.0,
    }
    sign = {"bottom": -1.0, "top": 1.0, "left": -1.0, "right": 1.0}
    c.setStrokeColor(HexColor("#000000"))
    for chain in drawing.dim_chains:
        if not chain.entries:
            continue
        horiz = chain.side in ("bottom", "top")
        # room chain hugs the plot, the plot/setback chain keeps its historical
        # lane, and the dual-unit overall chain (level 1) sits outermost
        lane_idx = {0: 0, 2: 1}.get(chain.level, 2)
        lane = base[chain.side] + sign[chain.side] * lane_step * lane_idx
        bounds = [chain.entries[0].start] + [e.end for e in chain.entries]
        pts = [(ox if horiz else oy) + b * s for b in bounds]
        c.setLineWidth(DIM_LW)
        if horiz:
            c.line(pts[0], lane, pts[-1], lane)
        else:
            c.line(lane, pts[0], lane, pts[-1])
        for p in pts:
            if horiz:
                c.line(p, lane - 3, p, lane + 3)  # extension stub
                c.line(p - 2, lane - 2, p + 2, lane + 2)  # arch tick
            else:
                c.line(lane - 3, p, lane + 3, p)
                c.line(lane - 2, p - 2, lane + 2, p + 2)
        if chain.level == 1:
            c.setFont("Helvetica-Bold", 6.5)  # overall dual-unit dim reads bolder
        else:
            c.setFont("Helvetica", 6)
        c.setFillColor(HexColor("#000000"))
        for e in chain.entries:
            mid = (ox if horiz else oy) + (e.start + e.end) / 2 * s
            if horiz:
                c.drawCentredString(mid, lane + 2.5, e.text)
            else:
                c.saveState()
                c.translate(lane - 2.5, mid)
                c.rotate(90)
                c.drawCentredString(0, 0, e.text)
                c.restoreState()


def _draw_labels(
    c: canvas.Canvas, drawing, s: float, ox: float, oy: float, denom: int
) -> None:
    font_factor = min(1.0, 100.0 / denom)
    for lb in drawing.labels:
        eff = lb.font_pt * font_factor
        cxp, cyp = ox + lb.cx * s, oy + lb.cy * s
        if lb.leader is not None:
            tx, ty = ox + lb.leader[0] * s, oy + lb.leader[1] * s
            c.setStrokeColor(HexColor("#000000"))
            c.setLineWidth(0.4)
            c.line(cxp, cyp, tx, ty)
            c.circle(tx, ty, 1.2, stroke=1, fill=1)
        line_h = eff * 1.25
        top = (len(lb.lines) - 1) * line_h / 2
        c.setFillColor(HexColor("#000000"))
        c.saveState()
        c.translate(cxp, cyp)
        if lb.rotated:
            c.rotate(90)
        for i, text in enumerate(lb.lines):
            c.setFont(
                "Helvetica-Bold" if i == 0 else "Helvetica", eff if i == 0 else eff - 1
            )
            c.drawCentredString(0, top - i * line_h - eff * 0.35, text)
        c.restoreState()


def _draw_stair_geometry(
    c: canvas.Canvas, drawing, s: float, ox: float, oy: float, stair_label: str = "UP"
) -> None:
    stair = drawing.stair
    if stair is None:
        return
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.5)
    for x1, y1, x2, y2 in stair.treads:
        c.line(ox + x1 * s, oy + y1 * s, ox + x2 * s, oy + y2 * s)
    bx1, by1, bx2, by2 = stair.break_line
    c.setLineWidth(0.7)
    c.setDash(3, 2)
    c.line(ox + bx1 * s, oy + by1 * s, ox + bx2 * s, oy + by2 * s)
    c.setDash()
    ax1, ay1, ax2, ay2 = stair.arrow
    p1 = (ox + ax1 * s, oy + ay1 * s)
    p2 = (ox + ax2 * s, oy + ay2 * s)
    c.setLineWidth(0.8)
    c.line(*p1, *p2)
    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    for da in (2.6, -2.6):
        c.line(
            p2[0],
            p2[1],
            p2[0] - 5 * math.cos(ang + da * 0.5),
            p2[1] - 5 * math.sin(ang + da * 0.5),
        )
    ux, uy = stair.up_label_xy
    c.setFont("Helvetica-Bold", 6)
    c.drawString(ox + ux * s + 3, oy + uy * s, stair_label)


def _draw_floor_projected(
    c: canvas.Canvas,
    floor_plan: FloorPlan,
    layout: Layout,
    cfg: PlotConfig,
    project_name: str,
    num_bedrooms: int,
    floor_label: str,
    annotations: dict | None = None,
    watermark_preliminary: bool = False,
) -> None:
    """Architectural floor page rendered purely from the canonical FloorDrawing."""
    from app.engine.plan_geometry import (
        build_floor_drawing,
        opening_boxes,
        wall_polygons,
    )

    page_w, page_h = A4
    s, denom = _standard_scale(cfg, page_w, page_h, reserve_w=SCHED_RESERVE)
    plot_px, plot_py = cfg.plot_width * s, cfg.plot_length * s
    # Centre the plot in the left region, leaving the reserved schedule column
    # on the right; centre the plot+road group vertically in the page band.
    ox = MARGIN + (page_w - 2 * MARGIN - SCHED_RESERVE - plot_px) / 2
    oy = _centered_plot_oy(
        page_h, plot_py, title_h=TITLE_H, margin=MARGIN, road_below=ROAD_H + ROAD_GAP
    )

    drawing = build_floor_drawing(floor_plan, cfg)

    # Road strip + floor label (drawn directly below the plot)
    road_y = oy - ROAD_GAP - ROAD_H
    c.setFillColor(HexColor("#DDDDDD"))
    c.rect(ox, road_y, plot_px, ROAD_H, fill=1, stroke=0)
    road_side_name = {"S": "SOUTH", "N": "NORTH", "E": "EAST", "W": "WEST"}.get(
        cfg.road_side, ""
    )
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(
        ox + plot_px / 2, road_y + ROAD_H - 7, floor_label.upper() + " PLAN"
    )
    c.setFillColor(HexColor("#444444"))
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(
        ox + plot_px / 2,
        road_y + 3,
        f"ROAD  ({road_side_name})" if road_side_name else "ROAD",
    )

    # Plot boundary (dashed)
    c.setDash(5, 3)
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(0.5)
    c.rect(ox, oy, plot_px, plot_py, fill=0, stroke=1)
    c.setDash()

    # Walls: poché (solid fill) from the unioned polygons with openings cut
    polys = wall_polygons(drawing.walls, openings=opening_boxes(drawing.openings))
    c.setFillColor(HexColor("#000000"))
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.5)
    _shape_path(c, polys["external"], s, ox, oy)
    c.setLineWidth(0.35)
    _shape_path(c, polys["internal"], s, ox, oy)

    # Section A-A cut marker
    line, _along_y = section_cut_line(floor_plan.rooms, buildable_polygon(cfg))
    (lx1, ly1), (lx2, ly2) = line.coords[0], line.coords[-1]
    draw_section_marker(c, ox + lx1 * s, oy + ly1 * s, ox + lx2 * s, oy + ly2 * s, "A")

    # Openings, columns, stair, labels, dims
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
    _draw_stair_geometry(
        c,
        drawing,
        s,
        ox,
        oy,
        stair_label="UP" if _has_floor_above(layout, floor_plan) else "DN",
    )
    _draw_labels(c, drawing, s, ox, oy, denom)
    _draw_voids(c, floor_plan.rooms, s, ox, oy)
    _draw_dim_chains(c, drawing, s, ox, oy, plot_px, plot_py)
    _draw_compound_wall(c, cfg, ox, oy, s)
    _draw_setback_callouts(c, cfg, drawing.bounds, s, ox, oy)
    marks, opening_rows = _opening_marks(drawing)
    _draw_opening_tags(c, drawing, marks, s, ox, oy)
    if annotations:
        _draw_annotations(c, floor_plan.rooms, annotations, s, ox, oy)

    # Furniture of the page: scale bar (bottom-left), schedule tables stacked
    # bottom-right just above the title block, north arrow (top-right), title block
    _draw_scale_bar(c, MARGIN, TITLE_H + 2, s, denom)
    sched_x = _schedule_column_x(page_w, MARGIN)
    area_top = TITLE_H + SCHED_PAD + _area_schedule_height(floor_plan)
    _draw_area_schedule_table(c, floor_plan, sched_x, area_top)
    if opening_rows:
        openings_top = area_top + SCHED_PAD + _openings_schedule_height(opening_rows)
        _draw_openings_schedule_table(c, opening_rows, sched_x, openings_top)
    _draw_north_arrow(c, page_w - MARGIN - 14, page_h - MARGIN - 16, 16)
    if watermark_preliminary:
        _draw_preliminary_watermark(c, page_w, page_h)
    _draw_title_block(
        c,
        project_name,
        layout.id,
        layout.name,
        floor_label,
        cfg,
        num_bedrooms,
        s,
        page_w,
        floor_plan=floor_plan,
        scale_denom=denom,
        far_text=_far_text(layout, cfg),
    )
