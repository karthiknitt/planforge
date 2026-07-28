"""Sheets S-02 (Column & Footing Plan), S-03 (Footing Details) and S-04
(Column Details & Schedule) of the construction-grade Structural Drawing Set.

These three sheets replace `structural_drawing_set.render_column_footing_plan`
/ `render_footing_details`, which drew footings with no column above them, no
setting-out dimensions, and one arbitrary "typical section" pictorial at a
hardcoded (non-standard) scale instead of one real detail per footing type.
Built entirely on the shared furniture in `structural_sheet.py` so these
sheets register against the rest of the set.
"""

from __future__ import annotations

import math
import re

from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas

from app.engine.pdf import (
    MARGIN,
    SCHED_PAD,
    TITLE_H,
    _draw_generic_schedule_table,
    _generic_schedule_height,
    _schedule_column_x,
)
from app.engine.section_render import hatch_polygon
from app.engine.structural_data import ColumnItem, FootingItem, StructuralModel
from app.engine.structural_sheet import (
    SHEET_TITLES,
    LabelPlacer,
    PlanFrame,
    detail_sheet_frame,
    draw_disclaimer,
    draw_grid_and_bubbles,
    draw_notes,
    draw_plan_scale_bar,
    draw_scale_note,
    fit_detail_scale,
    paginate_boxes,
    plan_sheet_frame,
    structural_title_block,
)

_MM_PER_M = 1000.0
_COVER_MM = 50.0  # footing bottom cover / column clear cover, IS 456 Table 16


# ── S-02 COLUMN & FOOTING PLAN ─────────────────────────────────────────────


def render_column_footing_plan(c: canvas.Canvas, model: StructuralModel) -> int:
    frame = plan_sheet_frame(c, model.cfg, heading=SHEET_TITLES["S-02"], drg_no="S-02")

    if model.gf_drawing is not None:
        c.setStrokeColor(HexColor("#CCCCCC"))
        c.setLineWidth(0.5)
        for w in model.gf_drawing.walls:
            c.line(frame.px(w.x1), frame.py(w.y1), frame.px(w.x2), frame.py(w.y2))

    if model.grid.ok and model.gf_drawing is not None:
        draw_grid_and_bubbles(
            c,
            frame,
            model.grid.x_lines_m,
            model.grid.y_lines_m,
            model.gf_drawing.bounds,
        )
        _draw_grid_spacing_chains(c, frame, model.grid.x_lines_m, model.grid.y_lines_m)

    placer = LabelPlacer()

    # Footings drawn first (dashed, under the columns they carry).
    c.setDash(3, 2)
    c.setStrokeColor(HexColor("#0088AA"))
    c.setLineWidth(0.6)
    footing_boxes: list[tuple[float, float, float, float, str]] = []
    for f in model.footings:
        fx, fy = frame.px(f.cx), frame.py(f.cy)
        fw, fh = f.length_m * frame.s, f.width_m * frame.s
        c.rect(fx - fw / 2, fy - fh / 2, fw, fh, fill=0, stroke=1)
        footing_boxes.append((fx, fy, fw, fh, f.mark))
    c.setDash()

    # Columns at their real designed size, solid-filled — a footing plan
    # without the column it carries can't be set out.
    c.setFillColor(HexColor("#444444"))
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.5)
    col_boxes: list[tuple[float, float, float, float, str]] = []
    for col in model.columns:
        cx, cy = frame.px(col.cx), frame.py(col.cy)
        cw = col.b_mm / _MM_PER_M * frame.s
        cd = col.D_mm / _MM_PER_M * frame.s
        c.rect(cx - cw / 2, cy - cd / 2, cw, cd, fill=1, stroke=1)
        col_boxes.append((cx, cy, cw, cd, col.tag))

    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 5.5)
    for fx, fy, fw, fh, mark in footing_boxes:
        lx, ly = placer.place(
            [(fx, fy - fh / 2 - 6), (fx, fy + fh / 2 + 6), (fx + fw / 2 + 10, fy)]
        )
        c.drawCentredString(lx, ly - 2, mark)
    for cx, cy, cw, cd, tag in col_boxes:
        lx, ly = placer.place(
            [
                (cx + cw / 2 + 8, cy + 8),
                (cx - cw / 2 - 8, cy + 8),
                (cx, cy + cd / 2 + 14),
            ]
        )
        c.drawCentredString(lx, ly - 2, tag)

    sched_x = _schedule_column_x(frame.page_w, MARGIN)
    headers, col_ws, rows = _footing_schedule_rows(model)
    if rows:
        # `_draw_generic_schedule_table` draws downward from its y_top arg
        # (rect spans [y_top - height, y_top]) — anchor so the BOTTOM sits
        # SCHED_PAD above the title block, not the top, or a tall table
        # dips below TITLE_H and prints over the title-block cells.
        height = _generic_schedule_height(len(rows))
        top = TITLE_H + SCHED_PAD + height
        _draw_generic_schedule_table(
            c, "FOOTING SCHEDULE", headers, col_ws, rows, sched_x, top
        )

    notes = [
        "NOTES:",
        "1. ALL FOOTINGS ISOLATED — SEE FOOTING SCHEDULE FOR SIZE + STEEL.",
        "2. COLUMNS SHOWN AT DESIGNED SIZE — SEE COLUMN SCHEDULE (S-04).",
        "3. SET OUT FROM GRID LINES SHOWN — CHAIN DIMENSIONS GIVE SPACINGS.",
    ]
    draw_notes(c, notes, MARGIN, frame.page_h - MARGIN - 4)

    draw_plan_scale_bar(c, frame)
    draw_disclaimer(c, model.disclaimer, MARGIN, TITLE_H - 8)
    structural_title_block(
        c,
        project_name=model.project_name,
        cfg=model.cfg,
        drg_no="S-02",
        sheet_title=SHEET_TITLES["S-02"],
        page_w=frame.page_w,
        scale_denom=frame.denom,
        layout_label=model.layout_label,
    )
    return 1


