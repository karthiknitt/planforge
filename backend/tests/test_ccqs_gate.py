"""CCQS regression gate — fails CI if drawing quality drops below baseline.

Renders the PDF from the FROZEN fixture geometry (never re-solves; CP-SAT
is not run-to-run deterministic) and compares the deterministic CCQS
against the committed baseline minus tolerance.

To re-baseline after a DELIBERATE drawing change:
    cd backend && uv run python scripts/make_ccqs_fixture.py
and commit the regenerated ccqs_baseline.json with the change.
"""

import json
from pathlib import Path

from app.engine.models import PlotConfig
from app.engine.pdf import render_pdf
from app.quality.ccqs import compute_ccqs_deterministic
from app.services.layout_store import engine_layout_from_geometry

BACKEND = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((BACKEND / "tests" / "fixtures" / "ccqs_fixture.json").read_text())
BASELINE = json.loads((BACKEND / "app" / "quality" / "ccqs_baseline.json").read_text())

TOTAL_TOLERANCE = 2.0
COMPONENT_TOLERANCE = 1.0
COMPONENTS = ("monochrome", "dimension_density", "ft_in_labels", "layout_completeness")


def _score():
    cfg = PlotConfig(**FIXTURE["cfg"])
    layout = engine_layout_from_geometry(FIXTURE["geometry"])
    pdf_bytes = render_pdf("CCQS Fixture", layout, cfg, cfg.num_bedrooms)
    return compute_ccqs_deterministic(pdf_bytes)


def test_ccqs_total_meets_baseline():
    result = _score()
    floor = BASELINE["total"] - TOTAL_TOLERANCE
    assert result.total >= floor, (
        f"CCQS regression: {result.total} < baseline {BASELINE['total']} - {TOTAL_TOLERANCE}. "
        f"Components: {result.as_dict()}. If the drop is deliberate, re-run "
        f"scripts/make_ccqs_fixture.py and commit the new baseline."
    )


def test_ccqs_components_meet_baseline():
    result = _score().as_dict()
    for key in COMPONENTS:
        floor = BASELINE[key] - COMPONENT_TOLERANCE
        assert result[key] >= floor, (
            f"CCQS component regression: {key}={result[key]} < "
            f"baseline {BASELINE[key]} - {COMPONENT_TOLERANCE}"
        )
