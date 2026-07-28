# SaaS Scalability + GCP Cost Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut PlanForge's recurring GCP bill to ~$0 and remove the six structural limits that stop the backend serving more than ~3 concurrent users.

**Architecture:** Two phases. **Phase B** (first — it saves money on day one) fixes a no-op Artifact Registry cleanup policy, shrinks the backend image, and adds CI layer caching. **Phase A** then removes the scalability limits: offload CP-SAT from the asyncio event loop, use Neon's pooled endpoint, add rate limiting, move export/render artifacts to Cloudflare R2 with bounded render concurrency, add render quotas, and split the solver onto its own Cloud Run service.

**Tech Stack:** FastAPI, SQLAlchemy (async), OR-Tools CP-SAT, ReportLab, ezdxf, boto3 (new), Cloudflare R2, Google Cloud Run, Artifact Registry, GitHub Actions, Neon Postgres.

## Global Constraints

- **Branch:** `feat/saas-scalability`. Worktree: `/home/karthik/projects/PlanForge-saas`. Based on `origin/main` @ `7cc9932`.
- **File ownership is binding.** Obey `docs/plans/merge-coordination-2026-07-27.md`. A second agent session owns `backend/app/engine/{solver,plan_geometry,archetypes}.py` and has uncommitted work in them. **Never open those three files.**
- **Never edit `backend/app/engine/generator.py`.** The event-loop fix wraps its caller in `layout_store.py`, not the callee.
- Python ≥3.12, type hints mandatory on all functions, `uv` for all package management (`uv add`, `uv run`), Ruff for lint+format.
- **Never run `ruff format` on `*.json`** — it corrupts them.
- **No real secrets in any committed file**, including docs. Use placeholders like `<your-r2-access-key-id>`. R2 keys were leaked this way once before; the setup guide must use placeholders only.
- Tests run against in-memory SQLite (`backend/tests/conftest.py`). `backend/tests/conftest.py` is append-only.
- Run `uv run ruff format . && uv run ruff check .` before every commit.
- Commits use Conventional Commits and end with the trailer `Karthikeyan N <karthiknitt@gmail.com>`.
- Deferred, explicitly out of scope: `min-instances=1`, the FreeCAD DWG export worker, any VPS deployment.

---

## File Structure

| File | Responsibility | Status |
|---|---|---|
| `backend/Dockerfile` | Multi-stage build; venv built in builder, copied to slim runtime | Modify |
| `.github/workflows/deploy-backend.yml` | buildx + registry layer cache; new R2 env vars | Modify |
| `.github/workflows/deploy-backend-v2.yml` | Dead (v2 branch deleted 2026-07-18) | Delete |
| `backend/app/config/settings.py` | R2 + quota + delivery-mode config | Modify |
| `backend/app/db.py` | Pooled-endpoint detection + warning | Modify |
| `backend/app/services/layout_store.py` | `solve_layouts_async` — offloads CP-SAT via `to_thread` | Modify |
| `backend/app/middleware/rate_limit.py` | Token-bucket limiter keyed by user/IP | Create |
| `backend/app/services/storage.py` | `StorageBackend` protocol, `R2Storage`, `NullStorage` | Create |
| `backend/app/api/routes/export.py` | Export semaphore + R2 delivery | Modify |
| `backend/app/services/render_runner.py` | Daily render quota; image bytes to R2 | Modify |
| `backend/app/models/render.py` | `image_key` column (R2 object key) | Modify |
| `backend/app/main.py` | Register rate-limit middleware (append-only) | Modify |
| `docs/guides/cloudflare-r2-setup.md` | Karthik's manual R2 + GitHub setup runbook | Create |

---

## Model Tier Assignment

| Task | Tier | Why |
|---|---|---|
| B1 Artifact Registry policy | **haiku** | Mechanical: run gcloud, read output |
| B2 Multi-stage Dockerfile | **sonnet** | Standard Docker refactor, verified by build |
| B3 CI layer caching | **sonnet** | YAML + buildx flags |
| B4 Remove dead v2 | **haiku** | Deletion + verification |
| A1 CP-SAT offload | **opus** | Concurrency correctness; the highest-value change |
| A2 Neon pooled endpoint | **haiku** | One helper + a warning log |
| A3 Rate limiting | **sonnet** | Middleware with careful test design |
| A4 R2 storage layer | **opus** | New subsystem, protocol design, auth edge cases |
| A5 Render quota + R2 blobs | **sonnet** | Extends A4's seam; schema migration |
| A6 Solver service split | **opus** | Infra topology + Inngest app_id hazard |

---

# PHASE B — Cost (do first)

### Task B1: Fix the no-op Artifact Registry cleanup policy

The repo has a `keep-recent-5` policy with `action: KEEP` and **no DELETE policy**. In Artifact Registry, KEEP policies only exempt artifacts from DELETE policies — with no DELETE policy, nothing is ever deleted. Live state: **8,493 MB across 51 versions**, ~$0.80/month, growing ~166 MB per deploy.

`keepCount` applies **per package**, so `api`, `api-v2`, and `structapi` each keep their own 2 most recent. All three live Cloud Run images survive.

**Files:**
- Create: `infra/artifact-registry-cleanup.json`

**Interfaces:**
- Produces: a committed, reviewable copy of the policy applied to `planforge-backend` in `us-central1`.

- [ ] **Step 1: Record the current state as a baseline**

```bash
gcloud artifacts repositories describe planforge-backend \
  --location=us-central1 --format="value(sizeBytes,name)"
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/thermal-well-451906-b0/planforge-backend \
  --format="value(version)" | wc -l
```

Expected: ~8493 MB, 51 versions. Write both numbers into the commit message later.

- [ ] **Step 2: Write the policy file**

```bash
mkdir -p infra
cat > infra/artifact-registry-cleanup.json <<'EOF'
[
  {
    "name": "keep-recent-2",
    "action": {"type": "Keep"},
    "mostRecentVersions": {"keepCount": 2}
  },
  {
    "name": "delete-stale",
    "action": {"type": "Delete"},
    "condition": {"olderThan": "1d"}
  }
]
EOF
```

`olderThan: 1d` is deliberate, not a typo. The oldest image is only 24 days old, so a conventional `30d` condition would delete **nothing**. Keep policies take precedence over delete policies, so the 2 newest per package are safe regardless of age.

- [ ] **Step 3: Dry run — this is the real verification, do not skip it**

```bash
gcloud artifacts repositories set-cleanup-policies planforge-backend \
  --location=us-central1 \
  --policy=infra/artifact-registry-cleanup.json \
  --dry-run
```

