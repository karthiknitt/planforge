"""Sheet S-01 – General Notes & Specifications.

A site engineer reads this sheet first. It contains materials specifications,
foundation details, reinforcement rules, curing requirements, codes of practice,
and any design warnings or conditions that apply to the whole set.
"""

from __future__ import annotations

from datetime import date

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.pdf import (
    MARGIN,
    TITLE_H,
    _draw_generic_schedule_table,
)
from app.engine.structural_data import StructuralModel
from app.engine.structural_sheet import (
    SHEET_TITLES,
    detail_sheet_frame,
    draw_disclaimer,
    paginate_boxes,
    structural_title_block,
)


def render_general_notes(c: canvas.Canvas, model: StructuralModel) -> int:
    """Render S-01 GENERAL NOTES & SPECIFICATIONS sheet(s).

    Draws material specs, foundation notes, reinforcement rules, curing
    requirements, codes of practice, design basis, violations (if any), and
    grid review warnings (if needed).

    Returns the number of pages drawn (1 or more).
    """
    page_w, page_h = A4
    page_count = 0

    # Assemble all text boxes (each is a list of lines)
    boxes = []

    # 1. MATERIALS
    boxes.append(_make_materials_box(model))

    # 2. FOUNDATIONS
    boxes.append(_make_foundations_box(model))

    # 3. REINFORCEMENT
    boxes.append(_make_reinforcement_box())

    # 4. CONCRETING & CURING
    boxes.append(_make_concreting_box())

    # 5. CODES OF PRACTICE
    boxes.append(_make_codes_box(model))

    # 6. GENERAL
    boxes.append(_make_general_box())

    # Additional structured blocks
    structured = []

    # Revision table
    if model.changelog:
        structured.append(("revision", model.changelog))

    # Design basis (if assumptions provided)
    if model.assumptions:
        structured.append(("assumptions", model.assumptions))

    # Unresolved checks (if any)
    if model.violations:
        structured.append(("violations", model.violations))

    # Grid review warning (if not confident)
    if not model.grid.confident and model.grid.notes:
        structured.append(("grid_review", model.grid.notes))

    # Paginate text boxes into pages
    pages = paginate_boxes(
        boxes,
        height_of=lambda box: _text_box_height(box),
        top=page_h - MARGIN - TITLE_H - 20,
        bottom=MARGIN + 60,  # Reserve space for title block + disclaimer
        gap=12,
    )

    # Render text pages
    for page_idx, page_boxes in enumerate(pages):
        frame = detail_sheet_frame(
            c,
            heading="GENERAL NOTES & SPECIFICATIONS",
            drg_no="S-01",
            continued=page_idx > 0,
        )
        y = frame.y1 - 8

        for box in page_boxes:
            y = _draw_text_box(c, box, frame.x0, y, leading=8.0)
            y -= 12  # gap between boxes

        # Render structured blocks on remaining space if any
        for block_type, data in structured:
            if y - 60 < frame.y0:
                break  # Not enough space, defer to next page
            if block_type == "revision":
                h = _draw_revision_table(c, data, frame.x0, y)
                y -= h + 12
            elif block_type == "assumptions":
                h = _draw_design_basis(c, data, frame.x0, y)
                y -= h + 12
            elif block_type == "violations":
                h = _draw_violations_block(c, data, frame.x0, y)
                y -= h + 12
            elif block_type == "grid_review":
                h = _draw_grid_review_warning(c, data, frame.x0, y)
                y -= h + 12

        # Title block + disclaimer
        structural_title_block(
            c,
            project_name=model.project_name,
            cfg=model.cfg,
            drg_no="S-01",
            sheet_title=SHEET_TITLES["S-01"],
            page_w=page_w,
            scale_text="NTS",
            layout_label=model.layout_label,
        )
        draw_disclaimer(c, model.disclaimer, MARGIN, MARGIN - 8)

        page_count += 1
        if page_idx < len(pages) - 1:
            c.showPage()

    return page_count