def _draw_grid_spacing_chains(
    c: canvas.Canvas, frame: PlanFrame, xs: list[float], ys: list[float]
) -> None:
    """Chain dimensions of the raw grid-line spacings, outside the bubble
    rows drawn by `draw_grid_and_bubbles` — what a foundation contractor
    actually sets out from, distinct from the room dimension chains."""
    lane_x = frame.oy - 34.0
    lane_y = frame.ox - 34.0
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.4)
    c.setFont("Helvetica", 6)
    c.setFillColor(HexColor("#000000"))
    for a, b in zip(xs, xs[1:]):
        pa, pb = frame.px(a), frame.px(b)
        c.line(pa, lane_x, pb, lane_x)
        c.line(pa, lane_x - 3, pa, lane_x + 3)
        c.line(pb, lane_x - 3, pb, lane_x + 3)
        c.drawCentredString((pa + pb) / 2, lane_x + 2.5, f"{b - a:.2f} m")
    for a, b in zip(ys, ys[1:]):
        pa, pb = frame.py(a), frame.py(b)
        c.line(lane_y, pa, lane_y, pb)
        c.line(lane_y - 3, pa, lane_y + 3, pa)
        c.line(lane_y - 3, pb, lane_y + 3, pb)
        c.saveState()
        c.translate(lane_y - 6, (pa + pb) / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, f"{b - a:.2f} m")
        c.restoreState()