Then wait for the dry-run evaluation and read what *would* be deleted:

```bash
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/thermal-well-451906-b0/planforge-backend \
  --include-tags --format="table(version,createTime,tags)"
```

**STOP and show the list to Karthik before Step 4.** Confirm these three tags are NOT on the delete list:
- `api:7cc99324e8999922f279c32379536160f5a22f29` (live prod)
- `api-v2:68ddb2ef73173dc41d429410c095316b840952fb` (live v2)
- the current `structapi` image

- [ ] **Step 4: Apply for real (only after Karthik approves the dry-run output)**

```bash
gcloud artifacts repositories set-cleanup-policies planforge-backend \
  --location=us-central1 \
  --policy=infra/artifact-registry-cleanup.json \
  --no-dry-run
```

- [ ] **Step 5: Verify deletion actually happened**

Cleanup runs asynchronously — allow up to 24h, then:

```bash
gcloud artifacts repositories describe planforge-backend \
  --location=us-central1 --format="value(sizeBytes)"
```

Expected: well under 1,500 MB. **Verify by observing the size drop, not by reading the policy back** — reading it back is exactly what failed to catch the original bug.

- [ ] **Step 6: Commit**

```bash
git add infra/artifact-registry-cleanup.json
git commit -m "fix(infra): add DELETE policy so Artifact Registry cleanup actually deletes

The existing keep-recent-5 policy was KEEP-only. Artifact Registry KEEP
policies only exempt artifacts from DELETE policies; with no DELETE policy
defined, nothing was ever removed. Repo had grown to 8493 MB / 51 versions
since 2026-07-03 (~\$0.80/mo, +166 MB per deploy).

keepCount=2 applies per package, so api, api-v2 and structapi each retain
their live image plus one rollback target.

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task B2: Multi-stage Dockerfile

Current image is ~166 MB per version and ships `uv`, `pip`, and build artifacts into the runtime.

**Files:**
- Modify: `backend/Dockerfile`

**Interfaces:**
- Produces: an image that runs `uvicorn app.main:app` identically, from `/app/.venv`.

- [ ] **Step 1: Record the current image size**

```bash
cd /home/karthik/projects/PlanForge-saas
docker build -t planforge-backend:before ./backend
docker images planforge-backend:before --format "{{.Size}}"
```

- [ ] **Step 2: Rewrite the Dockerfile**

```dockerfile
# ── builder ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project

# ── runtime ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY app/ ./app/

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
```

Two things changed beyond staging: `uv` now comes from its official image instead of `pip install uv` (removes pip's own footprint from the layer), and `--no-install-project` stops the app source being baked into the dependency layer — which is what makes the dependency layer cacheable in Task B3.

- [ ] **Step 3: Build and compare**

```bash
docker build -t planforge-backend:after ./backend
docker images planforge-backend:after --format "{{.Size}}"
```

Expected: 30–40% smaller than `:before`.

- [ ] **Step 4: Verify the app actually starts**

```bash
docker run --rm -d --name pf-smoke -p 8081:8080 \
  -e INTERNAL_AUTH_SECRET=test-secret-for-ci-0123456789abcdefgh \
  -e DATABASE_URL=sqlite+aiosqlite:///:memory: \
  planforge-backend:after
sleep 8
curl -fsS http://localhost:8081/health && echo " OK"
docker rm -f pf-smoke
```

Expected: a 200 from `/health`. If the container exits, `docker logs pf-smoke` before debugging.

- [ ] **Step 5: Commit**

```bash
git add backend/Dockerfile
git commit -m "perf(docker): multi-stage build, drop uv/pip from runtime image

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task B3: Registry-backed layer caching in CI

Root cause of 8.5 GB: GitHub Actions runners have no Docker layer cache, so `uv sync` re-executes every run and produces a byte-different dependency layer. No layer is ever shared between versions, so each deploy stores a **full** image rather than a small delta.

**Files:**
- Modify: `.github/workflows/deploy-backend.yml:35-40`

- [ ] **Step 1: Replace the build-and-push step**

Replace the existing `Build and push image` step with:

```yaml
      - uses: docker/setup-buildx-action@v3

      - name: Build and push image
        working-directory: backend
        run: |
          IMAGE="${{ vars.GCP_REGION }}-docker.pkg.dev/${{ vars.GCP_PROJECT_ID }}/planforge-backend/api:${{ github.sha }}"
          CACHE="${{ vars.GCP_REGION }}-docker.pkg.dev/${{ vars.GCP_PROJECT_ID }}/planforge-backend/api:buildcache"
          docker buildx build \
            --cache-from "type=registry,ref=$CACHE" \
            --cache-to   "type=registry,ref=$CACHE,mode=max" \
            --tag "$IMAGE" \
            --push \
            .
          echo "IMAGE=$IMAGE" >> "$GITHUB_ENV"
```

- [ ] **Step 2: Guard the cache tag against the cleanup policy**

The `:buildcache` tag would be deleted by B1's `olderThan: 1d` rule as soon as it is a day old, silently killing the cache. Add an exemption to `infra/artifact-registry-cleanup.json` — insert this object **before** `delete-stale`:

```json
  {
    "name": "keep-buildcache",
    "action": {"type": "Keep"},
    "condition": {"tagState": "TAGGED", "tagPrefixes": ["buildcache"]}
  },
```

Then re-apply:

```bash
gcloud artifacts repositories set-cleanup-policies planforge-backend \
  --location=us-central1 \
  --policy=infra/artifact-registry-cleanup.json --no-dry-run
```

- [ ] **Step 3: Verify on the next deploy**

After the first post-merge deploy, the build log should show `importing cache manifest`. On the second deploy, the `uv sync` step should report `CACHED`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy-backend.yml infra/artifact-registry-cleanup.json
git commit -m "perf(ci): registry-backed buildx layer cache for backend image

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task B4: Remove the dead v2 deployment

The `v2` branch was deleted on 2026-07-18, but `deploy-backend-v2.yml` still exists (and can never fire), and the `planforge-backend-v2` Cloud Run service is still live on a 2026-07-11 image.

**Files:**
- Delete: `.github/workflows/deploy-backend-v2.yml`

- [ ] **Step 1: Confirm the branch really is gone**

```bash
git ls-remote --heads origin v2
```

Expected: empty output.

- [ ] **Step 2: Delete the workflow**

```bash
git rm .github/workflows/deploy-backend-v2.yml
```

- [ ] **Step 3: Ask Karthik before deleting the Cloud Run service**

This is irreversible and outward-facing. Do **not** run it unprompted — present it and wait:

