# Stage 1 Phase 2 — Enhanced Outputs (CCQS Productization + AI Render Layer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productize the CCQS drawing-quality score (deterministic 4-component scorer + CI regression gate + user-facing badge) and build the AI render layer foundation (spatial prompt builder, PDF→PNG reference images, provider adapters, bake-off harness) — Phase 2 of `docs/plans/2026-07-03-fable-stage1-phase0-plan.md`.

**Architecture:** All new backend code reads the **persisted layout geometry** (Phase 1's `layouts` table, `LayoutOut`-shaped JSON) — nothing re-runs the solver. CCQS becomes `backend/app/quality/ccqs.py` operating on PDF *bytes* (pymupdf `stream=` mode) so the endpoint can score in-memory PDFs on Cloud Run. The CI gate scores a PDF rendered from a *frozen committed geometry fixture* (never a live solve — CP-SAT is not run-to-run deterministic). The render layer is provider-agnostic: one `RenderResult` interface, three adapters (Gemini / OpenAI / OpenRouter), bake-off before productizing (locked decision).

**Tech Stack:** FastAPI, pymupdf (promoted to main dep), reportlab (existing PDF engine), httpx (promoted to main dep), Next.js App Router + bun:test.

## Global Constraints

- Branch: `worktree-stage1-phase2-outputs`, stacked on `worktree-stage1-phase1-hardening` (PR #11, unmerged). PR for this phase targets the Phase 1 branch.
- CCQS CI gate = **deterministic 4 components only** (max 80). Vision VQ stays a dev-time tool (locked decision).
- **Bake-off before productizing** the render layer (locked decision). Part C tasks run only after Karthik picks a provider at the checkpoint.
- No spend beyond a few test renders (~₹50 total) without sign-off.
- Backend: `uv` only; `uv run pytest` / `uv run ruff format` / `uv run ruff check .` must pass before every commit.
- Frontend: bun:test (NOT Vitest); `bun run lint` before commit.
- Conventional commits. TDD: failing test first for every task.
- All commits end with: `Karthikeyan N <karthiknitt@gmail.com>`
- Working directory for backend commands: `backend/`; frontend commands: `frontend/`.
- **`db-migration-safe` workflow MUST run before Task 11's schema change** (new `layout_renders` table).

---

## Part A — CCQS Productization (2b)

### Task 1: Deterministic CCQS scorer module

**Files:**
- Create: `backend/app/quality/__init__.py` (empty)
- Create: `backend/app/quality/ccqs.py`
- Modify: `backend/pyproject.toml` (promote pymupdf from dev group to main dependencies)
- Test: `backend/tests/test_ccqs.py`

**Interfaces:**
- Consumes: nothing from other tasks (source logic: `/home/karthik/projects/PlanForge/experiments/eval.py` — UNTRACKED file in the main checkout; this task brings the 4 deterministic components into the repo. Read it there if needed, but the full implementation is below.)
- Produces: `compute_ccqs_deterministic(pdf_bytes: bytes) -> CcqsResult` where `CcqsResult` is a dataclass with `total: float` (0–80), `monochrome: float`, `dimension_density: float`, `ft_in_labels: float`, `layout_completeness: float`, `debug: dict`, and method `as_dict() -> dict`. Tasks 3, 4 import these.

- [ ] **Step 1: Promote pymupdf to a main dependency**

```bash
cd backend && uv add "pymupdf>=1.27"
```

(It currently sits in `[dependency-groups].dev`; `uv add` puts it in `[project].dependencies`. Leave the dev-group entry — uv dedupes — or remove the dev line in the same edit.)

- [ ] **Step 2: Write the failing test**

`backend/tests/test_ccqs.py`:

```python
"""CCQS deterministic scorer — synthetic PDFs built in-test with reportlab."""

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.quality.ccqs import CcqsResult, compute_ccqs_deterministic


def _mono_pdf_with_text(lines: list[str]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFillColorRGB(0, 0, 0)
    y = 800
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
    c.showPage()
    c.save()
    return buf.getvalue()


def _color_pdf() -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFillColorRGB(1, 0, 0)
    c.rect(0, 0, 595, 842, fill=1, stroke=0)
    c.showPage()
    c.save()
    return buf.getvalue()


FULL_MARKS_LINES = [
    # 10 dimension strings => dimension_density 20
    *[f"{n}'-6\"" for n in range(3, 13)],
    # the same lines are ft-in patterns (>=5 => ft_in_labels 20)
    "GROUND FLOOR PLAN",
    "FIRST FLOOR PLAN",
    "AREA STATEMENT",
    "ROOM AREA SQFT",
    "TOTAL AREA 1450 SQFT",
    "NORTH",
]


def test_full_marks_mono_pdf_scores_80():
    pdf = _mono_pdf_with_text(FULL_MARKS_LINES)
    result = compute_ccqs_deterministic(pdf)
    assert isinstance(result, CcqsResult)
    assert result.monochrome == 20.0
    assert result.dimension_density == 20.0
    assert result.ft_in_labels == 20.0
    assert result.layout_completeness == 20.0
    assert result.total == 80.0


def test_color_pdf_loses_monochrome_points():
    result = compute_ccqs_deterministic(_color_pdf())
    assert result.monochrome < 15.0


def test_sparse_pdf_scores_low():
    result = compute_ccqs_deterministic(_mono_pdf_with_text(["hello"]))
    assert result.dimension_density == 0.0
    assert result.ft_in_labels == 0.0
    assert result.layout_completeness == 0.0


def test_metric_dimensions_count_toward_density():
    pdf = _mono_pdf_with_text(["3.50 m", "4.25 m", "2.10 m"])
    result = compute_ccqs_deterministic(pdf)
    assert result.dimension_density == 6.0  # 3 dims x 2.0


def test_as_dict_shape():
    d = compute_ccqs_deterministic(_mono_pdf_with_text(["x"])).as_dict()
    assert set(d) == {
        "total",
        "max",
        "monochrome",
        "dimension_density",
        "ft_in_labels",
        "layout_completeness",
    }
    assert d["max"] == 80
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_ccqs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.quality'`

- [ ] **Step 4: Write the implementation**

`backend/app/quality/__init__.py`: empty file.

`backend/app/quality/ccqs.py`:

```python
"""CCQS — CAD Quality Composite Score, deterministic components only (0-80).

Extracted from experiments/eval.py. The 5th component (vision-judged visual
quality) intentionally stays a dev-time tool — the CI gate and the user-facing
badge use ONLY these 4 deterministic, API-free components (locked decision,
docs/plans/2026-07-03-fable-stage1-phase0-plan.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz  # pymupdf

_DIM_PATTERN = re.compile(r"\d+'-?\d+\"|\d+\.\d+\s*m")
_FTIN_PATTERN = re.compile(r"\d+'-\d+\"")

DETERMINISTIC_MAX = 80


@dataclass
class CcqsResult:
    total: float
    monochrome: float
    dimension_density: float
    ft_in_labels: float
    layout_completeness: float
    debug: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "max": DETERMINISTIC_MAX,
            "monochrome": self.monochrome,
            "dimension_density": self.dimension_density,
            "ft_in_labels": self.ft_in_labels,
            "layout_completeness": self.layout_completeness,
        }


def _open(pdf_bytes: bytes) -> fitz.Document:
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def compute_monochromaticity(pdf_bytes: bytes) -> float:
    """Render page 0, mean pixel saturation -> 0-20 (low saturation = good)."""
    doc = _open(pdf_bytes)
    try:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.0, 1.0), colorspace=fitz.csRGB)
    finally:
        doc.close()
    samples = pix.samples
    n_pixels = len(samples) // 3
    if n_pixels == 0:
        return 0.0
    total_sat = 0.0
    for i in range(n_pixels):
        r = samples[i * 3] / 255.0
        g = samples[i * 3 + 1] / 255.0
        b = samples[i * 3 + 2] / 255.0
        mx = max(r, g, b)
        total_sat += (mx - min(r, g, b)) / mx if mx > 0 else 0.0
    mean_sat = total_sat / n_pixels
    return round(20 * (1.0 - min(mean_sat, 1.0)), 2)


def compute_text_scores(pdf_bytes: bytes) -> tuple[float, float, float, dict]:
    """Extract all text -> (dim_density, ft_in, completeness, debug)."""
    doc = _open(pdf_bytes)
    try:
        all_text = "".join(pg.get_text() for pg in doc)
    finally:
        doc.close()

    dim_count = len(_DIM_PATTERN.findall(all_text))
    ftin_count = len(_FTIN_PATTERN.findall(all_text))
    dim_score = min(20.0, round(dim_count * 2.0, 2))
    ftin_score = min(20.0, round(ftin_count * 4.0, 2))

    text_upper = all_text.upper()
    both_floors = ("GROUND FLOOR" in text_upper or "G.F" in text_upper) and (
        "FIRST FLOOR" in text_upper or "F.F" in text_upper or "FF" in text_upper
    )
    has_sqft = "SQFT" in text_upper or "SQ.FT" in text_upper or "SQ FT" in text_upper
    has_schedule = (
        "SCHEDULE" in text_upper
        or "STATEMENT" in text_upper
        or ("ROOM" in text_upper and "AREA" in text_upper)
    )
    has_totals = "TOTAL" in text_upper and (
        "AREA" in text_upper or "SQFT" in text_upper or "SQ.FT" in text_upper
    )
    has_compass = "NORTH" in text_upper or " N " in all_text

    completeness = float(
        (4 if both_floors else 0)
        + (4 if has_sqft else 0)
        + (4 if has_schedule else 0)
        + (4 if has_totals else 0)
        + (4 if has_compass else 0)
    )

    debug = {
        "dim_count": dim_count,
        "ftin_count": ftin_count,
        "both_floors": both_floors,
        "has_sqft": has_sqft,
        "has_schedule": has_schedule,
        "has_totals": has_totals,
        "has_compass": has_compass,
    }
    return dim_score, ftin_score, completeness, debug


def compute_ccqs_deterministic(pdf_bytes: bytes) -> CcqsResult:
    mono = compute_monochromaticity(pdf_bytes)
    dim_score, ftin_score, completeness, debug = compute_text_scores(pdf_bytes)
    total = round(mono + dim_score + ftin_score + completeness, 2)
    return CcqsResult(
        total=total,
        monochrome=mono,
        dimension_density=dim_score,
        ft_in_labels=ftin_score,
        layout_completeness=completeness,
        debug=debug,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ccqs.py -v`
Expected: 5 PASS

- [ ] **Step 6: Lint, format, commit**

```bash
cd backend && uv run ruff format . && uv run ruff check . && cd ..
git add backend/app/quality/ backend/tests/test_ccqs.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(quality): deterministic 4-component CCQS scorer (0-80) on PDF bytes

Extracted from the untracked experiments/eval.py; vision VQ component
deliberately excluded (locked decision - CI gate is deterministic only).
pymupdf promoted to a main dependency for in-memory PDF scoring.

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task 2: Frozen geometry fixture + baseline generator script

**Files:**
- Create: `backend/scripts/make_ccqs_fixture.py`
- Create (generated by running the script, then committed): `backend/tests/fixtures/ccqs_fixture.json`, `backend/app/quality/ccqs_baseline.json`

**Interfaces:**
- Consumes: `compute_ccqs_deterministic` (Task 1); existing `app.engine.generator.generate`, `app.engine.models.PlotConfig`, `app.engine.pdf.render_pdf`, `app.services.layout_store.layout_out_from_engine`.
- Produces: `backend/tests/fixtures/ccqs_fixture.json` with shape `{"cfg": {<PlotConfig kwargs>}, "geometry": {<LayoutOut dict>}}` and `backend/app/quality/ccqs_baseline.json` with shape `CcqsResult.as_dict()`. Task 3's gate test loads both.

**Why a frozen fixture:** CP-SAT is not guaranteed run-to-run deterministic (threading, version drift), so the CI gate must never invoke the solver. We solve ONCE here, freeze the winning geometry JSON (the same `LayoutOut` shape the `layouts` table stores), and CI re-renders the PDF from that frozen dict — reportlab rendering IS deterministic.

- [ ] **Step 1: Write the script**

`backend/scripts/make_ccqs_fixture.py`:

```python
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
from dataclasses import asdict
from pathlib import Path

from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.engine.pdf import render_pdf
from app.quality.ccqs import compute_ccqs_deterministic
from app.services.layout_store import layout_out_from_engine

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
```

- [ ] **Step 2: Run it and eyeball the baseline**

Run: `cd backend && uv run python scripts/make_ccqs_fixture.py`
Expected: prints both paths and a score dict. Sanity floor: `total >= 60`, `monochrome == 20.0` (the drawing pipeline is B/W). If total is far below the historical 80/80 deterministic subscore (`experiments/scores.json`), STOP and report — Phase 1's solver-objective change may have altered layouts, but a *large* drop means a drawing regression to investigate before freezing a bad baseline.

- [ ] **Step 3: Commit fixture + baseline + script**

```bash
git add backend/scripts/make_ccqs_fixture.py backend/tests/fixtures/ccqs_fixture.json backend/app/quality/ccqs_baseline.json
git commit -m "feat(quality): frozen CCQS fixture geometry + committed baseline

Solver runs once here; CI renders from the frozen LayoutOut JSON so the
gate never depends on CP-SAT determinism.

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task 3: CCQS CI regression gate test

**Files:**
- Create: `backend/tests/test_ccqs_gate.py`

**Interfaces:**
- Consumes: `backend/tests/fixtures/ccqs_fixture.json`, `backend/app/quality/ccqs_baseline.json` (Task 2), `compute_ccqs_deterministic` (Task 1), existing `engine_layout_from_geometry` (`app/services/layout_store.py:193`), `render_pdf` (`app/engine/pdf.py:181`), `PlotConfig`.
- Produces: a test that runs inside the existing `uv run pytest` CI step (`.github/workflows/backend-ci.yml`) — no new CI job needed; pytest IS the gate.

- [ ] **Step 1: Write the gate test (it should PASS immediately — the "failing first" check here is mutation: temporarily lower the baseline tolerance to -100 and confirm it still passes, then break the fixture path and confirm it fails loudly)**

`backend/tests/test_ccqs_gate.py`:

```python
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
```

- [ ] **Step 2: Run the gate**

Run: `cd backend && uv run pytest tests/test_ccqs_gate.py -v`
Expected: 2 PASS

- [ ] **Step 3: Mutation-check the gate actually bites**

Temporarily edit `ccqs_baseline.json`, set `"total"` to `999`, re-run — expected: `test_ccqs_total_meets_baseline` FAILS with the regression message. Revert the edit (`git checkout backend/app/quality/ccqs_baseline.json`), re-run — PASS.

- [ ] **Step 4: Run the full backend suite (the gate joins CI's pytest step automatically)**

Run: `cd backend && uv run pytest -q`
Expected: all pass (263 existing + new)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_ccqs_gate.py
git commit -m "test(quality): CCQS regression gate vs committed baseline in CI pytest

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task 4: Layout quality endpoint

**Files:**
- Modify: `backend/app/api/routes/export.py` (it already owns `_get_project`, stored-layout fetch, `render_pdf` import — the quality score is a property of the exported PDF, so it lives with exports)
- Test: `backend/tests/test_quality_endpoint.py`

**Interfaces:**
- Consumes: `compute_ccqs_deterministic`, `CcqsResult.as_dict()` (Task 1); existing helpers in `export.py` (`_get_project`, `layout_store.get_or_generate_layouts`, `layout_store.engine_layout_from_geometry`, `_cfg_from_project`, `render_pdf`).
- Produces: `GET /projects/{project_id}/layouts/{layout_id}/quality` → `200 {"total": float, "max": 80, "monochrome": float, "dimension_density": float, "ft_in_labels": float, "layout_completeness": float}`; `404` for unknown layout. Task 5's badge fetches this via the frontend proxy.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_quality_endpoint.py` — follow the existing pattern in `backend/tests/test_layout_persistence.py` for creating a project + stored layout through the conftest fixtures (in-memory SQLite, auth override). Structure:

```python
"""GET /projects/{id}/layouts/{layout_id}/quality returns the deterministic CCQS."""

import pytest

# Reuse the project-creation + client fixtures exactly as
# tests/test_layout_persistence.py does (same conftest).


@pytest.mark.anyio
async def test_quality_endpoint_scores_stored_layout(client, seeded_project):
    project_id, layout_key = seeded_project  # adapt to conftest fixture names
    resp = await client.get(f"/api/projects/{project_id}/layouts/{layout_key}/quality")
    assert resp.status_code == 200
    body = resp.json()
    assert body["max"] == 80
    assert 0 <= body["total"] <= 80
    for key in ("monochrome", "dimension_density", "ft_in_labels", "layout_completeness"):
        assert key in body


@pytest.mark.anyio
async def test_quality_endpoint_404_for_unknown_layout(client, seeded_project):
    project_id, _ = seeded_project
    resp = await client.get(f"/api/projects/{project_id}/layouts/nope/quality")
    assert resp.status_code == 404
```

**Implementer note:** open `backend/tests/test_layout_persistence.py` first and copy its exact fixture usage (client construction, project seeding, auth override, route prefix — verify whether routes are mounted under `/api`). The test above is the shape; the fixture names must match the real conftest.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_quality_endpoint.py -v`
Expected: FAIL with 404/405 (route doesn't exist)

- [ ] **Step 3: Implement the endpoint in `export.py`**

Add imports at top: `from app.quality.ccqs import compute_ccqs_deterministic`

Add after the `export_pdf` route:

```python
@router.get("/projects/{project_id}/layouts/{layout_id}/quality")
async def layout_quality(
    project_id: str,
    layout_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await _get_project(project_id, user_id, db)
    cfg = _cfg_from_project(project)

    stored = await layout_store.get_or_generate_layouts(project, db)
    row = next((r for r in stored if r.layout_key == layout_id), None)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layout {layout_id!r} not found",
        )
    layout = layout_store.engine_layout_from_geometry(row.geometry)
    pdf_bytes = render_pdf(project.name, layout, cfg, project.num_bedrooms)
    return compute_ccqs_deterministic(pdf_bytes).as_dict()
```

(Match the exact import style already in `export.py` — it already imports `layout_store`, `render_pdf`, `HTTPException`, `status`, `Depends`, `get_current_user_id`, `get_db`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_quality_endpoint.py tests/test_ccqs.py -v`
Expected: PASS

- [ ] **Step 5: Lint, commit**

```bash
cd backend && uv run ruff format . && uv run ruff check . && cd ..
git add backend/app/api/routes/export.py backend/tests/test_quality_endpoint.py
git commit -m "feat(quality): layout quality endpoint - deterministic CCQS of the stored geometry's PDF

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task 5: Frontend CAD-quality badge on layout cards

**Files:**
- Create: `frontend/src/lib/cad-quality.ts` (pure helpers)
- Test: `frontend/src/lib/cad-quality.test.ts`
- Modify: `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx` (badge beside the existing `ScoreBadge` on the layout cards, ~line 906)

**Interfaces:**
- Consumes: Task 4's endpoint via the existing catch-all proxy `frontend/src/app/api/backend/[...path]/route.ts` → fetch URL `/api/backend/projects/${projectId}/layouts/${layoutKey}/quality`.
- Produces: `CadQuality` type + `cadQualityLabel(q: CadQuality): string` in `cad-quality.ts`; a `CadQualityBadge` component inside `layout-viewer.tsx`.

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/cad-quality.test.ts`:

```typescript
import { describe, expect, it } from "bun:test";
import { type CadQuality, cadQualityLabel, cadQualityTone } from "./cad-quality";

const q = (total: number): CadQuality => ({
  total,
  max: 80,
  monochrome: 20,
  dimension_density: 20,
  ft_in_labels: 20,
  layout_completeness: 20,
});

describe("cadQualityLabel", () => {
  it("formats as CAD n/80 with rounding", () => {
    expect(cadQualityLabel(q(76.4))).toBe("CAD 76/80");
    expect(cadQualityLabel(q(80))).toBe("CAD 80/80");
  });
});

describe("cadQualityTone", () => {
  it("classifies good/ok/poor at 70 and 50 thresholds", () => {
    expect(cadQualityTone(q(72))).toBe("good");
    expect(cadQualityTone(q(60))).toBe("ok");
    expect(cadQualityTone(q(40))).toBe("poor");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && bun test src/lib/cad-quality.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `frontend/src/lib/cad-quality.ts`**

```typescript
export type CadQuality = {
  total: number;
  max: number;
  monochrome: number;
  dimension_density: number;
  ft_in_labels: number;
  layout_completeness: number;
};

export function cadQualityLabel(q: CadQuality): string {
  return `CAD ${Math.round(q.total)}/${q.max}`;
}

export function cadQualityTone(q: CadQuality): "good" | "ok" | "poor" {
  if (q.total >= 70) return "good";
  if (q.total >= 50) return "ok";
  return "poor";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && bun test src/lib/cad-quality.test.ts`
Expected: PASS

- [ ] **Step 5: Wire the badge into `layout-viewer.tsx`**

Add a small client component near the existing `ScoreBadge` (line ~107) that lazily fetches once per layout and renders nothing until loaded (no spinner — badge is progressive enhancement). Match the surrounding styling idiom (Tailwind + the pill classes used by `ScoreBadge`):

```tsx
function CadQualityBadge({
  projectId,
  layoutKey,
}: {
  projectId: string;
  layoutKey: string;
}) {
  const [quality, setQuality] = useState<CadQuality | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/backend/projects/${projectId}/layouts/${layoutKey}/quality`)
      .then((r) => (r.ok ? r.json() : null))
      .then((q) => {
        if (!cancelled && q) setQuality(q);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [projectId, layoutKey]);
  if (!quality) return null;
  const tone = cadQualityTone(quality);
  return (
    <span
      className={
        tone === "good"
          ? "rounded-full px-2 py-0.5 text-xs bg-emerald-500/15 text-emerald-400"
          : tone === "ok"
            ? "rounded-full px-2 py-0.5 text-xs bg-amber-500/15 text-amber-400"
            : "rounded-full px-2 py-0.5 text-xs bg-red-500/15 text-red-400"
      }
      title="Deterministic CAD drawing quality (monochrome, dimensions, labels, completeness)"
    >
      {cadQualityLabel(quality)}
    </span>
  );
}
```

Import `useState`/`useEffect` (already imported in this file) and `type CadQuality, cadQualityLabel, cadQualityTone` from `@/lib/cad-quality`. Render it in the layout-card map (line ~906) next to `{l.score && <ScoreBadge score={l.score.total} />}`:

```tsx
<CadQualityBadge projectId={projectId} layoutKey={l.id} />
```

**Implementer note:** confirm the actual prop/variable names in scope at line 889–906 (`projectId` may be `project.id` or similar) before inserting; check how `l.id` is used in existing export links to get the right layout key. Match the file's existing badge styling — if `ScoreBadge` uses different classes (Blueprint Dark theme utility classes), reuse those instead of the raw Tailwind above.

- [ ] **Step 6: Lint + full frontend tests**

Run: `cd frontend && bun run lint && bun test`
Expected: clean, all tests pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/cad-quality.ts frontend/src/lib/cad-quality.test.ts "frontend/src/app/(app)/projects/[id]/layout-viewer.tsx"
git commit -m "feat(frontend): CAD quality badge on layout cards from the quality endpoint

Karthikeyan N <karthiknitt@gmail.com>"
```

---

## Part B — AI Render Layer Foundation (2a)

### Task 6: PDF page → PNG helper

**Files:**
- Create: `backend/app/quality/pdf_image.py`
- Test: `backend/tests/test_pdf_image.py`

**Interfaces:**
- Consumes: nothing new (pymupdf from Task 1).
- Produces: `pdf_page_png(pdf_bytes: bytes, page_idx: int = 0, scale: float = 1.5) -> bytes` (raw PNG bytes). Tasks 8–9 use it to build the render reference image.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_pdf_image.py`:

```python
from io import BytesIO

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.quality.pdf_image import pdf_page_png

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _two_page_pdf() -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(100, 700, "PAGE ONE")
    c.showPage()
    c.drawString(100, 700, "PAGE TWO")
    c.showPage()
    c.save()
    return buf.getvalue()


def test_returns_png_bytes():
    png = pdf_page_png(_two_page_pdf())
    assert png.startswith(PNG_MAGIC)
    assert len(png) > 1000


def test_scale_changes_output_dimensions():
    small = pdf_page_png(_two_page_pdf(), scale=1.0)
    large = pdf_page_png(_two_page_pdf(), scale=2.0)
    assert len(large) != len(small)


def test_page_index_out_of_range_clamps_to_last():
    png = pdf_page_png(_two_page_pdf(), page_idx=99)
    assert png.startswith(PNG_MAGIC)


def test_empty_bytes_raises():
    with pytest.raises(Exception):
        pdf_page_png(b"")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_pdf_image.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement**

`backend/app/quality/pdf_image.py`:

```python
"""Render a PDF page to PNG bytes — reference images for AI renders and
dev-time visual checks. pymupdf only; no API calls."""

from __future__ import annotations

import fitz  # pymupdf


def pdf_page_png(pdf_bytes: bytes, page_idx: int = 0, scale: float = 1.5) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[min(page_idx, len(doc) - 1)]
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB)
        return pix.tobytes("png")
    finally:
        doc.close()
```

- [ ] **Step 4: Run tests, lint, commit**

Run: `cd backend && uv run pytest tests/test_pdf_image.py -v && uv run ruff format . && uv run ruff check .`
Expected: 4 PASS, clean lint

```bash
git add backend/app/quality/pdf_image.py backend/tests/test_pdf_image.py
git commit -m "feat(quality): pdf_page_png helper - PDF page to PNG reference images

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task 7: Spatial render-prompt builder

**Files:**
- Create: `backend/app/engine/render_prompt.py`
- Test: `backend/tests/test_render_prompt.py`

**Interfaces:**
- Consumes: the persisted geometry dict (`StoredLayout.geometry`, `LayoutOut` shape — floors have `rooms: [{id,name,type,x,y,width,depth,area}]`).
- Produces: `build_render_prompt(geometry: dict, *, plot_length_m: float, plot_width_m: float, north_direction: str = "N", floor: str = "ground_floor", style: str = DEFAULT_STYLE) -> str`. Pure function — Tasks 8–9 and the eventual render endpoint pass its output to providers.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_render_prompt.py`:

```python
from app.engine.render_prompt import build_render_prompt

GEOMETRY = {
    "id": "A",
    "name": "Layout A",
    "ground_floor": {
        "floor": 0,
        "rooms": [
            {"id": "gf-liv", "name": "Living Room", "type": "living", "x": 1.0, "y": 1.0, "width": 4.5, "depth": 3.6, "area": 16.2},
            {"id": "gf-kit", "name": "Kitchen", "type": "kitchen", "x": 5.5, "y": 1.0, "width": 2.8, "depth": 3.0, "area": 8.4},
        ],
        "columns": [],
    },
    "first_floor": {
        "floor": 1,
        "rooms": [
            {"id": "ff-bed1", "name": "Master Bedroom", "type": "bedroom", "x": 1.0, "y": 1.0, "width": 4.0, "depth": 3.5, "area": 14.0},
        ],
        "columns": [],
    },
}


def test_prompt_names_every_room_with_dimensions():
    prompt = build_render_prompt(GEOMETRY, plot_length_m=15.0, plot_width_m=9.0)
    assert "Living Room" in prompt
    assert "4.5" in prompt and "3.6" in prompt
    assert "Kitchen" in prompt


def test_prompt_selects_floor():
    prompt = build_render_prompt(
        GEOMETRY, plot_length_m=15.0, plot_width_m=9.0, floor="first_floor"
    )
    assert "Master Bedroom" in prompt
    assert "Kitchen" not in prompt


def test_prompt_includes_plot_and_north():
    prompt = build_render_prompt(
        GEOMETRY, plot_length_m=15.0, plot_width_m=9.0, north_direction="NE"
    )
    assert "15.0" in prompt and "9.0" in prompt
    assert "NE" in prompt


def test_prompt_instructs_fidelity_to_reference():
    prompt = build_render_prompt(GEOMETRY, plot_length_m=15.0, plot_width_m=9.0)
    assert "reference" in prompt.lower()
    assert "exact" in prompt.lower() or "match" in prompt.lower()


def test_unknown_floor_raises():
    import pytest

    with pytest.raises(KeyError):
        build_render_prompt(
            GEOMETRY, plot_length_m=15.0, plot_width_m=9.0, floor="attic"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_render_prompt.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement**

`backend/app/engine/render_prompt.py`:

```python
"""Structured spatial prompt for AI floor-plan renders.

Pure function over the persisted layout geometry (LayoutOut-shaped dict) —
no API calls, fully unit-testable. The reference/control image (the CAD SVG
or PDF page rendered to PNG) travels alongside this prompt to the provider.
"""

from __future__ import annotations

DEFAULT_STYLE = (
    "photorealistic top-down 3D architectural visualization (dollhouse view), "
    "soft daylight, realistic materials: matte plaster walls, wooden and tiled "
    "flooring appropriate to each room, subtle furniture staging per room type"
)


def build_render_prompt(
    geometry: dict,
    *,
    plot_length_m: float,
    plot_width_m: float,
    north_direction: str = "N",
    floor: str = "ground_floor",
    style: str = DEFAULT_STYLE,
) -> str:
    if floor not in geometry or geometry[floor] is None:
        raise KeyError(f"floor {floor!r} not present in geometry")
    fp = geometry[floor]
    floor_label = floor.replace("_", " ").title()

    room_lines = []
    for r in fp.get("rooms", []):
        room_lines.append(
            f"- {r['name']} ({r['type']}): {r['width']:.1f}m wide x "
            f"{r['depth']:.1f}m deep, positioned {r['x']:.1f}m from the left "
            f"edge and {r['y']:.1f}m from the bottom edge"
        )
    rooms_block = "\n".join(room_lines)

    return (
        f"Render the {floor_label} of an Indian residential house "
        f"({plot_length_m:.1f}m x {plot_width_m:.1f}m plot, north facing "
        f"{north_direction}).\n\n"
        f"Rooms (positions and sizes are exact, in metres):\n{rooms_block}\n\n"
        f"Style: {style}.\n\n"
        "IMPORTANT: The attached reference image is the exact CAD floor plan. "
        "Match the room positions, proportions and wall layout of the "
        "reference exactly — do not move, resize, add or remove any room. "
        "Walls are 230mm external / 115mm internal. Keep the same orientation "
        "as the reference image."
    )
```

- [ ] **Step 4: Run tests, lint, commit**

Run: `cd backend && uv run pytest tests/test_render_prompt.py -v && uv run ruff format . && uv run ruff check .`
Expected: 5 PASS

```bash
git add backend/app/engine/render_prompt.py backend/tests/test_render_prompt.py
git commit -m "feat(engine): spatial render-prompt builder from persisted geometry

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task 8: Provider adapters (Gemini / OpenAI / OpenRouter)

**Files:**
- Create: `backend/app/services/render_providers.py`
- Modify: `backend/app/config/settings.py` (add render keys)
- Modify: `backend/pyproject.toml` (promote httpx to main dependency: `cd backend && uv add "httpx>=0.28"`)
- Test: `backend/tests/test_render_providers.py`

**Interfaces:**
- Consumes: prompt string (Task 7), reference PNG bytes (Task 6).
- Produces:
  - `RenderResult` dataclass: `image_png: bytes`, `provider: str`, `model: str`, `cost_usd: float | None`
  - `RenderProviderError(Exception)` with readable message
  - `async def render_image(prompt: str, reference_png: bytes, provider: str, *, api_key: str, model: str | None = None, timeout: float = 120.0) -> RenderResult` where `provider` ∈ `{"gemini", "openai", "openrouter"}`
  - Settings gains: `gemini_api_key: str = ""`, `openai_api_key: str = ""`, `openrouter_api_key: str = ""`, `render_provider: str = ""`, `render_model: str = ""`

**⚠️ API-currency step:** Before implementing, verify the CURRENT request/response shapes with the find-docs skill / `ctx7` CLI (`npx ctx7@latest library "Google Gemini API" "image generation REST generateContent inline_data"`, same for "OpenAI Images API gpt-image-1 edits" and "OpenRouter image generation modalities"). The payloads below are the best-known shapes as of 2026-07; adjust to what the docs say and keep the tests' mocked shapes in sync.

- [ ] **Step 1: Verify current provider API shapes (ctx7/find-docs), note any deltas**

- [ ] **Step 2: Write the failing tests (mock httpx via `httpx.MockTransport`)**

`backend/tests/test_render_providers.py`:

```python
import base64
import json

import httpx
import pytest

from app.services.render_providers import (
    RenderProviderError,
    RenderResult,
    render_image,
)

FAKE_PNG = b"\x89PNG\r\n\x1a\nfakepixels"
FAKE_B64 = base64.b64encode(FAKE_PNG).decode()


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.anyio
async def test_gemini_happy_path(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "generativelanguage.googleapis.com" in str(request.url)
        body = json.loads(request.content)
        parts = body["contents"][0]["parts"]
        assert any("inline_data" in p for p in parts)
        assert any("text" in p for p in parts)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"inline_data": {"mime_type": "image/png", "data": FAKE_B64}}]}}
                ]
            },
        )

    import app.services.render_providers as rp

    monkeypatch.setattr(rp, "_transport_for_tests", _transport(handler))
    result = await render_image("prompt", FAKE_PNG, "gemini", api_key="k")
    assert isinstance(result, RenderResult)
    assert result.image_png == FAKE_PNG
    assert result.provider == "gemini"


