"""Structural Drawing Set: the 12-sheet construction-grade PDF.

    S-01  GENERAL NOTES & SPECIFICATIONS
    S-02  COLUMN & FOOTING PLAN
    S-03  FOOTING DETAILS
    S-04  COLUMN DETAILS & SCHEDULE
    S-05  PLINTH BEAM PLAN
    S-06  PLINTH BEAM DETAILS
    S-07  GF ROOF / FF FLOOR BEAM & SLAB PLAN
    S-08  GF ROOF BEAM DETAILS
    S-09  FF ROOF BEAM & SLAB PLAN
    S-10  FF ROOF BEAM DETAILS
    S-11  SLAB REINFORCEMENT DETAILS
    S-12  STAIRCASE DETAILS

This module is only the orchestrator. Sheet content lives in
`structural_sheets_*.py`, all page furniture in `structural_sheet.py`, and
every sheet reads from the typed model built by `structural_data.py` rather
than from structapi's raw response.

Both floors are covered. structapi designs one framing grid for the whole
building (see `structural_data`), so S-07/S-08 and S-09/S-10 are the *same*
renderers invoked once per `FloorFraming` — the level label, drawing number
and geometry underlay come from the framing record, not from duplicated code.

Sheets may run to more than one page: a renderer returns the number of pages
it drew and paginates internally rather than truncating its content.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.models import Layout, PlotConfig
from app.engine.structural_data import StructuralModel, build_structural_model
from app.engine.structural_sheets_foundation import (
    render_column_details,
    render_column_footing_plan,
    render_footing_details,
)
from app.engine.structural_sheets_framing import (
    render_framing_details,
    render_framing_plan,
    render_plinth_beam_details,
    render_plinth_beam_plan,
)
from app.engine.structural_sheets_notes import render_general_notes
from app.engine.structural_sheets_slab_stair import (
    render_slab_reinforcement_details,
    render_staircase_details,
)


def _sheet_sequence(model: StructuralModel) -> list:
    """Renderer thunks in drawing-number order.

    The two framing levels are appended from `model.floors` rather than
    written out twice, so a set can never end up with one floor detailed and
    the other missing.
    """
    sheets: list = [
        lambda c: render_general_notes(c, model),
        lambda c: render_column_footing_plan(c, model),
        lambda c: render_footing_details(c, model),
        lambda c: render_column_details(c, model),
        lambda c: render_plinth_beam_plan(c, model),
        lambda c: render_plinth_beam_details(c, model),
    ]
    for framing in model.floors:
        sheets.append(
            lambda c, f=framing: render_framing_plan(c, model, f),
        )
        sheets.append(
            lambda c, f=framing: render_framing_details(c, model, f),
        )
    sheets.append(lambda c: render_slab_reinforcement_details(c, model))
    sheets.append(lambda c: render_staircase_details(c, model))
    return sheets


def generate_structural_drawing_set(
    *,
    project_name: str,
    cfg: PlotConfig,
    layout: Layout,
    structural_design: dict[str, Any],
    plinth_beams_data: dict[str, Any] | None = None,
) -> bytes:
    """Render the full set for one approved + designed layout."""
    model = build_structural_model(
        project_name=project_name,
        cfg=cfg,
        layout=layout,
        structural_design=structural_design,
        plinth_beams_data=plinth_beams_data or {},
    )

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for render in _sheet_sequence(model):
        render(c)
        c.showPage()
    c.save()
    return buf.getvalue()