```bash
gcloud run services delete planforge-backend-v2 --region=us-central1
```

Idle cost is $0 (`minScale=0`), so there is no urgency; the only saving is registry space once its images age out under B1.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(ci): remove dead v2 deploy workflow (branch deleted 2026-07-18)

Karthikeyan N <karthiknitt@gmail.com>"
```

---

# PHASE A — Scalability

### Task A1: Offload CP-SAT from the asyncio event loop

`grep -rn "to_thread\|run_in_executor" backend/app` returns nothing. `solver.py` runs `SOLVE_TIME_S = 14.0` per archetype × 3 archetypes, single-threaded, **directly on the event loop**. While one layout solves, that worker serves nothing — not health checks, not login. With `--concurrency=4`, three other requests sit in the queue.

CP-SAT is blocking C++ that releases the GIL, so `to_thread` genuinely restores concurrency here.

**Files:**
- Modify: `backend/app/services/layout_store.py`
- Test: `backend/tests/test_solve_offload.py` (create)

**Interfaces:**
- Produces: `async def solve_layouts_async(cfg: PlotConfig) -> list[Layout]` in `app.services.layout_store`.
- **Does NOT touch** `generator.py`, `solver.py` — see the coordination contract.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_solve_offload.py`:

```python
"""The CP-SAT solve must not block the asyncio event loop.

A blocked loop means one user's 40s generate freezes health checks, login and
every other in-flight request on that Cloud Run instance.
"""

import asyncio
import time

import pytest

from app.services import layout_store


@pytest.mark.asyncio
async def test_solve_layouts_async_does_not_block_event_loop(monkeypatch):
    def slow_generate(cfg):
        time.sleep(0.5)  # stands in for a real CP-SAT solve
        return ["layout"]

    monkeypatch.setattr(layout_store, "generate", slow_generate)

    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(20):
            await asyncio.sleep(0.02)
            ticks += 1

    result, _ = await asyncio.gather(
        layout_store.solve_layouts_async(object()),
        ticker(),
    )

    assert result == ["layout"]
    # With the solve on the loop, the ticker cannot advance at all during the
    # 0.5s sleep. Off-loop it should complete nearly all 20 ticks.
    assert ticks >= 15, f"event loop was blocked during solve (ticks={ticks})"
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd /home/karthik/projects/PlanForge-saas/backend
uv run pytest tests/test_solve_offload.py -v
```

Expected: FAIL with `AttributeError: module 'app.services.layout_store' has no attribute 'solve_layouts_async'`.

- [ ] **Step 3: Implement**

In `backend/app/services/layout_store.py`, add `import asyncio` to the stdlib imports at the top, then add this function immediately above `regenerate_and_store`:

```python
async def solve_layouts_async(cfg: PlotConfig) -> list[Layout]:
    """Run the CP-SAT solve off the event loop.

    CP-SAT is blocking C++ (it releases the GIL). Called inline it pins the
    whole worker for the duration of a ~40s solve, so no other request on this
    instance is served. Wrapping the caller — not solver.py — keeps this change
    off the concurrently-edited geometry engine.
    """
    return await asyncio.to_thread(generate, cfg)
```

Then in `regenerate_and_store`, change:

```python
    layouts = generate(cfg)
```

to:

```python
    layouts = await solve_layouts_async(cfg)
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
uv run pytest tests/test_solve_offload.py -v
```

- [ ] **Step 5: Run the regression suite around generation**

```bash
uv run pytest tests/test_api_e2e.py tests/test_agent_no_solve.py -q
```

Expected: all pass. `to_thread` changes scheduling, not results.

- [ ] **Step 6: Commit**

```bash
uv run ruff format . && uv run ruff check .
git add backend/app/services/layout_store.py backend/tests/test_solve_offload.py
git commit -m "perf(api): run CP-SAT solve off the event loop via asyncio.to_thread

A 3-archetype solve blocks for up to 42s. Run inline on the loop it froze
every other request on the instance, including health checks. Wrapped at the
layout_store call site rather than in solver.py, which another branch owns.

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task A2: Detect a non-pooled Neon endpoint

Prod runs `DB_USE_NULLPOOL=true` (`deploy-backend.yml:64`), so every request opens a fresh TCP+TLS connection to Neon — 30–80 ms each, and connection *count* becomes the ceiling. NullPool is correct for scale-to-zero; the fix is pointing it at Neon's PgBouncer endpoint (the `-pooler` hostname).

The env change is Karthik's; the code change makes a wrong value loud instead of silent.

**Files:**
- Modify: `backend/app/db.py`
- Test: `backend/tests/test_db_pooling.py` (create)

**Interfaces:**
- Produces: `def is_pooled_url(url: str) -> bool` in `app.db`.

- [ ] **Step 1: Write the failing test**

```python
"""NullPool + a direct (non-pooler) Neon endpoint means a fresh TLS handshake
per request and a hard ceiling on Neon connections."""

from app.db import is_pooled_url


def test_pooler_hostname_is_detected():
    assert is_pooled_url(
        "postgresql+asyncpg://u:p@ep-x-123-pooler.us-east-2.aws.neon.tech/db"
    )


def test_direct_hostname_is_not_pooled():
    assert not is_pooled_url(
        "postgresql+asyncpg://u:p@ep-x-123.us-east-2.aws.neon.tech/db"
    )


def test_local_dev_url_is_not_pooled():
    assert not is_pooled_url("postgresql+asyncpg://planforge@localhost:5432/planforge")
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
uv run pytest tests/test_db_pooling.py -v
```

Expected: FAIL with `ImportError: cannot import name 'is_pooled_url'`.

- [ ] **Step 3: Implement**

In `backend/app/db.py`, add after the imports:

```python
import logging

logger = logging.getLogger(__name__)


def is_pooled_url(url: str) -> bool:
    """True if the URL points at Neon's PgBouncer endpoint."""
    return "-pooler." in url
```

And after the `engine = create_async_engine(...)` block:

```python
if settings.db_use_nullpool and not is_pooled_url(settings.database_url):
    logger.warning(
        "DB_USE_NULLPOOL is on but DATABASE_URL is not Neon's pooled endpoint. "
        "Every request will open a new TLS connection and Neon's connection "
        "cap becomes the scaling ceiling. Use the '-pooler' hostname."
    )
```

- [ ] **Step 4: Run the test — expect PASS**

- [ ] **Step 5: Write the operator note**

Append to `docs/guides/cloudflare-r2-setup.md` (created in Task A4) under a `## Neon pooled endpoint` heading, or create `docs/guides/neon-pooling.md` if A4 has not run yet:

```markdown
## Neon pooled endpoint

In the Neon console, project `planforge` (`plain-brook-17631682`), copy the
**Pooled connection** string — its host contains `-pooler`. Then:

    gh secret set NEON_DATABASE_URL --body '<pooled-connection-string>'

Re-deploy the backend. Check Cloud Run logs for the "not Neon's pooled
endpoint" warning — its absence confirms the change took effect.
```

- [ ] **Step 6: Commit**

```bash
uv run ruff format . && uv run ruff check .
git add backend/app/db.py backend/tests/test_db_pooling.py docs/guides/
git commit -m "feat(db): warn when NullPool runs against a non-pooled Neon endpoint

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task A3: Per-user and per-IP rate limiting

With a hard ceiling of 12 in-flight requests (`max-instances=3 × concurrency=4`), one retry loop can deny service to every user. **Use in-memory counters — do not introduce Memorystore/Redis**, which is ~$35/mo always-on and would become the largest line on the GCP bill.

With `max-instances=3` the per-instance counter is approximate (a user could get up to 3× the limit). That is an accepted trade-off: the goal is blocking runaway loops, not precise billing.

**Files:**
- Create: `backend/app/middleware/__init__.py`, `backend/app/middleware/rate_limit.py`
- Modify: `backend/app/main.py` (append-only), `backend/app/config/settings.py`
- Test: `backend/tests/test_rate_limit.py` (create)

**Interfaces:**
- Produces: `class RateLimitMiddleware(BaseHTTPMiddleware)` and `class TokenBucket`.

- [ ] **Step 1: Write the failing test**

```python
"""Expensive endpoints must shed load before the instance does."""

import pytest

from app.middleware.rate_limit import TokenBucket


def test_bucket_allows_up_to_capacity():
    b = TokenBucket(capacity=3, refill_per_second=0.0)
    assert b.take(now=0.0)
    assert b.take(now=0.0)
    assert b.take(now=0.0)
    assert not b.take(now=0.0)


def test_bucket_refills_over_time():
    b = TokenBucket(capacity=2, refill_per_second=1.0)
    assert b.take(now=0.0)
    assert b.take(now=0.0)
    assert not b.take(now=0.0)
    assert b.take(now=1.0)          # one token back after 1s
    assert not b.take(now=1.0)


def test_bucket_never_exceeds_capacity():
    b = TokenBucket(capacity=2, refill_per_second=100.0)
    b.take(now=0.0)
    assert b.take(now=1000.0)
    assert b.take(now=1000.0)
    assert not b.take(now=1000.0)   # capped at capacity, not 100k tokens


@pytest.mark.asyncio
async def test_generate_endpoint_returns_429_when_exhausted(client):
    headers = {"X-Test-User-Id": "rl-user"}
    codes = [
        (await client.post("/projects/does-not-exist/layouts", headers=headers)).status_code
        for _ in range(12)
    ]
    assert 429 in codes, f"expected a 429 among {codes}"
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
uv run pytest tests/test_rate_limit.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.middleware'`.

- [ ] **Step 3: Implement the bucket and middleware**

Create `backend/app/middleware/__init__.py` (empty file), then `backend/app/middleware/rate_limit.py`:

```python
"""In-process token-bucket rate limiting for expensive endpoints.

Deliberately in-memory: Memorystore/Redis is ~$35/mo always-on, which would
exceed the entire rest of this project's GCP bill. With max-instances=3 the
effective limit is up to 3x the configured value; that is fine for stopping
runaway clients, which is the actual threat.
"""

import time
from dataclasses import dataclass, field

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# (method, path-prefix) pairs that cost real CPU or real money.
LIMITED_PREFIXES: tuple[str, ...] = (
    "/layouts",
    "/export",
    "/render",
    "/generation-jobs",
    "/render-jobs",
)


@dataclass
class TokenBucket:
    capacity: int
    refill_per_second: float
    tokens: float = field(default=None)  # type: ignore[assignment]
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if self.tokens is None:
            self.tokens = float(self.capacity)

    def take(self, now: float) -> bool:
        elapsed = max(0.0, now - self.updated_at)
        self.tokens = min(
            float(self.capacity), self.tokens + elapsed * self.refill_per_second
        )
        self.updated_at = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, capacity: int = 10, refill_per_second: float = 0.2) -> None:
        super().__init__(app)
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._buckets: dict[str, TokenBucket] = {}

    def _key(self, request: Request) -> str:
        user = request.headers.get("X-Test-User-Id") or request.headers.get(
            "X-User-Id"
        )
        if user:
            return f"u:{user}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    async def dispatch(self, request: Request, call_next):
        if not any(p in request.url.path for p in LIMITED_PREFIXES):
            return await call_next(request)

        key = self._key(request)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self.capacity, self.refill_per_second)
            self._buckets[key] = bucket

        if not bucket.take(now=time.monotonic()):
            return JSONResponse(
                status_code=429,
                content={
                    "code": "rate_limited",
                    "detail": "Too many requests.",
                    "help": "Wait a few seconds and retry.",
                },
                headers={"Retry-After": "5"},
            )
        return await call_next(request)
```

- [ ] **Step 4: Register it (append-only edit to a shared file)**

In `backend/app/config/settings.py`, add to the `Settings` class:

```python
    # Rate limiting — in-process token bucket (see app/middleware/rate_limit.py)
    rate_limit_capacity: int = 10
    rate_limit_refill_per_second: float = 0.2
```

In `backend/app/main.py`, add the import next to the other `app.` imports and register the middleware **after** the existing `CORSMiddleware` registration — do not reorder existing lines:

```python
from app.middleware.rate_limit import RateLimitMiddleware

app.add_middleware(
    RateLimitMiddleware,
    capacity=settings.rate_limit_capacity,
    refill_per_second=settings.rate_limit_refill_per_second,
)
```

Middleware runs in reverse registration order, so registering after CORS means the limiter runs *before* CORS on the way in — a 429 would miss CORS headers. If the browser reports a CORS error on 429, move this registration above the CORS one.

- [ ] **Step 5: Run the tests — expect PASS**

```bash
uv run pytest tests/test_rate_limit.py -v
```

- [ ] **Step 6: Run the full suite — middleware is global and can break unrelated tests**

```bash
uv run pytest -q
```

Expected: no new failures. If existing tests trip the limiter, raise `capacity` in `conftest.py` via env rather than weakening the production default.

- [ ] **Step 7: Commit**

