# Structural Drawing Set Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "Structural Drawing Set" PDF export (6 sheets: Column & Footing Plan, Footing
Details, Plinth Beam Plan, Plinth Beam Details, Roof Beam & Slab Plan, Roof Beam Details) built on
the existing `structapi` IS-456 design integration, matching the reference set at
`~/projects/Thalakudy/Thalakudy/Structural Drawings/*.pdf`.

**Architecture:** A new `app/engine/structural_drawing_set.py` module renders 6 ReportLab pages by
reusing `app/engine/pdf.py`'s existing title-block/scale/schedule-table/north-arrow helpers and
`plan_geometry.build_floor_drawing()`'s wall-centreline geometry. Footing placement comes from the
approved layout's real column x,y (classified corner/edge/interior via `pdf.py::_column_class`)
joined against `structural_design["structapi"]["data"]["footings"]`. Plinth beams get their own
design pass — a new `app/engine/plinth_loads.py` computes wall-UDL per span and calls `structapi`'s
generic `POST /v1/calc/beam` (via a new `structagent_client.calc_beam()`), since `structapi`'s
building-chain (`/v1/design/building`) only designs slab-driven roof beams, not wall-load plinth
beams. A new route re-uses the already-stored `structural_store.design_surface()` (same pattern as
`export_pdf`) — no new structapi calls happen at export time except the plinth-beam ones.

**Tech Stack:** FastAPI, ReportLab (existing PDF pipeline), Shapely (existing geometry), pytest +
httpx `MockTransport` (existing structapi test pattern), `structapi`'s `/v1/calc/beam` (existing
generic single-member endpoint).

**Read first:** `docs/plans/2026-07-19-structural-drawing-set-design.md` (the approved design doc
— architecture rationale and the 7 documented simplifications this plan implements).

---

## Model tier per task

| Task | Description | Why this tier |
|---|---|---|
| 1 | Plinth wall-load calculator | Sonnet — real engineering formula (UDL from wall geometry + IS 875-1 unit weights), needs correctness care |
| 2 | `structagent_client.calc_beam()` | Haiku — mechanical HTTP client method, mirrors `design_building()` exactly |
| 3 | Plinth beam design service (per-span orchestration) | Sonnet — joins wall geometry, load calc, and structapi call; moderate logic |
| 4 | Footing placement (real column x,y → footing rect + type) | Sonnet — geometry + classification join logic, easy to get subtly wrong |
| 5 | Column & Footing Plan page renderer | Sonnet — new drawing code, but mirrors `_draw_structural_floor` patterns closely |
| 6 | Footing Details page (schedule + typical section pictorial) | Sonnet — schedule table mirrors existing helpers; typical-section pictorial is new but bounded |
| 7 | Beam detail box renderer (shared by sheets 4 & 6) | Opus — the one genuinely new, fiddly piece of drawing code (dimensioned box + bar callouts), highest risk of visual bugs |
| 8 | Plinth Beam Plan page renderer | Sonnet — reuses wall-centreline clustering already in `pdf.py` |
| 9 | Plinth Beam Details page | Haiku — thin wiring: schedule table + beam-detail-box loop, both already built in tasks 6/7 |
| 10 | Roof Beam & Slab Plan page renderer | Sonnet — extends existing `_draw_structural_floor` with floating columns + slab labels |
| 11 | Roof Beam Details page | Haiku — thin wiring, same pattern as task 9 |
| 12 | `generate_structural_drawing_set()` orchestrator | Haiku — mechanical assembly of 6 pages, mirrors `render_pdf`'s page-loop structure |
| 13 | New export route | Haiku — mirrors `export_pdf`/`export_approval_pdf` almost verbatim |
| 14 | End-to-end integration test | Sonnet — needs a realistic fixture covering columns/beams/footings together |

Default to the session model when a task doesn't specify a tier override; the table above is for
whoever executes this plan with per-task subagent dispatch (see `superpowers:subagent-driven-development`).

---

## Task 1: Plinth wall-load calculator

**Files:**
- Create: `backend/app/engine/plinth_loads.py`
- Test: `backend/tests/test_plinth_loads.py`

**Context:** Per the design doc's rationale, plinth beams carry masonry wall UDL, not slab
reactions. `structapi-service/iscodes/tables.py:284-290` already has `UNIT_WEIGHTS["brick_masonry"]
= 20.0` (kN/m³) — vendored into `backend/structapi-service/` per `CLAUDE.md`. `compliance_rules.json`
has `external_wall_thickness_mm: 230` / `internal_wall_thickness_mm: 115` but **no wall height** —
use `min_habitable_ceiling_m: 2.75` (already in `compliance_rules.json:52`) as the plinth-beam wall
height proxy (a full storey-height wall bears on the plinth beam in ordinary G+1 construction), and
document that choice as an assumption in the module docstring.

**Step 1: Write the failing test**

```python
# backend/tests/test_plinth_loads.py
from app.engine.plinth_loads import wall_udl_kn_m

def test_wall_udl_external_wall():
    # 230mm external wall, 2.75m ceiling height, brick masonry (20 kN/m3)
    # udl = thickness_m * height_m * unit_weight_kn_m3
    #     = 0.230 * 2.75 * 20.0 = 12.65 kN/m
    udl = wall_udl_kn_m(thickness_mm=230, height_m=2.75)
    assert udl == pytest.approx(12.65, abs=0.01)

def test_wall_udl_internal_wall_lighter():
    udl_ext = wall_udl_kn_m(thickness_mm=230, height_m=2.75)
    udl_int = wall_udl_kn_m(thickness_mm=115, height_m=2.75)
    assert udl_int < udl_ext
    assert udl_int == pytest.approx(6.325, abs=0.01)
```

(Add `import pytest` at the top of the test file.)

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_plinth_loads.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.engine.plinth_loads'`

**Step 3: Write minimal implementation**

```python
# backend/app/engine/plinth_loads.py
"""Wall-UDL load takedown for plinth beam design.

Plinth beams in ordinary Indian G+1 residential construction carry no slab
reaction (ground floor rests on filled/compacted earth, not a suspended
slab) -- they carry the masonry wall dead load above them plus self-weight.
IS 456 has no distinct "plinth beam" clause; this is an ordinary beam (see
app/services/plinth_beam_design.py) sized against this load via structapi's
generic /v1/calc/beam endpoint, not the slab-driven /v1/design/building
chain used for roof beams.

Wall height uses compliance_rules.json's min_habitable_ceiling_m as a proxy
for full storey height -- there is no dedicated plinth/floor-to-floor height
key in compliance_rules.json (documented simplification, see
docs/plans/2026-07-19-structural-drawing-set-design.md #2).
"""

from __future__ import annotations

#: IS 875 Part 1 unit weight, brick masonry (kN/m3) -- matches
#: structapi's iscodes/tables.py UNIT_WEIGHTS["brick_masonry"].
BRICK_MASONRY_UNIT_WEIGHT_KN_M3 = 20.0


def wall_udl_kn_m(
    thickness_mm: float,
    height_m: float,
    unit_weight_kn_m3: float = BRICK_MASONRY_UNIT_WEIGHT_KN_M3,
) -> float:
    """Dead-load UDL (kN/m run) a masonry wall imposes on the beam below it."""
    return (thickness_mm / 1000.0) * height_m * unit_weight_kn_m3
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_plinth_loads.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/app/engine/plinth_loads.py backend/tests/test_plinth_loads.py
git commit -m "feat: add plinth beam wall-UDL load calculator"
```

