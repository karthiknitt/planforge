# Cloud Run $0-Tier Backend Deployment Implementation Plan

> **Status: executed 2026-07-03. Historical record — do not follow verbatim.**
>
> This plan was written before the GCP project existed and proposes the project ID
> `planforge-prod`. The project actually created is **`thermal-well-451906-b0`**
> (region `us-central1`), and the deploy service account is
> `planforge-deployer@thermal-well-451906-b0.iam.gserviceaccount.com`. Every
> `planforge-prod` reference below is superseded by those values.
>
> Current live URLs: backend
> `https://planforge-backend-912195238699.us-central1.run.app` (`/api/health`),
> frontend `https://planforge-mauve.vercel.app`.
> See [../ARCHITECTURE.md](../ARCHITECTURE.md) for current state.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy `backend/` (FastAPI) to Google Cloud Run inside the Always Free tier,
backed by Neon Postgres, auto-deployed via GitHub Actions, with hard-enforced guardrails
that keep monthly cost at $0 for solo-dev-level traffic.

**Architecture:** GitHub Actions builds the backend image, pushes it to Artifact Registry
(`us-central1`), and deploys it to a Cloud Run service capped at `min-instances=0,
max-instances=3, concurrency=4`. The service reads `$PORT` (Cloud Run's injected port) and
connects to Neon's pooled Postgres endpoint over the public internet. Auth from GitHub
Actions to GCP uses Workload Identity Federation (no stored keys). Design rationale and
research citations live in `docs/plans/2026-07-02-cloud-run-deployment-design.md` — read
that first if anything below seems under-justified.

**Tech Stack:** FastAPI, SQLAlchemy async + asyncpg, uv, Docker, Google Cloud Run,
Artifact Registry, Workload Identity Federation, Neon Postgres, GitHub Actions.

---

## Before you start

This plan has two kinds of tasks:
- **Claude-executable** (Phase 1, Phase 3 code tasks): plain file edits and tests, safe,
  reversible, no cloud account needed.
- **User-run** (Phase 2, and the secret-wiring step in Phase 3): these create real
  billing-attached GCP resources or need interactive account auth (`gcloud auth login`,
  Neon dashboard, GitHub repo settings) that Claude cannot and should not do unattended.
  Each is marked **[USER RUNS THIS]** with the exact command(s) to copy-paste.

Do not run Phase 2 until Phase 1 is committed and passing tests — Phase 3's workflow file
references resource names created in Phase 2, so doing Phase 2 first just means re-typing
names later if Phase 1 changes anything.

---

## Phase 1 — Code changes (Claude-executable, no cloud dependency)

### Task 1: Fix Dockerfile to bind to Cloud Run's `$PORT`

**Files:**
- Modify: `backend/Dockerfile:12`

**Step 1: Make the change**

Replace line 12:
```dockerfile
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
with a shell-form CMD so `$PORT` is expanded at container start (exec-form `CMD [...]` does
NOT expand env vars — this distinction is the actual bug to avoid):
```dockerfile
CMD uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
```

**Step 2: Verify locally**

Run:
```bash
cd backend
docker build -t planforge-backend-test .
docker run --rm -e PORT=8080 -e DATABASE_URL="postgresql+asyncpg://planforge:planforge@host.docker.internal:5432/planforge" -p 8080:8080 planforge-backend-test
```
Expected: uvicorn logs `Uvicorn running on http://0.0.0.0:8080`. In a second terminal,
`curl http://localhost:8080/api/health` returns `{"status":"ok"}` (adjust if your DB isn't
reachable from the container — the bind succeeding is what this step verifies, not full DB
connectivity).

Also verify the *old* hardcoded-port form would have failed the way Cloud Run fails, so you
recognize the error class in the future:
```bash
docker run --rm -e PORT=9999 -p 8080:8080 planforge-backend-test
```
Expected: server starts listening on 8080 (correct — it should ignore/not need port 9999
since we hardcode nothing; if you see it fail to respond on 8080 here, the fix didn't take).

**Step 3: Commit**

```bash
git add backend/Dockerfile
git commit -m "fix(backend): bind uvicorn to \$PORT for Cloud Run compatibility"
```

---

### Task 2: Env-driven CORS origins with Vercel preview support

**Files:**
- Create: `backend/app/config/cors.py`
- Modify: `backend/app/config/settings.py`
- Modify: `backend/app/main.py:35-41`
- Test: `backend/tests/test_config_cors.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_config_cors.py
from app.config.cors import parse_allowed_origins


def test_parse_allowed_origins_empty_string():
    assert parse_allowed_origins("") == []


def test_parse_allowed_origins_single():
    assert parse_allowed_origins("https://planforge.example.com") == [
        "https://planforge.example.com"
    ]


def test_parse_allowed_origins_multiple_trims_whitespace():
    raw = "https://planforge.example.com, https://staging.planforge.example.com "
    assert parse_allowed_origins(raw) == [
        "https://planforge.example.com",
        "https://staging.planforge.example.com",
    ]


def test_parse_allowed_origins_ignores_empty_segments():
    assert parse_allowed_origins("https://a.com,,https://b.com,") == [
        "https://a.com",
        "https://b.com",
    ]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_config_cors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config.cors'`

**Step 3: Write minimal implementation**

```python
# backend/app/config/cors.py
def parse_allowed_origins(raw: str) -> list[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_config_cors.py -v`
Expected: 4 passed

**Step 5: Wire it into settings and main.py**

In `backend/app/config/settings.py`, add a field:
```python
    allowed_origins: str = ""
```
(so the class now has `database_url`, `razorpay_key_id`, `razorpay_key_secret`,
`allowed_origins`).

In `backend/app/main.py`, replace the CORS block (currently lines 35-41):
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
with:
```python
from app.config.cors import parse_allowed_origins

default_origins = ["http://localhost:3001", "http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=default_origins + parse_allowed_origins(settings.allowed_origins),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
(`allow_origin_regex` covers every Vercel preview-deployment URL automatically —
`https://<project>-<hash>-<team>.vercel.app` — so you don't have to add a new origin by
hand for every PR preview. `allowed_origins` env var is for your one stable production
Vercel domain, e.g. `https://planforge-mauve.vercel.app`.)

You'll also need `from app.config.settings import settings` already present in
`main.py` — check before adding a duplicate import.

**Step 6: Run full backend test suite**

Run: `cd backend && uv run pytest -q`
Expected: all tests pass (108 existing + 4 new = 112)

**Step 7: Commit**

```bash
git add backend/app/config/cors.py backend/app/config/settings.py backend/app/main.py backend/tests/test_config_cors.py
git commit -m "feat(backend): env-driven CORS origins with Vercel preview regex support"
```

---

### Task 3: Toggleable NullPool for Neon's pooled connection

**Files:**
- Modify: `backend/app/config/settings.py`
- Modify: `backend/app/db.py`
- Test: `backend/tests/test_db_engine.py`

**Why:** Neon's pooled endpoint (PgBouncer, transaction mode) already multiplexes
connections. Layering SQLAlchemy's own connection pool on top is the classic
double-pooling misconfiguration — it causes stale/exhausted-connection errors under Cloud
Run's scale-to-zero-and-burst traffic pattern (see design doc §"Research findings").
`NullPool` disables SQLAlchemy's pool so every checkout goes straight to PgBouncer, which is
correct when *it* is already pooling.

**Step 1: Write the failing test**

```python
# backend/tests/test_db_engine.py
from sqlalchemy.pool import NullPool

from app.db import build_engine_kwargs


def test_build_engine_kwargs_default_has_no_poolclass():
    kwargs = build_engine_kwargs(use_nullpool=False)
    assert kwargs == {"echo": False}


def test_build_engine_kwargs_nullpool_enabled():
    kwargs = build_engine_kwargs(use_nullpool=True)
    assert kwargs["poolclass"] is NullPool
    assert kwargs["echo"] is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_db_engine.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_engine_kwargs' from 'app.db'`

**Step 3: Write minimal implementation**

In `backend/app/config/settings.py`, add:
```python
    db_use_nullpool: bool = False
```

Rewrite `backend/app/db.py`:
```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config.settings import settings


def build_engine_kwargs(use_nullpool: bool) -> dict:
    kwargs: dict = {"echo": False}
    if use_nullpool:
        kwargs["poolclass"] = NullPool
    return kwargs


engine = create_async_engine(
    settings.database_url, **build_engine_kwargs(settings.db_use_nullpool)
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_db_engine.py -v`
Expected: 2 passed

**Step 5: Run full backend test suite**

Run: `cd backend && uv run pytest -q`
Expected: all tests pass (112 + 2 = 114)

**Step 6: Commit**

```bash
git add backend/app/config/settings.py backend/app/db.py backend/tests/test_db_engine.py
git commit -m "feat(backend): toggleable NullPool for Neon pooled connections via DB_USE_NULLPOOL"
```

---

### Task 4: Document new env vars

**Files:**
- Modify: `backend/.env.example`

**Step 1: Add the two new vars with placeholder values (no real secrets)**

Append to `backend/.env.example`:
```
ALLOWED_ORIGINS=https://planforge-mauve.vercel.app
DB_USE_NULLPOOL=false
```

**Step 2: Commit**

```bash
git add backend/.env.example
git commit -m "docs(backend): document ALLOWED_ORIGINS and DB_USE_NULLPOOL env vars"
```

---

## Phase 2 — One-time GCP + Neon setup **[USER RUNS THIS]**

Everything in this phase creates real cloud resources tied to your billing account or needs
interactive browser auth Claude doesn't have. Run these yourself; paste back any output if
you want me to sanity-check it. Do this in order — later steps reference IDs from earlier
ones.

### Task 5: Authenticate and set the active project

```bash
gcloud auth login
gcloud projects create planforge-prod --name="PlanForge"
gcloud config set project planforge-prod
```
If you already have a GCP project you want to reuse instead of creating one, run
`gcloud config set project <existing-project-id>` and skip the `projects create` line.

**Attach a billing account** (required even for free-tier usage — see design doc):
```bash
gcloud billing accounts list
gcloud billing projects link planforge-prod --billing-account=<BILLING_ACCOUNT_ID>
```

### Task 6: Enable required APIs

```bash
gcloud services enable run.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  cloudbilling.googleapis.com
```

### Task 7: Create the Artifact Registry repo with a cleanup policy

```bash
gcloud artifacts repositories create planforge-backend \
  --repository-format=docker \
  --location=us-central1 \
  --description="PlanForge backend images"
```

Free tier is only 0.5GB — add a cleanup policy that keeps only the 5 most recent images:
```bash
gcloud artifacts repositories set-cleanup-policies planforge-backend \
  --location=us-central1 \
  --policy=<(cat <<'EOF'
[
  {
    "name": "keep-recent-5",
    "action": {"type": "Keep"},
    "mostRecentVersions": {"keepCount": 5}
  },
  {
    "name": "delete-rest",
    "action": {"type": "Delete"}
  }
]
EOF
)
```

### Task 8: Create the Neon project and get connection strings

1. Go to https://console.neon.tech and create a new project named `planforge`.
2. In the project's Connection Details panel, copy **two** connection strings:
   - The **pooled** one (hostname ends in `-pooler`) — this becomes your app's
     `DATABASE_URL` in Cloud Run.
   - The **direct** one (no `-pooler` suffix) — keep this for any future Alembic/DDL work;
     not needed for this deployment since the app doesn't run migrations via a separate
     tool yet.
3. Convert the driver prefix: Neon gives you `postgresql://...`; the app needs
   `postgresql+asyncpg://...` (same credentials, just swap the scheme prefix) since
   SQLAlchemy's async engine requires the asyncpg driver name.

Keep both strings somewhere safe (a password manager) — you'll paste the pooled one into a
Cloud Run env var / GitHub secret in Task 10, never into a committed file.

### Task 9: Create the Workload Identity Federation trust + deploy service account

```bash
PROJECT_ID=planforge-prod
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
GITHUB_REPO="karthiknitt/PlanForge"   # adjust if the org/repo name differs

# Service account the workflow will impersonate
gcloud iam service-accounts create planforge-deployer \
  --display-name="PlanForge Cloud Run deployer"

# Minimal roles: push images, deploy to Cloud Run, act as the runtime SA
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:planforge-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:planforge-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:planforge-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Workload Identity Pool + Provider trusting GitHub's OIDC tokens
gcloud iam workload-identity-pools create github-pool \
  --location="global" \
  --display-name="GitHub Actions pool"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub OIDC provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Allow only this exact repo to impersonate the deploy service account
gcloud iam service-accounts add-iam-policy-binding \
  "planforge-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${GITHUB_REPO}"
```

Save the full provider resource name for Task 10:
```bash
gcloud iam workload-identity-pools providers describe github-provider \
  --location=global --workload-identity-pool=github-pool \
  --format="value(name)"
```

### Task 10: Set a budget alert

```bash
gcloud billing budgets create \
  --billing-account=<BILLING_ACCOUNT_ID> \
  --display-name="PlanForge $0 tripwire" \
  --budget-amount=1USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=1.0
```
This emails the billing account's admins at 50% ($0.50) and 100% ($1) of spend. Remember:
this is notification-only (design doc §Guardrails) — if you get this email, go check the
Cloud Run console, don't assume it self-resolves.

---

## Phase 3 — Wire CI/CD and deploy

### Task 11: Add GitHub repo secrets/variables **[USER RUNS THIS]**

Via `gh` CLI (per your convention of preferring `gh` over the web UI):
```bash
gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --body "<full provider resource name from Task 9>"
gh secret set GCP_SERVICE_ACCOUNT --body "planforge-deployer@planforge-prod.iam.gserviceaccount.com"
gh secret set NEON_DATABASE_URL --body "<pooled connection string from Task 8, with +asyncpg>"
gh secret set BACKEND_ALLOWED_ORIGINS --body "https://planforge-mauve.vercel.app"
gh variable set GCP_PROJECT_ID --body "planforge-prod"
gh variable set GCP_REGION --body "us-central1"
```

### Task 12: Write the deploy workflow

**Files:**
- Create: `.github/workflows/deploy-backend.yml`

Matches the existing `backend-ci.yml`'s path-filter and `uses: actions/checkout@v7`
convention already in this repo.

```yaml
name: Deploy Backend to Cloud Run

on:
  push:
    branches: [main]
    paths:
      - "backend/**"
      - ".github/workflows/deploy-backend.yml"
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v7

      - id: auth
        uses: google-github-actions/auth@v3
        with:
          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}

      - uses: google-github-actions/setup-gcloud@v3

      - name: Configure Docker for Artifact Registry
        run: gcloud auth configure-docker ${{ vars.GCP_REGION }}-docker.pkg.dev --quiet

      - name: Build and push image
        working-directory: backend
        run: |
          IMAGE="${{ vars.GCP_REGION }}-docker.pkg.dev/${{ vars.GCP_PROJECT_ID }}/planforge-backend/api:${{ github.sha }}"
          docker build -t "$IMAGE" .
          docker push "$IMAGE"
          echo "IMAGE=$IMAGE" >> "$GITHUB_ENV"

      - name: Deploy to Cloud Run
        uses: google-github-actions/deploy-cloudrun@v3
        with:
          service: planforge-backend
          region: ${{ vars.GCP_REGION }}
          image: ${{ env.IMAGE }}
          flags: >-
            --min-instances=0
            --max-instances=3
            --concurrency=4
            --timeout=300
            --cpu=1
            --memory=1Gi
            --allow-unauthenticated
          env_vars: |
            DATABASE_URL=${{ secrets.NEON_DATABASE_URL }}
            DB_USE_NULLPOOL=true
            ALLOWED_ORIGINS=${{ secrets.BACKEND_ALLOWED_ORIGINS }}
            RAZORPAY_KEY_ID=${{ secrets.RAZORPAY_KEY_ID }}
            RAZORPAY_KEY_SECRET=${{ secrets.RAZORPAY_KEY_SECRET }}
```

Note: `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` secrets need to be set via `gh secret set` too
if payments are exercised against this deployment — add them in Task 11 if/when needed;
omit from `env_vars` if not, since an empty secret reference will just deploy an empty
string (matches the existing `Settings` defaults of `""`).

Commit:
```bash
git add .github/workflows/deploy-backend.yml
git commit -m "ci(backend): add Cloud Run deploy workflow via Workload Identity Federation"
```

### Task 13: First deploy — verify on a throwaway branch before merging

**[USER RUNS THIS — needs your GitHub push access and triggers real GCP deploys]**

```bash
git checkout -b test/cloud-run-deploy
git push -u origin test/cloud-run-deploy
gh workflow run deploy-backend.yml --ref test/cloud-run-deploy
gh run watch --exit-status
```
Expected: workflow goes green. If it fails, the two most likely causes per the design
doc's research are (a) IAM binding attribute condition mismatch on the WIF provider (Task
9's `--attribute-condition` must exactly match `owner/repo`), or (b) the container failing
to bind — re-check Task 1's Dockerfile fix actually built into the pushed image.

Once green:
```bash
gcloud run services describe planforge-backend --region=us-central1 --format='value(status.url)'
```
Copy this URL — it's the backend's production address.

### Task 14: Post-deploy smoke test

**[USER RUNS THIS]**

```bash
curl https://<cloud-run-url>/api/health
```
Expected: `{"status":"ok"}`

Then from a browser on your actual Vercel preview/production URL, exercise one real
"generate layout" flow end-to-end — this is the one request that exercises OR-Tools +
Shapely + ReportLab + the Neon pooled connection together, which is exactly the path the
research flagged as highest-risk for cold-start/connection issues. If it works once, it'll
keep working; if it fails, check Cloud Run logs first:
```bash
gcloud run services logs read planforge-backend --region=us-central1 --limit=50
```

### Task 15: Point the frontend at the new backend

**[USER RUNS THIS — Vercel project settings]**

Update the Vercel project's `NEXT_PUBLIC_API_URL` env var (production + preview scopes) to
the Cloud Run URL from Task 13, then redeploy the frontend. This is the one frontend touch
required to complete the integration — no other frontend changes are in scope.

### Task 16: Merge and clean up

```bash
git checkout main
git merge test/cloud-run-deploy
git push origin main
git push origin --delete test/cloud-run-deploy
git branch -d test/cloud-run-deploy
```
Merging to `main` re-triggers `deploy-backend.yml` for real (expected — this is your
steady-state deploy path going forward: push to `main` → auto-deploy).

### Task 17: Update project docs

**Files:**
- Modify: `/home/karthik/projects/PlanForge/CLAUDE.md` (Known Issues & Review Backlog
  section — add a "Fixed" entry noting Cloud Run deployment is live, with the Cloud Run URL
  and Neon project name for future reference)

Commit:
```bash
git add CLAUDE.md
git commit -m "docs: record Cloud Run deployment details in project backlog"
```

---

## Explicitly out of scope

- Fixing `create_all`/auto-migrate-on-boot with real Alembic migrations (flagged in design
  doc, not addressed here).
- The automated billing circuit-breaker Cloud Function (deferred per your decision).
- Any product feature work.
