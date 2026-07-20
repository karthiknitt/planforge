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

from reportlab.lib.colors import HexColor
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
    _draw_north_arrow,
    _draw_title_block,
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
