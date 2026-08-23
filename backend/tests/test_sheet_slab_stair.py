"""Tests for S-11/S-12 (Slab Reinforcement Details, Staircase Details) —
app.engine.structural_sheets_slab_stair."""

from __future__ import annotations

import os
import tempfile
from io import BytesIO

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine import generator
from app.engine.models import PlotConfig
from app.engine.structural_data import (
    GridRef,
    SlabPanel,
    Stirrup,
    StructuralModel,
    build_structural_model,
)
from app.engine.structural_sheets_slab_stair import (
    _steel_pair,
    render_slab_reinforcement_details,
    render_staircase_details,
)
from tests.helpers.pdf_png import pdf_page_text, pdf_pages

SAMPLE_DIR = os.environ.get("PLANFORGE_SAMPLE_DIR", tempfile.gettempdir())

CFG = PlotConfig(
    plot_x_extent=12.192,
    plot_y_extent=18.288,
    num_bedrooms=2,
    toilets=2,
    setback_front=1.5,
    setback_rear=1.5,
    setback_left=1.2,
    setback_right=1.2,
    parking=True,
    city="other",
    road_side="E",
)

# 6 distinct designed panel types (deliberately more than fit one S-11 page,
# to exercise pagination) plus one exact duplicate of "ow-1" under a
# different structapi group key, to exercise dedup. All are pinned to the
# same grid cell [0,0] — S-11 only cares about the design fields, not where
# on the plot a bay happens to sit.
_SLABS_DATA = {
    "ow-1": {
        "panel_indices": [[0, 0]],
        "lx_m": 3.0,
        "ly_m": 3.0,
        "type": "one-way",
        "case_": "interior",
        "D_mm": 100,
        "main_bar_dia_mm": 8,
        "main_bar_spacing_mm": 150,
        "dist_bar_dia_mm": 8,
        "dist_bar_spacing_mm": 250,
        "top_bar_dia_mm": 8,
        "top_bar_spacing_mm": 150,
    },
    "ow-1-dup": {
        "panel_indices": [[0, 0]],
        "lx_m": 3.0,
        "ly_m": 3.0,
        "type": "one-way",
        "case_": "interior",
        "D_mm": 100,
        "main_bar_dia_mm": 8,
        "main_bar_spacing_mm": 150,
        "dist_bar_dia_mm": 8,
        "dist_bar_spacing_mm": 250,
        "top_bar_dia_mm": 8,
        "top_bar_spacing_mm": 150,
    },
    "tw-1": {
        "panel_indices": [[0, 0]],
        "lx_m": 3.0,
        "ly_m": 4.5,
        "type": "two-way",
        "case_": "corner",
        "D_mm": 125,
        "main_bar_dia_mm": 10,
        "main_bar_spacing_mm": 150,
        "dist_bar_dia_mm": 8,
        "dist_bar_spacing_mm": 200,
        "top_bar_dia_mm": 10,
        "top_bar_spacing_mm": 150,
    },
    "ow-2-nominal": {
        # deliberately no steel keys — exercises the nominal fallback path
        "panel_indices": [[0, 0]],
        "lx_m": 2.4,
        "ly_m": 3.6,
        "type": "one-way",
        "case_": "edge",
        "D_mm": 110,
    },
    "tw-2": {
        "panel_indices": [[0, 0]],
        "lx_m": 3.5,
        "ly_m": 3.5,
        "type": "two-way",
        "case_": "interior",
        "D_mm": 130,
        "main_bar_dia_mm": 10,
        "main_bar_spacing_mm": 125,
        "dist_bar_dia_mm": 8,
        "dist_bar_spacing_mm": 175,
        "top_bar_dia_mm": 10,
        "top_bar_spacing_mm": 125,
    },
    "ow-3": {
        "panel_indices": [[0, 0]],
        "lx_m": 2.8,
        "ly_m": 4.0,
        "type": "one-way",
        "case_": "interior",
        "D_mm": 105,
        "main_bar_dia_mm": 8,
        "main_bar_spacing_mm": 175,
        "dist_bar_dia_mm": 8,
        "dist_bar_spacing_mm": 250,
        "top_bar_dia_mm": 8,
        "top_bar_spacing_mm": 175,
    },
    "tw-3": {
        "panel_indices": [[0, 0]],
        "lx_m": 4.0,
        "ly_m": 4.4,
        "type": "two-way",
        "case_": "edge",
        "D_mm": 135,
        "main_bar_dia_mm": 12,
        "main_bar_spacing_mm": 150,
        "dist_bar_dia_mm": 10,
        "dist_bar_spacing_mm": 175,
        "top_bar_dia_mm": 12,
        "top_bar_spacing_mm": 150,
    },
}

