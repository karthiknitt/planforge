"""Structural Drawing Set: 6-sheet CAD-style PDF (Column & Footing Plan,
Footing Details, Plinth Beam Plan, Plinth Beam Details, Roof Beam & Slab
Plan, Roof Beam Details) built on structapi's IS-456 member design.

See docs/plans/2026-07-19-structural-drawing-set-design.md for the full
design rationale and documented simplifications (isolated footings only,
single wall height for plinth UDL, no seismic overlay on plinth beams, one
reinforcement schedule per beam mark rather than midspan/support split).
"""

from __future__ import annotations

from typing import Any

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.cad_elements import ColumnMarker, WallSegment
from app.engine.footing_placement import place_footings
from app.engine.models import PlotConfig
from app.engine.pdf import (
    MARGIN,
    ROAD_GAP,
    ROAD_H,
    TITLE_H,
    _centered_plot_oy,
    _draw_generic_schedule_table,
    _draw_north_arrow,
    _draw_title_block,
    _generic_schedule_height,
    _standard_scale,
)

#: footing type -> reference-style mnemonic. Mapping follows the same
#: corner/edge/interior classification `place_footings()` (Task 4) derives
#: from the structural grid: corner columns (extreme on both axes) get the
#: smallest/lightest mark T1, edge columns (extreme on one axis) T2, and
#: interior columns (largest tributary area, heaviest footing) T3.
_FOOTING_MARK = {"corner": "T1", "edge": "T2", "interior": "T3"}

#: `_draw_title_block`'s `num_bedrooms` field renders "N BHK" in the CONFIG
#: line. Structural sheets have no meaningful bedroom count (they're not
#: architectural plans), so every sheet in this set passes 0 and the title
#: block prints "0 BHK" — a known cosmetic quirk, not a bug. Left as-is
#: rather than special-casing `_draw_title_block` for non-architectural
#: callers, since that helper is shared with the 4 architectural/structural
#: floor-plan pages where the BHK count *is* meaningful.
_NUM_BEDROOMS_NA = 0

#: scale for `_draw_typical_footing_section`'s schematic (points per mm of
#: real-world footing dimension) -- shared with `render_footing_details`'s
#: vertical-space budgeting so the two stay in sync.
_FOOTING_SECTION_PX_PER_MM = 0.15

#: scale for `_draw_beam_detail_box`'s cross-section (points per mm of real
#: beam dimension) -- shared with future sheet callers stacking these boxes
#: so their vertical-space budgeting matches the drawn size.
_BEAM_SECTION_PX_PER_MM = 0.12


def _draw_sheet_frame(
    c: canvas.Canvas, cfg: PlotConfig, heading: str
) -> tuple[float, float, float, int]:
    """Shared furniture for every structural drawing sheet: road strip, plot
    boundary (dashed, matching `_draw_structural_floor`'s architectural-page
    look), sheet heading, and north arrow. Callers draw sheet-specific
    content (footings, beams, etc.) within the returned frame, then call
    `_draw_title_block` themselves (each sheet has a different title/label).

    Returns ``(ox, oy, s, denom)``: plot-origin X/Y in points and the
    computed scale (points-per-model-metre, scale denominator) from
    `_standard_scale`, for callers to project model coordinates with.
    """
    page_w, page_h = A4
    s, denom = _standard_scale(cfg, page_w, page_h)
    plot_px, plot_py = cfg.plot_width * s, cfg.plot_length * s
    ox = MARGIN + (page_w - 2 * MARGIN - plot_px) / 2
    oy = _centered_plot_oy(
        page_h,
        plot_py,
        title_h=TITLE_H,
        margin=MARGIN,
        road_below=ROAD_H + ROAD_GAP,
    )

    # Road strip + page label — identical furniture to _draw_structural_floor
    # (app/engine/pdf.py) so all sheets in the set read as one drawing set.
    road_y = oy - ROAD_GAP - ROAD_H
    c.setFillColor(HexColor("#DDDDDD"))
    c.rect(ox, road_y, plot_px, ROAD_H, fill=1, stroke=0)
    road_side_name = {"S": "SOUTH", "N": "NORTH", "E": "EAST", "W": "WEST"}.get(
        cfg.road_side, ""
    )
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(ox + plot_px / 2, road_y + ROAD_H - 7, heading)
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

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(HexColor("#000000"))
    c.drawCentredString(page_w / 2, oy + plot_py + 20, heading)

    _draw_north_arrow(c, ox + plot_px - 20, oy + plot_py - 20, 12)

    return ox, oy, s, denom


