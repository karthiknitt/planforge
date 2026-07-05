# Stage 1 Phase 3 — Canvas-First Editing + Drafted-Class UX + Inngest Async Generation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Phase 3 items 3a–3e from `docs/plans/2026-07-03-fable-stage1-phase0-plan.md` §4: async generation via Inngest (fixes the live cold-start timeout), canvas-first room editing (select/move/resize/snap/undo), agent-edit hardening, plot preview on the input form, and drafted-class DXF output (standard opening sizes + blocks).

**Architecture:** Generation and AI renders move to a durable job pipeline: a `generation_jobs` table + Inngest functions served from FastAPI at `/api/inngest`, with an inline synchronous fallback when Inngest env keys are absent (dev/CI parity). Page loads never solve — they read a new read-only layouts endpoint. The canvas editor extends the existing `FloorPlanSVG` edit mode (wall-drag) with room selection, move-drag, resize handles, and snapping, writing back through the **existing** `PATCH /api/projects/{id}/layouts/{layout_key}` endpoint from Phase 1. DXF openings become config-driven block inserts.

**Tech Stack:** FastAPI + SQLAlchemy async + `inngest` (Python SDK, FastAPI integration) · Next.js 16 App Router + bun test · ezdxf blocks · no new frontend data libs (hand-rolled 2s polling; Inngest Realtime deferred — see Scope guard).

## Global Constraints