@pytest.mark.anyio
async def test_openrouter_happy_path(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "openrouter.ai" in str(request.url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"images": [{"image_url": {"url": f"data:image/png;base64,{FAKE_B64}"}}]}}
                ]
            },
        )

    import app.services.render_providers as rp

    monkeypatch.setattr(rp, "_transport_for_tests", _transport(handler))
    result = await render_image("prompt", FAKE_PNG, "openrouter", api_key="k")
    assert result.image_png == FAKE_PNG


@pytest.mark.anyio
async def test_provider_error_raises_readable_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}})

    import app.services.render_providers as rp

    monkeypatch.setattr(rp, "_transport_for_tests", _transport(handler))
    with pytest.raises(RenderProviderError, match="gemini"):
        await render_image("prompt", FAKE_PNG, "gemini", api_key="k")


@pytest.mark.anyio
async def test_unknown_provider_raises():
    with pytest.raises(RenderProviderError, match="unknown provider"):
        await render_image("prompt", FAKE_PNG, "dalle", api_key="k")


@pytest.mark.anyio
async def test_missing_key_raises():
    with pytest.raises(RenderProviderError, match="api_key"):
        await render_image("prompt", FAKE_PNG, "gemini", api_key="")
```

(Add an OpenAI happy-path test mirroring the gemini one once Step 1 confirms the current `images/edits` multipart response shape — assert `data[0].b64_json` decoding.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_render_providers.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: Implement**

`backend/app/services/render_providers.py` (adjust endpoint/payload details to Step 1's doc findings):

```python
"""Image-render provider adapters — Gemini, OpenAI, OpenRouter.

One interface: render_image(prompt, reference_png, provider, api_key=...).
Provider choice is config (RENDER_PROVIDER env) — locked decision: bake-off
picks the default before this is user-facing.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

# Test seam: tests monkeypatch this with httpx.MockTransport.
_transport_for_tests: httpx.AsyncBaseTransport | None = None

GEMINI_MODEL = "gemini-2.5-flash-image"
OPENAI_MODEL = "gpt-image-1"
OPENROUTER_MODEL = "google/gemini-2.5-flash-image"

# Indicative per-image cost (USD) — refined at bake-off from real usage data.
_COSTS = {"gemini": 0.039, "openai": 0.07, "openrouter": 0.04}


@dataclass
class RenderResult:
    image_png: bytes
    provider: str
    model: str
    cost_usd: float | None


class RenderProviderError(Exception):
    pass


def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=_transport_for_tests)


async def render_image(
    prompt: str,
    reference_png: bytes,
    provider: str,
    *,
    api_key: str,
    model: str | None = None,
    timeout: float = 120.0,
) -> RenderResult:
    if not api_key:
        raise RenderProviderError(f"{provider}: api_key is empty")
    if provider == "gemini":
        return await _render_gemini(prompt, reference_png, api_key, model, timeout)
    if provider == "openai":
        return await _render_openai(prompt, reference_png, api_key, model, timeout)
    if provider == "openrouter":
        return await _render_openrouter(prompt, reference_png, api_key, model, timeout)
    raise RenderProviderError(f"unknown provider {provider!r}")


async def _render_gemini(
    prompt: str, reference_png: bytes, api_key: str, model: str | None, timeout: float
) -> RenderResult:
    model = model or GEMINI_MODEL
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": base64.b64encode(reference_png).decode(),
                        }
                    },
                    {"text": prompt},
                ]
            }
        ]
    }
    async with _client(timeout) as client:
        resp = await client.post(url, json=payload, headers={"x-goog-api-key": api_key})
    if resp.status_code != 200:
        raise RenderProviderError(f"gemini: HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        parts = resp.json()["candidates"][0]["content"]["parts"]
        data = next(p["inline_data"]["data"] for p in parts if "inline_data" in p)
    except (KeyError, IndexError, StopIteration) as e:
        raise RenderProviderError(f"gemini: no image in response ({e})") from e
    return RenderResult(base64.b64decode(data), "gemini", model, _COSTS["gemini"])


async def _render_openai(
    prompt: str, reference_png: bytes, api_key: str, model: str | None, timeout: float
) -> RenderResult:
    model = model or OPENAI_MODEL
    async with _client(timeout) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": model, "prompt": prompt},
            files={"image": ("reference.png", reference_png, "image/png")},
        )
    if resp.status_code != 200:
        raise RenderProviderError(f"openai: HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        b64 = resp.json()["data"][0]["b64_json"]
    except (KeyError, IndexError) as e:
        raise RenderProviderError(f"openai: no image in response ({e})") from e
    return RenderResult(base64.b64decode(b64), "openai", model, _COSTS["openai"])


async def _render_openrouter(
    prompt: str, reference_png: bytes, api_key: str, model: str | None, timeout: float
) -> RenderResult:
    model = model or OPENROUTER_MODEL
    payload = {
        "model": model,
        "modalities": ["image", "text"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,"
                            + base64.b64encode(reference_png).decode()
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    async with _client(timeout) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://planforge.app",
                "X-Title": "PlanForge Render",
            },
        )
    if resp.status_code != 200:
        raise RenderProviderError(
            f"openrouter: HTTP {resp.status_code}: {resp.text[:300]}"
        )
    try:
        url = resp.json()["choices"][0]["message"]["images"][0]["image_url"]["url"]
        b64 = url.split("base64,", 1)[1]
    except (KeyError, IndexError) as e:
        raise RenderProviderError(f"openrouter: no image in response ({e})") from e
    return RenderResult(base64.b64decode(b64), "openrouter", model, _COSTS["openrouter"])
```

Settings additions in `backend/app/config/settings.py` (inside `Settings`):

```python
    # AI render layer (Phase 2) — all optional; provider picked at bake-off
    render_provider: str = ""
    render_model: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
```

- [ ] **Step 5: Run tests, lint, commit**

Run: `cd backend && uv run pytest tests/test_render_providers.py -v && uv run ruff format . && uv run ruff check .`
Expected: PASS

```bash
git add backend/app/services/render_providers.py backend/app/config/settings.py backend/tests/test_render_providers.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(render): provider adapters (gemini/openai/openrouter) behind one interface

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task 9: Bake-off harness script

**Files:**
- Create: `backend/scripts/render_bakeoff.py`

**Interfaces:**
- Consumes: `build_render_prompt` (Task 7), `pdf_page_png` (Task 6), `render_image`/`RenderProviderError` (Task 8), `generate`/`PlotConfig`/`render_pdf`/`layout_out_from_engine` (existing), fixture from Task 2.
- Produces: `experiments/renders/<config>_<provider>.png` + `experiments/renders/bakeoff_results.json` (`{runs: [{config, provider, model, cost_usd, output, error}], skipped_providers: [...]}`).

- [ ] **Step 1: Write the script**

`backend/scripts/render_bakeoff.py`:

```python
"""Render bake-off: same layouts through every provider with a key set.

    cd backend && uv run python scripts/render_bakeoff.py [--providers gemini,openai,openrouter]