def render_column_footing_plan(
    c: canvas.Canvas,
    columns: list[ColumnMarker],
    walls: list[WallSegment],
    footings_data: dict[str, Any],
    cfg: PlotConfig,
    project_name: str,
) -> None:
    """Render the "COLUMN & FOOTING PLAN" sheet: plot boundary, north arrow,
    title block, and each column's footing drawn as a dashed rectangle
    (sized per `place_footings()`) centred on the column position, labelled
    with its footing-type mark.
    """
    page_w, _page_h = A4
    ox, oy, s, denom = _draw_sheet_frame(c, cfg, "COLUMN & FOOTING PLAN")

    placed = place_footings(columns, walls, footings_data)

    # Two passes instead of toggling setDash per-footing: draw every dashed
    # footing rectangle first, reset the dash state once, then draw every
    # label. Cheaper on canvas-state churn and easier to copy for the next
    # sheet renderer than interleaved dash-on/dash-off calls.
    c.setDash(3, 2)
    c.setStrokeColor(HexColor("#0088AA"))
    boxes = []
    for f in placed:
        fx, fy = ox + f.cx * s, oy + f.cy * s
        fw, fh = f.length_m * s, f.width_m * s
        c.rect(fx - fw / 2, fy - fh / 2, fw, fh, fill=0, stroke=1)
        boxes.append((fx, fy, fh, f.footing_type))
    c.setDash()

    c.setFont("Helvetica-Bold", 6)
    c.setFillColor(HexColor("#000000"))
    for fx, fy, fh, footing_type in boxes:
        c.drawCentredString(fx, fy + fh / 2 + 4, _FOOTING_MARK.get(footing_type, "T?"))

    _draw_title_block(
        c,
        project_name,
        "A",
        "Column & Footing Plan",
        "Column & Footing Plan",
        cfg,
        _NUM_BEDROOMS_NA,
        s,
        page_w,
        scale_denom=denom,
    )


def render_footing_details(
    c: canvas.Canvas,
    footings_data: dict[str, Any],
    cfg: PlotConfig,
    project_name: str,
) -> None:
    """Render the "FOOTING DETAILS" sheet: a schedule table (one row per
    footing type) plus a single dimensioned "typical section" schematic of
    the largest footing (by plan area).

    Unlike `render_column_footing_plan`, this sheet has no plan-view content
    tied to model-space column positions -- its content is a data table and
    one representative pictorial. `_draw_sheet_frame` is still called (for
    heading/road-strip/plot-boundary/north-arrow furniture consistency across
    the drawing set, per the design doc), but the schedule and typical
    section are positioned at fixed page-relative offsets rather than
    projected through the returned `(ox, oy, s)` -- they simply overlay the
    (purely decorative, dashed) plot-boundary guide box near the top of the
    page. See docs/plans/2026-07-19-structural-drawing-set-design.md.
    """
    page_w, page_h = A4
    _ox, oy, s, denom = _draw_sheet_frame(c, cfg, "FOOTING DETAILS")

    # `_draw_sheet_frame` draws the sheet heading at (page_w/2, oy + plot_py +
    # 20) -- a position that scales with the plot's footprint (`plot_py =
    # cfg.plot_length * s`), so it lands higher on the page for small/narrow
    # plots. `_draw_generic_schedule_table` paints an OPAQUE white background
    # as its first draw op; if the table's fixed `page_h - MARGIN - 30` top
    # ever landed above (or too close to) that heading position, the white
    # box would paint over and visually erase the heading -- a real z-order
    # occlusion bug even though text-extraction tests can't detect it (the
    # heading's glyphs remain in the content stream regardless of paint
    # order). Fix: always clamp the table's top to at least 20pt below
    # wherever the heading actually landed for *this* plot's geometry, so
    # the invariant holds for any plot size without hardcoding a bound.
    plot_py = cfg.plot_length * s
    heading_y = oy + plot_py + 20
    table_y_top = min(page_h - MARGIN - 30, heading_y - 20)

    headers = ("TYPE", "SIZE (L×B m)", "DEPTH (mm)", "BARS-X", "BARS-Y")
    col_ws = (40.0, 80.0, 55.0, 100.0, 100.0)
    rows: list[tuple[str, str, str, str, str]] = []
    for ftype, f in sorted(footings_data.items()):
        d = f.get("data", {})
        bars_x, bars_y = d.get("bars_x", {}), d.get("bars_y", {})
        # `.get(..., "-")` renders as e.g. "-mmø@-c/c" when bar data is
        # missing for a footing type -- accepted display quirk for
        # incomplete input data, not worth a bigger reformat for.
        rows.append(
            (
                _FOOTING_MARK.get(ftype, "T?"),
                f"{d.get('L_m', 0):.2f}x{d.get('B_m', 0):.2f}",
                f"{d.get('D_overall_mm', 0):.0f}",
                f"{bars_x.get('dia', '-')}mmø@{bars_x.get('spacing', '-')}c/c",
                f"{bars_y.get('dia', '-')}mmø@{bars_y.get('spacing', '-')}c/c",
            )
        )
    _draw_generic_schedule_table(
        c, "FOOTING SCHEDULE", headers, col_ws, rows, MARGIN, table_y_top
    )
    table_bottom = table_y_top - _generic_schedule_height(len(rows))

    if footings_data:
        _largest_type, largest = max(
            footings_data.items(),
            key=lambda kv: (
                kv[1].get("data", {}).get("L_m", 0)
                * kv[1].get("data", {}).get("B_m", 0)
            ),
        )
        largest_data = largest.get("data", {})
        # Vertical span the typical-section schematic needs *above* its own
        # y-origin: column stub (40pt) + heading-text gap (40pt) + the
        # footing slab's own height in points. Same invariant as the table
        # clamp above -- never let the (fixed-target) typical section climb
        # high enough to collide with the schedule table sitting above it,
        # regardless of plot size or footing depth.
        fh_pts = largest_data.get("D_overall_mm", 450) * _FOOTING_SECTION_PX_PER_MM
        section_span_above_y = fh_pts + 80
        typical_y = min(page_h - 320, table_bottom - section_span_above_y - 20)
        typical_y = max(typical_y, TITLE_H + 40)
        _draw_typical_footing_section(c, largest_data, MARGIN, typical_y)

    _draw_title_block(
        c,
        project_name,
        "A",
        "Footing Details",
        "Footing Details",
        cfg,
        _NUM_BEDROOMS_NA,
        s,
        page_w,
        scale_denom=denom,
    )