def _footing_schedule_rows(
    model: StructuralModel,
) -> tuple[tuple[str, ...], tuple[float, ...], list[tuple]]:
    """Shared FOOTING SCHEDULE content for S-02 and S-03: one row per
    footing class, ``NOS`` counted from every footing of that class."""
    headers = ("MARK", "SIZE (L x B m)", "DEPTH (mm)", "BARS-X", "BARS-Y", "NOS")
    col_ws = (16.0, 34.0, 22.0, 30.0, 28.0, 18.0)
    counts: dict[str, int] = {}
    for f in model.footings:
        counts[f.footing_class] = counts.get(f.footing_class, 0) + 1
    rows: list[tuple] = []
    for cls, f in sorted(model.footings_by_class().items()):
        bars_x = f.design.get("bars_x") or {}
        bars_y = f.design.get("bars_y") or {}
        rows.append(
            (
                f.mark,
                f"{f.length_m:.2f}x{f.width_m:.2f}",
                f"{f.depth_mm:.0f}",
                f"{bars_x.get('dia', '-')}-{bars_x.get('spacing', '-')}",
                f"{bars_y.get('dia', '-')}-{bars_y.get('spacing', '-')}",
                str(counts.get(cls, 0)),
            )
        )
    return headers, col_ws, rows


# ── S-03 FOOTING DETAILS ────────────────────────────────────────────────────


def bar_count(length_mm: float, spacing_mm: float, cover_mm: float = _COVER_MM) -> int:
    """Number of bars across ``length_mm`` at ``spacing_mm`` c/c with cover
    each side: ``floor((L - 2*cover) / spacing) + 1``."""
    if spacing_mm <= 0 or length_mm <= 2 * cover_mm:
        return 0
    return math.floor((length_mm - 2 * cover_mm) / spacing_mm) + 1


_FOOTING_BOX_H = 190.0


def render_footing_details(c: canvas.Canvas, model: StructuralModel) -> int:
    footings = list(model.footings_by_class().values())
    footings.sort(key=lambda f: f.mark)

    def height_of(_f: FootingItem) -> float:
        return _FOOTING_BOX_H

    frame = detail_sheet_frame(c, heading=SHEET_TITLES["S-03"], drg_no="S-03")
    pages = paginate_boxes(footings, height_of, top=frame.y1, bottom=frame.y0 + 130.0)
    if not pages:
        pages = [[]]

    for page_i, page_items in enumerate(pages):
        if page_i > 0:
            frame = detail_sheet_frame(
                c, heading=SHEET_TITLES["S-03"], drg_no="S-03", continued=True
            )
        y = frame.y1 - 10.0
        for f in page_items:
            _draw_footing_detail(c, f, frame.x0, y, frame.x1 - frame.x0, _FOOTING_BOX_H)
            y -= _FOOTING_BOX_H + 15.0

        headers, col_ws, rows = _footing_schedule_rows(model)
        if rows:
            table_top = frame.y0 + 12.0 + _generic_schedule_height(len(rows))
            _draw_generic_schedule_table(
                c, "FOOTING SCHEDULE", headers, col_ws, rows, frame.x0, table_top
            )
        draw_disclaimer(c, model.disclaimer, frame.x0, frame.y0 - 4)
        structural_title_block(
            c,
            project_name=model.project_name,
            cfg=model.cfg,
            drg_no="S-03",
            sheet_title=SHEET_TITLES["S-03"],
            page_w=frame.page_w,
            scale_text="VARIES — SEE EACH DETAIL",
            layout_label=model.layout_label,
        )
        # Boundary between this page and the next — never after the last one
        # (the orchestrator that stitches this set together does that).
        if page_i < len(pages) - 1:
            c.showPage()
    return len(pages)