```bash
uv run ruff format . && uv run ruff check .
git add backend/app/middleware backend/app/main.py backend/app/config/settings.py backend/tests/test_rate_limit.py
git commit -m "feat(api): in-process token-bucket rate limiting on expensive endpoints

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task A4: Cloudflare R2 storage layer + bounded export concurrency

Two distinct problems, one task because they share the seam:

1. **OOM:** ReportLab builds whole PDFs in memory on a 1 GiB instance serving 4 concurrent requests. An OOM kills the *instance*, dropping every in-flight request. Spooling to `/tmp` does **not** help — Cloud Run's filesystem is RAM-backed.
2. **Waste:** every export re-renders from scratch, even for unchanged geometry.

Delivery mode ships as `inline` (byte-identical to today's API contract) with R2 caching active. Flipping to `redirect` is a one-line config change once the frontend is verified — deliberately reversible.

**Files:**
- Create: `backend/app/services/storage.py`, `docs/guides/cloudflare-r2-setup.md`
- Modify: `backend/app/config/settings.py`, `backend/app/api/routes/export.py`, `backend/pyproject.toml`
- Test: `backend/tests/test_storage.py`, `backend/tests/test_export_delivery.py` (create)

**Interfaces:**
- Produces: `StorageBackend` protocol with `async put_bytes(key, data, content_type) -> None`, `async get_bytes(key) -> bytes | None`, `def signed_url(key, ttl_seconds) -> str`; `R2Storage`; `NullStorage`; `get_storage() -> StorageBackend`.
- Consumed by Task A5.

- [ ] **Step 1: Add the dependency**

```bash
cd /home/karthik/projects/PlanForge-saas/backend
uv add boto3
```

R2 is S3-API compatible, so boto3 works unchanged with `region_name="auto"` and a custom endpoint.

- [ ] **Step 2: Write the failing storage test**

Create `backend/tests/test_storage.py`:

```python
"""Storage seam: R2 when configured, a no-op backend when not.

The no-op path matters — CI and local dev have no R2 credentials and must
still pass without network access.
"""

import pytest

from app.services.storage import NullStorage, R2Storage, build_storage


class _Settings:
    def __init__(self, **kw):
        self.r2_account_id = kw.get("account", "")
        self.r2_access_key_id = kw.get("key", "")
        self.r2_secret_access_key = kw.get("secret", "")
        self.r2_bucket = kw.get("bucket", "")


def test_unconfigured_settings_yield_null_storage():
    assert isinstance(build_storage(_Settings()), NullStorage)


def test_partial_config_yields_null_storage():
    s = _Settings(account="abc", key="k")  # missing secret + bucket
    assert isinstance(build_storage(s), NullStorage)


def test_full_config_yields_r2_storage():
    s = _Settings(account="abc", key="k", secret="s", bucket="b")
    assert isinstance(build_storage(s), R2Storage)


@pytest.mark.asyncio
async def test_null_storage_is_a_safe_no_op():
    st = NullStorage()
    await st.put_bytes("k", b"data", "application/pdf")
    assert await st.get_bytes("k") is None
    assert st.signed_url("k", 900) == ""


def test_r2_endpoint_url_is_account_scoped():
    s = _Settings(account="abc123", key="k", secret="s", bucket="b")
    assert build_storage(s).endpoint_url == "https://abc123.r2.cloudflarestorage.com"
```

- [ ] **Step 3: Run it and confirm it fails**

```bash
uv run pytest tests/test_storage.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.storage'`.

- [ ] **Step 4: Implement the storage layer**

Create `backend/app/services/storage.py`:

```python
"""Object storage for generated artifacts (PDF, DXF, XLSX, AI renders).

Cloudflare R2 rather than GCS: 10 GB free, and — the reason that matters at
consumer scale — zero egress fees. R2 speaks the S3 API, so boto3 works with
region_name='auto' and an account-scoped endpoint.

Unconfigured deployments get NullStorage so CI and local dev need no
credentials and no network.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get_bytes(self, key: str) -> bytes | None: ...
    def signed_url(self, key: str, ttl_seconds: int = 900) -> str: ...


class NullStorage:
    """No-op backend used when R2 is not configured."""

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        return None

    async def get_bytes(self, key: str) -> bytes | None:
        return None

    def signed_url(self, key: str, ttl_seconds: int = 900) -> str:
        return ""


class R2Storage:
    def __init__(
        self, account_id: str, access_key_id: str, secret_access_key: str, bucket: str
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
                region_name="auto",
                config=Config(signature_version="s3v4"),
            )
        return self._client

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        def _put() -> None:
            self._get_client().put_object(
                Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
            )

        await asyncio.to_thread(_put)

    async def get_bytes(self, key: str) -> bytes | None:
        def _get() -> bytes | None:
            client = self._get_client()
            try:
                resp = client.get_object(Bucket=self.bucket, Key=key)
                return resp["Body"].read()
            except client.exceptions.NoSuchKey:
                return None

        return await asyncio.to_thread(_get)

    def signed_url(self, key: str, ttl_seconds: int = 900) -> str:
        return self._get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )


def build_storage(cfg) -> StorageBackend:
    required = (
        cfg.r2_account_id,
        cfg.r2_access_key_id,
        cfg.r2_secret_access_key,
        cfg.r2_bucket,
    )
    if not all(required):
        logger.info("R2 not configured — artifacts stream inline, nothing is cached.")
        return NullStorage()
    return R2Storage(*required)


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        from app.config.settings import settings

        _storage = build_storage(settings)
    return _storage
```

- [ ] **Step 5: Add the settings**

In `backend/app/config/settings.py`, add to `Settings`:

```python
    # Cloudflare R2 artifact storage — all four empty => NullStorage (no-op).
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    # "inline" streams bytes (today's contract). "redirect" 307s to a signed
    # R2 URL — flip only after verifying the frontend download path.
    export_delivery_mode: str = "inline"
    # Concurrent PDF/DXF renders per instance. ReportLab builds in memory and
    # Cloud Run's filesystem is RAM-backed, so this is the real OOM guard.
    export_max_concurrency: int = 2
```

- [ ] **Step 6: Run the storage test — expect PASS**

```bash
uv run pytest tests/test_storage.py -v
```

- [ ] **Step 7: Write the failing export-delivery test**

Create `backend/tests/test_export_delivery.py`:

```python
"""Exports must be concurrency-bounded and cacheable."""

import asyncio

import pytest

from app.api.routes import export as export_routes


@pytest.mark.asyncio
async def test_export_semaphore_bounds_concurrency(monkeypatch):
    monkeypatch.setattr(export_routes, "_EXPORT_SEM", asyncio.Semaphore(2))
    peak = 0
    live = 0

    async def worker():
        nonlocal peak, live
        async with export_routes._EXPORT_SEM:
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.05)
            live -= 1

    await asyncio.gather(*(worker() for _ in range(8)))
    assert peak <= 2, f"exceeded the export concurrency cap (peak={peak})"


def test_artifact_key_is_stable_and_content_addressed():
    k1 = export_routes._artifact_key("proj1", "A", "pdf", b"same-bytes")
    k2 = export_routes._artifact_key("proj1", "A", "pdf", b"same-bytes")
    k3 = export_routes._artifact_key("proj1", "A", "pdf", b"other-bytes")
    assert k1 == k2
    assert k1 != k3
    assert k1.startswith("exports/proj1/A/") and k1.endswith(".pdf")
```

- [ ] **Step 8: Run it and confirm it fails**

Expected: FAIL with `AttributeError: ... has no attribute '_EXPORT_SEM'`.

- [ ] **Step 9: Implement in `export.py`**

Add near the top of `backend/app/api/routes/export.py`, after the existing imports:

```python
import asyncio
import hashlib

from fastapi.responses import RedirectResponse

from app.config.settings import settings
from app.services.storage import get_storage

# ReportLab builds the whole document in memory; Cloud Run's filesystem is
# RAM-backed so spooling to /tmp would not help. Bounding concurrency is the
# only thing that actually stops an OOM taking the instance down.
_EXPORT_SEM = asyncio.Semaphore(settings.export_max_concurrency)


def _artifact_key(project_id: str, layout_id: str, ext: str, content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()[:16]
    return f"exports/{project_id}/{layout_id}/{digest}.{ext}"


async def _deliver(
    content: bytes, media_type: str, filename: str, key: str
) -> Response:
    """Persist to R2 (best-effort) and return the artifact to the caller."""
    storage = get_storage()
    try:
        await storage.put_bytes(key, content, media_type)
    except Exception:
        logger.warning("R2 upload failed for %s — serving inline", key, exc_info=True)

    if settings.export_delivery_mode == "redirect":
        url = storage.signed_url(key)
        if url:
            return RedirectResponse(url=url, status_code=307)

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

Add a module logger if one is not already present:

```python
import logging

logger = logging.getLogger(__name__)
```

Then convert each of the **five** export endpoints. For `export_pdf` (currently `export.py:61-100`), wrap the render and replace the `return Response(...)`:

```python
    async with _EXPORT_SEM:
        pdf_bytes = render_pdf(
            project.name,
            layout,
            cfg,
            project.num_bedrooms,
            annotations=annotations or None,
            structural_design=design,
            watermark_preliminary=True,
        )

    filename = f"planforge-{project_id}-layout-{layout_id}.pdf"
    return await _deliver(
        pdf_bytes,
        "application/pdf",
        filename,
        _artifact_key(project_id, layout_id, "pdf", pdf_bytes),
    )
```

Apply the same shape to the other four, using the matching extension and media type:

| Endpoint | ext | media_type |
|---|---|---|
| `export_structural_drawing_set` (~:108) | `pdf` | `application/pdf` |
| `export_approval_pdf` (~:247) | `pdf` | `application/pdf` |
| `export_dxf` (~:293) | `dxf` | `application/dxf` |
| `export_boq` / `_boq_excel_response` (~:793) | `xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |

- [ ] **Step 10: Run both test files — expect PASS**

```bash
uv run pytest tests/test_storage.py tests/test_export_delivery.py -v
```

- [ ] **Step 11: Run the export regression suite**

```bash
uv run pytest tests/ -q -k "export or pdf or dxf or boq"
```

Expected: all pass. With `export_delivery_mode="inline"` (the default) and no R2 configured, responses are byte-identical to before.

- [ ] **Step 12: Wire the secrets into deployment**

In `.github/workflows/deploy-backend.yml`, add to the `env_vars:` block (append at the end, do not reorder):

```yaml
            R2_ACCOUNT_ID=${{ secrets.R2_ACCOUNT_ID }}
            R2_ACCESS_KEY_ID=${{ secrets.R2_ACCESS_KEY_ID }}
            R2_SECRET_ACCESS_KEY=${{ secrets.R2_SECRET_ACCESS_KEY }}
            R2_BUCKET=${{ secrets.R2_BUCKET }}
```

- [ ] **Step 13: Write the R2 setup guide**

Create `docs/guides/cloudflare-r2-setup.md` with the content specified in **Appendix A** of this plan. **Placeholders only — no real keys.**

- [ ] **Step 14: Commit**

```bash
uv run ruff format . && uv run ruff check .
git add backend/app/services/storage.py backend/app/api/routes/export.py \
        backend/app/config/settings.py backend/pyproject.toml backend/uv.lock \
        backend/tests/test_storage.py backend/tests/test_export_delivery.py \
        .github/workflows/deploy-backend.yml docs/guides/cloudflare-r2-setup.md
git commit -m "feat(export): R2 artifact storage + bounded export concurrency

ReportLab builds PDFs in memory on a 1GiB instance serving 4 concurrent
requests; an OOM kills the instance and every in-flight request with it.
Cloud Run's filesystem is RAM-backed so spooling to /tmp is not a fix --
bound concurrency instead. Artifacts are content-addressed into R2 (10GB
free, zero egress). Delivery stays inline by default; redirect mode is a
config flip once the frontend download path is verified.

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task A5: Render quota + move render blobs to R2

A geometry-hash render cache **already exists** (`render_runner.py:140-151`, `LayoutRender.layout_hash`) — do not rebuild it. Two gaps remain:

1. **No quota.** A free-tier user hammering render bills you directly on OpenRouter `gpt-image-1`. This is the only genuinely unbounded variable cost in the system.
2. **`image_png` is a `LargeBinary` in Neon** (`models/render.py:37`). Multi-MB PNGs in Postgres bloat storage, slow backups, and consume the Neon tier. They belong in R2.

**Files:**
- Modify: `backend/app/services/render_runner.py`, `backend/app/models/render.py`, `backend/app/config/settings.py`
- Test: `backend/tests/test_render_quota.py` (create)

**Interfaces:**
- Consumes: `get_storage()` from Task A4.
- Produces: `async def check_render_quota(user_id, db) -> None` (raises `HTTPException` 429).

- [ ] **Step 1: Write the failing test**

```python
"""AI renders cost real money per call — cap them per user per day."""

import pytest
from fastapi import HTTPException

from app.services import render_runner