_STRUCTAPI_DESIGN = {
    "structapi": {
        "disclaimer": "Advisory design — a licensed engineer must review before construction.",
        "data": {
            "slabs": _SLABS_DATA,
            "inputs": {
                "fck": 25,
                "fy": 500,
                "storey_height_m": 3.0,
            },
        },
    }
}


@pytest.fixture(scope="module")
def real_model() -> StructuralModel:
    """A `StructuralModel` built from an actually-generated layout so S-12's
    staircase-room/geometry path exercises real derived stair geometry
    rather than a hand-built stand-in. Generation is slow (~20s), so this
    fixture builds it once for every test in this module."""
    layouts = generator.generate(CFG)
    assert layouts, "generator.generate produced no layouts for the fixture plot"
    layout = layouts[0]
    return build_structural_model(
        project_name="Test Project",
        cfg=CFG,
        layout=layout,
        structural_design=_STRUCTAPI_DESIGN,
    )


@pytest.fixture(scope="module")
def no_stair_model(real_model: StructuralModel) -> StructuralModel:
    """Same model but with every staircase room's type swapped out, so
    render_staircase_details must take the explicit no-staircase path."""
    import dataclasses

    stripped_floors = []
    for floor in real_model.floors:
        rooms = [
            dataclasses.replace(r, type="store_room") if r.type == "staircase" else r
            for r in floor.floor_plan.rooms
        ]
        fp = dataclasses.replace(floor.floor_plan, rooms=rooms)
        stripped_floors.append(dataclasses.replace(floor, floor_plan=fp))
    return dataclasses.replace(real_model, floors=stripped_floors)


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


# ── S-11 ─────────────────────────────────────────────────────────────────────


def test_slab_details_drawing_number_and_scale(real_model: StructuralModel):
    pdf_bytes = _render_to_pdf(render_slab_reinforcement_details, real_model, "s11.pdf")
    text = pdf_page_text(pdf_bytes, 0)
    assert "S-11" in text
    assert "SCALE 1:" in text


def test_slab_details_dedups_identical_panel_types(real_model: StructuralModel):
    from app.engine.structural_sheets_slab_stair import _slab_types

    panels = _slab_types(real_model)
    keys = [(p.lx_m, p.ly_m, p.kind, p.case, p.D_mm) for p in panels]
    assert len(keys) == len(set(keys)), "duplicate panel type was not deduped"
    # 7 raw structapi entries (ow-1 + its exact duplicate + 5 others) collapse
    # to 6 distinct detail types.
    assert len(panels) == 6
    assert keys.count((3.0, 3.0, "one-way", "interior", 100.0)) == 1


def test_slab_details_one_way_and_two_way_have_different_callouts(
    real_model: StructuralModel,
):
    pdf_bytes = _render_to_pdf(render_slab_reinforcement_details, real_model, "s11.pdf")
    full_text = "\n".join(
        pdf_page_text(pdf_bytes, p) for p in range(pdf_pages(pdf_bytes))
    )
    # one-way panel: main steel called out "ALONG SHORT SPAN"; two-way corner
    # panel additionally gets a torsion-mesh callout that one-way never does.
    assert "ALONG SHORT SPAN" in full_text
    assert "TORSION MESH" in full_text


