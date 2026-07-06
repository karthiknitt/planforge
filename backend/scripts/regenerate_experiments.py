"""Regenerate the committed reference PDFs + scores after a deliberate
drawing-pipeline change (Sprint 7: FloorDrawing projection across all
renderers). Renders from the SAME frozen golden fixture the regression
suite uses (tests/fixtures/ccqs_fixture.json) — never re-solves, since
CP-SAT is not run-to-run deterministic.

Run from backend/:
    uv run python scripts/regenerate_experiments.py

Writes (repo root):
    experiments/current_standard.pdf
    experiments/current_approval.pdf
    experiments/current_standard.png   (page 0, for visual sign-off)
    experiments/current_approval.png   (page 0, for visual sign-off)
    experiments/scores.json            (CCQS + GCS side by side)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("INTERNAL_AUTH_SECRET", "test-secret-for-ci-0123456789abcdefgh")

from app.engine.approval_pdf import OwnerInfo, generate_approval_pdf  # noqa: E402
from app.engine.pdf import render_pdf  # noqa: E402
from app.quality.ccqs import compute_ccqs_deterministic, compute_gcs  # noqa: E402
from tests.helpers.golden import golden_config, golden_layout  # noqa: E402
from tests.helpers.pdf_png import render_page_png  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND.parent
EXPERIMENTS = REPO_ROOT / "experiments"

OWNER = OwnerInfo(
    owner_name="Reference Owner",
    survey_number="123/4A",
    locality="Sample Locality",
    engineer_name="Reference Engineer",
    license_number="REF-0001",
    municipality="Generic (NBC)",
)


def main() -> None:
    layout = golden_layout()
    cfg = golden_config()

    standard_pdf = render_pdf("Reference Project", layout, cfg, cfg.num_bedrooms)
    approval_pdf = generate_approval_pdf(layout, cfg, OWNER, layout.id)

    EXPERIMENTS.mkdir(parents=True, exist_ok=True)
    (EXPERIMENTS / "current_standard.pdf").write_bytes(standard_pdf)
    (EXPERIMENTS / "current_approval.pdf").write_bytes(approval_pdf)
    (EXPERIMENTS / "current_standard.png").write_bytes(
        render_page_png(standard_pdf, 0, zoom=2.0)
    )
    (EXPERIMENTS / "current_approval.png").write_bytes(
        render_page_png(approval_pdf, 0, zoom=2.0)
    )

    ccqs = compute_ccqs_deterministic(standard_pdf)
    gcs = compute_gcs(layout.ground_floor, cfg)
    scores = {"ccqs": ccqs.as_dict(), "gcs": gcs.as_dict()}
    (EXPERIMENTS / "scores.json").write_text(json.dumps(scores, indent=2))

    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()