Reads keys from env (GEMINI_API_KEY / OPENAI_API_KEY / OPENROUTER_API_KEY).
Writes PNGs + bakeoff_results.json to ../experiments/renders/. Providers
without keys are skipped and reported — the script never fails on a missing
key. Total spend is a few test renders (~USD 0.5); the locked budget cap.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.engine.pdf import render_pdf
from app.engine.render_prompt import build_render_prompt
from app.quality.pdf_image import pdf_page_png
from app.services.layout_store import layout_out_from_engine
from app.services.render_providers import RenderProviderError, render_image

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "experiments" / "renders"

KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

CONFIGS = {
    "3bhk_rect": PlotConfig(
        plot_length=15.0, plot_width=9.0,
        setback_front=1.5, setback_rear=1.0, setback_left=1.0, setback_right=1.0,
        num_bedrooms=3, toilets=2, parking=True, num_floors=2,
    ),
    "2bhk_compact": PlotConfig(
        plot_length=12.0, plot_width=8.0,
        setback_front=1.5, setback_rear=1.0, setback_left=0.9, setback_right=0.9,
        num_bedrooms=2, toilets=1, parking=False, num_floors=2,
    ),
    "3bhk_lshape": PlotConfig(
        plot_length=14.0, plot_width=10.0,
        setback_front=1.5, setback_rear=1.0, setback_left=1.0, setback_right=1.0,
        num_bedrooms=3, toilets=2, parking=True, num_floors=2,
        plot_shape="l_shaped", cutout_corner="NE", cutout_width=4.0, cutout_height=3.5,
    ),
}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", default="gemini,openai,openrouter")
    args = parser.parse_args()
    wanted = [p.strip() for p in args.providers.split(",") if p.strip()]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    runs: list[dict] = []
    skipped = [p for p in wanted if not os.environ.get(KEY_ENV.get(p, ""), "")]
    active = [p for p in wanted if p not in skipped]
    print(f"providers: {active} (skipped, no key: {skipped})")

    for cfg_name, cfg in CONFIGS.items():
        layouts = generate(cfg)
        if not layouts:
            runs.append({"config": cfg_name, "error": "no layouts generated"})
            continue
        layout = layouts[0]
        geometry = layout_out_from_engine(layout).model_dump()
        pdf_bytes = render_pdf(f"Bakeoff {cfg_name}", layout, cfg, cfg.num_bedrooms)
        reference_png = pdf_page_png(pdf_bytes, page_idx=0, scale=1.5)
        (OUT_DIR / f"{cfg_name}_reference.png").write_bytes(reference_png)
        prompt = build_render_prompt(
            geometry, plot_length_m=cfg.plot_length, plot_width_m=cfg.plot_width,
        )

        for provider in active:
            key = os.environ[KEY_ENV[provider]]
            try:
                result = await render_image(prompt, reference_png, provider, api_key=key)
                out = OUT_DIR / f"{cfg_name}_{provider}.png"
                out.write_bytes(result.image_png)
                runs.append({
                    "config": cfg_name, "provider": provider, "model": result.model,
                    "cost_usd": result.cost_usd, "output": str(out), "error": None,
                })
                print(f"OK   {cfg_name} x {provider} -> {out.name}")
            except RenderProviderError as e:
                runs.append({
                    "config": cfg_name, "provider": provider,
                    "model": None, "cost_usd": None, "output": None, "error": str(e),
                })
                print(f"FAIL {cfg_name} x {provider}: {e}")

    total_cost = sum(r["cost_usd"] or 0 for r in runs if r.get("cost_usd"))
    results = {"runs": runs, "skipped_providers": skipped, "est_total_cost_usd": total_cost}
    (OUT_DIR / "bakeoff_results.json").write_text(json.dumps(results, indent=2))
    print(f"est total cost: ${total_cost:.2f} -> {OUT_DIR / 'bakeoff_results.json'}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Dry-run with no keys (validates wiring without spend)**

Run: `cd backend && env -u GEMINI_API_KEY -u OPENAI_API_KEY -u OPENROUTER_API_KEY uv run python scripts/render_bakeoff.py`
Expected: all 3 providers reported skipped, 3 `*_reference.png` files written, `bakeoff_results.json` written with empty runs cost 0. (This also smoke-tests generate→pdf→png→prompt end-to-end.)

- [ ] **Step 3: Lint, commit**

```bash
cd backend && uv run ruff format . && uv run ruff check . && cd ..
git add backend/scripts/render_bakeoff.py
git commit -m "feat(render): bake-off harness - same layouts through every keyed provider

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task 10: ⛔ CHECKPOINT — run the bake-off, present to Karthik

**Not a coding task.** Steps:

- [ ] Locate keys: check `backend/.env` / `frontend/.env.local` for `OPENAI_API_KEY` / `OPENROUTER_API_KEY` (do NOT print values). `GEMINI_API_KEY` likely absent — the Phase 0 plan says Karthik must supply it (free tier).
- [ ] Run the bake-off with whatever keys exist: `cd backend && uv run python scripts/render_bakeoff.py`
- [ ] Send Karthik: reference PNG + each provider's render side-by-side per config, plus `bakeoff_results.json` costs (SendUserFile).
- [ ] **needs input:** (1) which provider becomes `RENDER_PROVIDER` default, (2) tier gating — Pro-only or per-render credit add-on, (3) Gemini key if he wants Gemini in the comparison.
- [ ] Part C proceeds only after these answers.

---

## Part C — Render Productization (POST-CHECKPOINT ONLY)

### Task 11: `layout_renders` table + render endpoints

**⚠️ Run `Workflow({ name: 'db-migration-safe', args: 'add layout_renders table (id, project_id FK CASCADE, layout_id FK layouts.id CASCADE, layout_hash, provider, model, image_png bytea, created_at)' })` BEFORE writing the model, and apply any mandates it returns.**

**Files:**
- Create: `backend/app/models/render.py`
- Create: `backend/app/api/routes/render.py`, register in `backend/app/main.py` (mirror how other routers are included; add explicit model import per Phase 1's db-migration-safe mandate — see `app/main.py` imports)
- Test: `backend/tests/test_render_endpoint.py`

**Interfaces:**
- Consumes: Tasks 6–8 + `settings.render_provider` / key fields; `get_effective_plan_tier` (`app/services/plans.py`) for gating; `layout_store.get_stored_layout`.
- Produces:
  - `POST /projects/{project_id}/layouts/{layout_id}/render` → generates (or returns cached) render; `202`-style sync JSON `{"cached": bool, "provider": str, "model": str}`; `402` if tier below the gate; `503` if no provider configured.
  - `GET /projects/{project_id}/layouts/{layout_id}/render` → `image/png` bytes or `404`.
  - Cache key: `layout_hash = sha256(json.dumps(row.geometry, sort_keys=True))` + provider — regenerate only when geometry changed.

**Model:**

```python
"""Cached AI renders per layout geometry-hash."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.db import Base


class LayoutRender(Base):
    __tablename__ = "layout_renders"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    layout_id: Mapped[str] = mapped_column(
        ForeignKey("layouts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    layout_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    image_png: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

**Endpoint sketch (`app/api/routes/render.py`)** — TDD it with mocked `render_image` (monkeypatch), following `test_layout_persistence.py` fixtures:

```python
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db  # match export.py's actual import path
from app.config.settings import settings
from app.engine.pdf import render_pdf
from app.engine.render_prompt import build_render_prompt
from app.models.render import LayoutRender
from app.quality.pdf_image import pdf_page_png
from app.services import layout_store
from app.services.plans import get_effective_plan_tier
from app.services.render_providers import RenderProviderError, render_image

router = APIRouter()

_PROVIDER_KEYS = {
    "gemini": lambda: settings.gemini_api_key,
    "openai": lambda: settings.openai_api_key,
    "openrouter": lambda: settings.openrouter_api_key,
}

RENDER_MIN_TIER = "pro"  # confirm at checkpoint (tier gating decision)


def _geometry_hash(geometry: dict) -> str:
    return hashlib.sha256(
        json.dumps(geometry, sort_keys=True).encode()
    ).hexdigest()
```

(POST: gate tier → load stored layout via `layout_store.get_stored_layout` → hash → return cached row if hash+provider match → else render PDF→PNG reference, build prompt, `await render_image(...)`, upsert row. GET: return latest matching row's `image_png` as `Response(media_type="image/png")`. Tier comparison: reuse how `export.py`'s DXF gate compares tiers — read it first. `503` when `settings.render_provider` empty; map `RenderProviderError` to `502`.)

Tests must cover: 402 below tier, 503 unconfigured, cache hit (second POST doesn't call the mocked `render_image` again), cache miss after geometry edit (different hash), GET 404 before first render.

Commit: `feat(render): persisted per-geometry-hash render cache + gated endpoints`

### Task 12: Frontend "Render" tab

**Files:**
- Modify: `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx`: extend the tab union (line ~325) to `"plan" | "section" | "boq" | "chat" | "compare" | "render"`, add to the tab row array (line ~1413) and label chain, add `{activeTab === "render" && (...)}` block modeled on the section tab (line ~1803).
- Tab content: "Generate render" button → `POST /api/backend/projects/{id}/layouts/{key}/render`, then `<img src={/api/backend/... GET url}>`; loading state while POST in flight; upsell card when 402 (mirror existing Pro upsell for DXF export if one exists in this file — search `402` / `upgrade`); error toast on 5xx.
- Test: extend `frontend/src/lib/cad-quality.test.ts` pattern — pure helpers only if any are extracted; UI behavior verified on Vercel preview.

Commit: `feat(frontend): Render tab - generate + view AI render of the active layout`

---

## Final ceremony

- [ ] Update `Status.md` (phase 2 section: what shipped, checkpoint outcome, deployment notes — new env vars `RENDER_PROVIDER`/`RENDER_MODEL`/key names for Cloud Run GitHub secrets).
- [ ] `Workflow({ name: 'finish-feature' })` — full ceremony (scoped tests → pre-push gates → pr-quality-gate → PR → ci-green-loop). PR must target `worktree-stage1-phase1-hardening` (stacked), not `main` — pass/verify the base branch when the PR is created.
- [ ] PR description: what + why, note the stack on PR #11 and the Task 10 checkpoint outcome.

## Self-review notes

- Spec coverage: 2a → Tasks 6–12 (prompt ✓ reference image ✓ adapters ✓ bake-off ✓ tab ✓ caching ✓ gating ✓); 2b → Tasks 1–5 (extraction ✓ CI gate ✓ badge ✓ VQ stays dev-time ✓). Baseline re-baselining after B6 solver change: Task 2 solves fresh post-Phase-1, satisfying the plan's "re-baseline once" risk note.
- Deliberate deviations from the Phase-0 text: (1) reference image = PDF page 0 → PNG (server-side, deterministic, pymupdf already needed) instead of "SVG rendered to PNG" — the SVG only exists client-side; same visual content. (2) CI gate = pytest test in the existing CI pytest step, not a separate workflow job — same gate, less CI YAML. (3) Render cache in Postgres `bytea` (Neon) not object storage — no new infra for MVP; revisit if renders exceed a few MB.
- Placeholder scan: Task 4/11 intentionally delegate exact conftest fixture names and router-registration details to the implementer with pointers to the reference files (they must read the real conftest — names were not verifiable at plan time and inventing them would be worse). Task 8 payloads flagged for doc verification (API currency).