def render_plinth_beam_plan(
    c: canvas.Canvas,
    walls: list[WallSegment],
    plinth_beams_data: dict[str, Any],
    cfg: PlotConfig,
    project_name: str,
) -> None:
    """Render the "PLINTH BEAM PLAN" sheet: each wall centreline drawn as a
    beam line, labelled with a short `PB<n>` mark. Marks are assigned by
    sorting `plinth_beams_data`'s groups by span (ascending) and numbering
    them in that order -- unlike `_FOOTING_MARK`, plinth-beam groups aren't a
    fixed small set (they depend on the actual wall layout), so the mapping
    is built dynamically per call rather than as a module constant.

    A wall segment whose recomputed `(kind, round(length, 1))` group key has
    no entry in `plinth_beams_data` (e.g. stale/mismatched input) is drawn
    but left unlabelled rather than given a fabricated placeholder mark --
    an unlabelled beam line is still useful, a made-up mark would mislead.
    """
    page_w, _page_h = A4
    ox, oy, s, denom = _draw_sheet_frame(c, cfg, "PLINTH BEAM PLAN")

    sorted_keys = sorted(
        plinth_beams_data.keys(), key=lambda k: plinth_beams_data[k]["span_m"]
    )
    mark_by_key = {k: f"PB{i + 1}" for i, k in enumerate(sorted_keys)}

    # Two passes, same convention as render_column_footing_plan: draw every
    # beam line first with one color/width state, reset, then draw labels.
    c.setStrokeColor(HexColor("#0088AA"))
    c.setLineWidth(1.5)
    labels = []
    for w in walls:
        x1, y1 = ox + w.x1 * s, oy + w.y1 * s
        x2, y2 = ox + w.x2 * s, oy + w.y2 * s
        c.line(x1, y1, x2, y2)
        key = f"plinth-{w.kind}-span{round(w.length, 1):.2f}"
        mark = mark_by_key.get(key)
        if mark is not None:
            labels.append(((x1 + x2) / 2, (y1 + y2) / 2, mark))
    c.setLineWidth(1)
    c.setStrokeColor(HexColor("#000000"))

    c.setFont("Helvetica-Bold", 6)
    c.setFillColor(HexColor("#000000"))
    for mx, my, mark in labels:
        c.drawCentredString(mx, my + 4, mark)

    _draw_title_block(
        c,
        project_name,
        "A",
        "Plinth Beam Plan",
        "Plinth Beam Plan",
        cfg,
        _NUM_BEDROOMS_NA,
        s,
        page_w,
        scale_denom=denom,
    )