# ── Text box construction ────────────────────────────────────────────────────


def _make_materials_box(model: StructuralModel) -> list[str]:
    """Return lines for MATERIALS section."""
    mat = model.materials or {}
    fck = mat.get("fck", "30")
    fy = mat.get("fy", "500")
    exposure = mat.get("exposure", "mild")

    lines = ["1. MATERIALS"]
    lines.append(f"  Concrete Grade: M{fck} (fck = {fck} N/mm²)")
    lines.append(f"  Steel Grade: Fe{fy} (fy = {fy} N/mm²)")
    lines.append(f"  Exposure Condition: {exposure.upper()}")
    lines.append("  Nominal Cover (IS 456:2000 Table 16):")
    lines.append("    - Footing: 50 mm")
    lines.append("    - Column: 40 mm")
    lines.append("    - Beam: 25 mm")
    lines.append("    - Slab: 20 mm")
    return lines


def _make_foundations_box(model: StructuralModel) -> list[str]:
    """Return lines for FOUNDATIONS section."""
    mat = model.materials or {}
    sbc = mat.get("sbc_kpa", "150")

    lines = ["2. FOUNDATIONS"]
    lines.append(f"  Safe Bearing Capacity: {sbc} kPa")
    lines.append("  Founding Depth: As recommended by soil test report")
    lines.append("  PCC Bed: 100 mm of M10 concrete under all footings")
    lines.append("  IMPORTANT: SBC must be confirmed by site soil test")
    lines.append("  before construction begins.")
    return lines


def _make_reinforcement_box() -> list[str]:
    """Return lines for REINFORCEMENT section."""
    lines = ["3. REINFORCEMENT"]
    lines.append("  Lap Length: 50φ in tension; 40φ in compression")
    lines.append("  Development Length: As per IS 456:2000, Clause 26.2.1")
    lines.append("  Cover Blocks: Concrete or plastic, as approved")
    lines.append("  Hooks & Bends: Per IS 2502:2019")
    lines.append("  No lapping at points of maximum stress")
    lines.append("  Stagger laps wherever possible")
    return lines


def _make_concreting_box() -> list[str]:
    """Return lines for CONCRETING & CURING section."""
    lines = ["4. CONCRETING & CURING"]
    lines.append("  Minimum Curing: 7 days for all concrete")
    lines.append("  Slump: Site-specific per design engineer direction")
    lines.append("  No construction joints at midspan of beams")
    lines.append("  Formwork removal: Not before 7 days (beam/slab)")
    return lines


def _make_codes_box(model: StructuralModel) -> list[str]:
    """Return lines for CODES OF PRACTICE section."""
    mat = model.materials or {}
    seismic = mat.get("seismic_zone", "II")
    lateral = model.lateral or {}

    lines = ["5. CODES OF PRACTICE & DESIGN CRITERIA"]
    lines.append("  IS 456:2000 - Plain & Reinforced Concrete Code")
    lines.append("  IS 875 (Parts 1–3) - Code of Practice for Loads")
    lines.append(f"  IS 1893 (Part 1) - Seismic Design Code (Zone {seismic})")
    lines.append("  IS 13920 - Ductile Detailing of Reinforced Concrete")
    lines.append("  IS 2502:2019 - Steel Reinforcement for Concrete")
    lines.append("  IS 962:1989 - Code of Practice for Presentation of")
    lines.append("    Structural Drawings in Building Works")
    if lateral:
        case = lateral.get("case", "unknown")
        base_shear = lateral.get("base_shear_kn", 0)
        lines.append(f"  Governing Lateral Case: {case}")
        if base_shear > 0:
            lines.append(f"  Base Shear: {base_shear:.1f} kN")
    return lines


def _make_general_box() -> list[str]:
    """Return lines for GENERAL section."""
    lines = ["6. GENERAL"]
    lines.append("  All dimensions are in millimetres unless otherwise noted")
    lines.append("  Do not scale drawings for construction")
    lines.append("  Report discrepancies to the structural engineer before")
    lines.append("    proceeding with construction")
    lines.append("  This drawing must be read with the architectural set")
    return lines


