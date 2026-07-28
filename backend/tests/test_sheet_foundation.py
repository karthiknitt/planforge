"""Tests for S-02/S-03/S-04 (Column & Footing Plan, Footing Details, Column
Details & Schedule) — app.engine.structural_sheets_foundation."""

from __future__ import annotations

import os
import tempfile
from io import BytesIO

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine import generator
from app.engine.models import ComplianceResult, FloorPlan, Layout, PlotConfig
from app.engine.structural_data import (
    ColumnItem,
    FootingItem,
    GridRef,
    StructuralModel,
    build_structural_model,
)
from app.engine.structural_sheets_foundation import (
    _parse_bars,
    _perimeter_points,
    bar_count,
    render_column_details,
    render_column_footing_plan,
    render_footing_details,
)
from tests.helpers.pdf_png import pdf_page_text, pdf_pages

SAMPLE_DIR = os.environ.get("PLANFORGE_SAMPLE_DIR", tempfile.gettempdir())

CFG = PlotConfig(
    plot_length=9.0,
    plot_width=8.0,
    setback_front=3.0,
    setback_rear=1.5,
    setback_left=1.0,
    setback_right=1.0,
    num_bedrooms=2,
    toilets=2,
    parking=True,
)

# Proven-generatable config (mirrors tests/test_column_consistency.py) for the
# module fixture that runs the real generator — CFG above rejects at the
# navigability gate on this codebase revision.
GENERATE_CFG = PlotConfig(
    plot_width=10.0,
    plot_length=15.2,
    num_bedrooms=3,
    setback_front=1.5,
    setback_rear=1.5,
    setback_left=0.9,
    setback_right=0.9,
    toilets=2,
    parking=True,
    city="other",
    road_side="S",
    vastu_enabled=False,
)

_STRUCTAPI_DESIGN = {
    "structapi": {
        "disclaimer": "Advisory design — a licensed engineer must review before construction.",
        "data": {
            "columns": {
                "corner": {"b_mm": 300, "D_mm": 300, "bars": "6-16"},
                "edge": {"b_mm": 300, "D_mm": 350, "bars": "8-16"},
                "interior": {"b_mm": 350, "D_mm": 350, "bars": "8-20"},
            },
            "footings": {
                "corner": {
                    "data": {
                        "L_m": 1.35,
                        "B_m": 1.35,
                        "D_overall_mm": 450,
                        "bars_x": {"dia": 12, "spacing": 150},
                        "bars_y": {"dia": 12, "spacing": 150},
                    }
                },
                "edge": {
                    "data": {
                        "L_m": 1.6,
                        "B_m": 1.5,
                        "D_overall_mm": 500,
                        "bars_x": {"dia": 12, "spacing": 125},
                        "bars_y": {"dia": 16, "spacing": 150},
                    }
                },
                "interior": {
                    "data": {
                        "L_m": 1.8,
                        "B_m": 1.8,
                        "D_overall_mm": 600,
                        "bars_x": {"dia": 16, "spacing": 100},
                        "bars_y": {"dia": 16, "spacing": 100},
                    }
                },
            },
        },
    }
}


@pytest.fixture(scope="module")
def real_model() -> StructuralModel:
    """A `StructuralModel` built from an actually-generated layout, so S-02's
    grid/gf_drawing/column-classification path exercises real geometry
    rather than a hand-built stand-in. Generation is slow (~20s), so this
    fixture builds it once for every test in this module."""
    layouts = generator.generate(GENERATE_CFG)
    assert layouts, "generator.generate produced no layouts for the fixture plot"
    layout = layouts[0]
    return build_structural_model(
        project_name="Test Project",
        cfg=GENERATE_CFG,
        layout=layout,
        structural_design=_STRUCTAPI_DESIGN,
    )


def _minimal_layout() -> Layout:
    empty = FloorPlan(floor=0, floor_type="ground", rooms=[])
    return Layout(
        id="T",
        name="Test Layout",
        ground_floor=empty,
        first_floor=FloorPlan(floor=1, floor_type="first", rooms=[]),
        compliance=ComplianceResult(passed=True),
    )


def _synthetic_model(
    footings: list[FootingItem], columns: list[ColumnItem]
) -> StructuralModel:
    return StructuralModel(
        project_name="Synthetic Project",
        cfg=CFG,
        layout=_minimal_layout(),
        grid=GridRef(),
        gf_drawing=None,
        columns=columns,
        footings=footings,
        disclaimer="Advisory — engineer sign-off required.",
    )