- **Branch/worktree:** create branch `worktree-stage1-phase3` off `v2` in a git worktree (`git worktree add ../phase3 -b worktree-stage1-phase3 v2` or via `superpowers:using-git-worktrees`). One PR per phase, back into `v2`, via `finish-feature`.
- **TDD everywhere:** write the failing test first. Backend: `cd backend && uv run pytest tests/<file> -x -q`. Frontend: `cd frontend && bun test <file>`.
- **No local dev servers** (project rule). Verification = unit tests + `bun run build` + `uv run ruff format . && uv run ruff check .`. Visual verification happens on the Vercel preview after push.
- **Schema changes** (Tasks 3, 11): invoke `Workflow({ name: 'db-migration-safe', args: '<description>' })` BEFORE writing the model. Tables are created by `Base.metadata.create_all` at startup (no Alembic) — every new model MUST be imported in `backend/app/main.py`'s model-import block.
- **Scope guard (locked in phase-0 plan §4-3e):** Inngest wraps ONLY the two provably-slow paths — layout generation and AI render. Everything else stays synchronous. Progress UI is 2-second polling of the job endpoint; Inngest Realtime is explicitly deferred (no realtime scaffolding exists in the frontend; polling is the phase-0 plan's sanctioned fallback path).
- **Tier order (single source of truth after Task 1):** `free < basic < pro < firm`.
- **Package managers:** `uv add` (backend), `bun add` (frontend — none needed this phase).
- **Conventional commits.** Commit at the end of every task, or more often.
- Wall thickness constants: external 230 mm / internal 115 mm. Model units are metres everywhere in geometry code; `RoomData` uses `depth` (frontend PATCH body maps `height: r.depth`).

## Key existing interfaces (read-only reference — all verified on `v2` @ `717acd8`)

| Thing | Where | Signature |
|---|---|---|
| Layout store | `backend/app/services/layout_store.py` | `get_stored_layouts(project_id, db)` :90 · `regenerate_and_store(project, db) -> list[StoredLayout]` :111 · `to_generate_response(project_id, stored)` :159 |
| StoredLayout | `backend/app/models/layout.py:12` | table `layouts`; cols `id, project_id (FK project.id CASCADE), layout_key, source, geometry(JSON), created_at, updated_at` |
| Generate route | `backend/app/api/routes/generate.py:14` | `GET /api/projects/{project_id}/generate?refresh=` → `GenerateResponse{project_id, layouts: list[LayoutOut]}` |
| PATCH write-back | `backend/app/api/routes/rooms.py:645` | `PATCH /api/projects/{project_id}/layouts/{layout_key}`, body `LayoutRoomsUpdate{rooms: list[RoomEditItem]}` |
| Compliance check | `backend/app/api/routes/rooms.py:621` | `POST /api/layouts/{layout_id}/compliance-check` + `X-Project-Id` header |
| Plan tier | `backend/app/services/plans.py` | `get_effective_plan_tier(user_id, db) -> str` |
| Render core | `backend/app/api/routes/render.py:79` | `POST /api/projects/{id}/layouts/{layout_id}/render`; providers in `backend/app/services/render_providers.py` (`render_image(...) -> RenderResult`) |
| DB session factory | `backend/app/db.py:18` | `SessionLocal = async_sessionmaker(engine, expire_on_commit=False)` |
| Auth dep | `backend/app/dependencies/auth.py` | `get_current_user_id` (X-Internal-Auth JWT); tests override via `X-Test-User-Id` (see `backend/tests/conftest.py`) |
| Frontend proxy | `frontend/src/app/api/backend/[...path]/route.ts` | browser → `/api/backend/<path>` → backend `/api/<path>` (no timeout) |
| Server-side fetch | `frontend/src/lib/backend-fetch.ts:5` | `fetchBackend(userId, path, init?)` — **15 s AbortController timeout** |
| SVG component | `frontend/src/components/floor-plan-svg.tsx:1018` | props at :944 incl. `editMode?, onRoomsChange?(rooms: RoomData[]), complianceIssues?`; consts `VP_W=600, VP_H=720` :22; `scale` px/m :1066; `getMinSide(type)` :808; `RoomData` from `@/lib/layout-types` |
| Viewer | `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx` | tabs `["plan","section","boq","compare","chat","render"]` :1617; save handler `handleSaveEditedRooms` :751; `RenderTab` :165 |
| Project page | `frontend/src/app/(app)/projects/[id]/page.tsx:35` | `fetchLayouts` — `unstable_cache` around `fetchBackend(userId, 'projects/${id}/generate')`, tag `project-${projectId}`; revalidate route `POST /api/projects/{id}/revalidate` exists |

Task order rationale: Task 1 is a tiny bug fix touching files nearly every later task touches (do it first, avoid conflicts). Tasks 2–6 are workstream **3e** (live production failure — highest urgency). Tasks 7–10 are **3a** (canvas editor). Task 11 is **3b**, Task 12 is **3c**, Tasks 13–14 are **3d**, Task 15 closes out.

---

### Task 1: Ranked tier gate — fix the firm-tier lockout

Firm-tier users are currently DENIED layout editing (11 gates in `rooms.py` use `tier != "pro"`), DXF export (`plan not in ("basic","pro")`), and BOQ (`plan != "pro"`). Render already uses `("pro","firm")`. Replace every literal comparison with one ranked helper on both sides of the stack.

**Files:**
- Modify: `backend/app/services/plans.py`
- Modify: `backend/app/api/routes/rooms.py` (11 gate sites — grep `!= "pro"`)
- Modify: `backend/app/api/routes/export.py:174,573`
- Modify: `backend/app/api/routes/render.py:34,87`
- Create: `frontend/src/lib/plan.ts`
- Modify: `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx` (grep `planTier === "pro"` / `=== "firm"`)
- Test: `backend/tests/test_tier_order.py`, `frontend/src/lib/plan.test.ts`

**Interfaces:**
- Produces: `tier_at_least(tier: str, minimum: str) -> bool` in `app.services.plans`; `TIER_ORDER = ("free","basic","pro","firm")`. Frontend: `tierAtLeast(tier: string | null | undefined, minimum: string): boolean` in `@/lib/plan`. Tasks 6 and 15 consume `tier_at_least`.

- [ ] **Step 1: Write the failing backend test**

```python
# backend/tests/test_tier_order.py
from app.services.plans import TIER_ORDER, tier_at_least


def test_tier_order_is_free_basic_pro_firm():
    assert TIER_ORDER == ("free", "basic", "pro", "firm")


def test_firm_is_at_least_pro():
    assert tier_at_least("firm", "pro")


def test_firm_is_at_least_basic():
    assert tier_at_least("firm", "basic")


def test_basic_is_not_pro():
    assert not tier_at_least("basic", "pro")


def test_unknown_tier_ranks_as_free():
    assert not tier_at_least("enterprise", "basic")
    assert tier_at_least("enterprise", "free")
```

- [ ] **Step 2: Run it — expect ImportError**

Run: `cd backend && uv run pytest tests/test_tier_order.py -x -q`
Expected: FAIL — `ImportError: cannot import name 'TIER_ORDER'`

- [ ] **Step 3: Implement in `backend/app/services/plans.py`** (append below `get_effective_plan_tier`)

```python
TIER_ORDER = ("free", "basic", "pro", "firm")


def _tier_rank(tier: str) -> int:
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return 0  # unknown tiers rank as free


def tier_at_least(tier: str, minimum: str) -> bool:
    return _tier_rank(tier) >= _tier_rank(minimum)
```

- [ ] **Step 4: Replace the gate sites**

In `backend/app/api/routes/rooms.py`, add `tier_at_least` to the existing `from app.services.plans import ...` line, then replace ALL 11 occurrences of:
```python
    if tier != "pro":
```
with:
```python
    if not tier_at_least(tier, "pro"):
```
(sites at approx. lines 276, 307, 322, 341, 374, 409, 445, 507, 531, 661, plus one more — verify with `grep -n '!= "pro"' backend/app/api/routes/rooms.py` that ZERO remain after the edit).

In `backend/app/api/routes/export.py`:
```python
# line ~174 (DXF):   if plan not in ("basic", "pro"):
    if not tier_at_least(plan, "basic"):
# line ~573 (BOQ):   if plan != "pro":
    if not tier_at_least(plan, "pro"):
```

In `backend/app/api/routes/render.py`, delete `_TIER_ALLOWED = ("pro", "firm")` (line 34) and replace its check (line ~87) `if tier not in _TIER_ALLOWED:` with `if not tier_at_least(tier, "pro"):` (import from `app.services.plans`).

- [ ] **Step 5: Add a firm-tier regression test** (append to `backend/tests/test_tier_order.py`)

Copy the user-seeding + client pattern from `backend/tests/test_team_and_plan_access.py` (it already seeds a `User` row with a `plan_tier` and drives endpoints via the `client` fixture's `X-Test-User-Id` header). Assert:

```python
# firm user hitting the edit PATCH gets past the tier gate
# (404 for a nonexistent layout is fine — 403 "Pro plan required" is the failure)
async def test_firm_user_passes_edit_gate(client_db):
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "firm-user", "firm")           # helper copied per above
    project_id = await _seed_project(SessionLocal, "firm-user")   # helper copied per above
    resp = await client.patch(
        f"/api/projects/{project_id}/layouts/nope",
        json={"rooms": [{"id": "r1", "type": "bedroom", "name": "B", "x": 1, "y": 1,
                          "width": 3, "height": 3, "floor": "gf"}]},
        headers={"X-Test-User-Id": "firm-user"},
    )
    assert resp.status_code != 403
```

- [ ] **Step 6: Run the whole backend suite**

Run: `cd backend && uv run pytest -x -q`
Expected: ALL PASS (274+ tests — existing gate tests that asserted `"pro"`-only behaviour, if any assert 403 for firm, must be UPDATED to the new correct behaviour, not deleted).

- [ ] **Step 7: Frontend helper + failing test**

```typescript
// frontend/src/lib/plan.test.ts
import { describe, expect, test } from "bun:test";
import { tierAtLeast } from "./plan";

describe("tierAtLeast", () => {
  test("firm >= pro", () => expect(tierAtLeast("firm", "pro")).toBe(true));
  test("basic < pro", () => expect(tierAtLeast("basic", "pro")).toBe(false));
  test("null tier ranks as free", () => expect(tierAtLeast(null, "basic")).toBe(false));
  test("unknown tier ranks as free", () => expect(tierAtLeast("x", "basic")).toBe(false));
});
```

Run: `cd frontend && bun test src/lib/plan.test.ts` → FAIL (module not found). Then:

```typescript
// frontend/src/lib/plan.ts
export const TIER_ORDER = ["free", "basic", "pro", "firm"] as const;

function rank(tier: string | null | undefined): number {
  const i = TIER_ORDER.indexOf((tier ?? "free") as (typeof TIER_ORDER)[number]);
  return i === -1 ? 0 : i;
}

export function tierAtLeast(
  tier: string | null | undefined,
  minimum: string
): boolean {
  return rank(tier) >= rank(minimum);
}
```

Run again → PASS.

- [ ] **Step 8: Sweep the viewer**

In `layout-viewer.tsx`, `grep -n 'planTier === "pro"\|planTier === "firm"'` and replace each edit/BOQ/render gate expression with `tierAtLeast(planTier, "pro")` (or `tierAtLeast(planTier, "basic")` where the old expression allowed basic — match the backend gate for the same feature). `RenderTab`'s `isPro` (line ~190) becomes `const isPro = tierAtLeast(planTier, "pro");`. Import `{ tierAtLeast } from "@/lib/plan"`.

- [ ] **Step 9: Verify + commit**

Run: `cd frontend && bun test && bun run lint && bun run build` → all pass.

```bash
git add backend/app/services/plans.py backend/app/api/routes/rooms.py backend/app/api/routes/export.py backend/app/api/routes/render.py backend/tests/test_tier_order.py frontend/src/lib/plan.ts frontend/src/lib/plan.test.ts "frontend/src/app/(app)/projects/[id]/layout-viewer.tsx"
git commit -m "fix: ranked tier gate — firm tier no longer locked out of edit/DXF/BOQ"
```

---

### Task 2: Read-only layouts endpoint — page loads stop solving

Today the project page's server component calls `GET /projects/{id}/generate`, which SOLVES on a store miss — inside `fetchBackend`'s 15 s timeout. That is the documented live failure. New rule: page reads never solve.

**Files:**
- Modify: `backend/app/api/routes/generate.py`
- Modify: `frontend/src/app/(app)/projects/[id]/page.tsx:47`
- Modify: `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx` (empty-layouts branch)
- Test: `backend/tests/test_layouts_read_endpoint.py`

**Interfaces:**
- Produces: `GET /api/projects/{project_id}/layouts` → `GenerateResponse` (same shape as generate; `layouts: []` when nothing stored — **never** solves). Task 5 replaces the placeholder empty state with the generation panel.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_layouts_read_endpoint.py
import pytest

from app.services import layout_store

# Reuse the project-seeding helper pattern from backend/tests/test_layout_persistence.py
# (it seeds a Project row and stored layouts through SessionLocal).


@pytest.mark.anyio
async def test_read_layouts_returns_empty_list_without_solving(client_db, monkeypatch):
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u1", "free")
    project_id = await _seed_project(SessionLocal, "u1")

    def _boom(*a, **k):  # any solver invocation is a failure
        raise AssertionError("read endpoint must never solve")

    monkeypatch.setattr(layout_store, "regenerate_and_store", _boom)
    monkeypatch.setattr(layout_store, "get_or_generate_layouts", _boom)

    resp = await client.get(
        f"/api/projects/{project_id}/layouts", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"project_id": project_id, "layouts": []}


@pytest.mark.anyio
async def test_read_layouts_returns_stored_geometry(client_db):
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u1", "free")
    project_id = await _seed_project_with_layout(SessionLocal, "u1")  # per test_layout_persistence.py
    resp = await client.get(
        f"/api/projects/{project_id}/layouts", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    assert len(resp.json()["layouts"]) >= 1
```

- [ ] **Step 2: Run** `cd backend && uv run pytest tests/test_layouts_read_endpoint.py -x -q` → FAIL 404 (route missing)

- [ ] **Step 3: Implement** (append to `backend/app/api/routes/generate.py`)

```python
@router.get("/projects/{project_id}/layouts", response_model=GenerateResponse)
async def read_layouts(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    """Read stored layouts. Never solves — generation is an explicit job
    (POST /projects/{id}/generate-jobs). Empty list means nothing generated yet."""
    project = await get_accessible_project(project_id, user_id, db)
    stored = await layout_store.get_stored_layouts(project.id, db)
    return layout_store.to_generate_response(project_id, stored)
```

- [ ] **Step 4: Run tests** → PASS. Run the full suite (`uv run pytest -x -q`) → PASS.

- [ ] **Step 5: Point the page at it**

In `frontend/src/app/(app)/projects/[id]/page.tsx:47` change:
```typescript
        const res = await fetchBackend(userId, `projects/${projectId}/generate`);
```
to:
```typescript
        const res = await fetchBackend(userId, `projects/${projectId}/layouts`);
```
(The `unstable_cache` wrapper, key, and `project-${projectId}` tag stay untouched.)

- [ ] **Step 6: Handle the empty case in the viewer (placeholder until Task 5)**

In `layout-viewer.tsx`, the component currently branches on `generateData` being null (backend offline). Add a second branch directly after it:

```tsx
  if (generateData && generateData.layouts.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
        <p className="font-medium">No layouts generated yet</p>
        <p className="mt-1 text-sm">Generation starts automatically — Task 5 wires this panel.</p>
      </div>
    );
  }
```

- [ ] **Step 7: Verify + commit**

Run: `cd frontend && bun test && bun run build` → PASS.

```bash
git add backend/app/api/routes/generate.py backend/tests/test_layouts_read_endpoint.py "frontend/src/app/(app)/projects/[id]/page.tsx" "frontend/src/app/(app)/projects/[id]/layout-viewer.tsx"
git commit -m "feat(backend): read-only layouts endpoint — page loads never solve"
```

---

### Task 3: `generation_jobs` table + jobs service + status endpoint

**Files:**
- Create: `backend/app/models/job.py`, `backend/app/schemas/job.py`, `backend/app/services/jobs.py`, `backend/app/api/routes/jobs.py`
- Modify: `backend/app/main.py` (model import + router)
- Test: `backend/tests/test_generation_jobs.py`

**Interfaces:**
- Produces (consumed by Tasks 4–6):
  - `GenerationJob` model — table `generation_jobs`: `id: str (uuid PK)`, `project_id: str (FK project.id, CASCADE, index)`, `kind: str ("layout"|"render")`, `layout_key: str | None`, `status: str ("queued"|"running"|"done"|"failed")`, `stage: str ("queued"|"solving"|"rendering"|"stored"|"failed")`, `error: str | None`, `requested_by: str`, `created_at`, `updated_at`.
  - `jobs.create_job(db, *, project_id, requested_by, kind="layout", layout_key=None) -> GenerationJob`
  - `jobs.get_job(db, project_id, job_id) -> GenerationJob | None`
  - `jobs.mark(db, job, *, status=None, stage=None, error=None) -> None` (commits)
  - `jobs.run_layout_job(job_id: str) -> None` — opens its OWN `SessionLocal` session; raises on failure AFTER marking the job failed (so Inngest retries fire).
  - `GET /api/projects/{project_id}/jobs/{job_id}` → `JobOut{id, project_id, kind, layout_key, status, stage, error, created_at, updated_at}`

- [ ] **Step 1: Migration gate**

Invoke `Workflow({ name: 'db-migration-safe', args: 'add generation_jobs table (id, project_id FK CASCADE, kind, layout_key, status, stage, error, requested_by, timestamps)' })`. Check `success` and apply any mandates before proceeding.

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_generation_jobs.py
import pytest

# seeding helpers: copy from backend/tests/test_layout_persistence.py as in Task 2


@pytest.mark.anyio
async def test_job_lifecycle_service(client_db):
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u1", "free")
    project_id = await _seed_project(SessionLocal, "u1")

    from app.services import jobs

    async with SessionLocal() as db:
        job = await jobs.create_job(db, project_id=project_id, requested_by="u1")
        assert job.status == "queued" and job.stage == "queued" and job.kind == "layout"
        await jobs.mark(db, job, status="running", stage="solving")

    async with SessionLocal() as db:  # fresh session — proves persistence
        job2 = await jobs.get_job(db, project_id, job.id)
        assert job2.status == "running" and job2.stage == "solving"


@pytest.mark.anyio
async def test_job_status_endpoint(client_db):
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u1", "free")
    project_id = await _seed_project(SessionLocal, "u1")
    from app.services import jobs

    async with SessionLocal() as db:
        job = await jobs.create_job(db, project_id=project_id, requested_by="u1")

    resp = await client.get(
        f"/api/projects/{project_id}/jobs/{job.id}", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job.id and body["status"] == "queued"

    # cross-project probe → 404
    resp = await client.get(
        f"/api/projects/{project_id}/jobs/not-a-job", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_run_layout_job_stores_layouts_and_marks_done(client_db, small_project_cfg=None):
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u1", "free")
    project_id = await _seed_project(SessionLocal, "u1")  # small rectangular plot → fast solve
    from app.services import jobs, layout_store

    async with SessionLocal() as db:
        job = await jobs.create_job(db, project_id=project_id, requested_by="u1")

    await jobs.run_layout_job(job.id)

    async with SessionLocal() as db:
        done = await jobs.get_job(db, project_id, job.id)
        assert done.status == "done" and done.stage == "stored"
        stored = await layout_store.get_stored_layouts(project_id, db)
        assert len(stored) >= 1
```

- [ ] **Step 3: Run** → FAIL (no `app.models.job` / `app.services.jobs`).

- [ ] **Step 4: Implement the model**

```python
# backend/app/models/job.py
from datetime import datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="layout")
    layout_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
```

Match the column/`Mapped` style of `backend/app/models/layout.py` exactly (timezone kwargs etc.) if it differs from the above. Add to `backend/app/main.py`'s model-import block:
```python
import app.models.job  # noqa: F401
```

- [ ] **Step 5: Implement schema + service**

```python
# backend/app/schemas/job.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    kind: str
    layout_key: str | None = None
    status: str
    stage: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime
```

```python
# backend/app/services/jobs.py
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import GenerationJob
from app.models.project import Project
from app.services import layout_store

logger = logging.getLogger(__name__)


async def create_job(
    db: AsyncSession,
    *,
    project_id: str,
    requested_by: str,
    kind: str = "layout",
    layout_key: str | None = None,
) -> GenerationJob:
    job = GenerationJob(
        project_id=project_id,
        requested_by=requested_by,
        kind=kind,
        layout_key=layout_key,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job(
    db: AsyncSession, project_id: str, job_id: str
) -> GenerationJob | None:
    job = await db.get(GenerationJob, job_id)
    if job is None or job.project_id != project_id:
        return None
    return job


async def mark(
    db: AsyncSession,
    job: GenerationJob,
    *,
    status: str | None = None,
    stage: str | None = None,
    error: str | None = None,
) -> None:
    if status is not None:
        job.status = status
    if stage is not None:
        job.stage = stage
    if error is not None:
        job.error = error[:2000]
    await db.commit()


async def run_layout_job(job_id: str) -> None:
    """Execute a layout-generation job in its own DB session.

    Called from the Inngest function (durable path) and from the inline
    fallback when Inngest is not configured. Marks the job failed and
    re-raises so Inngest's retry machinery sees the failure.
    """
    from app.db import SessionLocal  # local import: avoid engine init at module import

    async with SessionLocal() as db:
        job = await db.get(GenerationJob, job_id)
        if job is None or job.status == "done":
            return
        project = await db.get(Project, job.project_id)
        if project is None:
            await mark(db, job, status="failed", stage="failed", error="project missing")
            return
        try:
            await mark(db, job, status="running", stage="solving")
            await layout_store.regenerate_and_store(project, db)
            await mark(db, job, status="done", stage="stored")
        except Exception as exc:
            logger.exception("layout job %s failed", job_id)
            await mark(db, job, status="failed", stage="failed", error=str(exc))
            raise
```

- [ ] **Step 6: Implement the route**

```python
# backend/app/api/routes/jobs.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.schemas.job import JobOut
from app.services import jobs
from app.services.access import get_accessible_project

router = APIRouter()


@router.get("/projects/{project_id}/jobs/{job_id}", response_model=JobOut)
async def read_job(
    project_id: str,
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    project = await get_accessible_project(project_id, user_id, db)
    job = await jobs.get_job(db, project.id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut.model_validate(job)
```

Register in `backend/app/main.py`: add `jobs` to the `from app.api.routes import (...)` list and `app.include_router(jobs.router, prefix="/api")` next to the other routers.

- [ ] **Step 7: Run tests** → `uv run pytest tests/test_generation_jobs.py -x -q` PASS, then full suite PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/job.py backend/app/schemas/job.py backend/app/services/jobs.py backend/app/api/routes/jobs.py backend/app/main.py backend/tests/test_generation_jobs.py
git commit -m "feat(backend): generation_jobs table, jobs service, job status endpoint"
```

---

### Task 4: Inngest client + layout-generate function + POST generate-jobs

**Files:**
- Modify: `backend/pyproject.toml` (via `uv add inngest`)
- Modify: `backend/app/config/settings.py`
- Create: `backend/app/inngest_app.py`
- Modify: `backend/app/main.py` (serve Inngest)
- Modify: `backend/app/api/routes/jobs.py` (POST endpoint)
- Test: `backend/tests/test_generate_jobs_endpoint.py`

**Interfaces:**
- Consumes: `jobs.create_job` / `jobs.run_layout_job` / `JobOut` (Task 3), `save_auto_revision` (`app.api.routes.revisions`), `get_stored_layouts` (layout_store).
- Produces:
  - `inngest_client: inngest.Inngest` and `inngest_enabled() -> bool` in `app.inngest_app` (Task 6 adds `render_generate` here).
  - Event contract: `layout/generate.requested` with `data={"job_id": str, "project_id": str}`.
  - `POST /api/projects/{project_id}/generate-jobs` → 202 `JobOut` (Inngest path) or 200 `JobOut` (inline fallback, already `done`/`failed`).
- New env vars (both optional; absent → inline fallback): `INNGEST_EVENT_KEY`, `INNGEST_SIGNING_KEY`.

- [ ] **Step 1: Add the dependency**

Run: `cd backend && uv add inngest`
Expected: `inngest` added to `[project] dependencies` in `pyproject.toml`, `uv.lock` updated.

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_generate_jobs_endpoint.py
import pytest

# seeding helpers as in Task 2/3


@pytest.mark.anyio
async def test_generate_job_inline_fallback_completes(client_db):
    """No Inngest keys in the test env → the endpoint solves inline and
    returns a finished job."""
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u1", "free")
    project_id = await _seed_project(SessionLocal, "u1")

    resp = await client.post(
        f"/api/projects/{project_id}/generate-jobs", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done" and body["stage"] == "stored"

    layouts = await client.get(
        f"/api/projects/{project_id}/layouts", headers={"X-Test-User-Id": "u1"}
    )
    assert len(layouts.json()["layouts"]) >= 1


@pytest.mark.anyio
async def test_generate_job_event_path_enqueues(client_db, monkeypatch):
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u1", "free")
    project_id = await _seed_project(SessionLocal, "u1")

    sent: list = []

    from app import inngest_app

    async def fake_send(event):
        sent.append(event)
        return ["evt-1"]

    monkeypatch.setattr(inngest_app, "inngest_enabled", lambda: True)
    monkeypatch.setattr(inngest_app.inngest_client, "send", fake_send)

    resp = await client.post(
        f"/api/projects/{project_id}/generate-jobs", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert len(sent) == 1
    assert sent[0].name == "layout/generate.requested"
    assert sent[0].data["job_id"] == body["id"]
```

- [ ] **Step 3: Run** → FAIL (no route / no `app.inngest_app`).

- [ ] **Step 4: Settings**

In `backend/app/config/settings.py`, add below the render block:

```python
    # Async job pipeline (Phase 3) — both empty => inline synchronous fallback
    inngest_event_key: str = ""
    inngest_signing_key: str = ""
```

- [ ] **Step 5: Inngest app module**

```python
# backend/app/inngest_app.py
"""Inngest client + durable functions.

Scope guard (phase-0 plan §4-3e): Inngest wraps ONLY layout generation and
AI renders. The executor invokes /api/inngest over HTTP, so the solve runs
inside a normal Cloud Run request lifecycle (full CPU) — no
--cpu-always-allocated needed.
"""
import inngest

from app.config.settings import settings
from app.services import jobs

inngest_client = inngest.Inngest(
    app_id="planforge",
    event_key=settings.inngest_event_key or None,
    signing_key=settings.inngest_signing_key or None,
    is_production=bool(settings.inngest_signing_key),
)


def inngest_enabled() -> bool:
    return bool(settings.inngest_event_key and settings.inngest_signing_key)


@inngest_client.create_function(
    fn_id="layout-generate",
    trigger=inngest.TriggerEvent(event="layout/generate.requested"),
    retries=2,
)
async def layout_generate(ctx: inngest.Context) -> str:
    job_id = ctx.event.data["job_id"]
    await ctx.step.run("solve-and-store", jobs.run_layout_job, job_id)
    return job_id
```

- [ ] **Step 6: Serve from FastAPI**

In `backend/app/main.py`, after the last `app.include_router(...)` line:

```python
import inngest.fast_api

from app.inngest_app import inngest_client, layout_generate

inngest.fast_api.serve(app, inngest_client, [layout_generate])
```

(`serve` mounts GET/POST/PUT at `/api/inngest`; requests are authenticated by the Inngest signing key, NOT by `get_current_user_id` — that is correct and expected.)

- [ ] **Step 7: POST endpoint** (append to `backend/app/api/routes/jobs.py`)

```python
import inngest as inngest_lib
from fastapi import Response

from app.api.routes.revisions import save_auto_revision
from app.services import layout_store


@router.post("/projects/{project_id}/generate-jobs", response_model=JobOut)
async def create_generate_job(
    project_id: str,
    response: Response,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    from app import inngest_app  # runtime import so tests can monkeypatch

    project = await get_accessible_project(project_id, user_id, db)

    existing = await layout_store.get_stored_layouts(project.id, db)
    if existing:
        # Fire-and-forget snapshot, mirroring generate?refresh=true
        try:
            await save_auto_revision(
                db, project, label_prefix="Auto-save before regeneration"
            )
        except Exception:
            pass

    job = await jobs.create_job(db, project_id=project.id, requested_by=user_id)

    if inngest_app.inngest_enabled():
        await inngest_app.inngest_client.send(
            inngest_lib.Event(
                name="layout/generate.requested",
                data={"job_id": job.id, "project_id": project.id},
            )
        )
        response.status_code = 202
        return JobOut.model_validate(job)

    # Inline fallback (dev/CI, or Inngest not yet provisioned): solve now.
    try:
        await jobs.run_layout_job(job.id)
    except Exception:
        pass  # job row already carries status=failed + error
    db.expire_all()  # job was mutated in another session
    fresh = await jobs.get_job(db, project.id, job.id)
    return JobOut.model_validate(fresh)
```

- [ ] **Step 8: Run** `uv run pytest tests/test_generate_jobs_endpoint.py -x -q` → PASS; full suite → PASS. Also `uv run ruff format . && uv run ruff check .` → clean.

- [ ] **Step 9: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/config/settings.py backend/app/inngest_app.py backend/app/main.py backend/app/api/routes/jobs.py backend/tests/test_generate_jobs_endpoint.py
git commit -m "feat(backend): Inngest layout-generate function + generate-jobs endpoint with inline fallback"
```

---

### Task 5: Frontend async generation UX — progress panel + regenerate

**Files:**
- Create: `frontend/src/lib/generation-job.ts`
- Test: `frontend/src/lib/generation-job.test.ts`
- Modify: `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx`

**Interfaces:**
- Consumes: `POST /api/backend/projects/{id}/generate-jobs` and `GET /api/backend/projects/{id}/jobs/{jobId}` (browser → proxy → Task 3/4 endpoints); existing `POST /api/projects/{id}/revalidate` route.
- Produces: `jobPhase(job: JobStatus | null): JobPhase`, `stageLabel(stage: string): string`, `POLL_INTERVAL_MS = 2000`, `MAX_POLLS = 150`, type `JobStatus { id: string; status: string; stage: string; error: string | null }` — Task 6's RenderTab reuses ALL of these.

- [ ] **Step 1: Failing test for the pure helpers**

```typescript
// frontend/src/lib/generation-job.test.ts
import { describe, expect, test } from "bun:test";
import { jobPhase, stageLabel } from "./generation-job";

describe("jobPhase", () => {
  test("null job is idle", () => expect(jobPhase(null)).toBe("idle"));
  test("queued", () =>
    expect(jobPhase({ id: "1", status: "queued", stage: "queued", error: null })).toBe("queued"));
  test("running", () =>
    expect(jobPhase({ id: "1", status: "running", stage: "solving", error: null })).toBe("running"));
  test("done", () =>
    expect(jobPhase({ id: "1", status: "done", stage: "stored", error: null })).toBe("done"));
  test("failed", () =>
    expect(jobPhase({ id: "1", status: "failed", stage: "failed", error: "x" })).toBe("failed"));
  test("unknown status treated as running (keep polling)", () =>
    expect(jobPhase({ id: "1", status: "weird", stage: "?", error: null })).toBe("running"));
});

describe("stageLabel", () => {
  test("solving", () => expect(stageLabel("solving")).toBe("Solving layouts…"));
  test("stored", () => expect(stageLabel("stored")).toBe("Finalizing…"));
  test("unknown falls back to Working", () => expect(stageLabel("x")).toBe("Working…"));
});
```

- [ ] **Step 2: Run** `cd frontend && bun test src/lib/generation-job.test.ts` → FAIL. Implement:

```typescript
// frontend/src/lib/generation-job.ts
export type JobPhase = "idle" | "queued" | "running" | "done" | "failed";

export interface JobStatus {
  id: string;
  status: string;
  stage: string;
  error: string | null;
}

export const POLL_INTERVAL_MS = 2000;
export const MAX_POLLS = 150; // 5 minutes — past this, surface a timeout error

export function jobPhase(job: JobStatus | null): JobPhase {
  if (!job) return "idle";
  switch (job.status) {
    case "queued":
      return "queued";
    case "done":
      return "done";
    case "failed":
      return "failed";
    default:
      return "running";
  }
}

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued…",
  solving: "Solving layouts…",
  rendering: "Rendering…",
  stored: "Finalizing…",
};

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? "Working…";
}
```

Run again → PASS.

- [ ] **Step 3: GenerationPanel component** (add inside `layout-viewer.tsx`, above the main `LayoutViewer` export; the file is already a client component)

```tsx
function GenerationPanel({
  projectId,
  autoStart,
  onDone,
}: {
  projectId: string;
  autoStart: boolean;
  onDone?: () => void;
}) {
  const router = useRouter(); // import { useRouter } from "next/navigation" if not present
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState("");
  const startedRef = useRef(false);
  const pollCountRef = useRef(0);

  const start = useCallback(async () => {
    setError("");
    setJob(null);
    pollCountRef.current = 0;
    try {
      const res = await fetch(`/api/backend/projects/${projectId}/generate-jobs`, {
        method: "POST",
      });
      if (!res.ok) {
        setError(`Could not start generation (HTTP ${res.status}).`);
        return;
      }
      setJob(await res.json());
    } catch {
      setError("Could not reach the layout engine.");
    }
  }, [projectId]);

  useEffect(() => {
    if (autoStart && !startedRef.current) {
      startedRef.current = true;
      start();
    }
  }, [autoStart, start]);

  const phase = jobPhase(job);

  useEffect(() => {
    if (!job || phase === "done" || phase === "failed") return;
    const t = setInterval(async () => {
      pollCountRef.current += 1;
      if (pollCountRef.current > MAX_POLLS) {
        setError("Generation is taking unusually long — try refreshing the page.");
        clearInterval(t);
        return;
      }
      try {
        const res = await fetch(`/api/backend/projects/${projectId}/jobs/${job.id}`);
        if (res.ok) setJob(await res.json());
      } catch {
        /* transient poll failure — keep polling */
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [job?.id, phase, projectId]);

  useEffect(() => {
    if (phase !== "done") return;
    fetch(`/api/projects/${projectId}/revalidate`, { method: "POST" }).finally(() => {
      onDone?.();
      router.refresh();
    });
  }, [phase, projectId, router, onDone]);

  if (error || phase === "failed") {
    return (
      <div className="rounded-lg border border-destructive/40 p-6 text-center">
        <p className="text-sm text-destructive">{error || job?.error || "Generation failed."}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={start}>
          Try again
        </Button>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-dashed p-10 text-center">
      <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      <p className="mt-3 font-medium">Generating your 3 layouts</p>
      <p className="mt-1 text-sm text-muted-foreground">
        {job ? stageLabel(job.stage) : "Starting…"}
      </p>
    </div>
  );
}
```

Imports to add at the top of `layout-viewer.tsx`:
```typescript
import { jobPhase, stageLabel, MAX_POLLS, POLL_INTERVAL_MS, type JobStatus } from "@/lib/generation-job";
```
(`useRouter`, `useCallback`, `useRef`, `useEffect`, `useState`, `Button` — add whichever aren't already imported.)

- [ ] **Step 4: Wire the empty state and the Regenerate button**

Replace Task 2's placeholder branch with:
```tsx
  if (generateData && generateData.layouts.length === 0) {
    return <GenerationPanel projectId={projectId} autoStart />;
  }
```

Add a Regenerate control near the layout-selector header (next to where layout cards/names render — the section that maps `generateData.layouts`): a `const [regenerating, setRegenerating] = useState(false)` in `LayoutViewer`; a button
```tsx
<Button variant="outline" size="sm" onClick={() => setRegenerating(true)} disabled={regenerating}>
  Regenerate layouts
</Button>
```
and directly under the header, when `regenerating` is true:
```tsx
{regenerating && (
  <GenerationPanel projectId={projectId} autoStart onDone={() => setRegenerating(false)} />
)}
```
`router.refresh()` re-runs the server component → fresh `generateData` flows in.

- [ ] **Step 5: Verify + commit**

Run: `cd frontend && bun test && bun run lint && bun run build` → PASS.

```bash
git add frontend/src/lib/generation-job.ts frontend/src/lib/generation-job.test.ts "frontend/src/app/(app)/projects/[id]/layout-viewer.tsx"
git commit -m "feat(frontend): non-blocking generation — job polling panel + regenerate flow"
```

---

### Task 6: Async render jobs — same pipeline, second consumer

**Files:**
- Create: `backend/app/services/render_runner.py`
- Modify: `backend/app/api/routes/render.py` (extract → delegate), `backend/app/inngest_app.py` (add `render_generate`), `backend/app/main.py` (serve list), `backend/app/api/routes/jobs.py` (POST render-jobs)
- Modify: `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx` (`RenderTab`)
- Test: `backend/tests/test_render_jobs.py`, update `frontend/src/lib/render-tab.test.ts` if signatures move

**Interfaces:**
- Consumes: `jobs.*` (Task 3), `inngest_client`/`inngest_enabled` (Task 4), `tier_at_least` (Task 1), `JobStatus`/`jobPhase`/`POLL_INTERVAL_MS` (Task 5).
- Produces:
  - `render_runner.perform_render(project_id: str, layout_id: str, db) -> LayoutRender` — the FULL body of today's `POST render` endpoint (geometry-hash cache check, PDF reference PNG, `build_render_prompt`, `render_image`, store row). Raises `HTTPException` exactly as the endpoint does today (moves the existing raises).
  - `render_runner.run_render_job(job_id: str) -> None` — own-session wrapper: mark `running`/`rendering` → `perform_render(job.project_id, job.layout_key, db)` → mark `done`/`stored`; on exception mark failed + re-raise.
  - Event contract: `render/requested` with `data={"job_id": str, "project_id": str, "layout_id": str}`.
  - `POST /api/projects/{project_id}/layouts/{layout_id}/render-jobs` → 202 `JobOut` / 200 `JobOut` inline. Tier gate `tier_at_least(tier, "pro")` → 402; provider unconfigured → 503 (same checks as the sync endpoint, BEFORE creating the job).

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_render_jobs.py
import pytest

from app.services import render_providers
from app.services.render_providers import RenderResult

# seeding helpers as before; _seed_project_with_layout returns (project_id, stored_layout_id)


@pytest.fixture
def fake_render(monkeypatch):
    async def _fake(prompt, reference_png, provider, *, api_key, model=None, timeout=120.0):
        return RenderResult(image_png=b"\x89PNG-fake", provider=provider, model=model or "m", cost_usd=None)

    # patch where it is USED (render_runner imports it)
    from app.services import render_runner
    monkeypatch.setattr(render_runner, "render_image", _fake)
    return _fake


@pytest.mark.anyio
async def test_render_job_inline_completes(client_db, fake_render, monkeypatch):
    from app.config.settings import settings
    monkeypatch.setattr(settings, "render_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u1", "pro")
    project_id, layout_id = await _seed_project_with_layout(SessionLocal, "u1")

    resp = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render-jobs",
        headers={"X-Test-User-Id": "u1"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"

    # image now served by the existing GET render endpoint
    img = await client.get(
        f"/api/projects/{project_id}/layouts/{layout_id}/render",
        headers={"X-Test-User-Id": "u1"},
    )
    assert img.status_code == 200


@pytest.mark.anyio
async def test_render_job_free_tier_402(client_db):
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u2", "free")
    project_id, layout_id = await _seed_project_with_layout(SessionLocal, "u2")
    resp = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render-jobs",
        headers={"X-Test-User-Id": "u2"},
    )
    assert resp.status_code == 402
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Extract `perform_render`.**

Create `backend/app/services/render_runner.py` by MOVING the body of the `POST` handler in `render.py:79-157` (everything after the tier/provider gates and `StoredLayout` load stays byte-identical — cache check via `_geometry_hash`, `render_pdf` → `pdf_page_png`, `build_render_prompt`, `render_image`, `LayoutRender` insert). Signature:

```python
async def perform_render(project_id: str, layout_id: str, db: AsyncSession) -> LayoutRender:
```

Move `_geometry_hash`, `_PROVIDER_KEYS`, `_DEFAULT_MODELS`, and the provider-config resolution from `render.py` into `render_runner.py`; `render.py` imports them back from `render_runner` (keep the route module thin). The sync `POST render` endpoint becomes: gates (tier via `tier_at_least`, provider configured) → `await perform_render(project.id, layout_id, db)` → same response dict as today. Run the EXISTING `tests/test_render_endpoint.py` → must still pass unchanged.

Then add:

```python
async def run_render_job(job_id: str) -> None:
    from app.db import SessionLocal
    from app.services import jobs

    async with SessionLocal() as db:
        job = await db.get(GenerationJob, job_id)
        if job is None or job.status == "done" or job.layout_key is None:
            return
        try:
            await jobs.mark(db, job, status="running", stage="rendering")
            await perform_render(job.project_id, job.layout_key, db)
            await jobs.mark(db, job, status="done", stage="stored")
        except Exception as exc:
            await jobs.mark(db, job, status="failed", stage="failed", error=str(exc))
            raise
```

- [ ] **Step 4: Inngest function + endpoint**

Append to `backend/app/inngest_app.py`:
```python
@inngest_client.create_function(
    fn_id="render-generate",
    trigger=inngest.TriggerEvent(event="render/requested"),
    retries=1,
)
async def render_generate(ctx: inngest.Context) -> str:
    from app.services import render_runner

    job_id = ctx.event.data["job_id"]
    await ctx.step.run("render-and-store", render_runner.run_render_job, job_id)
    return job_id
```
Update `main.py`: `inngest.fast_api.serve(app, inngest_client, [layout_generate, render_generate])`.

Append to `backend/app/api/routes/jobs.py` (imports: `tier_at_least` from `app.services.plans`, `get_effective_plan_tier`, and the provider-config check from `render_runner`):
```python
@router.post("/projects/{project_id}/layouts/{layout_id}/render-jobs", response_model=JobOut)
async def create_render_job(
    project_id: str,
    layout_id: str,
    response: Response,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    from app import inngest_app
    from app.services import render_runner

    project = await get_accessible_project(project_id, user_id, db)
    tier = await get_effective_plan_tier(user_id, db)
    if not tier_at_least(tier, "pro"):
        raise HTTPException(status_code=402, detail="AI renders require the Pro plan.")
    render_runner.ensure_provider_configured()  # raises HTTPException(503) — extract this tiny check during Step 3

    job = await jobs.create_job(
        db, project_id=project.id, requested_by=user_id, kind="render", layout_key=layout_id
    )
    if inngest_app.inngest_enabled():
        await inngest_app.inngest_client.send(
            inngest_lib.Event(
                name="render/requested",
                data={"job_id": job.id, "project_id": project.id, "layout_id": layout_id},
            )
        )
        response.status_code = 202
        return JobOut.model_validate(job)
    try:
        await render_runner.run_render_job(job.id)
    except Exception:
        pass
    db.expire_all()
    fresh = await jobs.get_job(db, project.id, job.id)
    return JobOut.model_validate(fresh)
```

- [ ] **Step 5: Run backend tests** → new file PASS, `test_render_endpoint.py` PASS unchanged, full suite PASS.

- [ ] **Step 6: RenderTab switches to the job path**

In `RenderTab` (`layout-viewer.tsx:165`): `handleGenerate` now POSTs `/api/backend/projects/${projectId}/layouts/${layoutKey}/render-jobs`. Keep `classifyRenderStatus(res.status)` for 402/503/other handling of the POST itself. On 200/202: store the returned job and poll `/api/backend/projects/${projectId}/jobs/${job.id}` every `POLL_INTERVAL_MS` (same pattern as `GenerationPanel` — reuse `jobPhase`); on phase `done` → bump the existing `version` state (cache-busts the image URL) and set phase `"ready"`; on `failed` → set the tab's error state with `job.error`. Remove the long-blocking single POST await.

- [ ] **Step 7: Verify + commit**

`cd frontend && bun test && bun run build` → PASS.

```bash
git add backend/app/services/render_runner.py backend/app/api/routes/render.py backend/app/inngest_app.py backend/app/main.py backend/app/api/routes/jobs.py backend/tests/test_render_jobs.py "frontend/src/app/(app)/projects/[id]/layout-viewer.tsx"
git commit -m "feat: async render jobs — render/requested event + RenderTab polling"
```

---

### Task 7: `canvas-snap` — pure snapping module

**Files:**
- Create: `frontend/src/lib/canvas-snap.ts`
- Test: `frontend/src/lib/canvas-snap.test.ts`

**Interfaces:**
- Produces (consumed by Tasks 8–9):
  - `interface RectMM { id: string; x: number; y: number; width: number; depth: number }` (metres, despite the name)
  - `GRID_M = 0.115`, `SNAP_TOL_M = 0.15`
  - `snapToGrid(v: number): number`
  - `snapScalar(v: number, candidates: number[], tol?: number): number`
  - `edgeCandidates(rooms: readonly RectMM[], excludeId: string, axis: "x" | "y"): number[]`
  - `snapRect(rect: RectMM, others: readonly RectMM[], plotW: number, plotD: number): RectMM` — snaps left/right/bottom/top edges to neighbor edges first, grid second; clamps inside the plot.

- [ ] **Step 1: Failing tests**

```typescript
// frontend/src/lib/canvas-snap.test.ts
import { describe, expect, test } from "bun:test";
import {
  GRID_M,
  SNAP_TOL_M,
  edgeCandidates,
  snapRect,
  snapScalar,
  snapToGrid,
} from "./canvas-snap";

const room = (id: string, x: number, y: number, w: number, d: number) => ({
  id, x, y, width: w, depth: d,
});

describe("snapToGrid", () => {
  test("rounds to nearest 115mm multiple", () => {
    expect(snapToGrid(0.12)).toBeCloseTo(0.115, 6);
    expect(snapToGrid(0.0)).toBe(0);
    expect(snapToGrid(0.23)).toBeCloseTo(0.23, 6);
  });
});

describe("snapScalar", () => {
  test("picks nearest candidate within tolerance", () => {
    expect(snapScalar(3.1, [3.0, 5.0])).toBe(3.0);
  });
  test("returns input when nothing within tolerance", () => {
    expect(snapScalar(4.0, [3.0, 5.0], 0.5)).toBe(4.0);
  });
  test("prefers the closest of several candidates", () => {
    expect(snapScalar(3.09, [3.0, 3.14])).toBe(3.14);
  });
});

describe("edgeCandidates", () => {
  test("collects both edges of other rooms on the axis", () => {
    const rooms = [room("a", 1, 1, 3, 4), room("b", 5, 2, 2, 2)];
    expect(edgeCandidates(rooms, "b", "x").sort()).toEqual([1, 4]);
    expect(edgeCandidates(rooms, "b", "y").sort()).toEqual([1, 5]);
  });
  test("excludes the moving room itself", () => {
    expect(edgeCandidates([room("a", 1, 1, 3, 4)], "a", "x")).toEqual([]);
  });
});

describe("snapRect", () => {
  test("snaps left edge to a neighbor's right edge", () => {
    const moving = room("m", 4.05, 1, 3, 3); // neighbor right edge at 4.0
    const others = [room("n", 1, 1, 3, 3)];
    const snapped = snapRect(moving, others, 12, 15);
    expect(snapped.x).toBeCloseTo(4.0, 6);
    expect(snapped.width).toBe(3); // move never resizes
  });
  test("clamps inside the plot", () => {
    const snapped = snapRect(room("m", -1, -2, 3, 3), [], 12, 15);
    expect(snapped.x).toBeGreaterThanOrEqual(0);
    expect(snapped.y).toBeGreaterThanOrEqual(0);
  });
  test("clamps at the far plot edge", () => {
    const snapped = snapRect(room("m", 11, 14, 3, 3), [], 12, 15);
    expect(snapped.x).toBeCloseTo(9, 6);
    expect(snapped.y).toBeCloseTo(12, 6);
  });
});
```

- [ ] **Step 2: Run** `bun test src/lib/canvas-snap.test.ts` → FAIL. **Step 3: Implement.**

```typescript
// frontend/src/lib/canvas-snap.ts
// Pure snapping math for the canvas editor. Units: metres.
// Grid = internal wall module (115mm); neighbor edges beat grid snaps.

export interface RectMM {
  id: string;
  x: number;
  y: number;
  width: number;
  depth: number;
}

export const GRID_M = 0.115;
export const SNAP_TOL_M = 0.15;

export function snapToGrid(v: number): number {
  return Math.round(v / GRID_M) * GRID_M;
}

export function snapScalar(
  v: number,
  candidates: number[],
  tol: number = SNAP_TOL_M
): number {
  let best = v;
  let bestDist = tol;
  for (const c of candidates) {
    const d = Math.abs(c - v);
    if (d <= bestDist) {
      best = c;
      bestDist = d;
    }
  }
  return best;
}

export function edgeCandidates(
  rooms: readonly RectMM[],
  excludeId: string,
  axis: "x" | "y"
): number[] {
  const out: number[] = [];
  for (const r of rooms) {
    if (r.id === excludeId) continue;
    if (axis === "x") out.push(r.x, r.x + r.width);
    else out.push(r.y, r.y + r.depth);
  }
  return out;
}

function snapEdge(v: number, edges: number[]): number {
  const edgeSnapped = snapScalar(v, edges);
  if (edgeSnapped !== v) return edgeSnapped;
  const grid = snapToGrid(v);
  return Math.abs(grid - v) <= SNAP_TOL_M ? grid : v;
}

export function snapRect(
  rect: RectMM,
  others: readonly RectMM[],
  plotW: number,
  plotD: number
): RectMM {
  const xEdges = edgeCandidates(others, rect.id, "x");
  const yEdges = edgeCandidates(others, rect.id, "y");

  // try snapping the left edge, then the right edge (keep whichever moved)
  let x = snapEdge(rect.x, xEdges);
  if (x === rect.x) {
    const right = snapEdge(rect.x + rect.width, xEdges);
    if (right !== rect.x + rect.width) x = right - rect.width;
  }
  let y = snapEdge(rect.y, yEdges);
  if (y === rect.y) {
    const top = snapEdge(rect.y + rect.depth, yEdges);
    if (top !== rect.y + rect.depth) y = top - rect.depth;
  }

  x = Math.min(Math.max(0, x), Math.max(0, plotW - rect.width));
  y = Math.min(Math.max(0, y), Math.max(0, plotD - rect.depth));
  return { ...rect, x, y };
}
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit.**

```bash
git add frontend/src/lib/canvas-snap.ts frontend/src/lib/canvas-snap.test.ts
git commit -m "feat(frontend): pure canvas snapping module (grid + neighbor edges)"
```

---

### Task 8: Room selection + move-drag in `FloorPlanSVG`

Extends the existing edit mode (wall-drag stays). No prop changes — selection is internal; committed geometry still flows out through the existing `onRoomsChange`.

**Files:**
- Modify: `frontend/src/components/floor-plan-svg.tsx`
- Test: `frontend/src/components/floor-plan-svg.select.test.ts` (pure-logic smoke; interaction verified on the Vercel preview)

**Interfaces:**
- Consumes: `snapRect`, `RectMM` (Task 7); existing internals — `editRooms`/`setEditRooms` (:1052), `displayRooms` (:1064), `scale`, `VP_W` (:22), `handleSVGMouseMove`/`handleSVGMouseUp` (:1137/:1233), `onRoomsChange` prop.
- Produces: internal `selectedRoomId: string | null` state + `selectRoom(id)` — Task 9's resize handles key off it. `clientDeltaToMetres` helper reused by Task 9.

- [ ] **Step 1: Add state, refs, and the coordinate helper** (near the existing `editRooms` state, ~:1052)

```tsx
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null);
  const moveRef = useRef<{
    roomId: string;
    startClientX: number;
    startClientY: number;
    origX: number;
    origY: number;
  } | null>(null);
  const svgElRef = useRef<SVGSVGElement | null>(null);

  // client-pixel delta → metres in model space (y flipped: SVG y grows down,
  // model y grows away from the road at the bottom)
  const clientDeltaToMetres = (dxPx: number, dyPx: number): [number, number] => {
    const el = svgElRef.current;
    if (!el) return [0, 0];
    const pxPerUnit = el.getBoundingClientRect().width / VP_W;
    return [dxPx / pxPerUnit / scale, -dyPx / pxPerUnit / scale];
  };
```

Attach `ref={svgElRef}` on the root `<svg>` element (:~1254, where the mouse handlers are already wired). Reset selection when edit mode toggles off: extend the existing effect that clears `editRooms` (or add one) with `setSelectedRoomId(null)`.

- [ ] **Step 2: Pointer-down on room rects**

In the `displayRooms` render loop (the block that draws each room `<rect>`), add to the room rect element — ONLY the fill rect, not labels:

```tsx
  onMouseDown={editMode ? (e) => handleRoomMouseDown(e, room) : undefined}
  style={editMode ? { cursor: "move" } : undefined}
```

and the handler (next to `handleWallMouseDown`, :1125):

```tsx
  const handleRoomMouseDown = (
    e: React.MouseEvent,
    room: RoomData
  ) => {
    if (!editMode) return;
    e.stopPropagation(); // don't let the svg background deselect
    setSelectedRoomId(room.id);
    moveRef.current = {
      roomId: room.id,
      startClientX: e.clientX,
      startClientY: e.clientY,
      origX: room.x,
      origY: room.y,
    };
  };
```

- [ ] **Step 3: Extend the existing SVG move/up handlers**

At the TOP of `handleSVGMouseMove` (:1137), before the wall-drag branch:

```tsx
    if (moveRef.current) {
      const m = moveRef.current;
      const [dxM, dyM] = clientDeltaToMetres(
        e.clientX - m.startClientX,
        e.clientY - m.startClientY
      );
      const base = editRooms ?? floorPlan.rooms;
      const moving = base.find((r) => r.id === m.roomId);
      if (!moving) return;
      const snapped = snapRect(
        { id: moving.id, x: m.origX + dxM, y: m.origY + dyM, width: moving.width, depth: moving.depth },
        base,
        plotWidth,
        plotLength
      );
      setEditRooms(base.map((r) => (r.id === m.roomId ? { ...r, x: snapped.x, y: snapped.y } : r)));
      return;
    }
```

At the top of `handleSVGMouseUp` (:1233):

```tsx
    if (moveRef.current) {
      moveRef.current = null;
      if (editRooms) onRoomsChange?.(editRooms);
      return;
    }
```

Mirror the same guard in `handleSVGMouseLeave`. Add a background-click deselect: on the `<svg>`'s existing `onMouseDown` (add one if absent) — `if (editMode && !moveRef.current) setSelectedRoomId(null);`.

Import at the top of the file: `import { snapRect } from "@/lib/canvas-snap";`

- [ ] **Step 4: Selection highlight**

In the room-rect render, when `editMode && selectedRoomId === room.id`, add a highlight: `strokeWidth` bumped (e.g. `2.5`) and a distinct stroke (use the existing accent/primary color token used elsewhere in this file — match its conventions, e.g. the wall-drag hover color).

- [ ] **Step 5: Smoke test the module still typechecks and exports**

```typescript
// frontend/src/components/floor-plan-svg.select.test.ts
import { describe, expect, test } from "bun:test";
import { detectSharedWalls } from "./floor-plan-svg";

describe("floor-plan-svg module", () => {
  test("still exports detectSharedWalls after canvas-editor changes", () => {
    expect(typeof detectSharedWalls).toBe("function");
  });
});
```

Run: `cd frontend && bun test && bun run build` → PASS (build is the real typecheck here).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/floor-plan-svg.tsx frontend/src/components/floor-plan-svg.select.test.ts
git commit -m "feat(canvas): room selection + snap-aware move drag in edit mode"
```

---

### Task 9: Resize handles on the selected room

**Files:**
- Modify: `frontend/src/lib/canvas-snap.ts` (+ `applyResize`), `frontend/src/lib/canvas-snap.test.ts`
- Modify: `frontend/src/components/floor-plan-svg.tsx`

**Interfaces:**
- Consumes: `selectedRoomId`, `clientDeltaToMetres`, `svgElRef` (Task 8); `getMinSide(type)` (floor-plan-svg.tsx:808); `snapScalar`/`edgeCandidates` (Task 7).
- Produces: `applyResize(rect: RectMM, corner: Corner, dxM: number, dyM: number, minSide: number, others: readonly RectMM[], plotW: number, plotD: number): RectMM` with `type Corner = "nw" | "ne" | "sw" | "se"`.

- [ ] **Step 1: Failing tests for the pure resize math** (append to `canvas-snap.test.ts`)

```typescript
import { applyResize } from "./canvas-snap";

describe("applyResize", () => {
  const base = room("m", 2, 2, 4, 3);
  test("se corner grows width; negative dyM extends the bottom edge toward the road", () => {
    // se = east (high-x) + south (low-y) edges move. dyM=-1 → bottom edge
    // 2-1=1 → y=1, depth = top(5) - bottom(1) = 4.
    const r = applyResize(base, "se", 1, -1, 2, [], 20, 20);
    expect(r.width).toBeCloseTo(5, 6);
    expect(r.y).toBeCloseTo(1, 6);
    expect(r.depth).toBeCloseTo(4, 6);
  });
  test("nw corner moves origin x and adjusts width", () => {
    const r = applyResize(base, "nw", 1, 0, 2, [], 20, 20);
    expect(r.x).toBeCloseTo(3, 6);
    expect(r.width).toBeCloseTo(3, 6);
  });
  test("never shrinks below minSide", () => {
    const r = applyResize(base, "se", -10, 0, 2.5, [], 20, 20);
    expect(r.width).toBeCloseTo(2.5, 6);
  });
  test("snaps the moving edge to a neighbor edge", () => {
    const others = [room("n", 7.05, 2, 2, 2)]; // neighbor left edge at 7.05
    const r = applyResize(base, "se", 1, 0, 2, others, 20, 20); // new right edge 7.0 → snap 7.05
    expect(r.x + r.width).toBeCloseTo(7.05, 6);
  });
});
```

Convention (write it as a comment in the impl): model y grows AWAY from the road; the SVG flips it. Corners are named in MODEL space: `n` = high-y edge (`y + depth`), `s` = low-y edge (`y`), `w` = low-x edge (`x`), `e` = high-x edge (`x + width`).

- [ ] **Step 2: Run → FAIL. Implement** (append to `canvas-snap.ts`):

```typescript
export type Corner = "nw" | "ne" | "sw" | "se";

export function applyResize(
  rect: RectMM,
  corner: Corner,
  dxM: number,
  dyM: number,
  minSide: number,
  others: readonly RectMM[],
  plotW: number,
  plotD: number
): RectMM {
  const xEdges = edgeCandidates(others, rect.id, "x");
  const yEdges = edgeCandidates(others, rect.id, "y");

  let { x, y, width, depth } = rect;

  if (corner.includes("e")) {
    let right = snapScalar(x + width + dxM, xEdges);
    right = Math.min(right, plotW);
    width = Math.max(minSide, right - x);
  } else {
    let left = snapScalar(x + dxM, xEdges);
    left = Math.max(0, left);
    const right = x + width;
    left = Math.min(left, right - minSide);
    width = right - left;
    x = left;
  }

  if (corner.includes("n")) {
    let top = snapScalar(y + depth + dyM, yEdges);
    top = Math.min(top, plotD);
    depth = Math.max(minSide, top - y);
  } else {
    let bottom = snapScalar(y + dyM, yEdges);
    bottom = Math.max(0, bottom);
    const top = y + depth;
    bottom = Math.min(bottom, top - minSide);
    depth = top - bottom;
    y = bottom;
  }

  return { ...rect, x, y, width, depth };
}
```

Fix the Step-1 test expectations to this exact convention if any disagree (the convention is authoritative; tests document it). Run → PASS.

- [ ] **Step 3: Render handles + drag wiring in `floor-plan-svg.tsx`**

Next to the room-rect render, when `editMode && selectedRoomId === room.id`, render 4 corner handles (model-space corners converted with the existing `px()`/`py()` transforms):

```tsx
  {editMode && selectedRoomId === room.id &&
    (["nw", "ne", "sw", "se"] as const).map((corner) => {
      const cx = px(corner.includes("w") ? room.x : room.x + room.width);
      const cy = py(corner.includes("s") ? room.y : room.y + room.depth);
      return (
        <rect
          key={`handle-${room.id}-${corner}`}
          x={cx - 4}
          y={cy - 4}
          width={8}
          height={8}
          className="fill-background stroke-primary"
          strokeWidth={1.5}
          style={{ cursor: corner === "nw" || corner === "se" ? "nwse-resize" : "nesw-resize" }}
          onMouseDown={(e) => handleResizeMouseDown(e, room, corner)}
        />
      );
    })}
```

State + handlers (pattern-match `moveRef` from Task 8):

```tsx
  const resizeRef = useRef<{
    roomId: string;
    corner: Corner;
    startClientX: number;
    startClientY: number;
    orig: RectMM;
  } | null>(null);

  const handleResizeMouseDown = (e: React.MouseEvent, room: RoomData, corner: Corner) => {
    e.stopPropagation();
    resizeRef.current = {
      roomId: room.id,
      corner,
      startClientX: e.clientX,
      startClientY: e.clientY,
      orig: { id: room.id, x: room.x, y: room.y, width: room.width, depth: room.depth },
    };
  };
```

In `handleSVGMouseMove`, above the move branch:

```tsx
    if (resizeRef.current) {
      const rz = resizeRef.current;
      const [dxM, dyM] = clientDeltaToMetres(
        e.clientX - rz.startClientX,
        e.clientY - rz.startClientY
      );
      const base = editRooms ?? floorPlan.rooms;
      const target = base.find((r) => r.id === rz.roomId);
      if (!target) return;
      const resized = applyResize(
        rz.orig, rz.corner, dxM, dyM, getMinSide(target.type), base, plotWidth, plotLength
      );
      setEditRooms(base.map((r) => (r.id === rz.roomId ? { ...r, ...resized } : r)));
      return;
    }
```

In `handleSVGMouseUp` (above the move branch): `if (resizeRef.current) { resizeRef.current = null; if (editRooms) onRoomsChange?.(editRooms); return; }`. Import `applyResize, type Corner, type RectMM` from `@/lib/canvas-snap`.

- [ ] **Step 4: Verify + commit**

`cd frontend && bun test && bun run build` → PASS.

```bash
git add frontend/src/lib/canvas-snap.ts frontend/src/lib/canvas-snap.test.ts frontend/src/components/floor-plan-svg.tsx
git commit -m "feat(canvas): corner resize handles with min-size and edge snapping"
```

---

### Task 10: Client-side undo/redo for the canvas editor

**Files:**
- Create: `frontend/src/lib/edit-history.ts`
- Test: `frontend/src/lib/edit-history.test.ts`
- Modify: `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx`

**Interfaces:**
- Consumes: `handleRoomsChange` (:741) — the single funnel through which committed edits arrive (drag-end / resize-end fire `onRoomsChange`).
- Produces: `History<T>`, `initHistory`, `pushHistory`, `undoHistory`, `redoHistory`, `canUndo`, `canRedo`.

- [ ] **Step 1: Failing tests**

```typescript
// frontend/src/lib/edit-history.test.ts
import { describe, expect, test } from "bun:test";
import {
  canRedo, canUndo, initHistory, pushHistory, redoHistory, undoHistory,
} from "./edit-history";

describe("edit-history", () => {
  test("init has no undo/redo", () => {
    const h = initHistory([1]);
    expect(canUndo(h)).toBe(false);
    expect(canRedo(h)).toBe(false);
  });
  test("push then undo restores previous", () => {
    let h = initHistory([1]);
    h = pushHistory(h, [2]);
    expect(canUndo(h)).toBe(true);
    h = undoHistory(h);
    expect(h.present).toEqual([1]);
    expect(canRedo(h)).toBe(true);
  });
  test("redo replays the undone state", () => {
    let h = pushHistory(initHistory([1]), [2]);
    h = redoHistory(undoHistory(h));
    expect(h.present).toEqual([2]);
  });
  test("push clears the redo stack", () => {
    let h = pushHistory(initHistory([1]), [2]);
    h = undoHistory(h);
    h = pushHistory(h, [3]);
    expect(canRedo(h)).toBe(false);
  });
  test("history is capped at 50 entries", () => {
    let h = initHistory(0 as unknown as number[]);
    for (let i = 1; i <= 60; i++) h = pushHistory(h, i as unknown as number[]);
    expect(h.past.length).toBe(50);
  });
  test("undo/redo at the boundary are no-ops", () => {
    const h = initHistory([1]);
    expect(undoHistory(h)).toBe(h);
    expect(redoHistory(h)).toBe(h);
  });
});
```

- [ ] **Step 2: Run → FAIL. Implement:**

```typescript
// frontend/src/lib/edit-history.ts
const CAP = 50;

export interface History<T> {
  past: T[];
  present: T;
  future: T[];
}

export function initHistory<T>(present: T): History<T> {
  return { past: [], present, future: [] };
}

export function pushHistory<T>(h: History<T>, next: T): History<T> {
  return { past: [...h.past, h.present].slice(-CAP), present: next, future: [] };
}

export function undoHistory<T>(h: History<T>): History<T> {
  if (h.past.length === 0) return h;
  return {
    past: h.past.slice(0, -1),
    present: h.past[h.past.length - 1],
    future: [h.present, ...h.future],
  };
}

export function redoHistory<T>(h: History<T>): History<T> {
  if (h.future.length === 0) return h;
  return {
    past: [...h.past, h.present],
    present: h.future[0],
    future: h.future.slice(1),
  };
}

export const canUndo = <T>(h: History<T>): boolean => h.past.length > 0;
export const canRedo = <T>(h: History<T>): boolean => h.future.length > 0;
```

Run → PASS.

- [ ] **Step 3: Wire into the viewer**

In `layout-viewer.tsx`:
- Add state `const [editHistory, setEditHistory] = useState<History<RoomData[]> | null>(null);` next to `editedRooms` (:537 area).
- On entering edit mode (where `editedRooms` is initialised), also `setEditHistory(initHistory(initialRooms))`; on exit, `setEditHistory(null)`.
- In `handleRoomsChange` (:741), after `setEditedRooms(rooms)`, add `setEditHistory((h) => (h ? pushHistory(h, rooms) : h));`.
- Undo/redo actions:

```tsx
  const handleUndo = useCallback(() => {
    setEditHistory((h) => {
      if (!h || !canUndo(h)) return h;
      const next = undoHistory(h);
      setEditedRooms(next.present);
      runComplianceCheck(next.present); // existing debounced checker
      return next;
    });
  }, [runComplianceCheck]);
  // handleRedo: identical with redoHistory/canRedo
```

- Toolbar: next to the existing Save/Cancel edit buttons add
```tsx
  <Button variant="ghost" size="sm" onClick={handleUndo} disabled={!editHistory || !canUndo(editHistory)}>Undo</Button>
  <Button variant="ghost" size="sm" onClick={handleRedo} disabled={!editHistory || !canRedo(editHistory)}>Redo</Button>
```
- Keyboard: one `useEffect` active only in edit mode —
```tsx
  useEffect(() => {
    if (!editMode) return;
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      if (e.shiftKey) handleRedo();
      else handleUndo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editMode, handleUndo, handleRedo]);
```
- **Sync gotcha:** `FloorPlanSVG` keeps its own `editRooms` copy. Pass the authoritative rooms down: the viewer already passes edited rooms into `FloorPlanSVG` via `floorPlan` — ensure the plan-tab `FloorPlanSVG` receives `{...activeFloorPlan, rooms: editedRooms ?? activeFloorPlan.rooms}` in edit mode, and add a `useEffect` in `FloorPlanSVG` that resets its internal `editRooms` when the incoming `floorPlan.rooms` identity changes while `editMode` is true (undo must visibly revert the canvas).

- [ ] **Step 4: Verify + commit**

`cd frontend && bun test && bun run lint && bun run build` → PASS.

```bash
git add frontend/src/lib/edit-history.ts frontend/src/lib/edit-history.test.ts "frontend/src/app/(app)/projects/[id]/layout-viewer.tsx" frontend/src/components/floor-plan-svg.tsx
git commit -m "feat(canvas): client-side undo/redo with keyboard shortcuts"
```

---

### Task 11: Persist agent undo stacks + agent-chat feature flag (3b)

The agent tools already operate on persisted layouts (done in Phase 1). Two leftovers: the in-memory `_undo_stacks` dict (`rooms.py:36`) dies on Cloud Run scale-to-zero and isn't shared across instances; and per the phase-0 plan the AI-edit surface ships default-off.

**Files:**
- Create: `backend/app/models/undo.py`
- Modify: `backend/app/api/routes/rooms.py` (lines 15, 36–56, and every `_push_undo`/`_pop_undo` call site — grep both names), `backend/app/main.py` (model import)
- Modify: `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx` (tab visibility), Create: `frontend/src/lib/tabs.ts` + test
- Test: `backend/tests/test_undo_persistence.py`, `frontend/src/lib/tabs.test.ts`

**Interfaces:**
- Produces: `UndoStack` model — table `undo_stacks`, composite PK `(project_id, user_id)`, `stack: JSON` (list of geometry-JSON strings, capped at 10), `updated_at`. Async `_push_undo(db, project_id, user_id, state: dict)` / `_pop_undo(db, project_id, user_id) -> dict | None` in rooms.py. Frontend `visibleTabs(agentChatEnabled: boolean): TabId[]`.
- Env var: `NEXT_PUBLIC_AGENT_CHAT` — chat tab renders only when `"1"` (build-time inlined; default hidden).

- [ ] **Step 1: Migration gate** — `Workflow({ name: 'db-migration-safe', args: 'add undo_stacks table (project_id+user_id composite PK, stack JSON, updated_at)' })`.

- [ ] **Step 2: Failing backend test**

```python
# backend/tests/test_undo_persistence.py
import pytest

# seeding helpers as before


@pytest.mark.anyio
async def test_undo_survives_a_fresh_session(client_db):
    """Move a room, then undo through a DIFFERENT session — proves the stack
    is in the DB, not process memory (Cloud Run multi-instance safety)."""
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u1", "pro")
    project_id = await _seed_project_with_layout(SessionLocal, "u1")

    rooms = (
        await client.get(
            f"/api/projects/{project_id}/rooms", headers={"X-Test-User-Id": "u1"}
        )
    ).json()["rooms"]
    first = rooms[0]

    moved = await client.post(
        f"/api/projects/{project_id}/rooms/{first['id']}/move",
        json={"x": first["x"] + 0.5, "y": first["y"]},
        headers={"X-Test-User-Id": "u1"},
    )
    assert moved.status_code == 200

    undone = await client.post(
        f"/api/projects/{project_id}/rooms/undo", headers={"X-Test-User-Id": "u1"}
    )
    assert undone.status_code == 200

    after = (
        await client.get(
            f"/api/projects/{project_id}/rooms", headers={"X-Test-User-Id": "u1"}
        )
    ).json()["rooms"]
    match = next(r for r in after if r["id"] == first["id"])
    assert match["x"] == pytest.approx(first["x"])
```

(Adjust the move endpoint's exact body/response keys to `rooms.py:332` — read the handler; the assertion structure stays.)

- [ ] **Step 3: Model**

```python
# backend/app/models/undo.py
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UndoStack(Base):
    __tablename__ = "undo_stacks"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    stack: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
```

Add `import app.models.undo  # noqa: F401` to main.py's import block.

- [ ] **Step 4: Replace the in-memory stack in `rooms.py`**

Delete lines 15 (`from collections import deque`), 36 (`_undo_stacks: ...`), and the old `_push_undo`/`_pop_undo` (44–56). Replace with:

```python
from sqlalchemy.orm.attributes import flag_modified

from app.models.undo import UndoStack

MAX_UNDO = 10  # keep the existing constant if it already exists


async def _push_undo(
    db: AsyncSession, project_id: str, user_id: str, state: dict
) -> None:
    row = await db.get(UndoStack, (project_id, user_id))
    if row is None:
        row = UndoStack(project_id=project_id, user_id=user_id, stack=[])
        db.add(row)
    stack = list(row.stack)
    stack.append(json.dumps(state))
    row.stack = stack[-MAX_UNDO:]
    flag_modified(row, "stack")
    await db.commit()


async def _pop_undo(db: AsyncSession, project_id: str, user_id: str) -> dict | None:
    row = await db.get(UndoStack, (project_id, user_id))
    if row is None or not row.stack:
        return None
    stack = list(row.stack)
    state = json.loads(stack.pop())
    row.stack = stack
    flag_modified(row, "stack")
    await db.commit()
    return state
```

Update every call site (`grep -n "_push_undo\|_pop_undo" backend/app/api/routes/rooms.py`): the old key `f"{project_id}:{user_id}"` becomes the two args, calls become `await _push_undo(db, project_id, user_id, state)` — the old sites at :358/:393 wrapped state in `json.loads(json.dumps(state))` for a deep copy; that's now redundant (we serialize anyway) — pass `state` directly. The undo endpoint (:731) awaits `_pop_undo(db, project_id, user_id)`.

- [ ] **Step 5: Run** `uv run pytest tests/test_undo_persistence.py tests/ -x -q` → PASS (the existing rooms tests exercise the changed call sites).

- [ ] **Step 6: Chat feature flag (frontend)**

```typescript
// frontend/src/lib/tabs.ts
export const ALL_TABS = ["plan", "section", "boq", "compare", "chat", "render"] as const;
export type TabId = (typeof ALL_TABS)[number];

export function visibleTabs(agentChatEnabled: boolean): TabId[] {
  return ALL_TABS.filter((t) => t !== "chat" || agentChatEnabled);
}
```

```typescript
// frontend/src/lib/tabs.test.ts
import { describe, expect, test } from "bun:test";
import { visibleTabs } from "./tabs";

describe("visibleTabs", () => {
  test("chat hidden by default", () => expect(visibleTabs(false)).not.toContain("chat"));
  test("chat shown when enabled", () => expect(visibleTabs(true)).toContain("chat"));
  test("other tabs always present", () =>
    expect(visibleTabs(false)).toEqual(["plan", "section", "boq", "compare", "render"]));
});
```

In `layout-viewer.tsx` (:1617), drive the tab buttons from `visibleTabs(process.env.NEXT_PUBLIC_AGENT_CHAT === "1")` instead of the hardcoded list, and guard the chat panel render (:2050) with the same condition. If `activeTab === "chat"` while hidden, fall back to `"plan"`.

- [ ] **Step 7: Verify + commit**

`cd frontend && bun test && bun run build` → PASS; backend suite + ruff → PASS.

```bash
git add backend/app/models/undo.py backend/app/api/routes/rooms.py backend/app/main.py backend/tests/test_undo_persistence.py frontend/src/lib/tabs.ts frontend/src/lib/tabs.test.ts "frontend/src/app/(app)/projects/[id]/layout-viewer.tsx"
git commit -m "feat: persist agent undo stacks in DB; agent chat behind NEXT_PUBLIC_AGENT_CHAT flag"
```

---

### Task 12: Plot preview on the new-project form (3c)

Render the form's existing inputs (dims, setbacks, road side) as a live plot diagram — no new inputs, no solving. NOTE: the form stores values in FEET (`feetToMetres` runs at submit, `new-project-form.tsx:408`); the preview must convert.

**Files:**
- Create: `frontend/src/lib/plot-preview.ts`, `frontend/src/components/plot-preview.tsx`
- Test: `frontend/src/lib/plot-preview.test.ts`
- Modify: `frontend/src/app/(app)/projects/new/new-project-form.tsx` (§3 Orientation & setbacks, ~line 752)

**Interfaces:**
- Produces:
  - `computePlotPreview(input: PlotPreviewInput, vpW?: number, vpH?: number): PlotPreviewGeom`
  - `interface PlotPreviewInput { plotLengthFt: string; plotWidthFt: string; setbackFrontFt: string; setbackRearFt: string; setbackLeftFt: string; setbackRightFt: string; roadSide: string }`
  - `interface PlotPreviewGeom { valid: boolean; viewW: number; viewH: number; plot: Box | null; buildable: Box | null; road: Box | null }` with `type Box = { x: number; y: number; w: number; h: number }` (SVG px; road at the `roadSide` edge; front setback measured from the road side).

- [ ] **Step 1: Failing tests**

```typescript
// frontend/src/lib/plot-preview.test.ts
import { describe, expect, test } from "bun:test";
import { computePlotPreview } from "./plot-preview";

const input = {
  plotLengthFt: "40",   // 12.19 m
  plotWidthFt: "30",    // 9.14 m
  setbackFrontFt: "5",
  setbackRearFt: "5",
  setbackLeftFt: "3",
  setbackRightFt: "3",
  roadSide: "S",
};

describe("computePlotPreview", () => {
  test("valid input produces plot, buildable and road boxes", () => {
    const g = computePlotPreview(input, 260, 260);
    expect(g.valid).toBe(true);
    expect(g.plot).not.toBeNull();
    expect(g.buildable).not.toBeNull();
    expect(g.road).not.toBeNull();
  });
  test("buildable is inset within the plot", () => {
    const g = computePlotPreview(input, 260, 260);
    const p = g.plot!, b = g.buildable!;
    expect(b.x).toBeGreaterThan(p.x);
    expect(b.y).toBeGreaterThan(p.y);
    expect(b.x + b.w).toBeLessThan(p.x + p.w);
    expect(b.y + b.h).toBeLessThan(p.y + p.h);
  });
  test("aspect ratio preserved (taller plot → taller box)", () => {
    const g = computePlotPreview(input, 260, 260);
    expect(g.plot!.h).toBeGreaterThan(g.plot!.w); // 40ft deep vs 30ft wide
  });
  test("road sits at the bottom for roadSide S", () => {
    const g = computePlotPreview(input, 260, 260);
    expect(g.road!.y).toBeGreaterThan(g.plot!.y + g.plot!.h - 1);
  });
  test("nonsense input → invalid", () => {
    expect(computePlotPreview({ ...input, plotLengthFt: "" }).valid).toBe(false);
    expect(computePlotPreview({ ...input, plotWidthFt: "-3" }).valid).toBe(false);
  });
  test("setbacks consuming the whole plot → buildable null but still valid", () => {
    const g = computePlotPreview({ ...input, setbackLeftFt: "20", setbackRightFt: "20" });
    expect(g.valid).toBe(true);
    expect(g.buildable).toBeNull();
  });
});
```

- [ ] **Step 2: Run → FAIL. Implement:**

```typescript
// frontend/src/lib/plot-preview.ts
const FT_TO_M = 0.3048;
const PAD = 18;
const ROAD_PX = 10;

export interface PlotPreviewInput {
  plotLengthFt: string;
  plotWidthFt: string;
  setbackFrontFt: string;
  setbackRearFt: string;
  setbackLeftFt: string;
  setbackRightFt: string;
  roadSide: string; // "N" | "S" | "E" | "W"
}

export type Box = { x: number; y: number; w: number; h: number };

export interface PlotPreviewGeom {
  valid: boolean;
  viewW: number;
  viewH: number;
  plot: Box | null;
  buildable: Box | null;
  road: Box | null;
}

const num = (s: string): number => {
  const v = Number.parseFloat(s);
  return Number.isFinite(v) ? v : Number.NaN;
};

export function computePlotPreview(
  input: PlotPreviewInput,
  viewW = 260,
  viewH = 260
): PlotPreviewGeom {
  const invalid: PlotPreviewGeom = { valid: false, viewW, viewH, plot: null, buildable: null, road: null };

  const wM = num(input.plotWidthFt) * FT_TO_M;
  const lM = num(input.plotLengthFt) * FT_TO_M;
  if (!(wM > 0) || !(lM > 0)) return invalid;

  const sb = {
    front: Math.max(0, num(input.setbackFrontFt) || 0) * FT_TO_M,
    rear: Math.max(0, num(input.setbackRearFt) || 0) * FT_TO_M,
    left: Math.max(0, num(input.setbackLeftFt) || 0) * FT_TO_M,
    right: Math.max(0, num(input.setbackRightFt) || 0) * FT_TO_M,
  };

  const availW = viewW - 2 * PAD;
  const availH = viewH - 2 * PAD - ROAD_PX;
  const scale = Math.min(availW / wM, availH / lM);

  const plotW = wM * scale;
  const plotH = lM * scale;
  const plot: Box = {
    x: (viewW - plotW) / 2,
    y: (viewH - ROAD_PX - plotH) / 2,
    w: plotW,
    h: plotH,
  };

  // Draw with the road at the roadSide edge. Front setback = road side.
  // Map front/rear/left/right onto screen top/bottom/left/right per roadSide.
  const side = ["N", "S", "E", "W"].includes(input.roadSide) ? input.roadSide : "S";
  const bySide: Record<string, { top: number; bottom: number; left: number; right: number }> = {
    S: { bottom: sb.front, top: sb.rear, left: sb.left, right: sb.right },
    N: { top: sb.front, bottom: sb.rear, left: sb.right, right: sb.left },
    E: { right: sb.front, left: sb.rear, top: sb.left, bottom: sb.right },
    W: { left: sb.front, right: sb.rear, top: sb.right, bottom: sb.left },
  };
  const m = bySide[side];

  const bx = plot.x + m.left * scale;
  const by = plot.y + m.top * scale;
  const bw = plot.w - (m.left + m.right) * scale;
  const bh = plot.h - (m.top + m.bottom) * scale;
  const buildable: Box | null = bw > 1 && bh > 1 ? { x: bx, y: by, w: bw, h: bh } : null;

  const road: Box =
    side === "S" ? { x: plot.x, y: plot.y + plot.h + 2, w: plot.w, h: ROAD_PX }
    : side === "N" ? { x: plot.x, y: plot.y - ROAD_PX - 2, w: plot.w, h: ROAD_PX }
    : side === "E" ? { x: plot.x + plot.w + 2, y: plot.y, w: ROAD_PX, h: plot.h }
    : { x: plot.x - ROAD_PX - 2, y: plot.y, w: ROAD_PX, h: plot.h };

  return { valid: true, viewW, viewH, plot, buildable, road };
}
```

Run → PASS.

- [ ] **Step 3: Component**

```tsx
// frontend/src/components/plot-preview.tsx
"use client";

import { computePlotPreview, type PlotPreviewInput } from "@/lib/plot-preview";

export function PlotPreview({ input }: { input: PlotPreviewInput }) {
  const g = computePlotPreview(input);
  if (!g.valid) {
    return (
      <div className="flex h-[260px] items-center justify-center rounded-md border border-dashed text-xs text-muted-foreground">
        Enter plot dimensions to preview
      </div>
    );
  }
  return (
    <svg
      viewBox={`0 0 ${g.viewW} ${g.viewH}`}
      className="h-[260px] w-full rounded-md border bg-muted/20"
      role="img"
      aria-label="Plot preview with setbacks"
    >
      {g.road && <rect {...boxProps(g.road)} className="fill-amber-500/60" rx={2} />}
      {g.plot && (
        <rect {...boxProps(g.plot)} className="fill-transparent stroke-foreground/70" strokeWidth={1.5} />
      )}
      {g.buildable && (
        <rect
          {...boxProps(g.buildable)}
          className="fill-primary/10 stroke-primary"
          strokeWidth={1}
          strokeDasharray="4 3"
        />
      )}
      {g.buildable && (
        <text
          x={g.buildable.x + g.buildable.w / 2}
          y={g.buildable.y + g.buildable.h / 2}
          textAnchor="middle"
          dominantBaseline="middle"
          className="fill-muted-foreground text-[9px]"
        >
          buildable
        </text>
      )}
    </svg>
  );
}

function boxProps(b: { x: number; y: number; w: number; h: number }) {
  return { x: b.x, y: b.y, width: b.w, height: b.h };
}
```

- [ ] **Step 4: Wire into the form**

In `new-project-form.tsx` §3 (Orientation & setbacks, next to `<PlotCompass roadSide={form.road_side} />` ~line 757), add:

```tsx
  <PlotPreview
    input={{
      plotLengthFt: form.plot_length,
      plotWidthFt: form.plot_width,
      setbackFrontFt: form.setback_front,
      setbackRearFt: form.setback_rear,
      setbackLeftFt: form.setback_left,
      setbackRightFt: form.setback_right,
      roadSide: form.road_side,
    }}
  />
```

(Confirm the exact `form` field names against the `useState` initialiser at :246 — `plot_length`/`plot_width`/`setback_*`/`road_side`.) Match Blueprint Dark styling conventions used by `PlotCompass`.

- [ ] **Step 5: Verify + commit**

`cd frontend && bun test && bun run lint && bun run build` → PASS.

```bash
git add frontend/src/lib/plot-preview.ts frontend/src/lib/plot-preview.test.ts frontend/src/components/plot-preview.tsx "frontend/src/app/(app)/projects/new/new-project-form.tsx"
git commit -m "feat(frontend): live plot + setback preview on the new-project form"
```

---

### Task 13: Standard opening sizes → config (3d, part 1)

Door width is a hardcoded `_DOOR_WIDTH = 0.9` (`backend/app/engine/cad_primitives.py:94`); window width is `min(1.2, room.width * 0.6)` (`backend/app/engine/cad_elements.py:219`). Move to `compliance_rules.json` per the project convention "compliance rules in JSON, not hardcoded".

**Files:**
- Modify: `backend/app/config/compliance_rules.json`
- Create: `backend/app/engine/standards.py`
- Modify: `backend/app/engine/cad_primitives.py:94`, `backend/app/engine/cad_elements.py:219`
- Test: `backend/tests/test_opening_standards.py`

**Interfaces:**
- Produces (consumed by Task 14): `get_opening_standards() -> OpeningStandards` with fields `door_width_m: float`, `window_width_m: float`, `window_max_room_fraction: float`, `ventilator_width_m: float`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_opening_standards.py
from app.engine.standards import OpeningStandards, get_opening_standards


def test_defaults_come_from_compliance_rules_json():
    std = get_opening_standards()
    assert std.door_width_m == 0.9
    assert std.window_width_m == 1.2
    assert std.window_max_room_fraction == 0.6
    assert std.ventilator_width_m == 0.6


def test_missing_config_section_falls_back_to_defaults(monkeypatch, tmp_path):
    import app.engine.standards as standards

    empty = tmp_path / "rules.json"
    empty.write_text("{}")
    monkeypatch.setattr(standards, "_RULES_PATH", empty)
    standards.get_opening_standards.cache_clear()
    try:
        assert standards.get_opening_standards() == OpeningStandards()
    finally:
        standards.get_opening_standards.cache_clear()


def test_openings_use_configured_door_width():
    from app.engine.cad_primitives import _DOOR_WIDTH

    assert _DOOR_WIDTH == get_opening_standards().door_width_m
```

- [ ] **Step 2: Run → FAIL. Add the JSON section** (top level of `backend/app/config/compliance_rules.json`):

```json
  "standard_openings": {
    "door_width_mm": 900,
    "window_width_mm": 1200,
    "window_max_room_fraction": 0.6,
    "ventilator_width_mm": 600
  }
```

- [ ] **Step 3: Implement `standards.py`**

```python
# backend/app/engine/standards.py
import json
import pathlib
from dataclasses import dataclass
from functools import lru_cache

_RULES_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "config" / "compliance_rules.json"
)


@dataclass(frozen=True)
class OpeningStandards:
    door_width_m: float = 0.9
    window_width_m: float = 1.2
    window_max_room_fraction: float = 0.6
    ventilator_width_m: float = 0.6


@lru_cache(maxsize=1)
def get_opening_standards() -> OpeningStandards:
    try:
        raw = json.loads(_RULES_PATH.read_text()).get("standard_openings", {})
    except (OSError, json.JSONDecodeError):
        raw = {}
    return OpeningStandards(
        door_width_m=raw.get("door_width_mm", 900) / 1000,
        window_width_m=raw.get("window_width_mm", 1200) / 1000,
        window_max_room_fraction=raw.get("window_max_room_fraction", 0.6),
        ventilator_width_m=raw.get("ventilator_width_mm", 600) / 1000,
    )
```

- [ ] **Step 4: Swap the literals**

`cad_primitives.py:94`:
```python
from app.engine.standards import get_opening_standards

_DOOR_WIDTH = get_opening_standards().door_width_m
```
`cad_elements.py:219` — replace `win_w = min(1.2, room.width * 0.6)` with:
```python
    _std = get_opening_standards()
    win_w = min(_std.window_width_m, room.width * _std.window_max_room_fraction)
```
(import at top). Grep BOTH files for any other `0.9` / `1.2` opening literals (`grep -n "0\.9\|1\.2" backend/app/engine/cad_primitives.py backend/app/engine/cad_elements.py`) and route genuine opening-size uses through the standards (leave unrelated numerics alone — e.g. scale factors).

- [ ] **Step 5: Run** `uv run pytest tests/test_opening_standards.py -x -q` → PASS; **full suite** → PASS — this is the CCQS-relevant step: `tests/test_ccqs_*` (regression gate) MUST stay green since values are unchanged (900/1200 in = 0.9/1.2 out). If any DXF/PDF test fails, the swap changed behaviour — stop and fix the mapping, do NOT re-baseline.

- [ ] **Step 6: Commit**

```bash
git add backend/app/config/compliance_rules.json backend/app/engine/standards.py backend/app/engine/cad_primitives.py backend/app/engine/cad_elements.py backend/tests/test_opening_standards.py
git commit -m "refactor(cad): standard opening sizes from compliance_rules.json"
```

---

### Task 14: DXF door/window blocks (3d, part 2)

Group door/window geometry into ezdxf BLOCK definitions inserted per opening — drafted-class DXF where a CAD user can select/replace/count openings as symbols.

**Files:**
- Create: `backend/app/engine/cad_blocks.py`
- Modify: `backend/app/api/routes/export.py` (`_render_dxf` :210 and the per-floor opening loop :~354–400)
- Test: `backend/tests/test_dxf_blocks.py`

**Interfaces:**
- Consumes: `get_opening_standards()` (Task 13); `collect_openings`' `Opening` items (read its dataclass in `backend/app/engine/cad_primitives.py` — it carries position, width, orientation, and kind; today's per-opening loop dispatches to `draw_door` / `draw_window` / `draw_ventilator`).
- Produces: `define_opening_blocks(doc) -> None` (idempotent), `insert_door(msp, x, y, rotation_deg, z=0.0)`, `insert_window(msp, x, y, rotation_deg, z=0.0)`, `insert_ventilator(msp, x, y, rotation_deg, z=0.0)`. Block names: `PF_DOOR`, `PF_WINDOW`, `PF_VENT`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_dxf_blocks.py
import io

import ezdxf


def _build_doc():
    """Render the same fixture layout the existing DXF tests use — copy the
    doc-building setup from backend/tests/test_dxf_export.py (or the closest
    test_dxf_* module) so this test exercises the real _render_dxf path."""
    ...


def test_opening_blocks_are_defined_and_inserted():
    doc = _build_doc()
    assert "PF_DOOR" in doc.blocks
    assert "PF_WINDOW" in doc.blocks
    msp = doc.modelspace()
    door_inserts = [e for e in msp.query("INSERT") if e.dxf.name == "PF_DOOR"]
    window_inserts = [e for e in msp.query("INSERT") if e.dxf.name == "PF_WINDOW"]
    assert len(door_inserts) >= 1
    assert len(window_inserts) >= 1
    assert all(e.dxf.layer == "A-DOOR" for e in door_inserts)
    assert all(e.dxf.layer == "A-WINDOW" for e in window_inserts)


def test_no_loose_door_arcs_left_on_a_door_layer():
    """Doors are now symbols: raw ARC entities on A-DOOR in modelspace mean the
    old free-floating drawing path is still active somewhere."""
    doc = _build_doc()
    msp = doc.modelspace()
    assert not [e for e in msp.query("ARC") if e.dxf.layer == "A-DOOR"]
```

- [ ] **Step 2: Run → FAIL. Implement `cad_blocks.py`:**

```python
# backend/app/engine/cad_blocks.py
"""Reusable DXF block definitions for openings (drafted-class symbols).

Blocks are defined once per document at their standard size (Task 13 config);
inserts place them by base point + rotation. Base point = hinge/sill start,
symbol drawn along +X.
"""
import math

from app.engine.standards import get_opening_standards

DOOR_BLOCK = "PF_DOOR"
WINDOW_BLOCK = "PF_WINDOW"
VENT_BLOCK = "PF_VENT"


def define_opening_blocks(doc) -> None:
    std = get_opening_standards()

    if DOOR_BLOCK not in doc.blocks:
        blk = doc.blocks.new(name=DOOR_BLOCK)
        w = std.door_width_m
        # door leaf, opened 90°: from hinge (0,0) up to (0, w)
        blk.add_line((0.0, 0.0), (0.0, w))
        # swing arc from the leaf tip to the closed position (w, 0)
        blk.add_arc(center=(0.0, 0.0), radius=w, start_angle=0.0, end_angle=90.0)

    if WINDOW_BLOCK not in doc.blocks:
        blk = doc.blocks.new(name=WINDOW_BLOCK)
        w = std.window_width_m
        t = 0.23  # external wall thickness — window symbol spans the wall
        for frac in (0.0, 0.5, 1.0):  # 3 parallel lines: faces + glazing line
            y = -t / 2 + t * frac
            blk.add_line((0.0, y), (w, y))
        blk.add_line((0.0, -t / 2), (0.0, t / 2))
        blk.add_line((w, -t / 2), (w, t / 2))

    if VENT_BLOCK not in doc.blocks:
        blk = doc.blocks.new(name=VENT_BLOCK)
        w = std.ventilator_width_m
        t = 0.23
        blk.add_line((0.0, -t / 2), (w, -t / 2))
        blk.add_line((0.0, t / 2), (w, t / 2))
        blk.add_line((0.0, 0.0), (w, 0.0))


def _insert(msp, name: str, layer: str, x: float, y: float, rotation_deg: float, z: float):
    msp.add_blockref(
        name,
        insert=(x, y, z),
        dxfattribs={"layer": layer, "rotation": rotation_deg},
    )


def insert_door(msp, x: float, y: float, rotation_deg: float, z: float = 0.0) -> None:
    _insert(msp, DOOR_BLOCK, "A-DOOR", x, y, rotation_deg, z)


def insert_window(msp, x: float, y: float, rotation_deg: float, z: float = 0.0) -> None:
    _insert(msp, WINDOW_BLOCK, "A-WINDOW", x, y, rotation_deg, z)


def insert_ventilator(msp, x: float, y: float, rotation_deg: float, z: float = 0.0) -> None:
    _insert(msp, VENT_BLOCK, "A-VENTILATOR", x, y, rotation_deg, z)
```

- [ ] **Step 3: Swap the call sites in `_render_dxf`**

In `export.py`, right after `doc = ezdxf.new("R2010", setup=True)` + layer setup: `define_opening_blocks(doc)`.

In the per-floor opening loop (:~354–400), each opening currently dispatches to `draw_door(...)` / `draw_window(...)` / `draw_ventilator(...)` with the opening's position and orientation. Replace each call with the matching `insert_*` — derive `(x, y, rotation_deg)` from the SAME `Opening` fields the old call used: the opening's start point along the wall is the insert base point; a horizontal wall segment → `rotation_deg=0`, vertical → `rotation_deg=90` (read `Opening`'s orientation field in `cad_primitives.py` for the exact attribute name; keep the same `z` the old call passed). Do NOT delete `draw_door`/`draw_window`/`draw_ventilator` from `cad_elements.py` if the PDF pipeline also calls them — `grep -rn "draw_door\|draw_window\|draw_ventilator" backend/app/` first; only the DXF call sites change.

- [ ] **Step 4: Run** `uv run pytest tests/test_dxf_blocks.py tests/ -x -q` → new test PASS; update any existing `test_dxf_*` assertions that counted raw door/window LINE/ARC entities in modelspace (they become INSERT-count assertions — same coverage intent, new entity type). CCQS gate must stay green (PDF path untouched).

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/cad_blocks.py backend/app/api/routes/export.py backend/tests/test_dxf_blocks.py
git commit -m "feat(dxf): door/window/ventilator as reusable block inserts"
```

---

### Task 15: Status, deployment notes, and the finish-feature handoff

**Files:**
- Modify: `Status.md` (append a Phase 3 section)
- Modify: `.github/workflows/deploy-backend.yml` (Inngest env vars)
- Modify: `backend/.env.example` if it exists (placeholder keys only — NEVER real values)

- [ ] **Step 1: Append to `Status.md`**

```markdown
---

# Stage 1 Phase 3: Canvas Editing + Async Generation (Inngest)

**Branch:** `worktree-stage1-phase3` (worktree off v2; PR into v2)
**Plan:** `docs/superpowers/plans/2026-07-05-stage1-phase3-canvas-async.md`

## Shipped
- 3e: Inngest async generation + render jobs (`generation_jobs` table, `/api/inngest`,
  inline fallback without keys). Page loads NEVER solve (new `GET /projects/{id}/layouts`).
- 3a: canvas editor — select/move/resize with 115mm-grid + neighbor snapping,
  client undo/redo; write-back via the Phase-1 PATCH endpoint.
- 3b: agent undo stacks persisted (`undo_stacks` table); chat tab behind `NEXT_PUBLIC_AGENT_CHAT=1`.
- 3c: live plot/setback preview on the new-project form.
- 3d: opening sizes in `compliance_rules.json` (`standard_openings`); DXF doors/windows/vents as PF_* block inserts.
- Fix: ranked tier gate — firm no longer locked out of edit/DXF/BOQ.

## Deployment (BEFORE merge to main)
1. Create the Inngest app (inngest.com, free tier) → copy EVENT KEY + SIGNING KEY.
2. GitHub Actions secrets: `INNGEST_EVENT_KEY`, `INNGEST_SIGNING_KEY` → wired into Cloud Run
   env by deploy-backend.yml. WITHOUT them the backend falls back to inline synchronous
   generation (works, but first generate can still hit the 15s proxy ceiling on cold start).
3. After the first deploy, sync the app in the Inngest dashboard against
   `https://<cloud-run-url>/api/inngest`.
4. Cloud Run request timeout must be ≥ 300s (default is 300 — confirm it wasn't lowered).
5. Vercel: `NEXT_PUBLIC_AGENT_CHAT` unset (chat hidden) until Anthropic billing is topped up.
```

- [ ] **Step 2: deploy-backend.yml**

In the Cloud Run deploy step's env-var flags (where `INTERNAL_AUTH_SECRET` etc. are passed), add:
```yaml
          INNGEST_EVENT_KEY=${{ secrets.INNGEST_EVENT_KEY }}
          INNGEST_SIGNING_KEY=${{ secrets.INNGEST_SIGNING_KEY }}
```
matching the file's existing `--set-env-vars`/env-file syntax exactly. Empty secrets are fine — the backend treats empty as "Inngest disabled".

- [ ] **Step 3: Full verification sweep**

```bash
cd backend && uv run ruff format . && uv run ruff check . && uv run pytest -q
cd ../frontend && bun run format && bun run lint && bun test && bun run build
```
Expected: everything green. Fix anything that isn't before proceeding.

- [ ] **Step 4: Commit, then hand off to the ceremony**

```bash
git add Status.md .github/workflows/deploy-backend.yml
git commit -m "docs: phase 3 status + Inngest deployment notes"
```

Then invoke `Workflow({ name: 'finish-feature' })` — it composes scoped tests → pre-push gates (both stacks changed: it detects Next.js AND Python) → pr-quality-gate adversarial review → PR into `v2` → ci-green-loop. Check `success` / `needs_user_input` on the result and relay to Karthik. **Do not merge** — per standing instruction, nothing merges until Karthik says so.

---

## Self-Review (performed at plan time)

- **Spec coverage:** 3a → Tasks 7–10 (+ existing PATCH/compliance endpoints reused, Pro gating carried via Task 1's ranked gate). 3b → Task 11. 3c → Task 12. 3d → Tasks 13–14 (blocks + standard sizes; "renders + CAD as co-equal tabs" already exists since Phase 2 — tabs `plan`/`render` are siblings; no work needed). 3e → Tasks 2–6 (backend read path, jobs, Inngest, frontend progress, render pipeline second consumer). Phase-0 §5 sequencing/risk notes → Global Constraints + task order. Firm-tier follow-up bug from Status.md → Task 1.
- **Deliberate deviations from the phase-0 text:** (1) Inngest **Realtime** replaced by 2s job polling for day one — the plan document itself names SWR-style polling as the sanctioned fallback; no realtime dep exists in the frontend and the Python SDK's realtime publish story is immature. Revisit post-launch. (2) Phase-0's "GET /projects/{id}/layouts SWR polling fallback" is implemented as the primary read endpoint (Task 2) plus job polling (Task 5) — same observable behaviour. (3) `--cpu-always-allocated` not needed: the Inngest executor invokes `/api/inngest` as a normal HTTP request, so the solve gets full request-lifecycle CPU (the "cleaner" option the phase-0 plan itself preferred).
- **Type consistency check:** `JobOut` fields = model columns = `JobStatus` (frontend, subset). `RectMM` used by Tasks 7/8/9. `tier_at_least` signature identical at all call sites. Event payload keys (`job_id`, `project_id`, `layout_id`) consistent between senders (Task 4/6 endpoints) and consumers (`layout_generate`/`render_generate`).
- **Known soft spots (flagged, not hidden):** test seeding helpers are referenced from existing test modules rather than reprinted (`test_team_and_plan_access.py`, `test_layout_persistence.py`, `test_dxf_export.py`) — implementers copy the real helpers, which is safer than this plan guessing `User`/`Project` column requirements. `Opening` dataclass field names (Task 14 Step 3) and the exact `form` field names (Task 12 Step 4) are verified in-task with the greps given. The `applyResize` corner convention is documented in-code; its tests are declared authoritative-to-the-convention.
```