def _draw_footing_detail(
    c: canvas.Canvas,
    f: FootingItem,
    x: float,
    y_top: float,
    avail_w: float,
    avail_h: float,
) -> None:
    """One dimensioned footing detail: section (earth/PCC/footing/column
    stub) on the left half, bar-mat plan on the right half."""
    half_w = avail_w / 2 - 10.0
    l_mm = f.length_m * _MM_PER_M
    b_mm = f.width_m * _MM_PER_M
    d_mm = f.depth_mm or 450.0
    pcc_mm = 100.0
    stub_mm = 450.0

    px_per_mm, denom = fit_detail_scale(
        l_mm + 2 * 50.0, d_mm + pcc_mm + stub_mm, half_w, avail_h - 50.0
    )

    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(HexColor("#000000"))
    c.drawString(x, y_top, f"{f.mark} — {f.footing_class.upper()} FOOTING SECTION")

    sy = y_top - avail_h + 20.0
    fw = l_mm * px_per_mm
    fh = d_mm * px_per_mm
    pcc_w = fw + 2 * 50.0 * px_per_mm
    pcc_h = pcc_mm * px_per_mm

    # The earth band and the PCC bed both project LEFT of the footing slab's
    # own origin, so anchoring the section at the frame's left edge pushed
    # them outside the sheet border. Inset by the widest leftward overhang so
    # the whole detail sits inside the frame.
    earth_h = 14.0
    earth_overhang = 20.0
    sx = x + max(earth_overhang, (pcc_w - fw) / 2)
    earth_pts = [
        (sx - earth_overhang, sy - earth_h),
        (sx + pcc_w + earth_overhang, sy - earth_h),
        (sx + pcc_w + earth_overhang, sy),
        (sx - earth_overhang, sy),
    ]
    hatch_polygon(c, earth_pts, "earth", spacing_pt=3.0)
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.4)
    c.rect(
        sx - earth_overhang,
        sy - earth_h,
        pcc_w + 2 * earth_overhang,
        earth_h,
        fill=0,
        stroke=1,
    )

    # PCC bed projects 50mm beyond the footing on each side
    pcc_x0 = sx - (pcc_w - fw) / 2
    pcc_pts = [
        (pcc_x0, sy),
        (pcc_x0 + pcc_w, sy),
        (pcc_x0 + pcc_w, sy + pcc_h),
        (pcc_x0, sy + pcc_h),
    ]
    hatch_polygon(c, pcc_pts, "pcc", spacing_pt=3.0)
    c.rect(pcc_x0, sy, pcc_w, pcc_h, fill=0, stroke=1)

    fx0 = sx  # footing slab sits centred within the PCC projection
    ftg_pts = [
        (fx0, sy + pcc_h),
        (fx0 + fw, sy + pcc_h),
        (fx0 + fw, sy + pcc_h + fh),
        (fx0, sy + pcc_h + fh),
    ]
    hatch_polygon(c, ftg_pts, "rcc", spacing_pt=4.0)
    c.rect(fx0, sy + pcc_h, fw, fh, fill=0, stroke=1)

    # column stub + starter bars with the 90-degree bend at the footing base
    stub_w = min(fw * 0.35, 40.0)
    stub_h = stub_mm * px_per_mm
    stub_x = fx0 + fw / 2 - stub_w / 2
    stub_y = sy + pcc_h + fh
    c.setFillColor(white)
    c.rect(stub_x, stub_y, stub_w, stub_h, fill=1, stroke=1)
    c.setStrokeColor(HexColor("#AA0000"))
    c.setLineWidth(0.6)
    for bx in (stub_x + 4, stub_x + stub_w - 4):
        c.line(bx, stub_y + stub_h, bx, sy + pcc_h + 10)
        c.line(bx, sy + pcc_h + 10, fx0 + 8, sy + pcc_h + 2)  # 90deg bend into the mat

    # bar mat plan view — real count, not a fixed tick count
    bars_x = f.design.get("bars_x") or {}
    bars_y = f.design.get("bars_y") or {}
    n_x = bar_count(l_mm, float(bars_x.get("spacing", 0) or 0))
    n_y = bar_count(b_mm, float(bars_y.get("spacing", 0) or 0))

    plan_scale, _plan_denom = fit_detail_scale(l_mm, b_mm, half_w, avail_h - 60.0)
    px = x + half_w + 20.0
    py = y_top - avail_h + 20.0
    pw, ph = l_mm * plan_scale, b_mm * plan_scale
    c.setFillColor(white)
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.6)
    c.rect(px, py, pw, ph, fill=1, stroke=1)
    c.setStrokeColor(HexColor("#AA0000"))
    c.setLineWidth(0.4)
    for i in range(n_x):
        bx = px + (pw * i / (n_x - 1) if n_x > 1 else pw / 2)
        c.line(bx, py, bx, py + ph)
    for j in range(n_y):
        by = py + (ph * j / (n_y - 1) if n_y > 1 else ph / 2)
        c.line(px, by, px + pw, by)

    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 6)
    c.drawString(px, py + ph + 10, "BAR MAT — PLAN")
    c.drawString(
        px,
        py - 10,
        f"{n_x} NOS {bars_x.get('dia', '-')}ø @ {bars_x.get('spacing', '-')} c/c X-DIR",
    )
    c.drawString(
        px,
        py - 19,
        f"{n_y} NOS {bars_y.get('dia', '-')}ø @ {bars_y.get('spacing', '-')} c/c Y-DIR",
    )

    if bars_x.get("dia") == bars_y.get("dia") and bars_x.get("spacing") == bars_y.get(
        "spacing"
    ):
        callout = f"{n_x + n_y} NOS {bars_x.get('dia', '-')}ø @ {bars_x.get('spacing', '-')} c/c BOTHWAYS"
        c.drawString(px, py - 28, callout)

    c.setFont("Helvetica", 5.5)
    c.drawString(
        sx,
        sy - earth_h - 10,
        f"L={f.length_m:.2f}m  B={f.width_m:.2f}m  D={d_mm:.0f}mm  PCC=100mm  COVER={_COVER_MM:.0f}mm",
    )
    draw_scale_note(c, sx, sy + pcc_h + fh + stub_h + 12, denom)


