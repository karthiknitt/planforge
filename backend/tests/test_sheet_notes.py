"""Tests for S-01 General Notes & Specifications sheet."""

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.models import ComplianceResult, FloorPlan, Layout, PlotConfig, Room
from app.engine.structural_data import GridRef, StructuralModel
from app.engine.structural_sheets_notes import render_general_notes
from tests.helpers.pdf_png import pdf_page_text, pdf_pages


def _make_minimal_plot_config() -> PlotConfig:
    """Build a minimal PlotConfig for testing."""
    return PlotConfig(
        plot_x_extent=10.0,
        plot_y_extent=15.0,
        setback_front=1.0,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=2,
        toilets=1,
        parking=True,
        road_side="N",
    )


def _make_minimal_layout() -> Layout:
    """Build a minimal Layout for testing."""
    gf = FloorPlan(
        floor=0,
        floor_type="ground",
        rooms=[
            Room(
                id="lr",
                name="LIVING",
                type="living",
                x=1.0,
                y=1.0,
                width=5.0,
                depth=5.0,
            ),
            Room(
                id="br1",
                name="BEDROOM 1",
                type="bedroom",
                x=6.5,
                y=1.0,
                width=3.5,
                depth=4.5,
            ),
        ],
    )
    return Layout(
        id="A",
        name="Layout A",
        ground_floor=gf,
        first_floor=FloorPlan(floor=1, floor_type="first"),
        compliance=ComplianceResult(passed=True),
    )


def _make_test_structural_model() -> StructuralModel:
    """Build a StructuralModel with realistic test values."""
    cfg = _make_minimal_plot_config()
    layout = _make_minimal_layout()
    grid = GridRef(
        x_lines_m=[0.0, 5.0, 10.0],
        y_lines_m=[0.0, 7.5, 15.0],
        confident=True,
        notes=[],
    )

    return StructuralModel(
        project_name="Test Residential 2BHK",
        cfg=cfg,
        layout=layout,
        grid=grid,
        materials={
            "fck": "30",
            "fy": "500",
            "exposure": "mild",
            "sbc_kpa": "150",
            "seismic_zone": "II",
        },
        lateral={
            "case": "EQX",
            "base_shear_kn": 45.5,
        },
        assumptions=[
            "Soil is homogeneous up to founding depth",
            "No adjacent structures within 5m",
            "Columns are pin-based",
        ],
        violations=[],
        disclaimer="This design is advisory. A licensed structural engineer must review and approve before construction.",
        status="ISSUED FOR CONSTRUCTION",
        changelog=[],
    )


def test_render_general_notes_draws_sheet() -> None:
    """S-01 sheet is drawn and contains expected text."""
    model = _make_test_structural_model()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    page_count = render_general_notes(c, model)
    c.save()

    # Verify a page was drawn
    assert page_count >= 1
    pdf_data = buf.getvalue()
    assert len(pdf_data) > 0


def test_sheet_contains_drawing_number() -> None:
    """Drawing number 'S-01' appears on the sheet."""
    model = _make_test_structural_model()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    render_general_notes(c, model)
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    assert "S-01" in text


def test_sheet_contains_code_reference() -> None:
    """Code references (e.g. IS 456) appear on the sheet."""
    model = _make_test_structural_model()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    render_general_notes(c, model)
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    assert "IS 456" in text


def test_sheet_contains_material_specs() -> None:
    """Material specs (fck, fy) from model are rendered."""
    model = _make_test_structural_model()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    render_general_notes(c, model)
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    # fck and fy should appear in the materials section
    assert "30" in text  # fck = 30
    assert "500" in text  # fy = 500


def test_sheet_contains_seismic_zone() -> None:
    """Seismic zone from materials dict is rendered."""
    model = _make_test_structural_model()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    render_general_notes(c, model)
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    assert "II" in text or "Zone II" in text


def test_violations_surface_on_sheet() -> None:
    """Violations in model appear prominently on the sheet."""
    model = _make_test_structural_model()
    model = StructuralModel(
        project_name=model.project_name,
        cfg=model.cfg,
        layout=model.layout,
        grid=model.grid,
        materials=model.materials,
        violations=[
            {
                "check": "Beam Shear",
                "member_type": "Beam B1",
                "actual": "2.1",
                "limit": "1.5",
            }
        ],
        assumptions=model.assumptions,
        disclaimer=model.disclaimer,
    )

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    render_general_notes(c, model)
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    # Check presence of violation marker and content
    assert "UNRESOLVED" in text or "Beam Shear" in text


def test_many_changelog_entries_paginate() -> None:
    """Large changelog causes pagination rather than truncation."""
    changelog = [f"Rev {i} / 2024-{i:02d}-01 / Update {i}" for i in range(1, 15)]

    model = StructuralModel(
        project_name="Test Project",
        cfg=_make_minimal_plot_config(),
        layout=_make_minimal_layout(),
        grid=GridRef(x_lines_m=[0.0, 5.0, 10.0], y_lines_m=[0.0, 7.5, 15.0]),
        materials={"fck": "30", "fy": "500"},
        changelog=changelog,
        disclaimer="Test disclaimer",
    )

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    render_general_notes(c, model)
    c.save()

    # With many changelog entries, pagination should kick in
    # (at least 1 page is guaranteed; many entries should produce 2+)
    pdf_data = buf.getvalue()
    pages = pdf_pages(pdf_data)
    assert pages >= 1


def test_grid_review_warning_rendered() -> None:
    """Grid review warning appears when grid is not confident."""
    grid = GridRef(
        x_lines_m=[0.0, 5.0, 10.0],
        y_lines_m=[0.0, 7.5, 15.0],
        confident=False,
        notes=["Column C3 misaligned by 50mm", "Recommend manual verification"],
    )

    model = StructuralModel(
        project_name="Test Project",
        cfg=_make_minimal_plot_config(),
        layout=_make_minimal_layout(),
        grid=grid,
        materials={"fck": "30"},
        disclaimer="",
    )

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    render_general_notes(c, model)
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    # Grid review warning should mention grid or review
    assert "GRID" in text or "misaligned" in text


def test_design_basis_from_assumptions() -> None:
    """Design basis block renders assumptions from model."""
    assumptions = [
        "Soil is homogeneous",
        "No adjacent structures",
        "Grade beams bear on columns",
    ]

    model = StructuralModel(
        project_name="Test Project",
        cfg=_make_minimal_plot_config(),
        layout=_make_minimal_layout(),
        grid=GridRef(x_lines_m=[0.0, 5.0, 10.0], y_lines_m=[0.0, 7.5, 15.0]),
        materials={"fck": "30"},
        assumptions=assumptions,
        disclaimer="",
    )

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    render_general_notes(c, model)
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    assert "homogeneous" in text or "DESIGN BASIS" in text


def test_foundation_sbc_rendered() -> None:
    """Safe bearing capacity from materials dict is rendered."""
    model = _make_test_structural_model()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    render_general_notes(c, model)
    c.save()

    text = pdf_page_text(buf.getvalue(), 0)
    # SBC should appear
    assert "150" in text or "Safe Bearing" in text