def _text_box_height(box: list[str]) -> float:
    """Height in points for a text box (lines at 8 pt leading)."""
    return len(box) * 8.0


def _draw_text_box(
    c: canvas.Canvas,
    lines: list[str],
    x: float,
    y_top: float,
    leading: float = 8.0,
) -> float:
    """Draw a text box and return the y of the line below it."""
    y = y_top
    for i, line in enumerate(lines):
        is_heading = (
            line.startswith(tuple(str(d) for d in range(1, 10))) and "." in line[:3]
        )
        c.setFont(
            "Helvetica-Bold" if is_heading else "Helvetica", 6 if is_heading else 5.5
        )
        c.setFillColor(HexColor("#000000"))
        c.drawString(x, y, line)
        y -= leading
    return y


def _draw_revision_table(
    c: canvas.Canvas, changelog: list[str], x: float, y_top: float
) -> float:
    """Draw revision table with one row per changelog entry plus ISSUED row."""
    rows = []

    # Base row: "A / <today> / ISSUED FOR CONSTRUCTION"
    today_str = date.today().strftime("%d %b %Y")
    rows.append(("A", today_str, "ISSUED FOR CONSTRUCTION"))

    # Add changelog entries (expected format: "Rev-Date-Description" or just "Description")
    for entry in changelog:
        parts = entry.split(" / ")
        if len(parts) == 3:
            rows.append((parts[0], parts[1], parts[2]))
        else:
            rows.append(("", "", entry))

    # Title and draw
    headers = ("REV", "DATE", "DESCRIPTION")
    col_ws = (40.0, 70.0, 180.0)  # Sum = 290 points, fits in frame

    return _draw_generic_schedule_table(
        c,
        title="REVISION TABLE",
        headers=headers,
        col_ws=col_ws,
        rows=rows,
        x=x,
        y_top=y_top,
    )


def _draw_design_basis(
    c: canvas.Canvas, assumptions: list[str], x: float, y_top: float
) -> float:
    """Draw design basis block from assumptions."""
    c.setFont("Helvetica-Bold", 6)
    c.setFillColor(HexColor("#000000"))
    c.drawString(x, y_top, "DESIGN BASIS")

    y = y_top - 10
    c.setFont("Helvetica", 5.5)
    for assumption in assumptions:
        c.drawString(x + 6, y, f"• {assumption}")
        y -= 7

    return y_top - y


def _draw_violations_block(
    c: canvas.Canvas, violations: list[dict], x: float, y_top: float
) -> float:
    """Draw unresolved design checks block (prominently)."""
    c.setFont("Helvetica-Bold", 6)
    c.setFillColor(HexColor("#CC0000"))  # Red for prominence
    c.drawString(x, y_top, "⚠ UNRESOLVED DESIGN CHECKS")

    y = y_top - 10
    c.setFont("Helvetica", 5.5)
    c.setFillColor(HexColor("#000000"))
    for v in violations:
        check = v.get("check", "unknown")
        member = v.get("member_type", "")
        actual = v.get("actual", "—")
        limit = v.get("limit", "—")
        line = f"{check} ({member}): {actual} vs limit {limit}"
        c.drawString(x + 6, y, line)
        y -= 7

    return y_top - y


def _draw_grid_review_warning(
    c: canvas.Canvas, notes: list[str], x: float, y_top: float
) -> float:
    """Draw grid review required warning."""
    c.setFont("Helvetica-Bold", 6)
    c.setFillColor(HexColor("#FF6600"))  # Orange for caution
    c.drawString(x, y_top, "⚠ GRID REVIEW REQUIRED")

    y = y_top - 10
    c.setFont("Helvetica", 5.5)
    c.setFillColor(HexColor("#000000"))
    for note in notes:
        c.drawString(x + 6, y, f"• {note}")
        y -= 7

    return y_top - y