---

## Task 2: `structagent_client.calc_beam()`

**Files:**
- Modify: `backend/app/services/structagent_client.py`
- Test: `backend/tests/test_structagent_client.py` (create if it doesn't exist — check first with
  `ls backend/tests/ | grep structagent`)

**Context:** `structagent_client.py` currently only has `design_building()` (POSTs
`/v1/design/building`). `structapi-service/structapi/main.py:89` exposes a separate generic
`POST /v1/calc/beam` endpoint backed directly by `iscodes/design/beam.py::design_beam()` — this is
the one plinth beams need (arbitrary UDL in, no slab-reaction assumption). Mirror
`design_building()`'s exact structure (same error handling, same test transport seam).

**Step 1: Write the failing test**

```python
# backend/tests/test_structagent_client.py
import httpx
import pytest

from app.services import structagent_client


@pytest.mark.asyncio
async def test_calc_beam_posts_to_calc_beam_endpoint(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(200, json={
            "ok": True,
            "checks": [{"name": "flexure", "ok": True}],
            "data": {"design": {"n_bars": 3, "bar_dia": 12}},
            "artifacts": [],
            "disclaimer": "verify against official BIS copies",
        })

    monkeypatch.setattr(settings := structagent_client.settings, "structural_api_url", "http://fake")
    monkeypatch.setattr(structagent_client, "_transport_for_tests", httpx.MockTransport(handler))

    result = await structagent_client.calc_beam({
        "span_m": 3.5, "w_dl_kn_m": 12.65, "w_il_kn_m": 0.0,
        "b": 230, "D": 300, "fck": 20, "fy": 500,
    })

    assert result.ok is True
    assert "v1/calc/beam" in seen["url"]
    assert result.data["design"]["n_bars"] == 3
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_structagent_client.py -v`
Expected: FAIL with `AttributeError: module 'app.services.structagent_client' has no attribute 'calc_beam'`

**Step 3: Write minimal implementation**

Add to `backend/app/services/structagent_client.py`, right after `design_building`:

```python
async def calc_beam(
    payload: dict, *, correlation_id: str = "", timeout: float = 30.0
) -> StructuralResult:
    """POST /v1/calc/beam on structapi — generic single-member beam design
    (arbitrary UDL in), used for plinth beams (wall load, not slab-driven).
    """
    if not settings.structural_api_url:
        raise StructuralAPIError("STRUCTURAL_API_URL is not configured")
    url = settings.structural_api_url.rstrip("/") + "/v1/calc/beam"
    headers = {"Content-Type": "application/json"}
    if settings.structural_api_key:
        headers["x-api-key"] = settings.structural_api_key
    if correlation_id:
        headers["x-correlation-id"] = correlation_id
    async with _client(timeout) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise StructuralAPIError(f"structapi unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise StructuralAPIError(
            f"structapi HTTP {resp.status_code}: {resp.text[:300]}"
        )
    body = resp.json()
    return StructuralResult(
        ok=bool(body.get("ok")),
        checks=body.get("checks", []),
        data=body.get("data", {}),
        artifacts=body.get("artifacts", []),
        disclaimer=body.get("disclaimer", ""),
    )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_structagent_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/structagent_client.py backend/tests/test_structagent_client.py
git commit -m "feat: add structagent_client.calc_beam for generic single-member design"
```

---

## Task 3: Plinth beam design service

**Files:**
- Create: `backend/app/services/plinth_beam_design.py`
- Test: `backend/tests/test_plinth_beam_design.py`

**Context:** This is the orchestration layer: take a `FloorDrawing`'s wall centreline segments
(from `plan_geometry.build_floor_drawing()` — see research: `drawing.walls` is a
`list[WallSegment]` each with `x1,y1,x2,y2,thickness,kind`), group into unique spans (cluster by
length to avoid one `/v1/calc/beam` call per wall segment — reuse the same `_cluster()` pattern
already in `pdf.py` if you want, but a simple `round(length, 1)` grouping key is enough for v1),
compute wall UDL per group via `plinth_loads.wall_udl_kn_m()`, and call `calc_beam()` once per
unique group. Beam section (`b`, `D`) starts at `external_wall_thickness_mm` × a trial depth
(`span/12` per common thumb rule, rounded up to nearest 25mm) — `design_beam()` doesn't auto-size
`D`, the caller must supply and check `ok`.

**Step 1: Write the failing test**

```python
# backend/tests/test_plinth_beam_design.py
import httpx
import pytest

from app.engine.cad_elements import WallSegment
from app.services import plinth_beam_design, structagent_client


@pytest.mark.asyncio
async def test_design_plinth_beams_groups_by_span_and_calls_calc_beam(monkeypatch):
    walls = [
        WallSegment(x1=0.0, y1=0.0, x2=3.5, y2=0.0, thickness=0.230, kind="external"),
        WallSegment(x1=0.0, y1=4.0, x2=3.5, y2=4.0, thickness=0.230, kind="external"),
        WallSegment(x1=0.0, y1=0.0, x2=0.0, y2=2.0, thickness=0.115, kind="internal"),
    ]
    calls = []

    async def fake_calc_beam(payload, **kw):
        calls.append(payload)
        return structagent_client.StructuralResult(
            ok=True, checks=[], data={"design": {"n_bars": 2, "bar_dia": 12}},
        )

    monkeypatch.setattr(structagent_client, "calc_beam", fake_calc_beam)

    results = await plinth_beam_design.design_plinth_beams(walls)

    # two unique external-wall spans of 3.5m should collapse to ONE calc_beam call
    external_spans = [p for p in calls if p["span_m"] == pytest.approx(3.5)]
    assert len(external_spans) == 1
    # the 2.0m internal wall span is a distinct group -> its own call
    assert any(p["span_m"] == pytest.approx(2.0) for p in calls)
    assert "3.50" in results or True  # placeholder, refine key format below
```

