# PlanForge

> G+1 residential floor plan generator for Indian small builders and civil engineers —
> and the front door to a multi-agent IS-code structural design engine.

**[▶ Live demo](https://planforge-mauve.vercel.app)** · **[Architecture](docs/ARCHITECTURE.md)** · **[Engine repo](https://github.com/karthiknitt/structapi)**

![PlanForge system flow: plot input to CP-SAT solver to three scored layouts, then to structapi for deterministic IS-code structural design](docs/assets/system-flow.svg)

PlanForge takes plot dimensions, setbacks, and room preferences and instantly generates three compliant layout variations — complete with SVG preview, section view, Bill of Quantities, PDF drawing, and DXF export. It then hands the resulting column grid to [structapi](https://github.com/karthiknitt/structapi) for IS-code structural design, without the user leaving the app.

**Why the engine is deterministic and not an agent:** structural design from a known floor plan is fully parameterised, so the same plan must always produce the same design — a hard requirement for revision history, approvals, and BOQ reproducibility. The LLM layer sits *above* it: PlanForge's Claude chat calls structapi as a tool, and StructAgent offers a natural-language front door for humans. Full reasoning in [the architecture doc](docs/ARCHITECTURE.md).

Verify both services are live right now:

```bash
curl -s --max-time 120 https://structapi-912195238699.us-central1.run.app/v1/health
# {"status":"ok","api_version":"1","iscodes_version":"0.3.0"}

curl -s --max-time 120 https://planforge-backend-912195238699.us-central1.run.app/api/health
# {"status":"ok","service":"planforge-api"}
```

> **Both services scale to zero.** They run on Cloud Run at `min-instances=0` to stay
> inside the free tier, so a cold request can take **60–120 seconds** before the first
> byte; subsequent requests settle around 1–15s. Give it the full timeout above rather
> than concluding the service is down. The same applies to the first plan you generate in
> the live app.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.129-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/license-PolyForm%20Shield-9c27b0)

---

## Overview

PlanForge is a SaaS tool for Indian residential construction. A user enters plot dimensions and room preferences; the engine runs an OR-Tools CP-SAT constraint solver to produce 3 scored, compliant layout options with staircase positions varied (front / mid / rear). Each layout can be previewed as SVG, exported as a professional PDF drawing or DXF CAD file, and accompanied by a Bill of Quantities.

**Target users:** Small builders, civil contractors, and independent homeowners in Tier 2/3 Indian cities who want compliance-checked floor plans without hiring an architect for early-stage planning.

---

## Features

### Planning Engine
- **3-layout generation** — OR-Tools CP-SAT solver with forced staircase diversity; archetypes as fallback
- **2BHK – 4BHK** with 1–6 bedrooms; optional pooja, study, balcony, servant quarter, home office, gym, store
- **Multi-floor support** — G / G+1 / G+2, optional stilt floor, optional basement
- **Plot shapes** — Rectangular, trapezoid, convex quadrilateral (arbitrary 4-corner), and **L-shaped** (rectangle with cutout corner)
- **Indian compliance engine** — bedroom ≥ 9.5 m², kitchen ≥ 7 m², FAR, setbacks, stair width, beam span
- **Municipality bye-laws** — CMDA (Chennai), BBMP (Bangalore), GHMC (Hyderabad), PMC (Pune), MCGM (Mumbai) city-specific FAR + setback rules
- **Vastu Shastra engine** — 8-zone directional analysis with SVG zone overlay (toggleable per layout)
- **5-component layout scorer** — natural light, adjacency, aspect ratio, circulation, Vastu (0–100)

### Output & Visualisation
- **SVG preview** — double-line walls, door arcs, window markers, columns, north arrow, dimension lines; main entrance door (MD) tagged on the road-facing wall
- **Section view** — parametric 2D cross-section (`SECTION A-A`) with floor slabs and parapet
- **Front elevation** — dedicated `FRONT ELEVATION` view always drawn for the road-facing (y-min) facade, with the main door shown full height
- **Interior furniture overlay** — 11 furniture symbols (bed, sofa, dining, kitchen slab, etc.)
- **Electrical overlay** — switch, socket, light point, fan positions per NBC residential standard
- **Plumbing overlay** — supply spine + drain routing for bathrooms and kitchen
- **Side-by-side comparison** — 2 layouts at same scale with diff highlights
- **Manual room edit mode** — drag shared walls to resize adjacent rooms; live compliance badges (Pro)
- **Room annotations** — sticky notes on rooms, exported to PDF

### Export
- **PDF export** — ReportLab A4 at 1:100; professional double-line walls, boxed window symbols, single door arcs (main door marked), chain dimensions in ft-in, room schedule, north arrow, plus `SECTION A-A` and `FRONT ELEVATION` pages (free)
- **Approval drawing PDF** — municipality-format package with site plan, GF/FF plans, `SECTION A-A` + title block, `FRONT ELEVATION` + title block; solid B&W walls, setback dims, FAR table, owner info, engineer seal, CMDA/BBMP/GHMC/PMC/MCGM submission ready (per-submission add-on)
- **DXF export** — ezdxf with CAD layers, ANSI hatch fills, door/window symbols, per-layer lineweights (0.09–0.50mm), ARCH_MM dimstyle (text above line), graphical scale bar (Basic+)
- **Bill of Quantities** — city-linked material rates for 8 cities; JSON (free) + formatted Excel (Pro)

### Workflow & Collaboration
- **Share link** — read-only client view at `/view/:token` (mobile-friendly, no login required)
- **WhatsApp share** — one-click plan share via WhatsApp Web API
- **Client approval workflow** — client clicks Approve/Request Changes; engineer notified in-product
- **Revision history** — v1/v2/v3 auto-snapshots with one-click restore
- **Team / firm plan** — shared project pool for 2–5 engineers (₹2,999/month)

### AI & Chat
- **Agentic chat** — Claude-powered room editor with 10 tools, voice input via OpenAI Whisper (Pro)
- **OpenRouter support** — any model (Claude, GPT-4, Llama, Gemini) via OpenRouter API key

### Platform
- **Template gallery** — public SEO-optimised gallery filterable by plot size, BHK, city
- **Per-project credits** — ₹99/project one-time purchase for occasional users
- **Regional languages** — Tamil and Hindi UI translations with locale context and cookie persistence
- **Mobile-first UI** — fully responsive; floor plan controls move to bottom sheet on phones; FAB for new project
- **Authentication** — Better Auth (TypeScript-native, session-based)
- **Payments** — Razorpay with plan tiers: Free / Basic / Pro
- **Blueprint Dark theme** — Outfit + Plus Jakarta Sans + JetBrains Mono fonts; `prefers-reduced-motion` support

### Structural
- **Structural design (StructAgent)** — IS-code structural design generated per layout via the `structapi` service; automatically disabled when no API key is configured, so layout generation still works standalone (when key configured)

### SEO & Marketing
- **Metadata API** — Per-page `title` / `description` with `%s | PlanForge` template; `lang="en-IN"` for Google India
- **Structured data (JSON-LD)** — SoftwareApplication schema (homepage), FAQPage (homepage + pricing), HowTo schema (how-it-works); injected via reusable `JsonLd` component
- **XML sitemap** — `/sitemap.xml` with priorities; 8 pages covered including gallery, privacy, terms
- **robots.txt** — disallows `/dashboard`, `/projects/`, `/account`, `/team`, `/api/`
- **Privacy Policy** — `/privacy` page with full data-collection, retention, and security disclosure
- **Terms of Service** — `/terms` page; governing law: Trichy, Tamil Nadu
- **OpenGraph / Twitter card** — static 1424×752 OG image (`opengraph-image.png`), Twitter large-image card
- **Favicon set** — `favicon.ico` (16/32/48 px), `icon.png` (512×512), `apple-touch-icon.png` (180×180)
- **Hero illustration** — colour-coded floor-plan schematic in hero section replacing animated SVG

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind v4, ShadCN |
| Auth | Better Auth + Drizzle ORM (PostgreSQL adapter) |
| Backend | FastAPI, SQLAlchemy async, Pydantic v2 |
| Layout engine | Shapely, OR-Tools CP-SAT |
| PDF / DXF | ReportLab, ezdxf |
| AI | Vercel AI SDK (Claude Sonnet/Opus), OpenAI Whisper |
| Database | PostgreSQL 16 (Neon, serverless/pooled) |
| Object storage | Cloudflare R2 (S3-compatible) |
| Payments | Razorpay |
| Hosting — frontend | Vercel |
| Hosting — backend | Google Cloud Run |
| Containerization | Docker (multi-stage, build-only locally) |
| CI/CD | GitHub Actions |
| Tooling | Bun (package manager + runtime + test runner), Biome, Drizzle ORM, uv |

### Deployment & infrastructure notes

- **Google Cloud Run (backend)** — the FastAPI app runs as a container on Cloud Run at the
  `$0` tier: `min-instances=0`, `max-instances=3`. Scale-to-zero keeps hosting cost at zero
  between requests, at the cost of a cold start (~20–25s) after idle — the trade-off is
  explicit in [Known gaps](#known-gaps). A second Cloud Run service (`planforge-solver`)
  runs the *same* `backend/` image to isolate CP-SAT solver load from API request handling
  — see [`docs/guides/solver-service-split.md`](docs/guides/solver-service-split.md). Both
  are deployed via `.github/workflows/deploy-backend.yml` / `deploy-solver.yml` using
  Workload Identity Federation (WIF) — no long-lived service-account keys ever leave GCP.
- **Vercel (frontend)** — Next.js is deployed with a preview build per branch and a
  production deploy on every push to `main`. Server Components call the backend directly;
  client components go through a same-origin `/api/backend/[...path]` proxy so the Cloud
  Run URL and `INTERNAL_AUTH_SECRET` never reach the browser.
- **Docker** — used for exactly one purpose: building and validating `backend/Dockerfile`
  (multi-stage: deps → builder → runner) so a broken image is caught in CI before Cloud Run
  ever sees it. There is **no `docker compose up`** dev workflow — see
  [Quick Start](#quick-start) for why local dev servers aren't part of this project's loop.
- **Cloudflare R2 (artifact storage)** — stores generated PDF/DXF/XLSX exports and AI
  render PNGs. Chosen over Google Cloud Storage for two reasons: the free 10 GB tier, and
  **zero egress fees** — egress is the cost line that scales badly with usage on GCS/S3.
  All export/import paths degrade gracefully to inline streaming when R2 isn't configured
  (`NullStorage`), so it's fully optional at small scale. Full setup:
  [Cloudflare R2 setup](#cloudflare-r2-setup-artifact-storage) below.

---

## Quick Start

This project has **no local dev server / preview testing workflow** — frontend is tested via Vercel (preview + production deploys), backend via Google Cloud Run, database is Neon (cloud, always-on). Locally you only run unit tests, lint, type-checks, and a Dockerfile build sanity check.

### Prerequisites

| Tool | Version |
|------|---------|
| Docker | 24+ (build-only — no `docker compose`) |
| Bun | 1.3+ — `curl -fsSL https://bun.sh/install \| bash` |
| Python | 3.12+ |
| uv | latest — `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### Setup

```bash
# 1. Install dependencies
cd frontend && bun install
cd backend && uv sync

# 2. Run local checks
cd backend && uv run pytest && uv run ruff check .
cd frontend && bun test && bun run lint

# 3. Validate the backend Dockerfile builds
docker build -t planforge-backend ./backend
```

Real environment values live in Vercel's env store (frontend) and GitHub Actions secrets (backend/Cloud Run) — see `frontend/.env.example` and `backend/.env.example` for reference only, and `scripts/gcp-cloud-run-setup.sh` for how the backend's secrets are provisioned.

To actually see a change working, push to a branch: Vercel builds a preview deploy automatically, and pushing to `main` under `backend/**` triggers `.github/workflows/deploy-backend.yml` against Cloud Run.

---

## Environment Variables

### `frontend/.env.local`

| Variable | Required | Example |
|----------|----------|---------|
| `DATABASE_URL` | ✓ | Neon Postgres connection string (Better Auth tables) |
| `BETTER_AUTH_SECRET` | ✓ | 32+ char random string |
| `BETTER_AUTH_URL` | ✓ | `https://planforge-mauve.vercel.app` |
| `NEXT_PUBLIC_BETTER_AUTH_URL` | ✓ | `https://planforge-mauve.vercel.app` |
| `NEXT_PUBLIC_API_URL` | ✓ | Cloud Run backend URL (public — used by client components calling the backend directly) |
| `BACKEND_URL` | ✓ | Cloud Run backend URL (server-side only — proxy route, `fetchBackend`) |
| `INTERNAL_AUTH_SECRET` | ✓ | Must match the backend's value exactly |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID` | optional | Razorpay test key |
| `NEXT_PUBLIC_AGENT_CHAT` | optional | `1` to show the agent chat tab |
| `OPENAI_API_KEY` | optional | Voice transcription (Whisper) + agent chat fallback |
| `ANTHROPIC_API_KEY` | optional | Agentic chat (Claude) |
| `OPENROUTER_API_KEY` | optional | Agentic chat via OpenRouter (any model) |
| `OPENROUTER_MODEL` | optional | e.g. `anthropic/claude-sonnet-5` (default) |

Set via `vercel env add <NAME> production|preview` — not a local `.env.local` in practice, since there's no local dev server. See `frontend/.env.example` for the full reference list.

### `backend/.env`

| Variable | Required | Example |
|----------|----------|---------|
| `DATABASE_URL` | ✓ | `postgresql+asyncpg://user:pass@ep-xxx-pooler.region.aws.neon.tech/dbname?ssl=require` |
| `DB_USE_NULLPOOL` | ✓ | `true` (required for Neon's pooled endpoint) |
| `ALLOWED_ORIGINS` | ✓ | `https://planforge-mauve.vercel.app` |
| `INTERNAL_AUTH_SECRET` | ✓ | Must match the frontend's value exactly, 32+ chars |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | optional | Payments — empty disables checkout |
| `STRUCTURAL_API_URL` / `STRUCTURAL_API_KEY` | optional | structapi structural design — empty returns 503 on `/structural` |
| `RENDER_PROVIDER` / `RENDER_MODEL` | optional | AI render layer — empty disables the render tab |
| `RENDER_DAILY_QUOTA` | optional | Default `20` — AI renders per user per rolling 24h |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | optional | Render-provider and agent-chat model keys |
| `INNGEST_EVENT_KEY` / `INNGEST_SIGNING_KEY` | optional | Async job pipeline — both empty falls back to inline synchronous generation |
| `INNGEST_APP_ID` | optional | Default `planforge` — **must be distinct per deployment** (main vs solver-split) or jobs silently no-op on the wrong URL |
| `JOB_QUEUED_TIMEOUT_S` | optional | Default `120` — fails a stuck job fast on next poll instead of hanging forever |
| `RATE_LIMIT_CAPACITY` / `RATE_LIMIT_REFILL_PER_SECOND` | optional | Defaults `10` / `0.2` — in-process token bucket |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` | optional | Cloudflare R2 artifact storage — all four empty = no-op, exports stream inline. **See [Cloudflare R2 setup](#cloudflare-r2-setup-artifact-storage) below.** |
| `EXPORT_DELIVERY_MODE` | optional | Default `inline` — `redirect` 307s to a presigned R2 URL instead of streaming bytes |
| `EXPORT_MAX_CONCURRENCY` | optional | Default `2` — concurrent PDF/DXF renders per instance (OOM guard, Cloud Run's filesystem is RAM-backed) |

Set via `gh secret set <NAME> --repo karthiknitt/planforge` — injected into Cloud Run at deploy time. See `scripts/gcp-cloud-run-setup.sh` and `backend/.env.example` for the full reference list.

### Cloudflare R2 setup (artifact storage)

R2 stores generated artifacts (PDF, DXF, XLSX, AI render PNGs) — chosen over GCS for the free 10 GB tier and, more importantly, **zero egress fees**. All four `R2_*` vars empty means the backend falls back to `NullStorage` and streams exports inline exactly as before R2 existed — nothing breaks if you skip this section.

Quick setup:

```bash
# 1. Cloudflare dashboard → R2 Object Storage → Create bucket
#    Name: planforge-artifacts · Location: Automatic · public access: disabled

# 2. R2 → Manage R2 API Tokens → Create API token
#    Permission: Object Read & Write · Scope: planforge-artifacts only

# 3. Store as GitHub Actions secrets (deploy-backend.yml passes these to Cloud Run)
gh secret set R2_ACCOUNT_ID        --body '<your-account-id>'
gh secret set R2_ACCESS_KEY_ID     --body '<your-access-key-id>'
gh secret set R2_SECRET_ACCESS_KEY --body '<your-secret-access-key>'
gh secret set R2_BUCKET            --body 'planforge-artifacts'

# 4. Verify after deploy — no output means R2 is configured correctly
gcloud run services logs read planforge-backend --region=us-central1 --limit=100 \
  | grep -i "R2 not configured"
```

> ⚠️ Never paste R2 keys into any file in the repo, including markdown — they belong only
> in GitHub Actions secrets. `EXPORT_DELIVERY_MODE` defaults to `inline`; switching to
> `redirect` (presigned URLs, bytes never pass through Cloud Run) requires a bucket CORS
> policy first — see the full guide for the exact JSON and a header gotcha with signed URLs.

Full walkthrough with cost breakdown, CORS config, and the redirect-mode gotcha: **[docs/guides/cloudflare-r2-setup.md](docs/guides/cloudflare-r2-setup.md)**.

---

## Project Structure

```
PlanForge/
├── .github/workflows/          # CI (backend-ci, frontend-ci) + CD (deploy-backend, deploy-solver,
│                               #   deploy-structapi) + verify-structapi-vendor (byte-diffs the vendored copy)
├── backend/
│   ├── app/
│   │   ├── api/routes/        # projects, generate, export, payments, rooms, structural, agent tools
│   │   ├── config/            # compliance_rules.json, room_specs.json, settings.py (env vars)
│   │   ├── core/              # shared core utilities
│   │   ├── dependencies/      # auth dependency (JWT verification for frontend proxy)
│   │   ├── engine/            # solver, archetypes, scorer, compliance, Vastu, geometry, PDF/DXF,
│   │   │                      #   section/elevation, structural drawing sheets (foundation/framing/slab/notes)
│   │   ├── middleware/        # in-process token-bucket rate limiter
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── quality/           # CCQS (CAD Compliance Quality Score) automated scoring
│   │   ├── schemas/           # Pydantic I/O schemas
│   │   └── services/          # jobs (Inngest), layout/structural store, R2 storage, Razorpay,
│   │                          #   render providers, structagent client
│   └── tests/                 # pytest — API e2e, engine, solver, scorer, L-shaped, CAD, openings, section
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── (app)/         # Dashboard, projects, account (auth-gated)
│       │   ├── (auth)/        # Sign-in, sign-up
│       │   ├── (marketing)/   # Landing, pricing, how-it-works, gallery, privacy, terms
│       │   ├── share/         # Public read-only share view
│       │   └── api/           # Better Auth handler, agent chat, transcription, backend proxy
│       ├── components/        # SVG renderer, section view, BOQ viewer, chat panel, overlays
│       ├── db/                # Drizzle client + schema (Better Auth tables)
│       ├── hooks/             # useVoiceInput
│       └── lib/               # auth config, layout types, utils, agent-error fallback chain
├── structapi-service/          # Vendored copy of structapi (IS-code structural engine), pinned to a
│                               #   tag — CI byte-diffs it against the tag on every push/PR, don't hand-edit
├── docs/
│   ├── ARCHITECTURE.md         # How PlanForge and structapi fit together
│   ├── developer-reference.md  # Full technical reference
│   ├── documentation.md        # Living technical reference / session log
│   ├── product-roadmap.md      # Shipped features (P0–P3) + backlog
│   ├── guides/                 # cloudflare-r2-setup, neon-pooling, solver-service-split
│   └── assets/                 # system-flow.svg
├── infra/
│   └── artifact-registry-cleanup.json  # GCP Artifact Registry image-pruning policy
├── scripts/
│   ├── gcp-cloud-run-setup.sh          # One-time GCP + Neon setup for the Cloud Run backend
│   ├── check_schema.py                 # DB schema drift check
│   ├── check-structapi-freshness.sh    # Weekly vendored-tag freshness check
│   └── verify-structapi-vendor.sh      # Byte-diffs structapi-service/ against its pinned tag
├── AGENTS.md
├── LICENSE                     # PolyForm Shield 1.0.0
└── README.md
```

> **Not tracked on GitHub, kept local-only:** `CLAUDE.md` (AI agent instructions — contains
> internal infra identifiers), `Status.md`/`Handover.md` (session diary),
> `docs/plans/`, `docs/archive/` (dated internal planning notes), `experiments/` (eval
> artifacts). See `.gitignore` for the full exclusion list.

---

## Development

### Commands

```bash
# Backend
cd backend
uv run pytest tests/ -v          # run 741 tests (in-memory SQLite, no Neon needed)
uv run ruff check . && uv run ruff format .
docker build -t planforge-backend .   # validate the Dockerfile only

# Frontend
cd frontend
bun run build                     # production build
bun run lint                      # lint + format check (Biome)
bun run format                    # auto-format (Biome)
bun test                          # unit tests (Bun test runner)
bun run seed                      # seed 3 test users (free/basic/pro) — targets Neon via DATABASE_URL
```

No local dev server and no Playwright/e2e locally — real end-to-end checks happen against a Vercel preview deploy (frontend) and Cloud Run (backend).

### Test users (dev/QA only)

Seed three tier-test accounts with `SEED_PASSWORD='<value>' bun run seed`, pointed at a
database via `DATABASE_URL`. The script refuses to run without `SEED_PASSWORD`.

| Email | Plan |
|-------|------|
| `free@planforge.dev` | Free |
| `basic@planforge.dev` | Basic |
| `pro@planforge.dev` | Pro |

> Passwords are not published. These accounts live on the production database and are for
> the maintainer's own QA. There is no self-serve demo login — creating and generating a
> plan requires an account (`/projects/new` redirects to sign-in).

### Conventions

- **Frontend:** App Router server components by default; `"use client"` only for interactivity
- **Linting:** Biome (no ESLint, no Prettier)
- **Frontend packages:** `bun add <pkg>` — never `npm install`
- **Backend packages:** `uv add <pkg>` — never `pip install`
- **Compliance rules:** edit `backend/app/config/compliance_rules.json`, not Python
- **Layout IDs:** always dynamic (e.g. `"solver-front-0"`), never assume `"A"/"B"/"C"`
- **Dashboard data:** queries Drizzle directly — never call the backend API for server-side project lists

---

## Documentation

Full index: **[docs/README.md](docs/README.md)**

| Doc | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How PlanForge and structapi fit together, and why the engine is deterministic |
| [docs/developer-reference.md](docs/developer-reference.md) | Architecture, API reference, engine internals, DB schema, feature gating, testing, UI design system |
| [docs/product-roadmap.md](docs/product-roadmap.md) | Shipped features (P0–P3) and remaining backlog |
| [docs/guides/cloudflare-r2-setup.md](docs/guides/cloudflare-r2-setup.md) | Full R2 artifact storage setup — bucket, API token, CORS, redirect delivery mode |
| [docs/guides/neon-pooling.md](docs/guides/neon-pooling.md) | Neon pooled connection setup for the backend's `DATABASE_URL` |
| [docs/guides/solver-service-split.md](docs/guides/solver-service-split.md) | Why the solver runs as a second Cloud Run service (`deploy-solver.yml`) sharing the `backend/` codebase |

---

## Known gaps

Stated up front rather than left to be discovered:

- **Test coverage is unit-heavy.** 741 backend tests (97 files) and 199 frontend tests
  (25 files) all pass, but coverage is concentrated in pure logic — geometry, compliance,
  scoring, parsing. Playwright is configured (`bun run test:e2e`) but end-to-end flows are
  not exercised in CI. Tracked in [docs/product-roadmap.md](docs/product-roadmap.md).
- **No Alembic migrations.** The backend schema is created and patched at startup via
  `Base.metadata.create_all` + `auto_migrate_missing_columns`. Adequate at current scale;
  would need replacing before multi-tenant production.
- **Cold starts are slow.** Cloud Run runs at `min-instances=0` to stay in the free tier,
  so the first request after idle can take ~20–25s.
- **Pre-revenue.** Razorpay checkout is integrated and functional, but the product has not
  launched commercially.

---

## License

**PolyForm Shield License 1.0.0** © Karthikeyan Natarajan

This project is licensed under the [PolyForm Shield License 1.0.0](LICENSE), which permits you to view, use, and modify the software for any purpose **except providing a product that competes with PlanForge or any product offered using this software**. See [LICENSE](LICENSE) for full terms.

For questions about licensing or commercial use, please reach out.