def _draw_typical_footing_section(
    c: canvas.Canvas, data: dict[str, Any], x: float, y: float
) -> None:
    """Schematic dimensioned cross-section of one representative footing:
    PCC bed, footing slab with schematic mat-reinforcement hatch lines, and
    a column stub on top. Simplified pictorial, not a precise CAD drawing --
    see docs/plans/2026-07-19-structural-drawing-set-design.md.
    """
    l_mm = data.get("L_m", 1.0) * 1000
    d_mm = data.get("D_overall_mm", 450)
    fw = l_mm * _FOOTING_SECTION_PX_PER_MM
    fh = d_mm * _FOOTING_SECTION_PX_PER_MM

    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(HexColor("#000000"))
    c.drawString(x, y + fh + 40, "TYPICAL FOOTING SECTION")

    c.setFillColor(HexColor("#DDDDDD"))
    c.rect(x, y - 10, fw, 10, fill=1, stroke=1)
    c.setFillColor(HexColor("#EEEEEE"))
    c.rect(x, y, fw, fh, fill=1, stroke=1)

    c.setStrokeColor(HexColor("#AA0000"))
    c.setLineWidth(0.5)
    for i in range(1, 6):
        xi = x + fw * i / 6
        c.line(xi, y + 3, xi, y + fh - 3)

    col_w = fw * 0.25
    c.setFillColor(HexColor("#CCCCCC"))
    c.rect(x + fw / 2 - col_w / 2, y + fh, col_w, 40, fill=1, stroke=1)

    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 6)
    c.drawCentredString(
        x + fw / 2,
        y - 20,
        f"{data.get('L_m', 0):.2f} x {data.get('B_m', 0):.2f} m, D={d_mm:.0f}mm",
    )


def _draw_beam_detail_box(
    c: canvas.Canvas,
    mark: str,
    b_mm: float,
    D_mm: float,
    design: dict[str, Any],
    x: float,
    y: float,
    px_per_mm: float = _BEAM_SECTION_PX_PER_MM,
) -> float:
    """Dimensioned rectangular beam cross-section pictorial (b x D, scaled by
    `px_per_mm`) showing the envelope reinforcement: tension bars along the
    bottom edge, compression bars along the top when doubly reinforced, and a
    stirrup-spacing note. structapi returns ONE envelope schedule per beam
    mark (worst-case moment over the whole span), so a single section is
    drawn -- never a midspan/support split. See
    docs/plans/2026-07-19-structural-drawing-set-design.md simplification #7.

    Returns the vertical height in points consumed (box + heading + margin),
    so callers stacking boxes down a page know how far to advance `y`.
    """
    bw = b_mm * px_per_mm
    bh = D_mm * px_per_mm

    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(HexColor("#000000"))
    c.drawString(x, y + bh + 24, f"{mark}-{b_mm:.0f}x{D_mm:.0f}mm")

    c.setFillColor(white)
    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.75)
    c.rect(x, y, bw, bh, fill=1, stroke=1)

    cover = 6.0
    radius = 1.5
    label_x = x + bw + 6
    bar_dia = design.get("bar_dia", 0)

    c.setFillColor(HexColor("#AA0000"))
    n_bars = design.get("n_bars", 0)
    if n_bars > 0:
        by = y + cover
        if n_bars == 1:
            xs = [x + bw / 2]
        else:
            span = bw - 2 * cover
            xs = [x + cover + span * i / (n_bars - 1) for i in range(n_bars)]
        for bx in xs:
            c.circle(bx, by, radius, fill=1, stroke=0)
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica", 5.5)
        c.drawString(label_x, y + cover - 2, f"Bot {n_bars}nos-{bar_dia:.0f}mmø")

    n_comp = design.get("n_bars_comp", 0)
    if design.get("doubly_reinforced") and n_comp > 0:
        c.setFillColor(HexColor("#AA0000"))
        by = y + bh - cover
        if n_comp == 1:
            xs = [x + bw / 2]
        else:
            span = bw - 2 * cover
            xs = [x + cover + span * i / (n_comp - 1) for i in range(n_comp)]
        for bx in xs:
            c.circle(bx, by, radius, fill=1, stroke=0)
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica", 5.5)
        c.drawString(label_x, y + bh - cover - 2, f"Top {n_comp}nos-{bar_dia:.0f}mmø")

    sv = (design.get("stirrups") or {}).get("sv_provided", "-")
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 5.5)
    c.drawString(label_x, y + bh / 2 - 2, f"stirrups@{sv}c/c")

    return bh + 40
