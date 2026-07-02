# PlanForge Backend: $0 Cloud Run Deployment — Design

**Date:** 2026-07-02
**Status:** Approved, not yet implemented
**Scope:** Backend only (FastAPI). Frontend deploy to Vercel is out of scope / already decided.

## Goal

Deploy `backend/` to Google Cloud Run, staying within Google's "Always Free" tier so the
service costs genuinely $0/month for a low-traffic solo dev project. Frontend (Next.js)
deploys to Vercel and calls the Cloud Run backend over HTTPS.

## Constraints established

- Must be free — every design decision below is chosen to avoid billable usage, not just
  "usually free."
- Backend deps include `ortools` (CP-SAT solver, heavy native code), `shapely`, `ezdxf`,
  `reportlab`, `asyncpg`, `sqlalchemy` — no Postgres currently provisioned in the cloud;
  local dev uses a docker-compose Postgres container only.
- Database: **Neon** (free tier), matching the project's existing stack convention.
- CI/CD: **GitHub Actions**, auto-deploy on push to `main`.
- Cold starts (container spins down after ~15 min idle, OR-Tools/Shapely re-import on next
  request) are **acceptable** for this dev project.
- Budget safety: **config-level guardrails + email budget alert only** — no automated
  billing circuit-breaker for v1 (explicitly deferred, not forgotten: see Guardrails below
  for why this isn't a mathematically perfect $0 guarantee).
- CI/CD auth: **Workload Identity Federation** (no long-lived service-account key stored in
  GitHub).

## Architecture

```
GitHub (push to main)
   │
   ▼
GitHub Actions (Workload Identity Federation → GCP, no stored keys)
   │  build image, docker push
   ▼
Artifact Registry (us-central1, with cleanup policy — free tier is only 0.5GB)
   │  gcloud run deploy
   ▼
Cloud Run service (us-central1)
   - min-instances=0, max-instances=3, concurrency=4
   - 1 vCPU / 1GiB memory, request-based billing, 300s timeout (defaults)
   - reads PORT env var, listens 0.0.0.0:$PORT
   │
   ▼ (public internet, pooled connection string)
Neon Postgres (free tier, autosuspend, "-pooler" hostname)

Vercel (Next.js frontend) ──HTTPS──▶ Cloud Run backend URL
```

## Research findings that shaped this design

Full detail lives in the conversation that produced this doc; key facts baked into the
design:

- Cloud Run Always Free: 180,000 vCPU-sec/month, 360,000 GiB-sec/month, 2,000,000 requests,
  1 GiB/month free egress (North America only). Pooled per **billing account**, not per
  project. A billing account must be attached to deploy at all — there is no
  free-tier-only project mode.
- `min-instances` must be 0 and billing mode must stay request-based (default) — any
  standing/idle allocation burns the free pool for nothing.
- Default concurrency (80) is wrong for CPU-bound CP-SAT work; lower it explicitly.
- Fire-and-forget background work after a response returns is unreliable under Cloud Run's
  default CPU allocation — keep the OR-Tools solve + PDF/DXF export synchronous inside the
  request.
- Container must bind `0.0.0.0:$PORT` (Cloud Run injects `PORT`, default 8080) — hardcoding
  a port is the most common Cloud Run "container failed to start" failure.
- Shapely 2.x and current `ortools` wheels are self-contained manylinux wheels — no extra
  `apt-get` system packages needed on `python:3.12-slim` for this dependency set.
- Neon free tier autosuspends (mandatory, can't be disabled); use the **pooled**
  (`-pooler`-suffixed hostname) connection string for the app, and the **direct** connection
  string for migrations/DDL. Use `NullPool` in SQLAlchemy's async engine when pointed at the
  pooler to avoid double-pooling connection exhaustion.
- Artifact Registry free storage is only 0.5 GB — a single ~300–400MB image plus history
  can exceed it; needs a cleanup/retention policy.
- **GCP budget alerts are notification-only** — they do not stop spending. The only
  mechanisms that actually bound spend are platform-enforced quotas (`max-instances`,
  concurrency, timeout). True zero-risk would require a custom Cloud Function circuit
  breaker, which is explicitly deferred per the user's decision above.

## Components / concrete code changes

1. `backend/Dockerfile` — `CMD` must read `$PORT`:
   `CMD uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}`
2. `backend/app/main.py` — add the Vercel production domain (and preview-deployment
   pattern) to `CORSMiddleware.allow_origins`, alongside the existing localhost entries.
3. `backend/app/config/settings.py` — `database_url` needs to come from an env var pointing
   at Neon's pooled connection string in production (local default stays as-is for dev).
4. Wherever `create_async_engine` is called (need to locate exact file, likely
   `backend/app/db.py`) — set `poolclass=NullPool` for the pooled Neon connection.
5. Migration path — use Neon's **direct** connection string for any DDL/Alembic-style
   operations, not the pooler. Note: current `main.py` lifespan runs
   `Base.metadata.create_all` + `auto_migrate_missing_columns` on every startup; this is a
   pre-existing pattern (not introduced by Cloud Run) that now runs more frequently due to
   scale-to-zero cold starts. Left as-is for this deployment — flagged, not fixed, unless
   scoped in later.
6. New `.github/workflows/deploy-backend.yml` — build/push to Artifact Registry, deploy to
   Cloud Run, using Workload Identity Federation.
7. One-time GCP setup (requires user-run `gcloud`/console steps per sudo-equivalent
   policy): enable billing + required APIs, create Artifact Registry repo + cleanup policy,
   create Workload Identity Pool/Provider + minimal-IAM deploy service account, set Cloud
   Run scaling flags, create Neon project + connection strings, set a GCP budget alert
   (e.g. $1 threshold, notify-only).

## Guardrails (the $0 protection)

- `max-instances=3` — strongest lever, hard platform-enforced ceiling on concurrent compute.
- `min-instances=0` + default request-based billing — no idle cost.
- `concurrency=4` — appropriate for CPU-bound solver work.
- Request timeout at the 300s default — bounds worst-case per-request compute burn.
- Artifact Registry cleanup policy (keep last N images).
- GCP budget alert at a low threshold — notification only, accepted trade-off for v1.

## Data flow / request lifecycle

Request hits Cloud Run → cold start (if idle): pull image, import OR-Tools/Shapely, connect
to Neon (possibly waking its suspended compute) → CP-SAT solve runs synchronously inside the
request → PDF/DXF built with ReportLab/ezdxf → response returned. Worst-case cold path (both
Cloud Run and Neon waking) could be several seconds — accepted.

## Testing / verification plan

- Local: `docker build` the updated Dockerfile, run with `PORT=8080` set manually, confirm
  correct bind before ever deploying to GCP.
- Post-deploy: hit the Cloud Run health route directly, confirm CORS from an actual Vercel
  preview URL, run one real generate request end-to-end (Neon pooled connection + OR-Tools
  solve under Cloud Run's CPU model).
- Confirm the GitHub Actions workflow succeeds on a throwaway branch before merging to
  `main`.

## Explicitly out of scope for this work

- Fixing `create_all`/auto-migrate-on-boot with real Alembic migrations.
- Automated billing circuit-breaker (Cloud Function + Pub/Sub).
- Any quadrilateral/Vastu/roadmap feature work — deployment only.