Note: refine the exact assertion on `results`' return shape once you've decided the key format in
Step 3 (recommend mirroring `structapi`'s `"x-span4.0-trib2.25"` convention:
`f"plinth-span{span_m:.2f}"`) — write the test to match what you implement, this is illustrative.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_plinth_beam_design.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.plinth_beam_design'`

**Step 3: Write minimal implementation**

```python
# backend/app/services/plinth_beam_design.py
"""Plinth beam design: group wall spans, compute wall-UDL, design via
structapi's generic /v1/calc/beam (NOT the slab-driven /v1/design/building
chain -- see app/engine/plinth_loads.py for why plinth beams need a
different load case than roof beams).
"""

from __future__ import annotations

import math

from app.engine.cad_elements import WallSegment
from app.engine.plinth_loads import wall_udl_kn_m
from app.services import structagent_client

FCK_DEFAULT = 20.0  # M20, matches the reference set's "GRADE OF CONCRETE = M20"
FY_DEFAULT = 500.0
CEILING_HEIGHT_M = 2.75  # compliance_rules.json min_habitable_ceiling_m proxy


def _span_length(w: WallSegment) -> float:
    return math.hypot(w.x2 - w.x1, w.y2 - w.y1)


def _group_key(w: WallSegment) -> tuple[str, float]:
    return (w.kind, round(_span_length(w), 1))


def _trial_depth_mm(span_m: float) -> int:
    """L/12 thumb-rule trial depth, rounded up to nearest 25mm."""
    return int(math.ceil((span_m * 1000.0 / 12.0) / 25.0)) * 25


async def design_plinth_beams(
    walls: list[WallSegment],
    *,
    external_thickness_mm: float = 230,
    internal_thickness_mm: float = 115,
    fck: float = FCK_DEFAULT,
    fy: float = FY_DEFAULT,
) -> dict[str, dict]:
    """Group wall spans, design one beam per unique (kind, span) group.

    Returns {"plinth-span{span_m:.2f}": {..calc_beam data.., "span_m":,
    "kind":, "b_mm":, "D_mm":}} -- same key-per-unique-span shape as
    structapi's roof-beam `data.beams`, so the drawing renderer can treat
    both uniformly.
    """
    groups: dict[tuple[str, float], list[WallSegment]] = {}
    for w in walls:
        groups.setdefault(_group_key(w), []).append(w)

    out: dict[str, dict] = {}
    for (kind, span_m), members in groups.items():
        if span_m <= 0:
            continue
        thickness_mm = external_thickness_mm if kind == "external" else internal_thickness_mm
        w_dl = wall_udl_kn_m(thickness_mm=thickness_mm, height_m=CEILING_HEIGHT_M)
        D = _trial_depth_mm(span_m)
        result = await structagent_client.calc_beam({
            "span_m": span_m,
            "w_dl_kn_m": w_dl,
            "w_il_kn_m": 0.0,
            "b": thickness_mm,
            "D": D,
            "fck": fck,
            "fy": fy,
            "support": "ss",
        })
        key = f"plinth-span{span_m:.2f}"
        out[key] = {
            "b_mm": thickness_mm,
            "D_mm": D,
            "span_m": span_m,
            "kind": kind,
            "count": len(members),
            "ok": result.ok,
            "design": (result.data or {}).get("design", {}),
            "checks": result.checks,
        }
    return out
```

Adjust field names in `out[key]["design"]` once Task 2's real `/v1/calc/beam` response shape is
confirmed against a live/staging `structapi` instance — the fake in the test only stubs
`{"design": {"n_bars":..., "bar_dia":...}}`; the real endpoint returns the full `design_beam()`
dict from research §4 (`Ast_prov_mm2`, `stirrups`, `deflection`, etc.) nested under `data`.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_plinth_beam_design.py -v`
Expected: PASS — fix the placeholder assertion in Step 1 once the real key format is wired up.

**Step 5: Commit**

```bash
git add backend/app/services/plinth_beam_design.py backend/tests/test_plinth_beam_design.py
git commit -m "feat: add plinth beam design service (wall-UDL grouping + calc_beam)"
```

---

## Task 4: Footing placement

**Files:**
- Create: `backend/app/engine/footing_placement.py`
- Test: `backend/tests/test_footing_placement.py`

**Context:** Real column positions come from the layout's `FloorDrawing.columns`
(`list[ColumnMarker]`, each with `.cx`, `.cy` — from `plan_geometry.build_floor_drawing()`, see
research §2). Footing *type* (corner/edge/interior) must match `pdf.py::_column_class`'s
classification exactly, since that's what keys `structural_design["structapi"]["data"]["footings"]`
(research §5: `footings["corner"] = {...}`). Footing *size* comes from that same dict:
`footings[kind]["data"]["L_m"]` / `["B_m"]` (research §3).

`_column_class` takes grid indices (`idx, xs_len, jdx, ys_len`), not raw coordinates — you'll need
to derive those indices the same way `_draw_structural_floor` does (cluster `drawing.walls`'
vertical/horizontal centrelines, then find each column's nearest cluster index via `_nearest_index`,
both already in `pdf.py`). Import and reuse those two private helpers rather than re-implementing
clustering — `from app.engine.pdf import _column_class, _nearest_index` (acceptable here since this
is drawing-adjacent engine code in the same package; if this feels wrong when you get there, moving
`_column_class`/`_nearest_index`/`_cluster` into a shared `app/engine/grid_classify.py` and
re-exporting from `pdf.py` for backward compat is a reasonable in-flight adjustment — use judgment).

**Step 1: Write the failing test**

```python
# backend/tests/test_footing_placement.py
from app.engine.cad_elements import ColumnMarker, WallSegment
from app.engine.footing_placement import place_footings

