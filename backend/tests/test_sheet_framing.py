"""Sheets S-05 … S-10 — the framing half of the Structural Drawing Set."""

from __future__ import annotations

import os
import tempfile
from io import BytesIO
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.engine.plan_geometry import build_floor_drawing
from app.engine.structural_data import (
    BarGroup,
    BeamRun,
    Cover,
    FloorFraming,
    Stirrup,
    build_structural_model,
)
from app.engine.structural_sheets_framing import (
    _draw_beam_detail,
    _read_steel,
    render_framing_details,
    render_framing_plan,
    render_plinth_beam_details,
    render_plinth_beam_plan,
)
from app.services.plinth_beam_design import plinth_group_key
from tests.helpers.pdf_png import pdf_page_text, pdf_pages

CFG = PlotConfig(
    plot_y_extent=15.0,
    plot_x_extent=9.0,
    setback_front=3.0,
    setback_rear=1.5,
    setback_left=1.0,
    setback_right=1.0,
    num_bedrooms=2,
    toilets=2,
    parking=True,
)

SAMPLE_DIR = Path(os.environ.get("PLANFORGE_SAMPLE_DIR", tempfile.gettempdir()))


def _beam_design(span: float, b: float, d: float, axis: str, lines: list[int]) -> dict:
    """One structapi beam group, in the element-dict shape the roof beams use."""
    return {
        "axis": axis,
        "b_mm": b,
        "D_mm": d,
        "span_m": span,
        "trib_width_m": 2.25,
        "n_spans": 3,
        "grid_line_indices": lines,
        "inputs": {"stirrup_dia": 8},
        "design": {
            "n_bars": 3,
            "bar_dia": 16,
            "doubly_reinforced": True,
            "n_bars_comp": 2,
            "stirrups": {"sv_provided": 150, "governing": "shear"},
            "pt_percent": 0.85,
        },
    }


def _slab_design(kind: str, lx: float, ly: float, cells: list[list[int]]) -> dict:
    d: dict = {
        "type": kind,
        "lx_m": lx,
        "ly_m": ly,
        "D_mm": 125,
        "case_": "1",
        "panel_indices": cells,
    }
    if kind == "one-way":
        d["main"] = {"bar": "10 φ @ 150 c/c"}
        d["distribution"] = {"bar": "8 φ @ 200 c/c"}
    else:
        d["strips"] = {
            "short_span_bottom": {"bar": "10 φ @ 140 c/c"},
            "long_span_bottom": {"bar": "10 φ @ 180 c/c"},
        }
    return d


@pytest.fixture(scope="module")
def model():
    """One real generated + designed layout, built once (generation is slow)."""
    layouts = generate(CFG)
    assert layouts, "generator produced no layouts"
    layout = layouts[0]

    gf_drawing = build_floor_drawing(layout.ground_floor, CFG)
    # plinth beams are keyed off the real wall groups, so derive the design
    # keys from the drawing rather than guessing wall lengths
    keys = []
    for w in gf_drawing.walls:
        k = plinth_group_key(w.kind, round(w.length, 1))
        if k not in keys:
            keys.append(k)
    plinth_data = {
        k: {
            "b_mm": 230,
            "D_mm": 300,
            "span_m": 2.5 + 0.4 * i,
            "design": {
                "n_bars": 3,
                "bar_dia": 12,
                "doubly_reinforced": False,
                "stirrups": {"sv_provided": 150, "dia": 8},
            },
        }
        for i, k in enumerate(keys[:4])
    }

    design = {
        "status": "designed",
        "revision_id": 1,
        "structapi": {
            "disclaimer": "Advisory design — to be verified by a licensed engineer.",
            "data": {
                "inputs": {"fck": 25, "fy": 500, "storeys": 2},
                "columns": {
                    "corner": {"b_mm": 300, "D_mm": 300, "bars": "4-16φ"},
                    "edge": {"b_mm": 300, "D_mm": 380, "bars": "6-16φ"},
                    "interior": {"b_mm": 300, "D_mm": 450, "bars": "8-16φ"},
                },
                "beams": {
                    "x-span4.00-trib2.25": _beam_design(
                        4.0, 230, 450, "x", [0, 1, 2, 3, 4]
                    ),
                    "y-span3.20-trib2.00": _beam_design(
                        3.2, 230, 380, "y", [0, 1, 2, 3, 4]
                    ),
                },
                "slabs": {
                    "one": _slab_design("one-way", 3.0, 5.4, [[0, 0], [1, 0]]),
                    "two": _slab_design("two-way", 3.4, 3.8, [[0, 1], [1, 1], [0, 2]]),
                },
            },
        },
    }

    return build_structural_model(
        project_name="Framing Sheet Test",
        cfg=CFG,
        layout=layout,
        structural_design=design,
        plinth_beams_data=plinth_data,
    )