# ── S-04 COLUMN DETAILS & SCHEDULE ─────────────────────────────────────────

#: IS 456 Cl 26.5.3.2(c) minimum lateral-tie diameter and Cl 26.5.3.2(c)/(2)
#: maximum spacing, used whenever structapi's design payload has no explicit
#: tie entry — an honest code-minimum fallback rather than a fabricated one.
_MIN_TIE_DIA_MM = 6.0


def _parse_bars(bars: str) -> tuple[int, float]:
    """Parse ``col.bars`` ("6-16" = 6 nos of 16 mm) defensively; falls back
    to a sensible minimum (4 nos 12mm) rather than crashing on an
    unrecognised format."""
    text = bars or ""
    m = re.match(r"\s*(\d+)\s*[-xX]\s*(\d+(?:\.\d+)?)", text)
    if m:
        return int(m.group(1)), float(m.group(2))
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if len(nums) >= 2:
        a, b = nums[0], nums[1]
        if a <= 20 and b >= 8:
            return int(a), b
        if b <= 20 and a >= 8:
            return int(b), a
    return 4, 12.0


def _tie_spec(
    design: dict, main_dia_mm: float, min_lateral_mm: float
) -> tuple[float, float]:
    ties = design.get("ties") or {}
    if ties.get("dia") and ties.get("spacing"):
        return float(ties["dia"]), float(ties["spacing"])
    tie_dia = max(_MIN_TIE_DIA_MM, main_dia_mm / 4.0)
    spacing = min(16 * main_dia_mm, 300.0, min_lateral_mm)
    return tie_dia, spacing


def _perimeter_points(
    cx: float, cy: float, w: float, h: float, n: int
) -> list[tuple[float, float]]:
    """``n`` points evenly spaced (by arc length) around a ``w`` x ``h``
    rectangle centred on ``(cx, cy)``, starting at the top-left corner —
    mirrors how main bars are actually tied around a column cage."""
    if n <= 0:
        return []
    perim = 2 * (w + h)
    x0, y0 = cx - w / 2, cy - h / 2
    pts: list[tuple[float, float]] = []
    for i in range(n):
        d = (perim * i / n) % perim
        if d <= w:
            pts.append((x0 + d, y0))
        elif d <= w + h:
            pts.append((x0 + w, y0 + (d - w)))
        elif d <= 2 * w + h:
            pts.append((x0 + w - (d - w - h), y0 + h))
        else:
            pts.append((x0, y0 + h - (d - 2 * w - h)))
    return pts


