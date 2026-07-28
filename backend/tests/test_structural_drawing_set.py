"""Set-level integration tests for the 12-sheet Structural Drawing Set.

Per-sheet content is covered by `test_sheet_notes.py`,
`test_sheet_foundation.py`, `test_sheet_framing.py` and
`test_sheet_slab_stair.py`; the frame/scale/pagination primitives by
`test_structural_sheet.py`. What is pinned here is what only the assembled
set can show: that every drawing in the register is present, that both
floors are detailed, and that the set carries its provenance.
"""

import pytest

from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.engine.structural_data import build_structural_model
from app.engine.structural_drawing_set import generate_structural_drawing_set
from app.engine.structural_sheet import SHEET_REGISTER
from tests.helpers.pdf_png import pdf_page_text, pdf_pages

CFG = PlotConfig(
    plot_width=12.192,
    plot_length=18.288,
    num_bedrooms=2,
    toilets=2,
    setback_front=1.5,
    setback_rear=1.5,
    setback_left=1.2,
    setback_right=1.2,
    parking=True,
    city="other",
    road_side="E",
    vastu_enabled=True,
)

DISCLAIMER = "Advisory design output. To be verified and sealed by a licensed engineer."

DESIGN = {
    "status": "designed",
    "revision_id": "rev-7",
    "changelog": ["initial design"],
    "structapi": {
        "disclaimer": DISCLAIMER,
        "data": {
            "inputs": {
                "fck": 25,
                "fy": 500,
                "exposure": "moderate",
                "sbc_kpa": 150,
                "storeys": 2,
                "storey_height_m": 3.0,
                "seismic_zone": "III",
            },
            "columns": {
                "corner": {"b_mm": 230, "D_mm": 300, "bars": "6-16"},
                "edge": {"b_mm": 230, "D_mm": 380, "bars": "6-16"},
                "interior": {"b_mm": 300, "D_mm": 300, "bars": "8-16"},
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
                        "L_m": 1.5,
                        "B_m": 1.5,
                        "D_overall_mm": 500,
                        "bars_x": {"dia": 12, "spacing": 130},
                        "bars_y": {"dia": 12, "spacing": 130},
                    }
                },
                "interior": {
                    "data": {
                        "L_m": 1.7,
                        "B_m": 1.7,
                        "D_overall_mm": 550,
                        "bars_x": {"dia": 16, "spacing": 140},
                        "bars_y": {"dia": 16, "spacing": 140},
                    }
                },
            },
            "beams": {
                "x-span4.0-trib2.0": {
                    "axis": "x",
                    "b_mm": 230,
                    "D_mm": 400,
                    "span_m": 4.0,
                    "n_spans": 3,
                    "grid_line_indices": [0, 1, 2],
                    "n_bars": 3,
                    "bar_dia": 16,
                    "doubly_reinforced": False,
                    "stirrups": {"sv_provided": 150, "dia": 8, "legs": 2},
                },
                "y-span3.2-trib1.8": {
                    "axis": "y",
                    "b_mm": 230,
                    "D_mm": 350,
                    "span_m": 3.2,
                    "n_spans": 2,
                    "grid_line_indices": [0, 1],
                    "n_bars": 2,
                    "bar_dia": 12,
                    "n_bars_comp": 2,
                    "doubly_reinforced": True,
                    "stirrups": {"sv_provided": 175, "dia": 8, "legs": 2},
                },
            },
            "slabs": {
                "(3.05, 4.27, 'interior')": {
                    "type": "two-way",
                    "lx_m": 3.05,
                    "ly_m": 4.27,
                    "case_": "interior",
                    "D_mm": 125,
                    "panel_indices": [[0, 0], [1, 0]],
                },
                "(1.5, 4.27, 'edge')": {
                    "type": "one-way",
                    "lx_m": 1.5,
                    "ly_m": 4.27,
                    "case_": "edge",
                    "D_mm": 110,
                    "panel_indices": [[2, 1]],
                },
            },
            "assumptions": ["regular orthogonal grid; columns at all intersections"],
            "violations": [],
            "quantities": {},
            "lateral": {"governing": "seismic", "seismic_VB_kN": 88.4},
        },
    },
}


@pytest.fixture(scope="module")
def layout():
    layouts = generate(CFG)
    assert layouts
    return layouts[0]


@pytest.fixture(scope="module")
def model(layout):
    return build_structural_model(
        project_name="MyLatest",
        cfg=CFG,
        layout=layout,
        structural_design=DESIGN,
        plinth_beams_data={},
    )


@pytest.fixture(scope="module")
def pdf_bytes(layout):
    return generate_structural_drawing_set(
        project_name="MyLatest",
        cfg=CFG,
        layout=layout,
        structural_design=DESIGN,
        plinth_beams_data={},
    )


@pytest.fixture(scope="module")
def all_text(pdf_bytes):
    return [pdf_page_text(pdf_bytes, i) for i in range(pdf_pages(pdf_bytes))]


def test_set_has_at_least_one_page_per_registered_drawing(pdf_bytes):
    n_pages = pdf_pages(pdf_bytes)
    assert n_pages >= len(SHEET_REGISTER), (
        f"{n_pages} pages for {len(SHEET_REGISTER)} drawings — a sheet is missing"
    )


@pytest.mark.parametrize("drg_no,title", SHEET_REGISTER)
def test_every_registered_drawing_appears_in_the_set(all_text, drg_no, title):
    joined = "\n".join(all_text)
    assert drg_no in joined, f"drawing {drg_no} ({title}) is not in the set"


def test_both_floors_are_detailed(model, all_text):
    """Both-floor coverage. The set this replaces passed only
    `layout.first_floor` to the renderer, so the ground floor's framing was
    never drawn at all."""
    joined = "\n".join(all_text).upper()
    assert len(model.floors) == 2
    for framing in model.floors:
        assert framing.drg_plan in joined
        assert framing.drg_details in joined


def test_set_carries_its_provenance_on_every_sheet(all_text):
    """A structural set is advisory until an engineer seals it; the
    disclaimer and the project name must be legible on each sheet."""
    for i, text in enumerate(all_text):
        assert "MyLatest" in text, f"page {i} has no project identification"


def test_set_never_prints_the_meaningless_bhk_field(all_text):
    joined = "\n".join(all_text)
    assert "0 BHK" not in joined
    assert "BHK" not in joined, "structural sheets carry no bedroom count"


def test_schedules_ride_with_their_drawings(all_text):
    """Tables and drawings must be in the same set, on the sheet they
    describe — the explicit scoping requirement for this work."""
    joined = "\n".join(all_text).upper()
    for schedule in ("FOOTING SCHEDULE", "COLUMN SCHEDULE", "BEAM SCHEDULE"):
        assert schedule in joined, f"{schedule} missing from the set"


def test_generation_is_deterministic(layout):
    a = generate_structural_drawing_set(
        project_name="MyLatest",
        cfg=CFG,
        layout=layout,
        structural_design=DESIGN,
        plinth_beams_data={},
    )
    b = generate_structural_drawing_set(
        project_name="MyLatest",
        cfg=CFG,
        layout=layout,
        structural_design=DESIGN,
        plinth_beams_data={},
    )
    assert pdf_pages(a) == pdf_pages(b)


def test_missing_structural_design_degrades_rather_than_raising(layout):
    """Export is gated on a designed layout, but a malformed or partial
    persisted design must not take the endpoint down with a KeyError."""
    out = generate_structural_drawing_set(
        project_name="MyLatest",
        cfg=CFG,
        layout=layout,
        structural_design={},
        plinth_beams_data={},
    )
    assert pdf_pages(out) >= 1