def _render_to_pdf(render_fn, model: StructuralModel, out_name: str) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    render_fn(c, model)
    c.save()
    pdf_bytes = buf.getvalue()
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    with open(os.path.join(SAMPLE_DIR, out_name), "wb") as fh:
        fh.write(pdf_bytes)
    return pdf_bytes


# ── S-02 ─────────────────────────────────────────────────────────────────


def test_column_footing_plan_draws_footings_columns_grid_and_schedule(real_model):
    pdf_bytes = _render_to_pdf(render_column_footing_plan, real_model, "s02.pdf")
    assert pdf_pages(pdf_bytes) == 1
    text = pdf_page_text(pdf_bytes, 0)
    assert "COLUMN & FOOTING PLAN" in text.upper()
    assert "DRG. NO. S-02" in text.upper()
    assert "FOOTING SCHEDULE" in text.upper()
    # every footing mark that actually got placed must appear on the plan
    for f in real_model.footings:
        assert f.mark in text
    # every column tag must appear too
    for col in real_model.columns:
        assert col.tag in text


def test_column_footing_plan_renders_without_crashing_when_grid_not_confident():
    model = _synthetic_model(
        footings=[
            FootingItem(
                mark="T1",
                footing_class="corner",
                cx=1.0,
                cy=1.0,
                length_m=1.35,
                width_m=1.35,
                depth_mm=450,
                design={
                    "bars_x": {"dia": 12, "spacing": 150},
                    "bars_y": {"dia": 12, "spacing": 150},
                },
            )
        ],
        columns=[
            ColumnItem(
                tag="C1",
                mark="C1",
                col_class="corner",
                cx=1.0,
                cy=1.0,
                b_mm=300,
                D_mm=300,
                bars="6-16",
            )
        ],
    )
    pdf_bytes = _render_to_pdf(render_column_footing_plan, model, "s02_no_grid.pdf")
    text = pdf_page_text(pdf_bytes, 0)
    assert "T1" in text
    assert "C1" in text


# ── S-03 ─────────────────────────────────────────────────────────────────


def _footing_items(classes: list[str]) -> list[FootingItem]:
    mark_for = {"corner": "T1", "edge": "T2", "interior": "T3"}
    out = []
    for i, cls in enumerate(classes):
        out.append(
            FootingItem(
                mark=mark_for.get(cls, f"T{i + 1}"),
                footing_class=cls,
                cx=float(i) * 3.0,
                cy=0.0,
                length_m=1.4 + i * 0.1,
                width_m=1.4 + i * 0.1,
                depth_mm=450 + i * 25,
                design={
                    "bars_x": {"dia": 12, "spacing": 150},
                    "bars_y": {"dia": 12, "spacing": 150},
                },
            )
        )
    return out


def test_footing_details_renders_marks_scale_and_schedule():
    model = _synthetic_model(
        footings=_footing_items(["corner", "edge", "interior"]), columns=[]
    )
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    n_pages = render_footing_details(c, model)
    c.save()
    pdf_bytes = buf.getvalue()
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    with open(os.path.join(SAMPLE_DIR, "s03.pdf"), "wb") as fh:
        fh.write(pdf_bytes)

    assert n_pages == pdf_pages(pdf_bytes)
    full_text = "".join(
        pdf_page_text(pdf_bytes, i) for i in range(pdf_pages(pdf_bytes))
    )
    assert "T1" in full_text
    assert "T2" in full_text
    assert "T3" in full_text
    assert "FOOTING SCHEDULE" in full_text.upper()
    for i in range(pdf_pages(pdf_bytes)):
        assert "SCALE 1:" in pdf_page_text(pdf_bytes, i).upper()


def test_footing_details_bar_count_matches_design_spacing():
    # L=1.35m=1350mm, spacing=150mm, cover=50mm -> floor((1350-100)/150)+1 = 9
    footing = FootingItem(
        mark="T1",
        footing_class="corner",
        cx=0.0,
        cy=0.0,
        length_m=1.35,
        width_m=1.35,
        depth_mm=450,
        design={
            "bars_x": {"dia": 12, "spacing": 150},
            "bars_y": {"dia": 12, "spacing": 150},
        },
    )
    assert bar_count(footing.length_m * 1000, footing.design["bars_x"]["spacing"]) == 9