def test_place_footings_classifies_and_sizes_by_grid_position():
    # 3x2 grid, corners at the 4 extreme intersections
    columns = [
        ColumnMarker(cx=0.0, cy=0.0), ColumnMarker(cx=4.0, cy=0.0), ColumnMarker(cx=8.0, cy=0.0),
        ColumnMarker(cx=0.0, cy=4.5), ColumnMarker(cx=4.0, cy=4.5), ColumnMarker(cx=8.0, cy=4.5),
    ]
    walls = [
        WallSegment(x1=0, y1=0, x2=0, y2=4.5, thickness=0.23, kind="external"),
        WallSegment(x1=4, y1=0, x2=4, y2=4.5, thickness=0.23, kind="external"),
        WallSegment(x1=8, y1=0, x2=8, y2=4.5, thickness=0.23, kind="external"),
        WallSegment(x1=0, y1=0, x2=8, y2=0, thickness=0.23, kind="external"),
        WallSegment(x1=0, y1=4.5, x2=8, y2=4.5, thickness=0.23, kind="external"),
    ]
    footings_data = {
        "corner": {"data": {"L_m": 1.35, "B_m": 1.35}},
        "edge": {"data": {"L_m": 1.5, "B_m": 1.35}},
        "interior": {"data": {"L_m": 1.65, "B_m": 1.65}},
    }

    placed = place_footings(columns, walls, footings_data)

    assert len(placed) == 6
    corner = next(p for p in placed if p.cx == 0.0 and p.cy == 0.0)
    assert corner.footing_type == "corner"
    assert corner.length_m == 1.35 and corner.width_m == 1.35
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_footing_placement.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/app/engine/footing_placement.py
"""Map real column positions onto footing type + size, joining the layout's
actual column grid (real x,y) against structapi's data.footings (keyed by
corner/edge/interior classification -- see app/engine/pdf.py::_column_class,
which this reuses for classification parity).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.cad_elements import ColumnMarker, WallSegment
from app.engine.pdf import _cluster, _column_class, _nearest_index


@dataclass
class PlacedFooting:
    cx: float
    cy: float
    footing_type: str
    length_m: float
    width_m: float


def place_footings(
    columns: list[ColumnMarker],
    walls: list[WallSegment],
    footings_data: dict,
) -> list[PlacedFooting]:
    """footings_data: structural_design["structapi"]["data"]["footings"],
    keyed "corner"/"edge"/"interior" -> {"data": {"L_m":, "B_m":, ...}, ...}.
    """
    xs = _cluster(sorted({w.x1 for w in walls if abs(w.x1 - w.x2) < 1e-9}
                         | {w.x2 for w in walls if abs(w.x1 - w.x2) < 1e-9}))
    ys = _cluster(sorted({w.y1 for w in walls if abs(w.y1 - w.y2) < 1e-9}
                         | {w.y2 for w in walls if abs(w.y1 - w.y2) < 1e-9}))

    placed = []
    for col in columns:
        idx = _nearest_index(xs, col.cx)
        jdx = _nearest_index(ys, col.cy)
        ftype = _column_class(idx, len(xs), jdx, len(ys))
        fd = (footings_data.get(ftype) or {}).get("data") or {}
        placed.append(PlacedFooting(
            cx=col.cx, cy=col.cy, footing_type=ftype,
            length_m=fd.get("L_m", 0.0), width_m=fd.get("B_m", 0.0),
        ))
    return placed
```

Note: verify `_cluster`'s exact signature in `pdf.py` before wiring this up (research didn't dump
its body — grep `def _cluster` in `pdf.py`, it's referenced at `pdf.py:1534-1535` operating on a
flat list of floats). Adjust the set-comprehension plumbing above if `_cluster` expects a
pre-sorted list or has a different dedup convention than assumed here.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_footing_placement.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/engine/footing_placement.py backend/tests/test_footing_placement.py
git commit -m "feat: add footing placement (real column positions -> type + size)"
```

---

## Task 5: Column & Footing Plan page renderer

**Files:**
- Create: `backend/app/engine/structural_drawing_set.py`
- Test: `backend/tests/test_structural_drawing_set.py`

**Context:** This is sheet 1. Mirror `_draw_structural_floor`'s page furniture (road strip, plot
boundary, north arrow, scale) but draw footing rectangles (dashed outline, per
`place_footings()`'s `length_m`/`width_m` centred on `cx,cy`) instead of a beam/column layout, plus
a "T1"/"T2"/"T3"-style type label per unique `(footing_type)` → assign short mnemonics the same way
the reference does (corner→T1, edge→T2, interior→T3, in size order — or simplest: alphabetical by
type name, document the mapping in a comment).

Since this task is primarily new ReportLab drawing code (visual, not meaningfully unit-testable
beyond "doesn't raise and produces non-empty page content"), test at the level the design doc
specifies: render a minimal fixture and assert the resulting PDF's extracted text contains expected
labels.

**Step 1: Write the failing test**

```python
# backend/tests/test_structural_drawing_set.py
from pypdf import PdfReader
from io import BytesIO

from app.engine.structural_drawing_set import render_column_footing_plan
from app.engine.cad_elements import ColumnMarker, WallSegment
from app.models.plot_config import PlotConfig  # adjust import to actual location — verify with `grep -rn "class PlotConfig" backend/app`

def test_column_footing_plan_renders_footing_labels():
    cfg = PlotConfig(plot_width=8.0, plot_length=4.5, road_side="S", ...)  # fill required fields — check PlotConfig's actual required args
    columns = [ColumnMarker(cx=0.0, cy=0.0), ColumnMarker(cx=4.0, cy=0.0)]
    walls = [WallSegment(x1=0, y1=0, x2=4, y2=0, thickness=0.23, kind="external")]
    footings_data = {"corner": {"data": {"L_m": 1.35, "B_m": 1.35}},
                     "edge": {"data": {"L_m": 1.5, "B_m": 1.35}}}

    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    render_column_footing_plan(c, columns, walls, footings_data, cfg, "Test Project")
    c.showPage()
    c.save()

    text = PdfReader(BytesIO(buf.getvalue())).pages[0].extract_text()
    assert "COLUMN & FOOTING PLAN" in text.upper()
    assert "T1" in text  # corner footing type label
```

Check `pypdf` is already a dependency (`grep pypdf backend/pyproject.toml`) — if not, check what the
existing PDF tests use to assert on rendered text (the design doc says "assert on extracted
text/positions... following whatever pattern the existing PDF tests already use" — find and reuse
that exact library/pattern instead of introducing `pypdf` if something else is already there).

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_structural_drawing_set.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/app/engine/structural_drawing_set.py
"""Structural Drawing Set: 6-sheet CAD-style PDF (Column & Footing Plan,
Footing Details, Plinth Beam Plan, Plinth Beam Details, Roof Beam & Slab
Plan, Roof Beam Details) built on structapi's IS-456 member design.