def _render(fn, *args) -> tuple[bytes, int]:
    """Drive a renderer the way the orchestrator does: it emits showPage()
    between its own pages but never after the last one."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    pages = fn(c, *args)
    c.showPage()
    c.save()
    data = buf.getvalue()
    assert pdf_pages(data) == pages, "reported page count != pages in the PDF"
    return data, pages


def _all_text(data: bytes) -> str:
    return "\n".join(pdf_page_text(data, i) for i in range(pdf_pages(data)))


def _write_sample(data: bytes, name: str) -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    (SAMPLE_DIR / name).write_bytes(data)


# ── S-05 ─────────────────────────────────────────────────────────────────────


def test_s05_plinth_beam_plan(model):
    data, _ = _render(render_plinth_beam_plan, model)
    _write_sample(data, "s05.pdf")
    text = pdf_page_text(data, 0)
    assert "S-05" in text
    assert "PLINTH BEAM PLAN" in text.upper()
    assert "PLINTH BEAM SCHEDULE" in text.upper()
    assert "PB1" in text


def test_s05_schedule_carries_steel_and_nos_columns(model):
    data, _ = _render(render_plinth_beam_plan, model)
    text = pdf_page_text(data, 0).upper()
    # the plan sheet's reserved column is only SCHED_W wide, so it carries the
    # abbreviated header set; the full one lives on the details sheet
    for header in ("MARK", "SPAN", "TOP", "BOT", "STIRR", "NOS"):
        assert header in text


def test_details_sheet_uses_the_full_schedule_headers(model):
    text = _all_text(_render(render_plinth_beam_details, model)[0]).upper()
    for header in ("SIZE (B X D MM)", "TOP STEEL", "BOTTOM STEEL", "STIRRUPS"):
        assert header in text


# ── S-06 ─────────────────────────────────────────────────────────────────────


def test_s06_plinth_beam_details(model):
    data, _ = _render(render_plinth_beam_details, model)
    _write_sample(data, "s06.pdf")
    text = _all_text(data)
    assert "S-06" in text
    assert "PLINTH BEAM DETAILS" in text.upper()
    assert "SCALE 1:" in text
    assert "SECTION" in text.upper()
    assert "LONGITUDINAL ELEVATION" in text.upper()
    assert "c/c" in text  # stirrup spacing callout


# ── S-07 / S-09 from one code path ───────────────────────────────────────────


def test_framing_plan_covers_both_floors_from_one_renderer(model):
    assert len(model.floors) == 2
    gf_data, _ = _render(render_framing_plan, model, model.floors[0])
    ff_data, _ = _render(render_framing_plan, model, model.floors[1])
    _write_sample(gf_data, "s07.pdf")
    _write_sample(ff_data, "s09.pdf")

    gf, ff = pdf_page_text(gf_data, 0), pdf_page_text(ff_data, 0)
    assert model.floors[0].drg_plan in gf
    assert model.floors[1].drg_plan in ff
    assert model.floors[0].drg_plan != model.floors[1].drg_plan
    assert model.floors[0].level_label.split(" ")[0] in gf
    assert "TERRACE" in ff.upper()


def test_framing_plan_shows_slab_marks_and_span_type(model):
    data, _ = _render(render_framing_plan, model, model.floors[0])
    # Panel marks and steel directions are ON the plan; the schedule rides
    # its own continuation sheet, so assert across the whole drawing.
    plan = pdf_page_text(data, 0).upper()
    text = _all_text(data).upper()
    assert "S1" in plan
    assert "ONE-WAY" in plan or "TWO-WAY" in plan
    assert "MAIN" in plan
    assert "DIST" in plan
    assert "SLAB SCHEDULE" in text


def test_framing_plan_carries_beam_schedule_too(model):
    data, _ = _render(render_framing_plan, model, model.floors[0])
    assert "BEAM SCHEDULE" in _all_text(data).upper()


def test_terrace_note_only_on_the_terrace_level(model):
    gf, _ = _render(render_framing_plan, model, model.floors[0])
    ff, _ = _render(render_framing_plan, model, model.floors[1])
    # Notes moved off the plan onto the sheet's continuation page, so search
    # the whole drawing — the discriminating half of this test is that the
    # ground-floor level never carries it.
    assert "WATERPROOFING" not in _all_text(gf).upper()
    assert "WATERPROOFING" in _all_text(ff).upper()


# ── S-08 / S-10 ──────────────────────────────────────────────────────────────


def test_framing_details_both_floors(model):
    gf_data, _ = _render(render_framing_details, model, model.floors[0])
    ff_data, _ = _render(render_framing_details, model, model.floors[1])
    _write_sample(gf_data, "s08.pdf")
    _write_sample(ff_data, "s10.pdf")

    gf, ff = _all_text(gf_data), _all_text(ff_data)
    assert model.floors[0].drg_details in gf
    assert model.floors[1].drg_details in ff
    assert "SCALE 1:" in gf and "SCALE 1:" in ff
    assert "BEAM SCHEDULE" in gf.upper()


def test_beam_detail_shows_stirrup_zoning_and_span(model):
    text = _all_text(_render(render_framing_details, model, model.floors[0])[0])
    assert "c/c" in text
    assert "SPAN" in text.upper()
    assert "2D FROM EACH SUPPORT FACE" in text.upper()


# ── pagination: nothing may be dropped ───────────────────────────────────────


def _many_beams(n: int) -> list[BeamRun]:
    return [
        BeamRun(
            mark=f"B{i + 1}",
            axis="x",
            ordinate_m=float(i),
            start_m=0.0,
            end_m=4.0,
            b_mm=230,
            D_mm=380 + (i % 3) * 30,
            span_m=3.0 + 0.2 * i,
            design={
                "inputs": {"stirrup_dia": 8},
                "design": {
                    "n_bars": 3,
                    "bar_dia": 16,
                    "doubly_reinforced": bool(i % 2),
                    "n_bars_comp": 2,
                    "stirrups": {"sv_provided": 125 + (i % 3) * 25},
                },
            },
        )
        for i in range(n)
    ]


def test_beam_details_paginate_without_dropping_any_mark(model):
    beams = _many_beams(14)
    framing = FloorFraming(
        level_label="GF ROOF / FF FLOOR",
        drg_plan="S-07",
        drg_details="S-08",
        floor_plan=model.layout.ground_floor,
        drawing=None,
        beams=beams,
        slabs=[],
    )
    data, pages = _render(render_framing_details, model, framing)
    _write_sample(data, "s08_paginated.pdf")

    assert pages > 1, "14 beam marks should not fit on a single sheet"
    text = _all_text(data)
    assert "(CONTD.)" in text.upper()
    for b in beams:
        # word-boundary-ish check: B1 must not be satisfied by B11
        assert f"{b.mark}  " in text or f"{b.mark}\n" in text or f" {b.mark}" in text


def test_every_mark_has_its_own_detail_heading(model):
    beams = _many_beams(14)
    framing = FloorFraming(
        level_label="GF ROOF / FF FLOOR",
        drg_plan="S-07",
        drg_details="S-08",
        floor_plan=model.layout.ground_floor,
        drawing=None,
        beams=beams,
        slabs=[],
    )
    data, _ = _render(render_framing_details, model, framing)
    text = _all_text(data)
    assert text.count("BEAM DETAIL") >= len(beams)


# ── degradation on incomplete design data ────────────────────────────────────


def test_missing_design_keys_degrade_to_labelled_assumptions():
    st = _read_steel({})
    assert st.assumed, "an empty design dict must be reported as assumed"
    assert st.n_bot >= 1 and st.dia_bot > 0 and st.sv > 0

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    h = _draw_beam_detail(
        c,
        "B9",
        b_mm=230,
        D_mm=380,
        span_m=3.6,
        design={},
        x=60,
        y=740,
        avail_w=470,
        avail_h=200,
    )
    c.showPage()
    c.save()
    assert h > 0
    text = pdf_page_text(buf.getvalue(), 0)
    assert "B9" in text
    assert "ASSUMED" in text.upper()
    assert "SCALE 1:" in text


def test_designed_values_are_not_flagged_as_assumed(model):
    run = next(b for b in model.floors[0].beams if b.mark)
    st = _read_steel(run.design)
    assert st.assumed == ()
    assert st.n_bot == 3


def test_non_positive_typed_steel_falls_back_to_assumed():
    """A typed BarGroup/Stirrup/Cover with a zero/negative field must not be
    trusted as designed data — it degrades to the labelled-assumption path
    the same as a genuinely missing value, instead of printing a bogus
    "0ø@0" callout as if it were real."""
    run = BeamRun(
        mark="B1",
        axis="x",
        ordinate_m=0.0,
        start_m=0.0,
        end_m=4.0,
        b_mm=230,
        D_mm=380,
        span_m=3.6,
        design={"design": {"stirrups": {}}},
        bottom_bars=BarGroup(quantity=0, diameter_mm=16.0),
        top_bars=BarGroup(quantity=2, diameter_mm=0.0),
        stirrups=Stirrup(diameter_mm=8.0, spacing_mm=0.0),
        cover=Cover(mm=0.0),
    )
    st = _read_steel(run)
    assert "BOT NOS" in st.assumed
    assert "BAR DIA" in st.assumed
    assert "STIRRUP SPACING" in st.assumed
    assert st.n_bot > 0
    assert st.dia_bot > 0
    assert st.sv > 0
    assert st.cover > 0