@pytest.mark.asyncio
async def test_quota_allows_under_limit(client, monkeypatch):
    monkeypatch.setattr(render_runner, "_daily_render_count", _fake_count(3))
    await render_runner.check_render_quota("u1", db=None, limit=10)


@pytest.mark.asyncio
async def test_quota_blocks_at_limit(client, monkeypatch):
    monkeypatch.setattr(render_runner, "_daily_render_count", _fake_count(10))
    with pytest.raises(HTTPException) as exc:
        await render_runner.check_render_quota("u1", db=None, limit=10)
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "render_quota_exceeded"


def _fake_count(n: int):
    async def _count(user_id, db):
        return n

    return _count
```

- [ ] **Step 2: Run it and confirm it fails**

Expected: FAIL with `AttributeError: ... has no attribute 'check_render_quota'`.

- [ ] **Step 3: Add the settings**

In `backend/app/config/settings.py`:

```python
    # AI renders bill per call — cap per user per rolling 24h.
    render_daily_quota: int = 20
```

- [ ] **Step 4: Implement the quota**

In `backend/app/services/render_runner.py`, add:

```python
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.render import LayoutRender


async def _daily_render_count(user_id: str, db) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    result = await db.execute(
        select(func.count())
        .select_from(LayoutRender)
        .join(Project, Project.id == LayoutRender.project_id)
        .where(Project.user_id == user_id, LayoutRender.created_at >= since)
    )
    return int(result.scalar_one())


async def check_render_quota(user_id: str, db, limit: int | None = None) -> None:
    """Raise 429 if the user has burned their 24h AI-render allowance."""
    from app.config.settings import settings

    cap = settings.render_daily_quota if limit is None else limit
    used = await _daily_render_count(user_id, db)
    if used >= cap:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "render_quota_exceeded",
                "detail": f"Daily AI render limit reached ({cap}).",
                "help": "Renders reset 24h after each generation.",
            },
        )
```

Import `Project` from `app.models.project` alongside the existing imports.

Then call it in `perform_render`, **after** the cache lookup so cached hits never count against quota (they cost nothing):

```python
    if cached is not None:
        cached.was_cached = True
        return cached

    await check_render_quota(user_id, db)
```

- [ ] **Step 5: Run the test — expect PASS**

- [ ] **Step 6: Move render bytes to R2**

In `backend/app/models/render.py`, make `image_png` nullable and add the key column:

```python
    image_png: Mapped[bytes | None] = deferred(
        mapped_column(LargeBinary, nullable=True)
    )
    # R2 object key. Rows written before R2 was enabled keep image_png instead.
    image_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
```

`auto_migrate_missing_columns` in `app/main.py` adds the new column at startup — no Alembic step. Making `image_png` nullable is backward compatible; existing rows keep their bytes.

In `render_runner.py`, on write:

```python
    storage = get_storage()
    image_key = f"renders/{project_id}/{layout_hash}/{floor}.png"
    stored_remotely = False
    try:
        await storage.put_bytes(image_key, image_bytes, "image/png")
        stored_remotely = not isinstance(storage, NullStorage)
    except Exception:
        logger.warning("R2 render upload failed — falling back to DB blob", exc_info=True)

    row = LayoutRender(
        ...,
        image_png=None if stored_remotely else image_bytes,
        image_key=image_key if stored_remotely else None,
    )
```

And on read, prefer R2 and fall back to the column:

```python
async def render_bytes(row: LayoutRender) -> bytes | None:
    if row.image_key:
        data = await get_storage().get_bytes(row.image_key)
        if data is not None:
            return data
    return row.image_png
```

Update the `with_image=True` read path in `app/api/routes/render.py` to call `render_bytes(row)` instead of reading `row.image_png` directly.

- [ ] **Step 7: Run the render suite**

```bash
uv run pytest tests/ -q -k "render"
```

Expected: all pass. With `NullStorage` (CI), `stored_remotely` is False and bytes stay in the column exactly as today.

- [ ] **Step 8: Commit**

```bash
uv run ruff format . && uv run ruff check .
git add backend/app/services/render_runner.py backend/app/models/render.py \
        backend/app/api/routes/render.py backend/app/config/settings.py \
        backend/tests/test_render_quota.py
git commit -m "feat(render): per-user daily quota and R2-backed render blobs

Karthikeyan N <karthiknitt@gmail.com>"
```

---

### Task A6: Split the solver onto its own Cloud Run service

Even with A1, generation and API traffic share instances and a 3-instance ceiling. Splitting lets the API stay small and responsive while the solver scales on its own axis with more CPU per instance.

Cloud Run's free tier is **per project** (2M requests, 180k vCPU-s, 360k GiB-s/month), so two services draw from one pool — splitting does not double cost. At ~42 vCPU-s per generate, the free tier covers roughly **4,200 generations/month**.

⚠️ **Hazard:** `inngest_app_id` must differ per deployment. Two deployments sharing `"planforge"` previously caused jobs to silently no-op on the wrong deployment (fixed in PR #16). Repeating that mistake here would be a silent, hard-to-diagnose outage.

**Files:**
- Create: `.github/workflows/deploy-solver.yml`
- Modify: `.github/workflows/deploy-backend.yml`

- [ ] **Step 1: Confirm A1 is merged and deployed first**

A6 is worthless without A1 — a split service whose loop still blocks just moves the problem.

- [ ] **Step 2: Create the solver deploy workflow**

Copy `.github/workflows/deploy-backend.yml` to `.github/workflows/deploy-solver.yml` and change **only**:

```yaml
        with:
          service: planforge-solver
          region: ${{ vars.GCP_REGION }}
          image: ${{ env.IMAGE }}
          flags: >-
            --min-instances=0
            --max-instances=5
            --concurrency=1
            --timeout=600
            --cpu=2
            --memory=2Gi
            --no-allow-unauthenticated
```

`--concurrency=1` is the point: one solve per instance, no queuing behind a busy worker. `--no-allow-unauthenticated` because only Inngest and the API service call it.

In its `env_vars:` block, override:

```yaml
            INNGEST_APP_ID=planforge-solver
```

- [ ] **Step 3: Pin the API service away from solving**

In `deploy-backend.yml`, add to `env_vars:`:

```yaml
            INNGEST_APP_ID=planforge-api
```

- [ ] **Step 4: Point Inngest's layout function at the solver**

In the Inngest dashboard, sync the `planforge-solver` app URL (`https://planforge-solver-<hash>-uc.a.run.app/api/inngest`). Confirm the `layout/generate.requested` function is registered under `planforge-solver` and **not** under `planforge-api`.

- [ ] **Step 5: Verify end to end**