def test_bar_count_handles_zero_spacing_without_crashing():
    assert bar_count(1350, 0) == 0


def test_footing_details_paginates_instead_of_dropping_a_type():
    # 6 synthetic footing classes (well beyond the real T1/T2/T3 set) forces
    # the per-page height budget to overflow, exercising paginate_boxes
    # rather than the old renderer's "draw only the largest" behaviour.
    classes = [f"class{i}" for i in range(6)]
    model = _synthetic_model(footings=_footing_items(classes), columns=[])
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    n_pages = render_footing_details(c, model)
    c.save()
    pdf_bytes = buf.getvalue()

    assert n_pages > 1
    assert pdf_pages(pdf_bytes) == n_pages
    full_text = "".join(
        pdf_page_text(pdf_bytes, i) for i in range(pdf_pages(pdf_bytes))
    )
    for f in model.footings:
        assert f.mark in full_text


def test_footing_details_renders_without_crashing_when_empty():
    model = _synthetic_model(footings=[], columns=[])
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    n_pages = render_footing_details(c, model)
    c.save()
    assert n_pages == 1
    assert buf.getvalue()[:5] == b"%PDF-"


# ── S-04 ─────────────────────────────────────────────────────────────────


def _column_items(classes: list[str]) -> list[ColumnItem]:
    mark_for = {"corner": "C1", "edge": "C2", "interior": "C3"}
    out = []
    for i, cls in enumerate(classes):
        out.append(
            ColumnItem(
                tag=f"C{i + 1}",
                mark=mark_for.get(cls, f"C{i + 1}"),
                col_class=cls,
                cx=float(i) * 3.0,
                cy=0.0,
                b_mm=300 + i * 25,
                D_mm=300 + i * 25,
                bars=f"{6 + i}-16",
            )
        )
    return out


def test_column_details_renders_bars_ties_scale_and_schedule():
    model = _synthetic_model(
        footings=[], columns=_column_items(["corner", "edge", "interior"])
    )
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    n_pages = render_column_details(c, model)
    c.save()
    pdf_bytes = buf.getvalue()
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    with open(os.path.join(SAMPLE_DIR, "s04.pdf"), "wb") as fh:
        fh.write(pdf_bytes)

    assert n_pages == pdf_pages(pdf_bytes)
    full_text = "".join(
        pdf_page_text(pdf_bytes, i) for i in range(pdf_pages(pdf_bytes))
    )
    assert "COLUMN SCHEDULE" in full_text.upper()
    assert "MAIN BARS" in full_text.upper()
    assert "TIES" in full_text.upper()
    for col in model.columns:
        assert col.mark in full_text
    for i in range(pdf_pages(pdf_bytes)):
        assert "SCALE 1:" in pdf_page_text(pdf_bytes, i).upper()


def test_column_details_paginates_instead_of_dropping_a_class():
    classes = [f"class{i}" for i in range(6)]
    model = _synthetic_model(footings=[], columns=_column_items(classes))
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    n_pages = render_column_details(c, model)
    c.save()
    pdf_bytes = buf.getvalue()

    assert n_pages > 1
    assert pdf_pages(pdf_bytes) == n_pages


def test_column_details_renders_without_crashing_when_empty():
    model = _synthetic_model(footings=[], columns=[])
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    n_pages = render_column_details(c, model)
    c.save()
    assert n_pages == 1
    assert buf.getvalue()[:5] == b"%PDF-"


# ── helpers ──────────────────────────────────────────────────────────────


def test_parse_bars_reads_n_dash_dia_format():
    assert _parse_bars("6-16") == (6, 16.0)


def test_parse_bars_falls_back_on_unrecognised_format():
    assert _parse_bars("nonsense") == (4, 12.0)


def test_parse_bars_handles_empty_string():
    assert _parse_bars("") == (4, 12.0)


def test_perimeter_points_returns_n_points_for_positive_n():
    pts = _perimeter_points(0.0, 0.0, 100.0, 60.0, 8)
    assert len(pts) == 8


def test_perimeter_points_empty_for_zero_bars():
    assert _perimeter_points(0.0, 0.0, 100.0, 60.0, 0) == []