See docs/plans/2026-07-19-structural-drawing-set-design.md for the full
design rationale and documented simplifications (isolated footings only,
single wall height for plinth UDL, no seismic overlay on plinth beams, one
reinforcement schedule per beam mark rather than midspan/support split).
"""

from __future__ import annotations

from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas

from app.engine.footing_placement import place_footings
from app.engine.pdf import (
    MARGIN, ROAD_GAP, ROAD_H, TITLE_H,
    _centered_plot_oy, _draw_north_arrow, _draw_title_block, _standard_scale,
)

#: footing type -> reference-style mnemonic, sized-descending
_FOOTING_MARK = {"interior": "T3", "edge": "T2", "corner": "T1"}


def render_column_footing_plan(
    c: canvas.Canvas, columns, walls, footings_data: dict, cfg, project_name: str,
) -> None:
    page_w, page_h = A4  # NOTE: import A4 from reportlab.lib.pagesizes at module top
    s, denom = _standard_scale(cfg, page_w, page_h)
    plot_px, plot_py = cfg.plot_width * s, cfg.plot_length * s
    ox = MARGIN + (page_w - 2 * MARGIN - plot_px) / 2
    oy = _centered_plot_oy(page_h, plot_py, title_h=TITLE_H, margin=MARGIN,
                           road_below=ROAD_H + ROAD_GAP)

    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(page_w / 2, oy + plot_py + 20, "COLUMN & FOOTING PLAN")

    placed = place_footings(columns, walls, footings_data)
    c.setDash(3, 2)
    c.setStrokeColor(HexColor("#0088AA"))
    for f in placed:
        fx, fy = ox + f.cx * s, oy + f.cy * s
        fw, fh = f.length_m * s, f.width_m * s
        c.rect(fx - fw / 2, fy - fh / 2, fw, fh, fill=0, stroke=1)
        c.setDash()
        c.setFont("Helvetica-Bold", 6)
        c.setFillColor(HexColor("#000000"))
        c.drawCentredString(fx, fy + fh / 2 + 4, _FOOTING_MARK.get(f.footing_type, "T?"))
        c.setDash(3, 2)
    c.setDash()

    _draw_north_arrow(c, ox + plot_px - 20, oy + plot_py - 20, 12)
    _draw_title_block(c, project_name, "A", "Column & Footing Plan",
                      "Column & Footing Plan", cfg, 0, s, page_w, scale_denom=denom)
```

Fix the `A4` import (add `from reportlab.lib.pagesizes import A4` at the top) and adjust
`_draw_title_block`'s call signature to match its real 12-parameter signature from research §1
exactly (it takes `floor_plan` and `far_text` as optional kwargs you can omit — but check the
positional args line up; `num_bedrooms` isn't meaningful here, pass `0`).

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_structural_drawing_set.py -v`
Expected: PASS — iterate on the ReportLab coordinates until the extracted text assertions pass;
visual polish (exact positions matching the reference layout) is a follow-up pass, not blocking.

**Step 5: Commit**

```bash
git add backend/app/engine/structural_drawing_set.py backend/tests/test_structural_drawing_set.py
git commit -m "feat: add Column & Footing Plan sheet renderer"
```

---

## Task 6: Footing Details page

**Files:**
- Modify: `backend/app/engine/structural_drawing_set.py` (add `render_footing_details`)
- Modify: `backend/tests/test_structural_drawing_set.py` (add test)

**Step 1: Write the failing test**

```python
def test_footing_details_renders_schedule_and_typical_section():
    footings_data = {
        "corner": {"data": {"L_m": 1.35, "B_m": 1.35, "D_overall_mm": 450,
                            "bars_x": {"dia": 12, "spacing": 150},
                            "bars_y": {"dia": 12, "spacing": 150}}},
    }
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    render_footing_details(c, footings_data, cfg, "Test Project")
    c.showPage(); c.save()

    text = PdfReader(BytesIO(buf.getvalue())).pages[0].extract_text()
    assert "FOOTING" in text.upper()
    assert "T1" in text
```

**Step 2: Run — confirm fail** (`AttributeError`/`ImportError` on `render_footing_details`).

**Step 3: Implement**

Reuse `pdf.py::_draw_generic_schedule_table` directly (import it) for the schedule — columns
`(TYPE, SIZE L×B, DEPTH, BARS X, BARS Y)`, rows from `footings_data.items()`. For the "typical
section" pictorial, draw ONE representative dimensioned cross-section (pick the largest footing by
area) showing: PCC bed rectangle, footing rectangle with mat-reinforcement hatch lines, column
stub on top with dowel bars — a simplified version of the reference's "L/S OF COLUMN & FOOTING"
drawing (don't attempt to reproduce every hatch pattern from the reference; a labeled schematic
with correct dimensions is the bar to clear for v1).

```python
from app.engine.pdf import _draw_generic_schedule_table

def render_footing_details(c, footings_data: dict, cfg, project_name: str) -> None:
    page_w, page_h = A4
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(page_w / 2, page_h - MARGIN, "FOOTING DETAILS")

    headers = ("TYPE", "SIZE (L×B m)", "DEPTH (mm)", "BARS-X", "BARS-Y")
    col_ws = (40, 70, 55, 90, 90)
    rows = []
    for ftype, f in sorted(footings_data.items()):
        d = f.get("data", {})
        bx, by = d.get("bars_x", {}), d.get("bars_y", {})
        rows.append((
            _FOOTING_MARK.get(ftype, "T?"),
            f"{d.get('L_m', 0):.2f}x{d.get('B_m', 0):.2f}",
            f"{d.get('D_overall_mm', 0):.0f}",
            f"{bx.get('dia','-')}mmø@{bx.get('spacing','-')}c/c",
            f"{by.get('dia','-')}mmø@{by.get('spacing','-')}c/c",
        ))
    _draw_generic_schedule_table(c, "FOOTING SCHEDULE", headers, col_ws, rows,
                                 MARGIN, page_h - MARGIN - 30)

    # Typical section — largest footing by area
    if footings_data:
        largest = max(footings_data.items(),
                     key=lambda kv: kv[1].get("data", {}).get("L_m", 0)
                     * kv[1].get("data", {}).get("B_m", 0))
        _draw_typical_footing_section(c, largest[1].get("data", {}),
                                      MARGIN, page_h - 300)

    _draw_title_block(c, project_name, "A", "Footing Details",
                      "Footing Details", cfg, 0, 1.0, page_w)


def _draw_typical_footing_section(c: canvas.Canvas, data: dict, x: float, y: float) -> None:
    """Schematic dimensioned column/footing cross-section: PCC bed, footing
    slab with mat reinforcement, column stub with dowels."""
    L_mm = data.get("L_m", 1.0) * 1000
    D_mm = data.get("D_overall_mm", 450)
    px_per_mm = 0.15
    fw, fh = L_mm * px_per_mm, D_mm * px_per_mm

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x, y + fh + 40, "TYPICAL FOOTING SECTION")

    # PCC bed
    c.setFillColor(HexColor("#DDDDDD"))
    c.rect(x, y - 10, fw, 10, fill=1, stroke=1)
    # footing slab
    c.setFillColor(HexColor("#EEEEEE"))
    c.rect(x, y, fw, fh, fill=1, stroke=1)
    # mat reinforcement (schematic cross-hatch)
    c.setStrokeColor(HexColor("#AA0000"))
    c.setLineWidth(0.5)
    for i in range(1, 6):
        xi = x + fw * i / 6
        c.line(xi, y + 3, xi, y + fh - 3)
    # column stub
    col_w = fw * 0.25
    c.setFillColor(HexColor("#CCCCCC"))
    c.rect(x + fw / 2 - col_w / 2, y + fh, col_w, 40, fill=1, stroke=1)

    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 6)
    c.drawCentredString(x + fw / 2, y - 20,
                        f"{data.get('L_m',0):.2f} x {data.get('B_m',0):.2f} m, "
                        f"D={D_mm:.0f}mm")
```

**Step 4: Run — confirm pass.**

**Step 5: Commit**

```bash
git add backend/app/engine/structural_drawing_set.py backend/tests/test_structural_drawing_set.py
git commit -m "feat: add Footing Details sheet (schedule + typical section)"
```

---

## Task 7: Beam detail box renderer (shared by sheets 4 & 6)

**Files:**
- Modify: `backend/app/engine/structural_drawing_set.py` (add `_draw_beam_detail_box`)
- Modify: `backend/tests/test_structural_drawing_set.py` (add test)

**Context:** This is the highest-risk new drawing code (per the model-tier table, use Opus for
this task). One dimensioned rectangular box pictorial per beam mark — per simplification #7 in the
design doc, this is a SINGLE section (not midspan/support split): outline box at `b_mm × D_mm`,
tension bars drawn as filled circles along the bottom (count = `design["n_bars"]`, labeled
`{n_bars}-{bar_dia}ø`), compression bars along the top ONLY if `design["doubly_reinforced"]` is
truthy, and a stirrup spacing label. Mirrors the reference's per-mark boxes (e.g. "PB4-SIZE-0'-9"X1'-0""
with a dimensioned rectangle below) but collapsed to one box instead of two (midspan/support).

**Step 1: Write the failing test**

```python
def test_beam_detail_box_renders_mark_and_bar_count():
    design = {
        "n_bars": 3, "bar_dia": 12, "doubly_reinforced": False,
        "stirrups": {"sv_provided": 150},
    }
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_beam_detail_box(c, mark="PB1", b_mm=230, D_mm=300, design=design,
                          x=100, y=500)
    c.showPage(); c.save()

    text = PdfReader(BytesIO(buf.getvalue())).pages[0].extract_text()
    assert "PB1" in text
    assert "3-12" in text.replace(" ", "")
```

**Step 2: Run — confirm fail.**

**Step 3: Implement**

```python
def _draw_beam_detail_box(
    c: canvas.Canvas, mark: str, b_mm: float, D_mm: float, design: dict,
    x: float, y: float, px_per_mm: float = 0.12,
) -> float:
    """One dimensioned beam cross-section pictorial. Returns height consumed.

    v1 simplification: ONE section per mark (tension + compression steel,
    stirrup spacing), NOT a midspan-vs-support split -- structapi's
    design_beam() returns a single envelope bar schedule, see design doc
    simplification #7."""
    bw, bh = b_mm * px_per_mm, D_mm * px_per_mm
    n_bars = design.get("n_bars", 0)
    bar_dia = design.get("bar_dia", 0)
    doubly = design.get("doubly_reinforced", False)
    n_comp = design.get("n_bars_comp", 0)
    sv = (design.get("stirrups") or {}).get("sv_provided", "-")

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x, y + bh + 24, f"{mark}-SIZE-{b_mm:.0f}x{D_mm:.0f}mm")

    c.setStrokeColor(HexColor("#000000"))
    c.setLineWidth(0.75)
    c.setFillColor(white)
    c.rect(x, y, bw, bh, fill=1, stroke=1)

    cover_px = 6
    if n_bars:
        for i in range(int(n_bars)):
            bx = x + cover_px + (bw - 2 * cover_px) * i / max(n_bars - 1, 1)
            c.setFillColor(HexColor("#000000"))
            c.circle(bx, y + cover_px, 2, fill=1, stroke=0)
        c.setFont("Helvetica", 5.5)
        c.drawString(x + bw + 4, y + cover_px - 2, f"Bot {n_bars}nos-{bar_dia:.0f}mmø")

    if doubly and n_comp:
        for i in range(int(n_comp)):
            bx = x + cover_px + (bw - 2 * cover_px) * i / max(n_comp - 1, 1)
            c.setFillColor(HexColor("#000000"))
            c.circle(bx, y + bh - cover_px, 2, fill=1, stroke=0)
        c.setFont("Helvetica", 5.5)
        c.drawString(x + bw + 4, y + bh - cover_px - 2,
                    f"Top {n_comp}nos-{bar_dia:.0f}mmø")

    c.setFont("Helvetica", 5.5)
    c.drawString(x + bw + 4, y + bh / 2, f"stirrups@{sv}c/c")

    return bh + 40
