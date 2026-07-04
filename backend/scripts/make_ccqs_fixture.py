"""Freeze a CCQS fixture geometry + baseline scores.

Run ONCE (and again only after deliberate drawing-pipeline changes):
    cd backend && uv run python scripts/make_ccqs_fixture.py

Solves a reference 3BHK config, freezes layouts[0] geometry to
tests/fixtures/ccqs_fixture.json, renders its PDF, scores it, and writes
app/quality/ccqs_baseline.json. Both outputs are committed — the CI gate
(tests/test_ccqs_gate.py) renders from the frozen geometry, never re-solves.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("INTERNAL_AUTH_SECRET", "test-secret-for-ci-0123456789abcdefgh")

from app.engine.generator import generate  # noqa: E402
from app.engine.models import PlotConfig  # noqa: E402
from app.engine.pdf import render_pdf  # noqa: E402
from app.quality.ccqs import compute_ccqs_deterministic  # noqa: E402
from app.services.layout_store import layout_out_from_engine  # noqa: E402

FIXTURE_CFG = PlotConfig(
    plot_length=15.0,
    plot_width=9.0,
    setback_front=1.5,
    setback_rear=1.0,
    setback_left=1.0,
    setback_right=1.0,
    num_bedrooms=3,
    toilets=2,
    parking=True,
    num_floors=2,
)

BACKEND = Path(__file__).resolve().parent.parent
FIXTURE_PATH = BACKEND / "tests" / "fixtures" / "ccqs_fixture.json"
BASELINE_PATH = BACKEND / "app" / "quality" / "ccqs_baseline.json"


def main() -> None:
    layouts = generate(FIXTURE_CFG)
    if not layouts:
        raise SystemExit("solver returned no layouts for the fixture config")
    layout = layouts[0]
    geometry = layout_out_from_engine(layout).model_dump()

    pdf_bytes = render_pdf(
        "CCQS Fixture", layout, FIXTURE_CFG, FIXTURE_CFG.num_bedrooms
    )
    result = compute_ccqs_deterministic(pdf_bytes)

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(
        json.dumps({"cfg": asdict(FIXTURE_CFG), "geometry": geometry}, indent=2)
    )
    BASELINE_PATH.write_text(json.dumps(result.as_dict(), indent=2))
    print(f"fixture  -> {FIXTURE_PATH}")
    print(f"baseline -> {BASELINE_PATH}")
    print(json.dumps(result.as_dict(), indent=2))


if __name__ == "__main__":
    main()