_COLUMN_BOX_H = 210.0


def render_column_details(c: canvas.Canvas, model: StructuralModel) -> int:
    classes = list(model.columns_by_class().values())
    classes.sort(key=lambda col: col.mark)

    def height_of(_col: ColumnItem) -> float:
        return _COLUMN_BOX_H

    frame = detail_sheet_frame(c, heading=SHEET_TITLES["S-04"], drg_no="S-04")
    pages = paginate_boxes(classes, height_of, top=frame.y1, bottom=frame.y0 + 140.0)
    if not pages:
        pages = [[]]

    for page_i, page_items in enumerate(pages):
        if page_i > 0:
            frame = detail_sheet_frame(
                c, heading=SHEET_TITLES["S-04"], drg_no="S-04", continued=True
            )
        y = frame.y1 - 10.0
        for col in page_items:
            _draw_column_detail(c, col, frame.x0, y, frame.x1 - frame.x0, _COLUMN_BOX_H)
            y -= _COLUMN_BOX_H + 15.0

        headers, col_ws, rows = _column_schedule_rows(model)
        if rows:
            table_top = frame.y0 + 12.0 + _generic_schedule_height(len(rows))
            _draw_generic_schedule_table(
                c, "COLUMN SCHEDULE", headers, col_ws, rows, frame.x0, table_top
            )
        draw_disclaimer(c, model.disclaimer, frame.x0, frame.y0 - 4)
        structural_title_block(
            c,
            project_name=model.project_name,
            cfg=model.cfg,
            drg_no="S-04",
            sheet_title=SHEET_TITLES["S-04"],
            page_w=frame.page_w,
            scale_text="VARIES — SEE EACH DETAIL",
            layout_label=model.layout_label,
        )
        # Boundary between this page and the next — never after the last one
        # (the orchestrator that stitches this set together does that).
        if page_i < len(pages) - 1:
            c.showPage()
    return len(pages)


def _column_schedule_rows(
    model: StructuralModel,
) -> tuple[tuple[str, ...], tuple[float, ...], list[tuple]]:
    headers = ("MARK", "CLASS", "SIZE (mm)", "MAIN BARS", "TIES", "NOS")
    col_ws = (16.0, 30.0, 34.0, 40.0, 22.0, 14.0)
    counts: dict[str, int] = {}
    for col in model.columns:
        counts[col.col_class] = counts.get(col.col_class, 0) + 1
    rows: list[tuple] = []
    for cls, col in sorted(model.columns_by_class().items()):
        n_bars, dia = _parse_bars(col.bars)
        tie_dia, spacing = _tie_spec(col.design, dia, min(col.b_mm, col.D_mm))
        rows.append(
            (
                col.mark,
                cls.upper(),
                f"{col.b_mm:.0f}x{col.D_mm:.0f}",
                f"{n_bars}-{dia:.0f}",
                f"{tie_dia:.0f}@{spacing:.0f}",
                str(counts.get(cls, 0)),
            )
        )
    return headers, col_ws, rows


