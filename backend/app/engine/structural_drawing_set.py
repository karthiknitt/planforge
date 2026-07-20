"""Structural Drawing Set: 6-sheet CAD-style PDF (Column & Footing Plan,
Footing Details, Plinth Beam Plan, Plinth Beam Details, Roof Beam & Slab
Plan, Roof Beam Details) built on structapi's IS-456 member design.

See docs/plans/2026-07-19-structural-drawing-set-design.md for the full
design rationale and documented simplifications (isolated footings only,
single wall height for plinth UDL, no seismic overlay on plinth beams, one
reinforcement schedule per beam mark rather than midspan/support split).
"""

from __future__ import annotations

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.footing_placement import place_footings
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


def render_column_footing_plan(
    c: canvas.Canvas,
    columns,
    walls,
    footings_data: dict,
    cfg,
    project_name: str,
) -> None:
    """Render the "COLUMN & FOOTING PLAN" sheet: plot boundary, north arrow,
    title block, and each column's footing drawn as a dashed rectangle
    (sized per `place_footings()`) centred on the column position, labelled
    with its footing-type mark.
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

    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(page_w / 2, oy + plot_py + 20, "COLUMN & FOOTING PLAN")

    c.setLineWidth(1.0)
    c.setStrokeColor(HexColor("#000000"))
    c.rect(ox, oy, plot_px, plot_py, fill=0, stroke=1)

    placed = place_footings(columns, walls, footings_data)
    c.setDash(3, 2)
    c.setStrokeColor(HexColor("#0088AA"))
    for f in placed:
        fx, fy = ox + f.cx * s, oy + f.cy * s
        fw, fh = f.length_m * s, f.width_m * s
        c.rect(fx - fw / 2, fy - fh / 2, fw, fh, fill=0, stroke=1)
        c.setDash()
        c.setFont("Helvetica-Bold", 6)
        c.setFillColor(HexColor("#000000"))
        c.drawCentredString(
            fx, fy + fh / 2 + 4, _FOOTING_MARK.get(f.footing_type, "T?")
        )
        c.setDash(3, 2)
    c.setDash()

    _draw_north_arrow(c, ox + plot_px - 20, oy + plot_py - 20, 12)
    _draw_title_block(
        c,
        project_name,
        "A",
        "Column & Footing Plan",
        "Column & Footing Plan",
        cfg,
        0,
        s,
        page_w,
        scale_denom=denom,
    )