```

**Step 4: Run — confirm pass.**

**Step 5: Commit**

```bash
git add backend/app/engine/structural_drawing_set.py backend/tests/test_structural_drawing_set.py
git commit -m "feat: add shared beam-detail cross-section box renderer"
```

---

## Task 8: Plinth Beam Plan page

**Files:**
- Modify: `backend/app/engine/structural_drawing_set.py` (add `render_plinth_beam_plan`)
- Modify: `backend/tests/test_structural_drawing_set.py` (add test)

**Context:** Plan-view of wall centrelines (from `drawing.walls`, same source as
`plinth_beam_design.design_plinth_beams()`'s input) drawn as beam lines, each labeled with its mark
(`f"plinth-span{span_m:.2f}"` key from Task 3 — assign short marks PB1, PB2… by unique
`(kind, span_m)` group, sorted by size, mirroring `_FOOTING_MARK`'s approach). Reuses the exact
wall-drawing + plot-boundary + north-arrow + title-block furniture from Task 5's
`render_column_footing_plan` — factor the shared furniture (road strip, plot boundary, north arrow
placement) into a small private helper `_draw_sheet_furniture(c, cfg, page_w, page_h) -> tuple[ox,
oy, s, denom]` if you find yourself copy-pasting it a third time (you will, by sheet 5) — apply
DRY here per project conventions.

**Step 1: Write the failing test** — same shape as Task 5's, asserting `"PLINTH BEAM PLAN"` and a
`"PB"`-prefixed mark appear in extracted text.

**Step 2: Run — confirm fail.**

**Step 3: Implement** — draw each wall centreline segment as a beam line (`c.line(...)` at plan
scale), label with its assigned mark near the midpoint, reuse `_draw_title_block`/`_draw_north_arrow`.

**Step 4: Run — confirm pass.**

**Step 5: Commit**

```bash
git commit -m "feat: add Plinth Beam Plan sheet renderer"
```

---

## Task 9: Plinth Beam Details page

**Files:**
- Modify: `backend/app/engine/structural_drawing_set.py` (add `render_plinth_beam_details`)
- Modify: `backend/tests/test_structural_drawing_set.py` (add test)

**Context:** Thin wiring only — a schedule table (reuse `_draw_generic_schedule_table`: columns
MARK/SIZE/SPAN, rows from `plinth_beams_data`) plus a loop calling Task 7's
`_draw_beam_detail_box` once per unique plinth beam mark, stacked vertically down the page.

**Step 1-5:** Same TDD shape as prior tasks — write failing test asserting a plinth beam mark and
its bar count appear in extracted text, implement by combining the two already-built pieces, run,
commit (`git commit -m "feat: add Plinth Beam Details sheet"`).

---

## Task 10: Roof Beam & Slab Plan page

**Files:**
- Modify: `backend/app/engine/structural_drawing_set.py` (add `render_roof_beam_slab_plan`)
- Modify: `backend/tests/test_structural_drawing_set.py` (add test)

**Context:** Extends the existing `_draw_structural_floor` (`pdf.py:1437`) rather than
reimplementing from scratch — that function already draws the beam/column layout at the correct
scale from `structural_design["structapi"]["data"]["columns"]`/`["beams"]`. This task's delta:
after calling (or inlining a copy of, if `_draw_structural_floor` isn't cleanly reusable
standalone — check whether it's easily callable outside `render_pdf`'s loop, since it currently
takes `layout`/`floor_label` params tied to the main architectural PDF flow) the existing beam/
column drawing, add:
- Floating column markers (small filled square, different color, at any `ColumnMarker` positions
  not resting on a ground-floor wall — this data already exists as `FC` markers in the reference;
  check if PlanForge's layout geometry already flags floating columns anywhere in
  `plan_geometry.py`/`cad_elements.py` before inventing new detection logic — grep
  `floating` in `backend/app/engine/` first).
- Slab panel labels (S1/S2/…) — one per room polygon or wall-bounded cell; if `structapi`'s
  `data.slabs` (mentioned in research §5's `design_building()` docstring: "two-way slab panels")
  carries panel geometry/keys, reuse those; otherwise derive simple panel labels from
  `floor_plan.rooms` (each room ≈ one slab panel in ordinary residential construction) and label
  by room index.

**Step 1-5:** Same TDD shape — write a failing test asserting `"ROOF BEAM"` / `"SLAB"` and at least
one `S`-prefixed panel label appear in extracted text, implement, run, commit
(`git commit -m "feat: add Roof Beam & Slab Plan sheet"`).

---

## Task 11: Roof Beam Details page

**Files:**
- Modify: `backend/app/engine/structural_drawing_set.py` (add `render_roof_beam_details`)
- Modify: `backend/tests/test_structural_drawing_set.py` (add test)

**Context:** Identical shape to Task 9, but sourced from
`structural_design["structapi"]["data"]["beams"]` (research §5's key format:
`"x-span4.0-trib2.25"`) instead of the plinth-beam dict — same schedule-table + beam-detail-box-
loop pattern. Assign short marks (B1, B2, …) by unique beam-design-entry, sorted by size, same
approach as `_FOOTING_MARK`.

**Step 1-5:** TDD shape, commit (`git commit -m "feat: add Roof Beam Details sheet"`).

---

## Task 12: `generate_structural_drawing_set()` orchestrator

**Files:**
- Modify: `backend/app/engine/structural_drawing_set.py` (add top-level `generate_structural_drawing_set`)
- Modify: `backend/tests/test_structural_drawing_set.py` (add integration-style test)

**Step 1: Write the failing test**

```python
def test_generate_structural_drawing_set_produces_6_pages():
    pdf_bytes = generate_structural_drawing_set(
        project_name="Test Project", cfg=cfg,
        columns=columns, walls=walls,
        plinth_beams_data=plinth_beams_data,
        structural_design=structural_design_fixture,  # full fixture, see Task 14
        floor_plan=floor_plan_fixture,
    )
    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) == 6