def test_slab_details_nominal_steel_is_labelled_not_fabricated(
    real_model: StructuralModel,
):
    pdf_bytes = _render_to_pdf(render_slab_reinforcement_details, real_model, "s11.pdf")
    full_text = "\n".join(
        pdf_page_text(pdf_bytes, p) for p in range(pdf_pages(pdf_bytes))
    )
    assert "NOMINAL" in full_text


def test_non_positive_typed_slab_steel_falls_back_to_nominal():
    """A typed Stirrup with a zero diameter/spacing must not be trusted as
    designed steel — it degrades to the fuzzy-key/nominal fallback the same
    as a genuinely missing value, instead of printing a bogus "0mm @ 0mm"
    callout as if it were real."""
    panel = SlabPanel(
        mark="S1",
        x1=0.0,
        y1=0.0,
        x2=3.0,
        y2=3.0,
        lx_m=3.0,
        ly_m=3.0,
        kind="one-way",
        case="interior",
        D_mm=125.0,
        design={},
        main_steel=Stirrup(diameter_mm=0.0, spacing_mm=150.0),
    )
    dia, spacing, is_nominal = _steel_pair(panel, ("main",), panel.D_mm, fy=415.0)
    assert is_nominal
    assert dia > 0
    assert spacing > 0


def test_slab_details_paginates_with_contd_and_drops_nothing(
    real_model: StructuralModel,
):
    pdf_bytes = _render_to_pdf(render_slab_reinforcement_details, real_model, "s11.pdf")
    n_pages = pdf_pages(pdf_bytes)
    assert n_pages > 1, "6 panel types should not fit on a single S-11 page"
    assert "CONTD" in pdf_page_text(pdf_bytes, 1)

    full_text = "\n".join(pdf_page_text(pdf_bytes, p) for p in range(n_pages))
    from app.engine.structural_sheets_slab_stair import _slab_types

    for panel in _slab_types(real_model):
        assert panel.mark in full_text, (
            f"panel mark {panel.mark} missing from rendered S-11 pages"
        )


def test_slab_details_no_panels_renders_explicit_sheet():
    empty_model = StructuralModel(
        project_name="Empty",
        cfg=CFG,
        layout=None,
        grid=GridRef(),
        disclaimer="Advisory.",
    )
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    pages = render_slab_reinforcement_details(c, empty_model)
    c.save()
    assert pages == 1
    text = pdf_page_text(buf.getvalue(), 0)
    assert "NO DESIGNED SLAB PANELS" in text


# ── S-12 ─────────────────────────────────────────────────────────────────────


def test_staircase_details_drawing_number_and_scale(real_model: StructuralModel):
    pdf_bytes = _render_to_pdf(render_staircase_details, real_model, "s12.pdf")
    text = pdf_page_text(pdf_bytes, 0)
    assert "S-12" in text
    assert "SCALE 1:" in text


def test_staircase_details_riser_count_and_self_consistency(
    real_model: StructuralModel,
):
    from app.engine.structural_sheets_slab_stair import _staircase_room

    floor, room = _staircase_room(real_model)
    assert floor is not None and room is not None
    stair = floor.drawing.stair
    riser_count = stair.tread_count + 1
    storey_h_mm = (real_model.materials.get("storey_height_m") or 3.0) * 1000.0
    riser_mm = storey_h_mm / riser_count

    pdf_bytes = _render_to_pdf(render_staircase_details, real_model, "s12.pdf")
    text = pdf_page_text(pdf_bytes, 0)
    assert f"{riser_count} RISERS" in text
    assert f"{riser_mm:.0f}" in text
    # self-consistency: n_risers * riser_height == storey height, exactly by
    # construction (riser_mm was derived by dividing storey height by
    # riser_count in the first place).
    assert abs(riser_count * riser_mm - storey_h_mm) < 1e-6


def test_staircase_details_no_staircase_renders_explicit_sheet(
    no_stair_model: StructuralModel,
):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    pages = render_staircase_details(c, no_stair_model)
    c.save()
    assert pages == 1
    text = pdf_page_text(buf.getvalue(), 0)
    assert "NO STAIRCASE ROOM" in text
