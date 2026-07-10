"""Tests that DXF export (S5.3) projects the canonical FloorDrawing — same
single source of truth as pdf.py/approval_pdf.py, not a private derivation."""

import io

import ezdxf
import pytest

from app.api.routes.export import _render_dxf
from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.engine.plan_geometry import build_floor_drawing


@pytest.fixture(scope="module")
def cfg():
    return PlotConfig(
        plot_length=11.0,
        plot_width=12.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=2,
        toilets=2,
        parking=True,
        city="trichy",
        road_side="S",
        num_floors=2,
    )


@pytest.fixture(scope="module")
def layout(cfg):
    return generate(cfg)[0]


@pytest.fixture(scope="module")
def dxf_doc(cfg, layout):
    dxf_bytes = _render_dxf("Test", layout, cfg)
    return ezdxf.read(io.StringIO(dxf_bytes.decode("utf-8"))), dxf_bytes


def _opening_counts(cfg, layout):
    counts = {"door": 0, "window": 0, "ventilator": 0}
    for floor_plan in (layout.ground_floor, layout.first_floor):
        drawing = build_floor_drawing(floor_plan, cfg)
        for op in drawing.openings:
            counts[op.kind] += 1
    return counts


def test_opening_insert_counts_match_canonical_floor_drawing(cfg, layout, dxf_doc):
    """PF_DOOR/PF_WINDOW/PF_VENT insert counts must equal the canonical
    FloorDrawing's opening counts — proof DXF no longer derives its own."""
    doc, _ = dxf_doc
    msp = doc.modelspace()
    expected = _opening_counts(cfg, layout)

    assert (
        len([e for e in msp.query("INSERT") if e.dxf.name == "PF_DOOR"])
        == (expected["door"])
    )
    assert (
        len([e for e in msp.query("INSERT") if e.dxf.name == "PF_WINDOW"])
        == (expected["window"])
    )
    assert (
        len([e for e in msp.query("INSERT") if e.dxf.name == "PF_VENT"])
        == (expected["ventilator"])
    )


def test_column_count_matches_canonical_junctions(cfg, layout, dxf_doc):
    doc, _ = dxf_doc
    msp = doc.modelspace()
    drawing_gf = build_floor_drawing(layout.ground_floor, cfg)
    columns_at_z0 = [
        e
        for e in msp.query("LWPOLYLINE")
        if e.dxf.layer == "S-COLUMN" and e.dxf.elevation == 0.0
    ]
    assert len(columns_at_z0) == len(drawing_gf.columns)


def test_no_mtext_paragraph_or_underline_escape_codes(dxf_doc):
    """Plan (S5.3): replace MTEXT \\P/{\\L...} codes with plain TEXT where
    they garble — title block previously used both."""
    _, raw_bytes = dxf_doc
    text = raw_bytes.decode("utf-8")
    assert "\\P" not in text, "Found an MTEXT paragraph-break code in DXF output"
    assert "{\\L" not in text, "Found an MTEXT underline-formatting code in DXF output"


def test_title_block_uses_plain_text_entities(dxf_doc):
    doc, _ = dxf_doc
    msp = doc.modelspace()
    title_texts = [e for e in msp.query("TEXT") if e.dxf.layer == "A-TITLE"]
    assert len(title_texts) >= 1