```

**Step 2: Run — confirm fail.**

**Step 3: Implement** — mirror `render_pdf`'s pattern exactly (research §1): open one
`canvas.Canvas(buf, pagesize=A4)`, call each of the 6 render functions from Tasks 5–11 in order,
`c.showPage()` after each, `c.save(); return buf.getvalue()`.

```python
def generate_structural_drawing_set(
    *, project_name: str, cfg, columns, walls, plinth_beams_data: dict,
    structural_design: dict, floor_plan,
) -> bytes:
    from io import BytesIO
    from reportlab.lib.pagesizes import A4

    footings_data = (structural_design.get("structapi") or {}).get("data", {}).get("footings", {})
    beams_data = (structural_design.get("structapi") or {}).get("data", {}).get("beams", {})

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    render_column_footing_plan(c, columns, walls, footings_data, cfg, project_name)
    c.showPage()
    render_footing_details(c, footings_data, cfg, project_name)
    c.showPage()
    render_plinth_beam_plan(c, walls, plinth_beams_data, cfg, project_name)
    c.showPage()
    render_plinth_beam_details(c, plinth_beams_data, cfg, project_name)
    c.showPage()
    render_roof_beam_slab_plan(c, columns, walls, floor_plan, beams_data, cfg, project_name)
    c.showPage()
    render_roof_beam_details(c, beams_data, cfg, project_name)
    c.showPage()

    c.save()
    return buf.getvalue()
```

**Step 4: Run — confirm pass.**

**Step 5: Commit**

```bash
git commit -m "feat: add generate_structural_drawing_set orchestrator (6-sheet PDF)"
```

---

## Task 13: Export route

**Files:**
- Modify: `backend/app/api/routes/export.py` (add new route, mirroring `export_pdf`/`export_approval_pdf`)
- Test: `backend/tests/test_export_structural_drawing_set.py`

**Context:** Follow `export_pdf`'s exact shape from research §10. Gate identically to the existing
`/structural` endpoints: 404 if the layout doesn't exist, and a clear error (409, matching the
`not_designed`/`not_approved` codes already used by `structural.py`'s `get_structural_design`) if
`structural_store.design_surface(...)` returns `None` — a structural design must already exist
(this export never triggers a new structapi call for roof beams/footings; only the plinth-beam
`calc_beam` calls happen at export time, per the design doc's "requires structapi, gated on
approved+designed" decision).

**Step 1: Write the failing test**

```python
# backend/tests/test_export_structural_drawing_set.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_export_structural_drawing_set_requires_existing_design(client, auth_headers):
    # project/layout exist but no structural design has been run yet
    resp = await client.get(
        "/api/projects/proj-1/export/structural-drawing-set?layout_id=A",
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "not_designed"
```

(Adapt fixture names `client`/`auth_headers` to whatever `conftest.py` actually provides — check
`backend/tests/conftest.py` for the real fixture names before writing this.)

**Step 2: Run — confirm fail** (404 route not found, or import error).

**Step 3: Implement**

```python
# in backend/app/api/routes/export.py, near export_approval_pdf
from app.engine.structural_drawing_set import generate_structural_drawing_set
from app.services import plinth_beam_design

@router.get("/projects/{project_id}/export/structural-drawing-set")
async def export_structural_drawing_set(
    project_id: str,
    layout_id: str = "A",
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_project(project_id, user_id, db)
    cfg = _cfg_from_project(project)

    stored = await layout_store.get_or_generate_layouts(project, db)
    row = next((r for r in stored if r.layout_key == layout_id), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail=f"Layout {layout_id!r} not found")

    design = await structural_store.design_surface(project_id, layout_id, row.geometry, db)
    if design is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "not_designed",
                "help": (
                    "Run structural design first: "
                    f"POST /api/projects/{project_id}/structural "
                    f'{{"layout_id": "{layout_id}"}}'
                ),
            },
        )

    layout = layout_store.engine_layout_from_geometry(row.geometry)
    from app.engine.plan_geometry import build_floor_drawing
    drawing = build_floor_drawing(layout.ground_floor, cfg)

    plinth_beams_data = await plinth_beam_design.design_plinth_beams(drawing.walls)

    pdf_bytes = generate_structural_drawing_set(
        project_name=project.name, cfg=cfg,
        columns=drawing.columns, walls=drawing.walls,
        plinth_beams_data=plinth_beams_data,
        structural_design=design, floor_plan=layout.ground_floor,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="planforge-structural-drawings-'
                f'{project_id}-layout-{layout_id}.pdf"'
            )
        },
    )