Trigger a generation from the deployed frontend. Then confirm:

```bash
gcloud run services logs read planforge-solver --region=us-central1 --limit=50
```

Expected: solve logs on `planforge-solver`. Meanwhile `/health` on `planforge-backend` must stay responsive **during** the solve — that is the whole point of the split.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/deploy-solver.yml .github/workflows/deploy-backend.yml
git commit -m "feat(infra): split solver onto its own Cloud Run service

Distinct INNGEST_APP_ID per service -- two deployments sharing one app_id
previously caused jobs to no-op on the wrong deployment (PR #16).

Karthikeyan N <karthiknitt@gmail.com>"
```

---

## Appendix A — `docs/guides/cloudflare-r2-setup.md`

Write this file verbatim in Task A4, Step 13. **Placeholders only.**

````markdown
# Cloudflare R2 Setup for PlanForge

R2 stores generated artifacts (PDF, DXF, XLSX, AI render PNGs). Chosen over
GCS for two reasons: 10 GB free storage, and **zero egress fees** — egress is
the line item that bites at consumer scale.

## What needs configuring where

| System | Needed? | Why |
|---|---|---|
| **Cloudflare** | ✅ Yes | Bucket + API token live here |
| **GitHub Actions secrets** | ✅ Yes | Injected into Cloud Run by `deploy-backend.yml` |
| **gcloud / GCP** | ❌ **No** | R2 is not a GCP service. Nothing to configure. |
| **Vercel** | ❌ **No env vars** | Exports are generated in the backend; the frontend only follows a URL it is handed. |
| **Cloudflare CORS** | ⚠️ Only for `redirect` mode | If the browser fetches signed URLs directly, the bucket's CORS policy must list the Vercel origins. Configured on Cloudflare, not Vercel. |

## 1. Create the bucket

1. Cloudflare dashboard → **R2 Object Storage** → **Create bucket**
2. Name: `planforge-artifacts`
3. Location: **Automatic** (or APAC if most users are in India)
4. Leave public access **disabled** — access is via presigned URLs only

## 2. Note your Account ID

R2 overview page, right sidebar → **Account ID**. A 32-char hex string. The
S3 endpoint is derived from it:

    https://<your-account-id>.r2.cloudflarestorage.com

## 3. Create an API token

1. R2 → **Manage R2 API Tokens** → **Create API token**
2. Name: `planforge-backend`
3. Permission: **Object Read & Write**
4. Scope to the single bucket `planforge-artifacts` — not "all buckets"
5. TTL: leave as forever, or set a rotation reminder

Copy the **Access Key ID** and **Secret Access Key** immediately — the secret
is shown exactly once.

> ⚠️ **Do not paste these into any file in the repo, including markdown.**
> R2 keys were once committed to a status doc in this project and sat exposed
> for four months. They belong only in GitHub Actions secrets.

## 4. Store them as GitHub secrets

```bash
cd /home/karthik/projects/PlanForge

gh secret set R2_ACCOUNT_ID        --body '<your-account-id>'
gh secret set R2_ACCESS_KEY_ID     --body '<your-access-key-id>'
gh secret set R2_SECRET_ACCESS_KEY --body '<your-secret-access-key>'
gh secret set R2_BUCKET            --body 'planforge-artifacts'

gh secret list | grep R2
```

`deploy-backend.yml` passes all four to Cloud Run as env vars. Nothing is
stored in GCP Secret Manager, so there is no gcloud step.

## 5. Deploy and verify

Push to `main` (or run the workflow manually), then:

```bash
gcloud run services logs read planforge-backend --region=us-central1 --limit=100 \
  | grep -i "R2 not configured"
```

**No output = success.** The message "R2 not configured — artifacts stream
inline" means one of the four values is missing or empty.

Then export a PDF from the app and confirm the object appears:
Cloudflare → R2 → `planforge-artifacts` → an `exports/<project-id>/...` key.

## 6. (Later) Switching to redirect delivery

Default is `EXPORT_DELIVERY_MODE=inline` — the backend streams bytes, exactly
as before R2. Switching to `redirect` makes the backend 307 to a presigned
URL, so file bytes never pass through Cloud Run.

Before switching, add a CORS policy on the bucket:

```json
[
  {
    "AllowedOrigins": [
      "https://planforge-mauve.vercel.app",
      "http://localhost:3000"
    ],
    "AllowedMethods": ["GET"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3600
  }
]
```

Then set `EXPORT_DELIVERY_MODE=redirect` in `deploy-backend.yml` and redeploy.

**Gotcha:** a presigned URL must not receive an `Authorization` header — S3
rejects requests carrying two auth mechanisms. The Fetch spec strips
`Authorization` on cross-origin redirects, so browser `fetch` is safe, but a
server-side proxy that forwards headers manually is not. Test the download
path from the deployed frontend before considering this done.

## Cost expectations

| Item | Free tier | PlanForge scale |
|---|---|---|
| Storage | 10 GB/month | Well inside |
| Class A ops (writes) | 1,000,000/month | Well inside |
| Class B ops (reads) | 10,000,000/month | Well inside |
| **Egress** | **Unlimited, always free** | The reason R2 was chosen |
````

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| Plan B first (immediate savings) | Phase B precedes Phase A |
| Delete policy with keep-count 2 | B1 |
| Reduce Artifact Registry billing | B1, B2, B3, B4 |
| A1 CP-SAT off the event loop | A1 |
| A2 Neon pooled endpoint | A2 |
| A3 Rate limiting | A3 |
| A4 Export storage (R2) | A4 |
| A5 Render quota + cache | A5 (cache already existed; quota + R2 blobs added) |
| A6 Solver service split | A6 |
| R2 setup guide | A4 Step 13 + Appendix A |
| Separate branch | `feat/saas-scalability`, worktree `/home/karthik/projects/PlanForge-saas` |
| No structural-branch conflict | `docs/plans/merge-coordination-2026-07-27.md`; A1 wraps at the call site |
| Items 7–8 deferred | Stated in Global Constraints |

**Type consistency:** `StorageBackend` / `put_bytes` / `get_bytes` / `signed_url` are used identically in A4 and A5. `get_storage()` is defined in A4 and consumed in A5. `_artifact_key` and `_EXPORT_SEM` are defined and tested in A4 only. `is_pooled_url` is A2 only. `TokenBucket.take(now=...)` is keyword-consistent across tests and implementation.

**Known gap accepted:** the A5 quota test passes `db=None` and monkeypatches `_daily_render_count`, so the SQL join is not exercised by unit tests. It is covered by the `-k render` integration run in Step 7.