def _draw_column_detail(
    c: canvas.Canvas,
    col: ColumnItem,
    x: float,
    y_top: float,
    avail_w: float,
    avail_h: float,
) -> None:
    """Cross-section (left) + lap-splice elevation (right) for one column
    class, at a real fitted detail scale."""
    half_w = avail_w / 2 - 10.0
    n_bars, dia = _parse_bars(col.bars)
    min_lateral = min(col.b_mm, col.D_mm)
    tie_dia, tie_spacing = _tie_spec(col.design, dia, min_lateral)

    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(HexColor("#000000"))
    c.drawString(
        x,
        y_top,
        f"{col.mark} — {col.col_class.upper()} COLUMN {col.b_mm:.0f}x{col.D_mm:.0f} mm",
    )

    px_per_mm, denom = fit_detail_scale(col.b_mm, col.D_mm, half_w, avail_h - 60.0)
    sec_w, sec_h = col.b_mm * px_per_mm, col.D_mm * px_per_mm
    sx = x + (half_w - sec_w) / 2
    sy = y_top - avail_h + 30.0

    c.setFillColor(white)
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.8)
    c.rect(sx, sy, sec_w, sec_h, fill=1, stroke=1)

    tie_inset = _COVER_MM * px_per_mm
    c.setStrokeColor(HexColor("#0088AA"))
    c.setLineWidth(0.6)
    c.rect(
        sx + tie_inset,
        sy + tie_inset,
        sec_w - 2 * tie_inset,
        sec_h - 2 * tie_inset,
        fill=0,
        stroke=1,
    )

    c.setFillColor(HexColor("#AA0000"))
    for bx, by in _perimeter_points(
        sx + sec_w / 2,
        sy + sec_h / 2,
        sec_w - 2 * tie_inset,
        sec_h - 2 * tie_inset,
        n_bars,
    ):
        c.circle(bx, by, max(1.2, dia * px_per_mm / 2), fill=1, stroke=0)

    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 6)
    c.drawString(sx, sy - 10, f"{n_bars} NOS {dia:.0f}ø MAIN BARS")
    c.drawString(sx, sy - 19, f"{tie_dia:.0f}ø TIES @ {tie_spacing:.0f} c/c")
    draw_scale_note(c, sx, sy + sec_h + 12, denom)

    # lap-splice elevation
    ex = x + half_w + 20.0
    lap_mm = 50.0 * dia
    total_mm = 2 * lap_mm + 300.0
    elev_px_per_mm, elev_denom = fit_detail_scale(
        col.b_mm, total_mm, half_w, avail_h - 60.0
    )
    ew = col.b_mm * elev_px_per_mm
    ey0 = y_top - avail_h + 30.0
    eh = total_mm * elev_px_per_mm
    lap_h = lap_mm * elev_px_per_mm

    c.setFillColor(white)
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.7)
    c.rect(ex, ey0, ew, eh, fill=1, stroke=1)
    joint_y = ey0 + eh / 2
    c.setDash(3, 2)
    c.line(ex, joint_y, ex + ew, joint_y)  # floor/slab soffit
    c.setDash()

    c.setStrokeColor(HexColor("#AA0000"))
    c.setLineWidth(0.7)
    stagger = ew * 0.15
    c.line(ex + ew * 0.3 - stagger, ey0, ex + ew * 0.3 - stagger, joint_y + lap_h / 2)
    c.line(ex + ew * 0.7 + stagger, ey0, ex + ew * 0.7 + stagger, joint_y - lap_h / 2)
    c.line(
        ex + ew * 0.3 + stagger, joint_y - lap_h / 2, ex + ew * 0.3 + stagger, ey0 + eh
    )
    c.line(
        ex + ew * 0.7 - stagger, joint_y + lap_h / 2, ex + ew * 0.7 - stagger, ey0 + eh
    )

    n_ties_lap = max(2, int(lap_h / max(4.0, (tie_spacing / 2) * elev_px_per_mm)))
    c.setStrokeColor(HexColor("#0088AA"))
    c.setLineWidth(0.4)
    for i in range(n_ties_lap + 1):
        ty = joint_y - lap_h / 2 + lap_h * i / n_ties_lap
        c.line(ex + 4, ty, ex + ew - 4, ty)

    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 6)
    c.drawString(ex, ey0 - 10, "LAP SPLICE DETAIL — STAGGERED")
    c.drawString(ex, ey0 - 19, f"LAP LENGTH = 50ø = {lap_mm:.0f} mm")
    c.drawString(ex, ey0 - 28, f"TIES @ {tie_spacing / 2:.0f} c/c OVER LAP ZONE")
    draw_scale_note(c, ex, ey0 + eh + 12, elev_denom)