```

**Step 4: Run — confirm pass**, then also add a happy-path test (design exists → 200, PDF content-type,
6-page PDF) using the same fixture-building approach as `test_structural_endpoint.py`.

**Step 5: Commit**

```bash
git add backend/app/api/routes/export.py backend/tests/test_export_structural_drawing_set.py
git commit -m "feat: add GET /projects/{id}/export/structural-drawing-set route"
```

---

## Task 14: End-to-end integration test with realistic fixture

**Files:**
- Create: `backend/tests/fixtures/structural_design_full.py` (or inline in the test file — your
  call based on how other tests in this repo structure large fixtures)
- Modify: `backend/tests/test_export_structural_drawing_set.py`

**Context:** All prior tests used minimal/stubbed data. This task builds ONE realistic fixture
covering `columns`, `beams`, AND `footings` together (per research §5's exact shapes) — close to
what a real `structapi` `/v1/design/building` response looks like for a 3×2 grid — and asserts the
full export route produces a 6-page PDF where every sheet's schedule table has at least one row
(i.e., nothing silently renders empty because of a field-name mismatch between what
`structural_drawing_set.py` reads and what `structapi` actually returns).

**Step 1: Write the failing test**

```python
FULL_STRUCTAPI_DATA = {
    "columns": {
        "corner": {"b_mm": 230, "D_mm": 300, "bars": "6-16 dia", "n_bars": 6, "bar_dia": 16,
                  "data": {"p_percent": 1.2, "tie_dia": 8, "tie_pitch_max": 200}},
        "edge": {"b_mm": 230, "D_mm": 350, "bars": "8-16 dia", "n_bars": 8, "bar_dia": 16,
                "data": {"p_percent": 1.5, "tie_dia": 8, "tie_pitch_max": 200}},
        "interior": {"b_mm": 300, "D_mm": 300, "bars": "8-20 dia", "n_bars": 8, "bar_dia": 20,
                    "data": {"p_percent": 1.8, "tie_dia": 8, "tie_pitch_max": 175}},
    },
    "beams": {
        "x-span4.00-trib2.25": {
            "b_mm": 230, "D_mm": 450, "span_m": 4.0, "trib_width_m": 2.25, "n_spans": 2,
            "design": {"n_bars": 3, "bar_dia": 16, "doubly_reinforced": False,
                      "stirrups": {"sv_provided": 150}, "Ast_prov_mm2": 603},
        },
    },
    "footings": {
        "corner": {"data": {"L_m": 1.3, "B_m": 1.3, "D_overall_mm": 400,
                            "bars_x": {"dia": 12, "spacing": 150},
                            "bars_y": {"dia": 12, "spacing": 150}}},
        "edge": {"data": {"L_m": 1.4, "B_m": 1.3, "D_overall_mm": 400,
                          "bars_x": {"dia": 12, "spacing": 150},
                          "bars_y": {"dia": 12, "spacing": 150}}},
        "interior": {"data": {"L_m": 1.6, "B_m": 1.6, "D_overall_mm": 450,
                              "bars_x": {"dia": 12, "spacing": 125},
                              "bars_y": {"dia": 12, "spacing": 125}}},
    },
}

@pytest.mark.asyncio
async def test_export_structural_drawing_set_happy_path_all_sheets_populated(
    client, auth_headers, seed_project_with_approved_and_designed_layout,  # build/find the right fixture chain
):
    resp = await client.get(
        "/api/projects/proj-1/export/structural-drawing-set?layout_id=A",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"

    reader = PdfReader(BytesIO(resp.content))
    assert len(reader.pages) == 6
    all_text = " ".join(p.extract_text() for p in reader.pages).upper()
    assert "COLUMN & FOOTING PLAN" in all_text
    assert "FOOTING DETAILS" in all_text
    assert "PLINTH BEAM PLAN" in all_text
    assert "PLINTH BEAM DETAILS" in all_text
    assert "ROOF BEAM" in all_text
```

Building `seed_project_with_approved_and_designed_layout` requires chaining the existing
approve+design test helpers already used in `test_structural_endpoint.py`/`test_structural_revisions.py`
— read those files for the exact DB-seeding pattern (project creation, layout generation, revision
approval, `StructuralDesign` row insertion) before writing this fixture from scratch; there is
almost certainly reusable setup code or a pytest fixture already doing most of this.

**Step 2: Run — confirm fail** (whatever's still missing — likely fixture wiring issues, iterate).

**Step 3: Implement** — no new production code expected here; this task is almost entirely about
building the test fixture correctly and fixing any field-name mismatches it surfaces in
`structural_drawing_set.py` from Tasks 5–12 (this is exactly the point of the task — it's the
integration check that catches "reads `v["Ast"]` but the real key is `v["Ast_prov_mm2"]`"-class bugs
that unit tests with hand-picked minimal fixtures miss).

**Step 4: Run — confirm pass.**

**Step 5: Commit**

```bash
git add backend/tests/test_export_structural_drawing_set.py
git commit -m "test: add end-to-end structural drawing set fixture covering columns/beams/footings"
```

---

## After all tasks: full backend check

```bash
cd backend
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
```

All green before considering this plan complete. If `ruff format --check` fails, run
`uv run ruff format .` and re-commit.
