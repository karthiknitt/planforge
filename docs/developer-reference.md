# PlanForge — Developer Reference

Complete technical documentation for contributors and maintainers.

---

## Table of Contents

1. [Architecture overview](#architecture-overview)
2. [Project structure](#project-structure)
3. [Getting started](#getting-started)
4. [Environment variables](#environment-variables)
5. [Backend — API reference](#backend--api-reference)
6. [Layout engine internals](#layout-engine-internals)
7. [Compliance engine](#compliance-engine)
8. [Vastu engine](#vastu-engine)
9. [Scoring engine](#scoring-engine)
10. [Export outputs](#export-outputs)
11. [Database schema](#database-schema)
12. [Frontend architecture](#frontend-architecture)
13. [Agentic interface](#agentic-interface)
14. [Payments & feature gating](#payments--feature-gating)
15. [Testing](#testing)
16. [Test seed users](#test-seed-users)
17. [UI/UX design system](#uiux-design-system)
18. [Known patterns & gotchas](#known-patterns--gotchas)

---

## Architecture Overview

```
Browser (Next.js 16)
  └── App Router (Server + Client Components)
        ├── /api/auth/*         ← Better Auth handler
        ├── /api/agent/*        ← Agentic chat (Vercel AI SDK + Claude, provider-fallback chain)
        ├── /api/transcribe     ← OpenAI Whisper voice input
        └── proxy.ts            ← Session-based route protection; mints X-Internal-Auth JWT
                                   for every backend call (never forwards a raw user id)

FastAPI (Python 3.12) — every route depends on X-Internal-Auth JWT (see Backend API Reference)
  └── /api/*
        ├── /projects, /projects/{id}/annotations       ← CRUD
        ├── /projects/{id}/generate                     ← Layout generation (sync)
        ├── /projects/{id}/generate-jobs, /jobs/{id}     ← Layout generation (async, Inngest-backed)
        ├── /projects/{id}/layouts/{id}/render(-jobs)    ← AI floor-plan render (Pro, geometry-hash cached)
        ├── /projects/{id}/structural, /structural/*     ← StructAgent IS-code design (optional)
        ├── /projects/{id}/export/*                      ← PDF / approval-PDF / DXF / BOQ
        ├── /projects/{id}/share, /share/{token}          ← Client approval workflow
        ├── /projects/{id}/revisions                      ← v1/v2/v3 auto + manual snapshots
        ├── /teams/*                                      ← Firm plan, shared project pool
        ├── /gallery/plans(/{id})                         ← Public SEO template gallery
        ├── /payments/*                                   ← Razorpay
        └── /projects/{id}/rooms/*                        ← Canvas room editor (agentic, Pro)

PostgreSQL 16
  ├── Better Auth tables (Drizzle)  ← user (+ hasSeenOnboarding), session, account, verification
  └── Backend tables (SQLAlchemy)   ← projects, revisions, teams, jobs, structural designs, renders
```

---

## Project Structure

```
PlanForge/
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   │   ├── export.py        # PDF + approval-PDF + DXF + BOQ exports
│   │   │   ├── generate.py      # GET /projects/{id}/generate (sync)
│   │   │   ├── jobs.py          # Async layout-generation + render jobs (Inngest-backed)
│   │   │   ├── render.py        # Cached AI floor-plan renders (Pro, geometry-hash keyed)
│   │   │   ├── structural.py    # StructAgent IS-code structural design (optional feature)
│   │   │   ├── share.py         # Share token + public view + client approval workflow
│   │   │   ├── revisions.py     # Revision snapshot CRUD
│   │   │   ├── teams.py         # Team/firm plan CRUD
│   │   │   ├── gallery.py       # Public template gallery
│   │   │   ├── health.py        # GET /api/health
│   │   │   ├── payments.py      # POST /payments/order + /verify (project + credit purchases)
│   │   │   ├── projects.py      # CRUD /projects + annotations
│   │   │   └── rooms.py         # In-memory canvas room editor + undo stack
│   │   ├── dependencies/
│   │   │   └── auth.py          # get_current_user_id/email — decodes the X-Internal-Auth JWT
│   │   ├── services/
│   │   │   ├── jobs.py, layout_store.py, render_runner.py   # Job execution + layout state + render provider calls
│   │   │   ├── structagent_client.py   # StructAgent HTTP client
│   │   │   └── access.py, plans.py     # Project access control, plan-tier gating
│   │   ├── inngest_app.py       # Inngest client + event handlers (layout/generate.requested, render)
│   │   ├── config/
│   │   │   ├── compliance_rules.json   # Editable rule thresholds
│   │   │   └── room_specs.json         # 19 room type specs for CP-SAT solver
│   │   ├── engine/
│   │   │   ├── archetypes.py    # Parametric room slicing (layouts A/B/C)
│   │   │   ├── boq.py           # Bill of Quantities calculator
│   │   │   ├── cad_elements.py  # Door/window CAD symbol helpers
│   │   │   ├── compliance.py    # Rule checker (violations + warnings)
│   │   │   ├── generator.py     # Top-level orchestrator
│   │   │   ├── models.py        # Dataclasses: Room, FloorPlan, Layout, PlotConfig, etc.
│   │   │   ├── pdf.py           # ReportLab PDF renderer
│   │   │   ├── scorer.py        # 5-component layout scoring
│   │   │   ├── solver.py        # OR-Tools CP-SAT constraint solver
│   │   │   └── vastu.py         # 8-zone Vastu Shastra engine
│   │   ├── models/
│   │   │   ├── project.py       # SQLAlchemy Project model
│   │   │   └── user.py          # SQLAlchemy User model (plan_tier, extend_existing=True)
│   │   ├── schemas/
│   │   │   ├── layout.py        # Pydantic output schemas
│   │   │   └── project.py       # Pydantic input schemas
│   │   ├── db.py                # Async engine + session factory
│   │   └── main.py              # FastAPI app + lifespan (create_all on startup)
│   ├── tests/
│   │   ├── test_api_e2e.py      # Full workflow API tests
│   │   ├── test_engine.py       # Layout engine unit tests
│   │   ├── test_multi_floor.py  # Multi-floor (G+2, stilt, basement)
│   │   ├── test_scorer.py       # Scorer unit tests
│   │   └── test_solver.py       # CP-SAT solver tests
│   └── pyproject.toml
│
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── (app)/
│       │   │   ├── account/           # Plan badge, expiry, upgrade CTA
│       │   │   ├── dashboard/         # Project list + plan badge
│       │   │   └── projects/
│       │   │       ├── [id]/          # LayoutViewer (Floor Plan | Section | BOQ | Chat)
│       │   │       ├── [id]/edit/     # Edit project form
│       │   │       └── new/           # Create project (Basic + Advanced modes)
│       │   ├── (auth)/
│       │   │   ├── sign-in/           # Split-screen auth page
│       │   │   └── sign-up/
│       │   ├── (marketing)/
│       │   │   ├── page.tsx           # Landing (Blueprint Dark theme)
│       │   │   ├── pricing/           # Pricing cards
│       │   │   └── how-it-works/
│       │   └── api/
│       │       ├── auth/[...all]/     # Better Auth handler
│       │       ├── agent/[projectId]/ # Agentic chat (streamText, 10 tools)
│       │       └── transcribe/        # Whisper transcription
│       ├── components/
│       │   ├── floor-plan-svg.tsx     # SVG renderer (walls, doors, Vastu/furniture/electrical/plumbing overlays)
│       │   ├── section-view-svg.tsx   # SECTION A-A + FRONT ELEVATION renderer
│       │   ├── plan-3d-scene.tsx      # React Three Fiber 3D canvas (parity with solver's room/column grid)
│       │   ├── dxf-preview-canvas.tsx # Inline DXF preview (Phase 4)
│       │   ├── boq-viewer.tsx         # BOQ table + Excel export
│       │   ├── chat-panel.tsx         # Agentic chat UI (AI SDK v6 tool-part parsing via chat-parts.ts)
│       │   ├── pricing-checkout-button.tsx  # Razorpay client
│       │   └── ui/                    # ShadCN components
│       ├── db/
│       │   ├── index.ts               # Drizzle client
│       │   └── schema.ts              # Better Auth tables (+ hasSeenOnboarding) + project columns
│       ├── hooks/
│       │   └── use-voice-input.ts     # MediaRecorder + Whisper integration
│       ├── lib/
│       │   ├── auth.ts                # Better Auth server config
│       │   ├── auth-client.ts         # Better Auth browser client
│       │   ├── layout-types.ts        # TypeScript types mirroring backend schemas
│       │   ├── agent-model-chain.ts   # Provider fallback chain (Anthropic → OpenAI → OpenRouter)
│       │   ├── agent-errors.ts        # shouldFallback() — 401/402/404/429/5xx/network → advance chain
│       │   ├── chat-parts.ts          # AI SDK v6 tool-part helpers (isToolUIPart/getToolName)
│       │   └── utils.ts               # cn() + misc
│       └── proxy.ts                   # Session-based middleware redirect; mints X-Internal-Auth JWT
│
├── docs/                        # This file lives here
├── scripts/
│   └── gcp-cloud-run-setup.sh   # One-time GCP + Neon setup for the Cloud Run backend
└── CLAUDE.md
```

---

## Getting Started

**No local dev server, no local Playwright/preview testing.** Frontend is tested via Vercel (preview + production deploys); backend is tested via Google Cloud Run; the database is Neon (cloud, always-on — nothing to start locally). Locally you run unit tests, lint/format, type-checks, and a Dockerfile build sanity check only.

### Prerequisites

| Tool | Version |
|------|---------|
| Docker | 24+ (build-only — no `docker compose`) |
| Bun | 1.3+ — `curl -fsSL https://bun.sh/install \| bash` |
| Python | 3.12+ |
| uv | latest — `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### Steps

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

Real values live in Vercel's env store (frontend) and GitHub Actions secrets (backend/Cloud Run) — `frontend/.env.example` / `backend/.env.example` are reference only (see Environment Variables section below).

To exercise a change for real: push a branch for a Vercel preview deploy (frontend), or push to `main` under `backend/**` to trigger `.github/workflows/deploy-backend.yml` against Cloud Run (backend).

---

## Environment Variables

### `frontend/.env.local`

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✓ | Neon Postgres for Drizzle (Better Auth tables) |
| `BETTER_AUTH_SECRET` | ✓ | ≥32-char random secret — run `bunx @better-auth/cli secret` |
| `BETTER_AUTH_URL` | ✓ | Canonical frontend URL — `https://planforge-mauve.vercel.app` |
| `NEXT_PUBLIC_BETTER_AUTH_URL` | ✓ | Same, exposed to browser |
| `NEXT_PUBLIC_API_URL` | ✓ | Cloud Run backend base URL |
| `BACKEND_URL` | ✓ | Cloud Run backend base URL (server-side only, proxy/fetchBackend) |
| `INTERNAL_AUTH_SECRET` | ✓ | Must match the backend's value exactly |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID` | optional | Razorpay test key |
| `OPENAI_API_KEY` | optional | Whisper voice transcription |
| `ANTHROPIC_API_KEY` | optional | Agentic chat (Claude Sonnet/Opus) |

Set via `vercel env add <NAME> production|preview`, not a local file — there's no local dev server to read `frontend/.env.local`.

### `backend/.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✓ | Neon pooled connection — `postgresql+asyncpg://user:pass@ep-xxx-pooler.region.aws.neon.tech/dbname?ssl=require` (asyncpg needs `ssl=require`, not `sslmode`/`channel_binding` — see `scripts/gcp-cloud-run-setup.sh`) |
| `DB_USE_NULLPOOL` | ✓ | `true` — required for Neon's pooled endpoint |
| `ALLOWED_ORIGINS` | ✓ | `https://planforge-mauve.vercel.app` |
| `INTERNAL_AUTH_SECRET` | ✓ | Must match the frontend's value exactly |
| `RAZORPAY_KEY_ID` | optional | Required to create payment orders |
| `RAZORPAY_KEY_SECRET` | optional | Required for HMAC verification |

Set via `gh secret set <NAME> --repo karthiknitt/planforge`, injected into Cloud Run at deploy time by `.github/workflows/deploy-backend.yml`.

---

## Backend — API Reference

All routes are prefixed with `/api`. Authenticated routes depend on `get_current_user_id`
(`backend/app/dependencies/auth.py`), which expects an **`X-Internal-Auth` JWT** — a
short-lived HS256 token minted server-side by the frontend from the verified Better Auth
session (`user_id` + optional `email` claims, `INTERNAL_AUTH_SECRET` shared between
frontend/backend), not the old raw `X-User-Id` header. Never trust a client-supplied
user id or email directly; only the JWT claim.

### Health

| Method | Path | Response |
|--------|------|----------|
| GET | `/api/health` | `{ "status": "ok" }` |

### Projects

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/projects` | Create project |
| GET | `/api/projects` | List user's projects |
| GET | `/api/projects/{id}` | Get single project |
| PUT | `/api/projects/{id}` | Update project |

**PlotConfig fields (POST/PUT body):**

```json
{
  "name": "My Plot",
  "plot_length": 12.192,
  "plot_width": 9.144,
  "plot_shape": "rectangular",
  "setback_front": 1.524,
  "setback_rear": 1.524,
  "setback_left": 0.914,
  "setback_right": 0.914,
  "road_side": "S",
  "num_bedrooms": 2,
  "toilets": 2,
  "parking": false,
  "city": "Chennai",
  "vastu_enabled": true,
  "road_width_m": 9.0,
  "has_pooja": false,
  "has_study": false,
  "has_balcony": false,
  "plot_front_width": 0.0,
  "plot_rear_width": 0.0,
  "num_floors": 2,
  "has_stilt": false,
  "has_basement": false,
  "custom_room_config": null
}
```

`road_side`: `"N" | "S" | "E" | "W"`
`plot_shape`: `"rectangular" | "trapezoid"`
`num_floors`: `1` (G) | `2` (G+1) | `3` (G+2)

### Layout Generation

```
GET /api/projects/{id}/generate
→ GenerateResponse
```

Returns up to 3 layouts scored and ranked by the layout scorer. Layout IDs are **not** guaranteed to be `A/B/C` — always use the IDs from the response.

**GenerateResponse:**
```json
{
  "project_id": "...",
  "layouts": [
    {
      "id": "solver-front-0",
      "name": "Front Staircase",
      "compliance": { "passed": true, "violations": [], "warnings": [] },
      "ground_floor": { "floor": 0, "floor_type": "ground", "rooms": [...], "columns": [...] },
      "first_floor": { "floor": 1, "floor_type": "first", "rooms": [...], "columns": [...] },
      "second_floor": null,
      "basement_floor": null,
      "score": {
        "total": 78.4,
        "natural_light": 82.0,
        "adjacency": 75.0,
        "aspect_ratio": 80.0,
        "circulation": 70.0,
        "vastu": 85.0
      }
    }
  ]
}
```

### Export

| Method | Path | Plan required | Output |
|--------|------|--------------|--------|
| GET | `/api/projects/{id}/export/pdf?layout_id=A` | Free+ | `application/pdf` |
| GET | `/api/projects/{id}/export/dxf?layout_id=A` | Basic+ | `application/octet-stream` (DXF) |
| GET | `/api/projects/{id}/boq?layout_id=A&fmt=json` | Free+ | `application/json` |
| GET | `/api/projects/{id}/boq?layout_id=A&fmt=excel` | Pro | `application/xlsx` |

### Payments

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/payments/order` | Create Razorpay order `{ "plan": "basic" \| "pro" }` |
| POST | `/api/payments/verify` | HMAC verify + activate plan tier |

### Rooms (Canvas Editor — Pro only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/{project_id}/rooms` | List rooms for the current layout state |
| GET | `/api/projects/{project_id}/rooms/layout-state` | Full in-memory layout state (agent-tool source of truth) |
| GET | `/api/projects/{project_id}/rooms/{room_id}` | Get a single room |
| POST | `/api/projects/{project_id}/rooms/{room_id}/move` | Move a room (Shapely validated) |
| POST | `/api/projects/{project_id}/rooms/{room_id}/resize` | Resize a room |
| POST | `/api/projects/{project_id}/rooms/swap` | Swap two rooms' positions |
| POST | `/api/projects/{project_id}/rooms` | Add a room to the current layout |
| DELETE | `/api/projects/{project_id}/rooms/{room_id}` | Remove a room |
| GET | `/api/projects/{project_id}/available-space` | Unallocated floor area, for the "add room" picker |
| GET | `/api/projects/{project_id}/compliance` | Re-run compliance against current in-memory state |
| POST | `/api/layouts/{layout_id}/compliance-check` | Stateless compliance check against a posted `{ rooms: Room[] }` (used during manual drag, debounced) |
| POST | `/api/projects/{project_id}/rooms/undo` | Undo last action (deque, maxlen=10) |

### Async Jobs (Inngest-backed layout generation & renders)

`backend/app/api/routes/jobs.py` — generation and AI-render are queued as durable jobs via
the Python `inngest` SDK (`app/inngest_app.py`) rather than solved synchronously in the
request, avoiding Cloud Run's request timeout on cold-start CP-SAT solves.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/projects/{project_id}/generate-jobs` | Enqueue a layout-generation job (`layout/generate.requested` event); `202` when Inngest is configured |
| POST | `/api/projects/{project_id}/layouts/{layout_id}/render-jobs` | Enqueue an AI floor-plan render job; accepts an optional multipart `reference` PNG (R3F 3D snapshot) to condition the render on exact geometry |
| GET | `/api/projects/{project_id}/jobs/{job_id}` | Poll job status/result |

**Fallback behaviour:** when `inngest_app.inngest_enabled()` is false (dev/CI, or Inngest
not yet provisioned in an environment), `create_generate_job` solves inline within the same
request/DB session instead of enqueueing — same endpoint, no separate code path for callers.

### Structural Design (StructAgent)

`backend/app/api/routes/structural.py` — IS-code structural design (columns, beams,
footings) generated per layout via the external `structapi` service
(`app/services/structagent_client.py`). Disabled (all endpoints 404/503) when no
`structagent` API key/endpoint is configured — layout generation and export work fully
without it.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/projects/{project_id}/structural` | Request a structural design run for a layout |
| GET | `/api/projects/{project_id}/structural/status` | Poll design-run status |
| GET | `/api/projects/{project_id}/structural/design` | Fetch the latest non-stale design for the layout's current approved revision (matched by geometry hash) |
| POST | `/api/projects/{project_id}/structural/approve` | Freeze the current layout geometry as an immutable approved revision |

### AI Render Cache

`backend/app/api/routes/render.py` — AI-generated floor-plan renders (photoreal preview),
persisted per layout **geometry-hash** so an unchanged layout never re-hits the paid render
provider. Pro plan required.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/projects/{project_id}/layouts/{layout_id}/render` | Generate (or return cached) AI render for a floor |
| GET | `/api/projects/{project_id}/layouts/{layout_id}/render` | Fetch the persisted render image |

### Share, Revisions, Teams, Gallery

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/projects/{project_id}/share` | Create a read-only share token |
| DELETE | `/api/projects/{project_id}/share` | Revoke the share token |
| GET | `/api/share/{token}` | Public read-only layout view (no auth) |
| POST | `/api/share/{token}/approve` | Client approves the shared layout |
| POST | `/api/share/{token}/request-changes` | Client requests changes |
| GET | `/api/projects/{project_id}/revisions` | List revision snapshots (v1/v2/v3...) |
| POST | `/api/projects/{project_id}/revisions` | Create a manual revision snapshot |
| GET | `/api/projects/{project_id}/revisions/{revision_id}` | Get a single revision |
| DELETE | `/api/projects/{project_id}/revisions/{revision_id}` | Delete a revision |
| POST | `/api/teams` | Create a team (firm plan) |
| GET | `/api/teams/mine` | Get the caller's team |
| POST | `/api/teams/claim` | Claim/join a team via invite |
| GET | `/api/teams/{team_id}/members` | List team members |
| GET | `/api/teams/{team_id}/projects` | List a team's shared project pool |
| GET | `/api/gallery/plans` | Public SEO template gallery listing |
| GET | `/api/gallery/plans/{preset_id}` | Fetch one gallery preset's full plan (used by the gallery "use this template" CTA) |
| GET | `/api/projects/{project_id}/annotations` | Get room sticky-note annotations |
| PUT | `/api/projects/{project_id}/annotations` | Save room annotations |

---

## Layout Engine Internals

### Generator (`engine/generator.py`)

Orchestrates the full pipeline:
1. Validate plot inputs (minimum size)
2. Run CP-SAT solver (`solver.py`) — 3 diverse runs with forced staircase positions
3. Score each layout (`scorer.py`)
4. Rank by score, return top 3
5. Check compliance (`compliance.py`)
6. Run Vastu analysis if `vastu_enabled=True` (`vastu.py`)

### CP-SAT Solver (`engine/solver.py`)

Uses **OR-Tools CP-SAT** for constraint-based room placement:

- Grid resolution: 10 cm (0.1 m)
- Variables: `room_x`, `room_y` (integer, in grid units)
- **Hard constraints:**
  - Rooms fit within floor plate, no overlaps
  - Staircase width ≥ 900 mm, main entrance door ≥ 900 mm
  - En-suite toilets: shared wall between bedroom and attached toilet ≥ 900 mm (when `attached_toilets=True`)
  - Door-graph navigability: all rooms BFS-reachable from entrance; wet rooms exactly one door; bedrooms one circulation entry; staircase doored per floor
- **Soft objectives:** adjacency preferences, natural light (exterior wall proximity), staircase centrality
- **3 runs** forced with staircase at front / mid / rear for layout diversity
- Room specs (min/max area, floor preference, mandatory flag) loaded from `config/room_specs.json`

**19 room types:**
`living`, `bedroom`, `master_bedroom`, `kitchen`, `toilet`, `staircase`, `parking`, `utility`, `pooja`, `study`, `balcony`, `dining`, `servant_quarter`, `gym`, `home_office`, `store_room`, `garage`, `passage`

### Multi-Floor Support

`PlotConfig.num_floors`:
- `1` → Ground floor only
- `2` → G + First floor (G+1)
- `3` → G + First + Second floor (G+2)

`PlotConfig.has_stilt = True` → Floor 0 is stilt (parking only; bedroom/gym banned)
`PlotConfig.has_basement = True` → Floor -1 basement (-1; gym allowed per NBC, stilt-banned rooms excluded)

Floor types: `"basement" | "stilt" | "ground" | "first" | "second"`

### Archetypes (`engine/archetypes.py`)

Fallback parametric room placement using proportional slicing when the CP-SAT solver doesn't converge within time budget:

- **Layout A** — Staircase at front
- **Layout B** — Staircase at centre
- **Layout C** — Staircase at rear

Room widths are proportional to their minimum area requirements, sliced from the floor plate.

---

## Compliance Engine

### Rules (`engine/compliance.py`)

Loaded from `backend/app/config/compliance_rules.json`:

| Rule | Threshold | Severity |
|------|-----------|----------|
| Bedroom area | ≥ 9.5 m² | Violation |
| Kitchen area | ≥ 7.0 m² | Violation |
| Toilet area | ≥ 2.8 m² / max 4.5 m² | Violation |
| WC area | ≥ 1.1 m² | Violation |
| Stair width | ≥ 900 mm | Violation |
| FAR / floor coverage | ≤ 70% | Violation |
| Setbacks | per input | Violation |
| Living room area | ≥ 12 m² | Warning |
| Beam span | ≤ 4.5 m | Warning |
| Kitchen ventilation | external wall access | Warning |
| Bath ventilation | window or mech vent | Warning |

Layouts failing any violation are returned with `compliance.passed = false`. They are still shown to the user with violations listed.

### En-Suite Toilets

When `attached_toilets=True` per PlotConfig, the solver enforces:
- **One attached bath per bedroom** — master bedroom gets `bathroom_master` (3.2–4.5 m²), other bedrooms get en-suite toilet (2.8–4.5 m², standard toilet spec)
- **Hard wall-adjacency constraint** — shared wall between bedroom and attached toilet ≥ 900 mm (allows door opening + minimum wall span)
- **Per-floor common toilet** — every occupied floor without a bedroom gets ≥1 common toilet (redistribution of user's toilet count; wet-zone only)
- **Soft placement penalties** — front band preference avoided; staircase/parking adjacency penalised
- **Wet-room exclusion** — wet rooms excluded from size-growth objective (soft constraint)

Room sizing per NBC 2016 + Indian conventions:
- `bathroom_master`: 3.2–4.5 m² (typical 5'×7' ≈ 3.25 m²)
- `toilet` (standard): 2.8–4.5 m² (typical 5'×7' ≈ 3.25 m²)
- `wc_only`: 1.1–2.0 m² (water-closet only, no bathing)

### Door-Graph Navigability

Generator enforces navigability via a repair pass (`plan_geometry.py` inside `derive_openings`) + gate (`generator.py`) after layout generation:
- **BFS reachability** — all rooms reachable from entrance/staircase via door traversal (no dead-end room chains)
- **Wet rooms exact-one-door** — bathrooms/toilets accessible via exactly one door (no corridor isolation)
- **Bedrooms one circulation entry** — each bedroom entered via one primary door from circulation (no isolated bedrooms)
- **Staircase doored per floor** — staircase core has a door on each floor it serves (landed access)
- **Repair pass** — if violations found, door-graph corrected (opens/closes doors, adds/removes openings as needed)
- **Generator gate** — layouts failing navigability post-repair are rejected (no output)

Navigability violations are diagnostic; layouts passing all other rules but failing navigability are filtered before ranking.

### City Presets

`city` field accepts: `"bangalore"`, `"chennai"`, `"mumbai"`, `"hyderabad"`, `"other"`. Each preset applies local setback and FAR overrides.

---

## Vastu Engine

### Zones (`engine/vastu.py`)

The plot is divided into 8 directional zones relative to `road_side`:

| Zone | Direction | Preferred rooms |
|------|-----------|----------------|
| N | North | Living, drawing room |
| NE | North-East | Pooja, study, open |
| E | East | Bedroom, bathroom |
| SE | South-East | Kitchen |
| S | South | Bedroom, heavy storage |
| SW | South-West | Master bedroom |
| W | West | Children's bedroom, dining |
| NW | North-West | Toilet, utility, garage |

Rules are evaluated per room type. Violations (wrong quadrant) and warnings (suboptimal placement) are attached to each layout's `vastu` result.

---

## Scoring Engine

### Components (`engine/scorer.py`)

Seven weighted components, total score 0–100:

| Component | Weight | Method |
|-----------|--------|--------|
| `natural_light` | 25% | Ratio of rooms touching exterior walls |
| `adjacency` | 25% | Preferred room-pair adjacency satisfaction |
| `toilet_placement` | 10% | En-suite adjacency + wet-zone coherence (when `attached_toilets=True`) |
| `grid_regularity` | 10% | Column-grid alignment efficiency + bay regularity |
| `aspect_ratio` | 10% | Per-room width:depth ratio (target 1:1.5) |
| `circulation` | 10% | Staircase centrality + corridor efficiency |
| `vastu` | 10% | Vastu rule satisfaction ratio |

`rank_and_select()` sorts layouts by `score.total` (descending) and returns top 3. Layout IDs assigned by the solver run (e.g., `"solver-front-0"`) — **not** guaranteed to be `A/B/C`.

### Compliance Warnings

Layouts passing geometry + navigability gates may emit placement warnings:
- **Toilet placement violation** — en-suite toilet not hard-adjacent to its bedroom (≥ 900 mm shared wall missing)
- **Staircase/parking proximity** — toilet adjacent to staircase/parking (preferred avoided per soft constraints)
- **Front-band placement** — toilet in front setback band (suboptimal; reserved for entry/living)

---

## Export Outputs

### PDF (`engine/pdf.py`)

- ReportLab renderer
- Two-page A4 at 1:100 scale
- Title block: project name, date, scale, north arrow
- Each page: one floor plan with room labels, dimensions, column markers

### DXF (`api/routes/export.py`)

- ezdxf, format `R2010`, units = metres
- Named layers: `A-WALL-BRICK` (red), `A-WALL-INT` (yellow), `A-DOOR` (cyan), `A-WINDOW` (blue), `S-COLUMN` (white), `DIM-LINE` (grey), `TEXT` (white)
- Ground + first floor at `z=0` and `z=3.0` respectively
- Linear dimension annotations for overall width and depth

### BOQ (`engine/boq.py`)

JSON output per layout:
```json
{
  "project_name": "...",
  "layout_id": "A",
  "line_items": [
    { "item": 1, "description": "Concrete (M20)", "quantity": 14.3, "unit": "m³" }
  ]
}
```

Excel output (Pro plan): formatted `.xlsx` with header, styled column headers, auto-width columns.

---

## Database Schema

### Backend tables (SQLAlchemy — `models/`)

**`projects`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | String | FK → auth user |
| `name` | String | |
| `plot_length` / `plot_width` | Numeric(10,3) | Metres |
| `setback_*` | Numeric(10,3) | Front/rear/left/right |
| `road_side` | String | N/S/E/W |
| `num_bedrooms` | Integer | 1–6 |
| `toilets` | Integer | |
| `parking` | Boolean | |
| `city` | String | |
| `vastu_enabled` | Boolean | |
| `road_width_m` | Numeric | |
| `has_pooja/has_study/has_balcony` | Boolean | |
| `plot_shape` | String | rectangular/trapezoid |
| `plot_front_width / plot_rear_width` | Numeric | Trapezoid only |
| `num_floors` | Integer | 1/2/3 |
| `has_stilt / has_basement` | Boolean | |
| `custom_room_config` | Text | JSON string or null |
| `created_at / updated_at` | DateTime | |

**`users`** (extends Better Auth user table with `extend_existing=True`)

| Column | Type | Notes |
|--------|------|-------|
| `plan_tier` | String | `"free"` / `"basic"` / `"pro"` |
| `plan_expires_at` | DateTime | null = no expiry |

### Frontend tables (Drizzle — `src/db/schema.ts`)

Better Auth tables: `user`, `session`, `account`, `verification`

Additional project columns managed by Drizzle:
`plotShape`, `plotFrontWidth`, `plotRearWidth`, `plotSideOffset`, `numFloors`, `hasStilt`, `hasBasement`

---

## Frontend Architecture

### Route Groups

| Group | Path | Protection |
|-------|------|-----------|
| `(marketing)` | `/`, `/pricing`, `/how-it-works` | Public |
| `(auth)` | `/sign-in`, `/sign-up` | Redirect if logged in |
| `(app)` | `/dashboard`, `/projects/*`, `/account` | Auth required |

### Middleware (`proxy.ts`)

Session-based route protection using Better Auth's `getSession()`. Unauthenticated requests to `(app)` routes redirect to `/sign-in`.

### SVG Renderer (`components/floor-plan-svg.tsx`)

Client component. Renders:
- Room fills + labels (area in m²)
- Double-line walls: 230 mm external, 115 mm internal (in SVG scale)
- Doors: arc symbols on exterior/shared walls
- Windows: frame symbols (W-delimiters)
- Columns: filled squares at corners
- Dimension lines + scale bar
- North arrow (rotated per `road_side`)
- Trapezoid plot boundary as SVG polygon

**Dark mode:** CSS vars (`--svg-bg`, `--svg-room`, etc.) applied via `.floor-plan-svg` class. SVG `<rect>` elements use `className="svg-bg"`.

### Section View (`components/section-view-svg.tsx`)

Parametric 2D section showing:
- Ground floor slab + walls (3 m floor-to-floor height)
- First floor slab + walls
- Parapet (900 mm)
- Height annotations

### LayoutViewer tabs

4 tabs: **Floor Plan** | **Section View** | **BOQ** | **Chat**

Chat tab is Pro-gated. Non-Pro users see an upgrade CTA.

---

## Agentic Interface

### Chat Agent (`app/api/agent/[projectId]/route.ts`)

- Vercel AI SDK `streamText` with `maxSteps=10`
- Model routing: `claude-opus-4-5` for complex requests, `claude-sonnet-4-5` default
- **10 tools:** `getProjectDetails`, `generateLayouts`, `moveRoom`, `resizeRoom`, `undoLastAction`, `getComplianceReport`, `exportPDF`, `getVastuReport`, `getBoQ`, `updateProjectConfig`
- Tool calls routed to the backend `/api/rooms/*` endpoints

### Voice Input (`hooks/use-voice-input.ts`)

States: `idle → recording → transcribing → idle | error`

- `MediaRecorder` captures audio (WebM/Opus)
- On stop: `Blob` posted to `/api/transcribe`
- `/api/transcribe/route.ts` calls OpenAI Whisper API
- Transcript injected into chat input

### In-memory Room Editor (`api/routes/rooms.py`)

- Per-project state stored in a `dict` in memory (no DB persistence)
- Undo stack: `collections.deque(maxlen=10)` per project
- Geometry validation: Shapely checks for overlaps after each move/resize
- Pro plan gate: 402 if `plan_tier != "pro"`

---

## Payments & Feature Gating

### Razorpay flow

1. Frontend calls `POST /api/payments/order` → backend creates Razorpay order
2. `pricing-checkout-button.tsx` loads Razorpay checkout script, opens modal
3. On success: frontend calls `POST /api/payments/verify` with `razorpay_payment_id`, `razorpay_order_id`, `razorpay_signature`
4. Backend verifies HMAC-SHA256 signature, updates `user.plan_tier` and `plan_expires_at`

### Gate locations

| Feature | Gate | File |
|---------|------|------|
| Max 3 projects | Free plan check | `api/routes/projects.py` |
| DXF export | Basic or Pro | `api/routes/export.py` |
| BOQ Excel | Pro only | `api/routes/export.py` |
| Room editor | Pro only | `api/routes/rooms.py` |
| Chat tab | Pro only (frontend) | `components/layout-viewer.tsx` |

### Plan tiers

| Tier | `plan_tier` value | Projects | DXF | BOQ Excel | Chat |
|------|-------------------|----------|-----|-----------|------|
| Free | `"free"` | 3 max | ✗ | ✗ | ✗ |
| Basic | `"basic"` | Unlimited | ✓ | ✗ | ✗ |
| Pro | `"pro"` | Unlimited | ✓ | ✓ | ✓ |

---

## Testing

### Backend (pytest)

```bash
cd backend
uv run pytest tests/ -v
```

Tests use an in-memory SQLite DB via `conftest.py`. No running PostgreSQL needed.

| File | Coverage |
|------|----------|
| `test_api_e2e.py` | Full workflow: create project → generate → export → payments |
| `test_engine.py` | Layout engine: archetypes, compliance, Vastu |
| `test_multi_floor.py` | G+2, stilt, basement floor configs |
| `test_scorer.py` | All 5 scoring components |
| `test_solver.py` | CP-SAT solver: room placement, overlap detection |

**Key testing conventions:**
- Never hardcode layout IDs (`"A"`, `"B"`, `"C"`) — use IDs from generate response
- `num_bedrooms` max is 6; use 7 to trigger 422 validation error
- E2E tests pass `X-User-Id` header directly (no real auth session)

### Frontend (Playwright)

Requires full dev stack running.

```bash
cd frontend
bun run test:e2e          # headless
bun run test:e2e:ui       # interactive
```

```
tests/e2e/
├── auth.setup.ts                     # Creates test user, saves cookies to playwright/.auth/
├── public-routes.unauth.spec.ts      # Public pages load, auth redirects work
└── app-flows.auth.spec.ts            # Dashboard, new project, account, sign-out
```

### Frontend lint

```bash
cd frontend
bun run lint                  # lint + format check (Biome)
bun run format                # auto-format (Biome)
bunx tsc --noEmit             # type check
```

---

## Test Seed Users

> **Dev/QA only.** These are dummy accounts for testing feature-gated functionality. Never commit real credentials.
> **Status (2026-07-03): live and verified.** Seeded against the production Neon DB and confirmed working via a real `POST /api/auth/sign-in/email` against `https://planforge-mauve.vercel.app` (200, session token returned). Use these to test the live frontend/backend — see the Cloud Run session log entry above for what had to be fixed first (`DATABASE_URL` was never configured on Vercel until then).

Three test users are pre-seeded into the database with different plan tiers so you can verify all gated features without going through the Razorpay payment flow.

### Credentials

| Email | Password | Plan | Features accessible |
|-------|----------|------|-------------------|
| `free@planforge.dev` | `Test@1234` | Free | Dashboard, 3 projects max, SVG preview, Section View, BOQ (view), PDF export |
| `basic@planforge.dev` | `Test@1234` | Basic | All Free features + unlimited projects + DXF export |
| `pro@planforge.dev` | `Test@1234` | Pro | All Basic features + BOQ Excel export + Agentic chat (room editor, voice input) |

The `basic` and `pro` accounts have `plan_expires_at` set to 2099-12-31 so they never expire during testing.

### Running the seed

Requires `DATABASE_URL` to point at the Neon database (cloud, always-on — nothing to start).

```bash
cd frontend && bun run seed
```

Output:
```
PlanForge — Seeding test users
DB: postgresql://<creds>@ep-xxx-pooler.region.aws.neon.tech/planforge

  ✓  free@planforge.dev  (free) — created
  ✓  basic@planforge.dev  (basic) — created
  ✓  pro@planforge.dev  (pro) — created
```

The script is **idempotent** — re-running it skips existing users and ensures `plan_tier` is correct (useful if a user's tier was accidentally changed).

### What the seed script does

Located at `frontend/scripts/seed-test-users.mjs`:

1. Checks if each email already exists in the `user` table
2. If new: generates a `userId`, hashes the password using the exact same Scrypt parameters that Better Auth / oslo uses (`N=16384 r=8 p=1`, 64-byte key, base64 encoded), inserts into `user` and `account` tables
3. If exists: updates `plan_tier` only (password unchanged)

### Password hash format

Better Auth uses `oslo/password` Scrypt internally. The stored format in the `account.password` column is:

```
<base64(scrypt(password, salt, 64, N=16384, r=8, p=1))>:<16-char-alphanumeric-salt>
```

Total length: 88 (base64) + 1 (colon) + 16 (salt) = **105 characters**.

### Data persistence

Data lives in Neon (cloud-hosted Postgres) — there is no local database or bind-mount to manage. Seed users persist in Neon until explicitly removed.

---

## UI/UX Design System

### Blueprint Dark Theme (`frontend/src/app/globals.css`)

| Token | Value | Usage |
|-------|-------|-------|
| `--background` dark | `oklch(0.085 0.02 255)` | App background |
| `--primary` dark | `oklch(0.58 0.19 230)` | Blueprint blue — CTAs, links |
| `--font-display` | Outfit | Headings, logo |
| `--font-body` | Plus Jakarta Sans | Body text |
| `--font-mono` | JetBrains Mono | Code blocks |

### Utility Classes

| Class | Effect |
|-------|--------|
| `.animate-fade-up` | Fade in + translate-up |
| `.animate-scale-in` | Scale from 95% to 100% |
| `.animate-float` | Continuous vertical float |
| `.delay-100` … `.delay-800` | Animation delay steps |
| `.bg-blueprint-grid` | Animated dot grid hero background |
| `.feature-card` | Hover: lift + glow |
| `.btn-shine` | CTA shine sweep animation |
| `.text-gradient-orange` | Orange gradient text |
| `.text-gradient-blue` | Blue gradient text |
| `.glow-card` | Orange glow (featured pricing card) |

### Logo Pattern

```tsx
<div className="bg-gradient-to-br from-blue-500 to-blue-700">
  {/* icon */}
</div>
<span className={outfit.className}>
  Plan<span className="text-[#f97316]">Forge</span>
</span>
```

---

## Known Patterns & Gotchas

### ShadCN Checkbox in forms

ShadCN `<Checkbox>` renders as `<button>`. Biome's `noLabelWithoutControl` rule rejects wrapping it in `<label>`. Use a `<div>` wrapper instead:

```tsx
// ✗ Biome error
<label><Checkbox /> Parking</label>

// ✓ Correct
<div className="flex items-center gap-2">
  <Checkbox id="parking" ... />
  <span>Parking</span>
</div>
```

### User model + Better Auth

`backend/app/models/user.py` uses `extend_existing=True` because the `"user"` table is owned by Better Auth (Drizzle). SQLAlchemy extends it with `plan_tier`, `plan_expires_at`, and `project_credits` columns without owning the table.

**Gotcha (found 2026-07-03, live):** SQLAlchemy's `default="free"` / `default=0` on these extension columns are Python-side ORM defaults only — they are never pushed to the actual Postgres column as a `DEFAULT`. Since Better Auth (not SQLAlchemy) is what actually `INSERT`s new `user` rows on sign-up, any real sign-up would violate the `NOT NULL` constraint on `project_credits` unless the DB column itself has a `DEFAULT`. Fixed live via `ALTER TABLE "user" ALTER COLUMN "plan_tier" SET DEFAULT 'free'` / `... "project_credits" SET DEFAULT 0`. Any *new* extension column added to this model in the future needs the same explicit DB-level default, or `server_default=` in the SQLAlchemy column definition — an ORM-level `default=` is not enough on a table another system inserts into.

### Frontend → Backend proxy

As of the backend-auth-verification fix (PR #10), the frontend does **not** send an `X-User-Id` header — that was a client-spoofable trust bypass, removed entirely. Two paths now exist:
- **Browser-originated calls** go through `/api/backend/[...path]` (`frontend/src/app/api/backend/[...path]/route.ts`), which validates the Better Auth session server-side via cookie and mints a short-lived HS256 JWT (signed with `INTERNAL_AUTH_SECRET`, shared between frontend and backend) forwarded as `X-Internal-Auth`.
- **Server-side callers that already have a verified session** (team routes, agent chat) use `frontend/src/lib/backend-fetch.ts`'s `fetchBackend(userId, path, init)`, calling FastAPI directly — bypassing the proxy, since an outbound server-side `fetch()` never forwards the original request's cookies.
- Backend verifies the JWT in `backend/app/dependencies/auth.py`'s `get_current_user_id` against `settings.internal_auth_secret`.

### drizzle-kit env loading

`drizzle-kit` does **not** auto-load `.env.local`. Always pass `DATABASE_URL` inline:

```bash
DATABASE_URL="<neon-postgres-connection-string>" \
  bunx drizzle-kit push
```

### ThemeToggle client component

Even if the parent is a Server Component, `ThemeToggle` must be `"use client"` since it calls `useTheme()`.

### Layout IDs from solver

The CP-SAT solver assigns IDs like `"solver-front-0"`, `"solver-mid-0"`, `"solver-rear-0"`. Do not assume `"A"`, `"B"`, `"C"`. All UI code and tests use the IDs from the generate response.

### OR-Tools interval var (OR-Tools 9.x breaking change)

`new_interval_var(x, w, x+w, name)` fails in OR-Tools 9.x because `x+w` is a two-`IntVar` sum (not affine). Fix: introduce explicit end var:

```python
ex = model.new_int_var(0, horizon, f"{name}_end")
model.add(ex == x + w)
model.new_interval_var(x, w, ex, name)
```

### DXF HATCH fill

```python
hatch = msp.add_hatch(dxfattribs={"layer": layer_name})
hatch.set_pattern_fill("ANSI31", scale=0.05)
hatch.paths.add_polyline_path(corners, is_closed=True)
```
`corners` is a list of 2-tuples. Wrap in `try/except` — hatch is non-critical.

### Road width input (frontend)

The "new project" form stores road width in **feet** in React state (user-facing unit), then converts to metres on submit (`ft * 0.3048`). This is intentional — Indian builders think in feet.

---

## Session Log

### 2026-03-03 — OR-Tools Solver Fix, DXF Hatch, Quad Plot, Road Width

**What was built:**

- **OR-Tools 9.x solver fix** — `new_interval_var()` end argument must be an affine expression, not a two-`IntVar` sum. Fixed by introducing explicit `end_var` IntVars. Solver now reliably produces 3 diverse layouts.
- **DXF HATCH fills** — wall area fill using `msp.add_hatch()` + `set_pattern_fill("ANSI31")` + polyline path. `ANSI37` for slab fill. Non-critical: wrapped in `try/except`.
- **Quadrilateral plot compliance fix** — `compliance.py` now uses the same Shapely avg-setback inset geometry as `_quad_floor_plate()` (was using rectangular setbacks inconsistently).
- **Pydantic ConfigDict migration** — confirmed already using `model_config = ConfigDict(env_file=".env")`, CLAUDE.md was stale.
- **Road width input UX fix** — new project form stores road width in feet in React state; converts to metres (`× 0.3048`) on form submit to match backend expectation.
- **Test suite** — 55/55 pytest tests passing on main.

**Key files changed:**

- `backend/app/engine/solver.py` — OR-Tools 9.x interval var fix; 3 layouts verified
- `backend/app/api/routes/export.py` — DXF HATCH fills for wall areas
- `backend/app/engine/compliance.py` — quad setback consistency fix
- `frontend/src/app/(app)/projects/new/page.tsx` — road width ft state + submit conversion

**Patterns established:**

- Never pass `x + w` (two-IntVar sum) directly as OR-Tools interval end — always create explicit end IntVar
- DXF HATCH: always use polyline path (not edge path) for simple polygons
- Quad plot compliance and geometry must use the same inset calculation path or compliance results are meaningless

---

### 2026-03-15 — Dashboard Fix, Dark-Mode UI Accessibility, Build Hardening

**What was built:**

- **Dashboard project list fix** — `/dashboard` was calling the FastAPI backend (`GET /api/projects`) to list projects, which silently returned `[]` if the backend was not running. Replaced with a direct Drizzle query (same pattern as `/projects/[id]` and `/projects/[id]/edit`). Both queries (`projects` + `user.planTier`) are now run in parallel via `Promise.all`. Field references updated from snake_case (`p.plot_length`) to Drizzle camelCase (`p.plotLength`).
- **Dark-mode CSS token overhaul** — raised three low-contrast tokens in `.dark {}`: `--muted-foreground` oklch(0.65→0.78) for readable secondary text; `--border` oklch(0.27→0.36) for visible card/tab/divider edges; `--input` oklch(0.20→0.40) for clearly visible form control borders. Also updated `--sidebar-border` to match.
- **Form control accessibility** — `Input`, `Select`, `Checkbox`, `Tabs`: all now have explicit `dark:border-input` at 1.5px border weight; orange focus glow (`box-shadow: 0 0 0 3px oklch(0.68 0.22 45 / 0.18)`) on focus in dark mode; hover colour brightening on all controls; `hover:scale-105` micro-interaction on checkboxes.
- **Button micro-interactions** — base button now scales `1.02` on hover and `0.98` on press via `transition` + `scale` utilities. Outline variant gets `dark:hover:border-ring/60`.
- **Tabs visibility** — `TabsList` default variant gains `border border-border shadow-sm` so the tab strip is visible as a raised surface. `TabsTrigger` inactive state shows a ghost border on hover; active state has solid `border-input` + `bg-input/40`. Line-variant active indicator colour changed to `--primary` (orange).
- **Card & dropdown elevation** — `Card` gains `dark:shadow-[0_2px_12px_rgba(0,0,0,0.4)]`. `DropdownMenuContent` gains a stronger dark shadow + thin border glow.
- **`prefers-reduced-motion`** — media query added to `globals.css` cancelling all custom animations and trimming all CSS transitions to 0.01ms for users who prefer reduced motion (WCAG 2.3 AAA).
- **`global-error.tsx`** — created minimal `"use client"` error boundary at `src/app/global-error.tsx` with inline styles (no context dependencies) to fix Next.js 16 prerender failure on `/_global-error`.
- **TS fix: `compatibility` prop removed** — `@ai-sdk/openai` v3 removed the `compatibility` option from `OpenAIProviderSettings`. Removed from `route.ts` OpenRouter client initialisation. Build now passes TypeScript strict mode with zero errors.
- **Biome format pass** — `npx biome format --write src/` applied across all 77 frontend source files; 28 files auto-corrected.

**Key files changed:**

- `frontend/src/app/(app)/dashboard/page.tsx` — replaced backend API fetch with direct Drizzle query; `Promise.all` for parallel DB calls; field names updated to camelCase
- `frontend/src/app/globals.css` — `--muted-foreground`, `--border`, `--input`, `--sidebar-border` tokens raised; dark focus-glow rules added; `prefers-reduced-motion` block added; `.dark [data-slot]` border-width 1.5px
- `frontend/src/components/ui/input.tsx` — hover/focus transitions, dark border, dark bg
- `frontend/src/components/ui/checkbox.tsx` — visible border, hover scale, focus ring
- `frontend/src/components/ui/select.tsx` — visible border, dark bg, hover/focus
- `frontend/src/components/ui/tabs.tsx` — `TabsList` border+shadow; `TabsTrigger` hover/active border states; line-variant orange underline
- `frontend/src/components/ui/button.tsx` — `scale-[1.02]` hover, `scale-[0.98]` press, outline dark border improved
- `frontend/src/components/ui/card.tsx` — dark elevation shadow
- `frontend/src/components/ui/dropdown-menu.tsx` — dark shadow + border glow on content
- `frontend/src/app/global-error.tsx` — new; minimal inline-styled error boundary
- `frontend/src/app/api/agent/[projectId]/route.ts` — removed `compatibility` from `createOpenAI()`

**Patterns established:**

- **Dashboard = Drizzle, not API**: Server Components in the app shell should query the DB directly. The backend API is for layout generation/export, not for basic CRUD that the frontend already owns via Drizzle.
- **CSS token "spread"**: When dark-mode elements are invisible, check if `--border`, `--input`, and `--card` lightness values are too close together. Spread them: card ≈ 0.13, border ≈ 0.36, input ≈ 0.40 gives clear visual layering.
- **Bun is the frontend package manager**: `bun install`, `bun dev`, `bun run build`. The lockfile is `bun.lockb` (binary). Do not use `npm install` or `npx` in the frontend — use `bun`/`bunx` equivalents.

---

### 2026-03-15 — Migrate Frontend to Bun

**What was built:**

- **Bun migration** — replaced npm with Bun (v1.3.9) as the frontend package manager, runtime, and test runner. `package-lock.json` removed; `bun.lockb` generated. Added `"packageManager": "bun@1.3.9"` to `package.json`.
- **Test script** — added `"test": "bun test"` to `package.json` scripts, enabling the Bun built-in test runner (Jest-compatible API, no config file needed).
- **`dev-start.sh` updated** — replaced `exec npx next dev --port 3001` with `exec bun dev` so the dev stack script uses the Bun runtime for the frontend process.
- **`frontend/Dockerfile` updated** — base image switched from `node:20-alpine` to `oven/bun:1.3.9-alpine`; `npm ci` → `bun install --frozen-lockfile`; CMD changed from `node server.js` to `bun server.js`.
- **Documentation sweep** — all `npm run`, `npx`, and `node_modules/.bin/` references in README.md, frontend/README.md, CLAUDE.md, docs/developer-reference.md, and the seed script comment updated to `bun`/`bunx` equivalents.

**Key files changed:**

- `frontend/package.json` — `"packageManager": "bun@1.3.9"`, `"test": "bun test"`, `"seed"` now uses `bun`
- `frontend/package-lock.json` — deleted
- `frontend/bun.lockb` — created
- `frontend/Dockerfile` — `oven/bun:1.3.9-alpine` base image throughout all stages
- `dev-start.sh` — line 35: `exec npx next dev` → `exec bun dev`
- `frontend/scripts/seed-test-users.mjs` — usage comment updated
- `README.md`, `frontend/README.md`, `CLAUDE.md`, `docs/developer-reference.md` — npm/npx → bun/bunx throughout

**Patterns established:**

- **Frontend package manager = Bun**: `bun add <pkg>` to add, `bun install` to restore, `bunx` for one-off executables (replaces `npx`). Lockfile is `bun.lockb`.
- **`dev-start.sh` uses `exec bun dev`**: `exec` replaces the subshell so `$!` captures the actual process PID that `dev-stop.sh` kills via `_kill_tree`. This works correctly with Bun as the runtime.
- **`bun test` is zero-config**: Bun's test runner discovers `*.test.ts` / `*.spec.ts` files automatically with no `vitest.config.ts` or `jest.config.js` required.

---

### 2026-03-16 — Full Product Roadmap Sprint (P0 → P3-8)

**What was built:**

All remaining roadmap items implemented via parallel sub-agents with git worktree isolation.

**P0 fixes:**
- `aca53a9` — CAD primitives rendering: ReportLab-native `_pdf_draw_double_line_wall` + `_draw_doors_in_gaps` (replaced broken ezdxf cross-API calls)
- `4516c03` — Blank area auto-fill: `_fill_blank_areas()` fills GF residual → Utility/Store, top floor residual → Open Terrace
- `40af73c` — Structural grid as separate PDF pages 3–4 (architectural plan pages 1–2 unchanged)
- `943b83a` — Duplicate column keys fix (index-based React keys)
- `5085bd2` — OpenRouter support: `OPENROUTER_API_KEY` + `OPENROUTER_MODEL` env vars

**P1 India workflow:**
- `a30a789` — Vastu toggle: enable/disable, 9-zone SVG overlay, per-layout score badge, violation list
- `24b2270` — Share link: `/view/:token` public read-only page, mobile-friendly
- `d09c45f` — WhatsApp share button: one-click thumbnail + link
- `ec5f145` — Municipality bye-law selector: CMDA/BBMP/GHMC/PMC/MCGM city compliance JSONs
- `8c8f44c` — Side-by-side layout comparison with diff highlights

**P2 professional tools:**
- `201ff1d` — BOQ city-wise material rates: 8-city rate table in `material_rates.json`
- `e51c17a` + `4cb6862` — Manual room edit mode: `detectSharedWalls()`, drag handles, co-resize adjacent rooms, live compliance badges (Pro gate); `POST /api/layouts/{id}/compliance-check` endpoint
- `af310ad` — Approval drawing PDF: 4-page municipality package (title block, owner, engineer seal)
- `94a0ba7` — Revision history: auto-snapshots on generate, one-click restore, v1/v2/v3 sidebar
- `ceb23bc` — Interior furniture overlay: 11 SVG symbols (presentation layer, no structural change)
- `02a5f67` — 4BHK support: extended room config form + solver constraints

**P3 growth & distribution:**
- `ff1edc9` — Template gallery: public SEO page filterable by plot size, BHK, city
- `2ee61f3` — Team/firm plan: admin seat + multiple engineer logins, shared project pool
- `d48a201` — Per-project credit pricing: ₹99/project credit packs
- `824aefb` — Tamil + Hindi language support: locale context, cookie persistence, SVG/PDF labels
- `93583ee` — Client approval workflow: Approve/Request Changes via read-only share link
- `339a2ea` — Room annotations: sticky notes on rooms, exported to PDF
- `0e0d968` + `6ba155e` — L-shaped plot support: 6-vertex Shapely polygon, `compute_l_shaped_polygon()`, primary/secondary rectangle decomposition in archetypes, cutout corner (NE/NW/SE/SW), solver half-plane constraints, 13 new tests (108/108 total), frontend polygon rendering + form inputs
- `4e8dc3a` — Electrical overlay: switch/socket/light/fan positions per NBC residential
- `4e8dc3a` — Plumbing overlay: supply spine + drain routing for bathrooms and kitchen
- `41b175c` — Mobile-first responsive redesign: hamburger nav, FAB for new project, bottom Sheet drawer for floor plan controls, responsive tab bar, 44px touch targets, `min-h-11` interactive elements

**Key files changed:**

- `backend/app/engine/generator.py` — blank-area fill, L-shaped polygon, archetype dispatch
- `backend/app/engine/archetypes.py` — `_l_shaped_floor_plate()` primary/secondary decomposition
- `backend/app/engine/pdf.py` — double-line walls, door arcs, annotation rendering, structural pages
- `backend/app/engine/compliance.py` — L-shaped FAR uses inset polygon area (not bounding box)
- `backend/app/engine/boq.py` — city-linked material rates
- `backend/app/engine/approval_pdf.py` — NEW: municipality approval PDF
- `backend/app/models/project.py` — added: share_token, approval_status, approval_note, team_id, annotations, cutout_corner/width/height, revision columns
- `backend/app/models/revision.py` — NEW: ProjectRevision model
- `backend/app/models/team.py` — NEW: Team + TeamMember models
- `backend/app/api/routes/share.py` — NEW: share token + public GET + approve/request-changes
- `backend/app/api/routes/revisions.py` — NEW: revision CRUD + auto-snapshot
- `backend/app/api/routes/teams.py` — NEW: team CRUD + member management
- `backend/app/api/routes/rooms.py` — NEW: `POST /compliance-check` for edit mode validation
- `backend/config/material_rates.json` — NEW: 8-city material rate table
- `backend/config/cities/` — NEW: 6 city compliance JSONs
- `backend/tests/test_l_shaped.py` + `test_l_shaped_plots.py` — NEW: 13 L-shaped tests
- `frontend/src/components/floor-plan-svg.tsx` — Vastu overlay, furniture/electrical/plumbing/annotation props, edit mode drag handles + `detectSharedWalls()`, L-shaped polygon, locale i18n
- `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx` — compare tab, Vastu badges, share dialog, WhatsApp, edit mode toolbar, annotation mode, mobile bottom Sheet, responsive tabs
- `frontend/src/app/(app)/mobile-nav.tsx` — NEW: hamburger menu + slide-in drawer
- `frontend/src/lib/i18n.ts` — NEW: en/ta/hi translation objects
- `frontend/src/lib/locale-context.tsx` — NEW: locale React Context + cookie persistence
- `frontend/src/components/furniture-overlay.tsx` — NEW: 11 furniture symbols
- `frontend/src/components/electrical-overlay.tsx` — NEW: 8 electrical symbols
- `frontend/src/components/plumbing-overlay.tsx` — NEW: supply spine + drain routing

**Patterns established:**

- **Shared wall detection tolerance**: `WALL_TOL = 0.01` (1 cm) — rooms sharing an edge are identified by `|a.x + a.width - b.x| < WALL_TOL`. Float rounding in the solver can produce gaps just below this.
- **L-shaped solver approach**: bounding rectangle as solver input + post-process `_remove_cutout_overlap()` removes rooms where >60% area falls in cutout zone. More robust than polygon constraints.
- **Mobile bottom Sheet pattern**: `import { Sheet, SheetContent, SheetTrigger }` from ShadCN. Trigger = gear icon (`Settings2`), `side="bottom"`, `h-[60vh]`. Desktop toolbar hidden with `hidden md:flex`; Sheet trigger hidden with `md:hidden`.
- **FAB pattern**: `fixed bottom-6 right-6 z-40 rounded-full w-14 h-14 shadow-lg` — only shown at `< sm` breakpoint.
- **Edit mode compliance check**: `POST /api/layouts/{id}/compliance-check` accepts `{ rooms: Room[] }` directly (stateless). Frontend calls it speculatively during drag (debounced 800ms) without committing room state.
- **Testing gap**: frontend has 0 test files. Backend has 108/108. Priority gaps: compliance-check endpoint, share token security, BOQ city rates, revision lifecycle.

---

### 2026-03-16 — SEO, CRO & Brand Asset Integration

**What was built:**

Full SEO hardening and conversion-rate optimisation pass on the marketing site.

**SEO infrastructure:**
- `frontend/src/app/sitemap.ts` — expanded to 8 URLs (added `/gallery`, `/privacy`, `/terms`); correct priority weights (`/pricing` = 0.9, gallery = 0.8)
- `frontend/src/app/robots.ts` — disallow list expanded to include `/account`, `/team`, `/api/`
- `frontend/src/app/layout.tsx` — enriched metadata: 12-keyword array, `lang="en-IN"`, `metadataBase`, canonical, OG/Twitter card, `icons` block (favicon.ico + icon.png + apple-touch-icon)
- `frontend/src/components/json-ld.tsx` — NEW: reusable JSON-LD injector via script tag; content is `JSON.stringify` of own static data objects only (no user input, no XSS risk)
- **Structured data injected per page:**
  - Homepage: `SoftwareApplication` schema + `FAQPage` schema (7 FAQs in details/summary accordion)
  - Pricing: `FAQPage` schema derived from existing `faqs` array
  - How It Works: `HowTo` schema with `totalTime: "PT1M"` and 4 named steps

**CRO improvements:**
- Homepage: FAQ section added using `<details>/<summary>` (zero JS, Google can crawl open content); hero `AnimatedFloorPlan` replaced with `<Image priority />` for LCP improvement
- Marketing layout footer: Privacy Policy + Terms of Service links added to bottom bar
- `frontend/src/app/(marketing)/privacy/page.tsx` — NEW: full privacy policy (data collection, cookies, retention, security, contact)
- `frontend/src/app/(marketing)/terms/page.tsx` — NEW: full ToS (7 sections, governing law: Trichy, Tamil Nadu)
- Pricing page: title updated to include prices (`"Pricing — Free, ₹499 & ₹999/month | PlanForge"`); FAQPage JSON-LD injected

**Brand assets (AI-generated via OpenRouter `google/gemini-3-pro-image-preview`):**
- `frontend/public/favicon.ico` — PF monogram logo (Option A), multi-size bundle: 16/32/48 px (ImageMagick)
- `frontend/src/app/icon.png` — Option A at 512×512 (Next.js App Router static icon)
- `frontend/public/apple-touch-icon.png` — Option A at 180×180
- `frontend/src/app/opengraph-image.png` — isometric G+1 two-storey house (Option C) with PlanForge branding, 1424×752; replaced `opengraph-image.tsx` edge function (static = faster, CDN-cacheable)
- `frontend/public/hero-illustration.png` — colour-coded floor-plan schematic (1200×630) in hero section

**Key files changed:**

- `frontend/src/app/layout.tsx` — enriched metadata object; `icons` block; `lang="en-IN"`
- `frontend/src/app/(marketing)/page.tsx` — FAQ data + accordion; JSON-LD (SoftwareApplication + FAQPage); `<Image>` hero
- `frontend/src/app/(marketing)/pricing/page.tsx` — enriched title/description; FAQPage JSON-LD
- `frontend/src/app/(marketing)/how-it-works/page.tsx` — enriched title; HowTo JSON-LD
- `frontend/src/app/(marketing)/layout.tsx` — Privacy + Terms links in footer
- `frontend/src/app/(marketing)/privacy/page.tsx` — NEW
- `frontend/src/app/(marketing)/terms/page.tsx` — NEW
- `frontend/src/components/json-ld.tsx` — NEW
- `frontend/src/app/sitemap.ts` — 8 URLs
- `frontend/src/app/robots.ts` — expanded disallow list
- `frontend/src/app/opengraph-image.tsx` — DELETED (replaced by static PNG)

**Patterns established:**

- **Static OG image over dynamic `.tsx`**: placing `opengraph-image.png` in `app/` overrides the edge-rendered `.tsx` route. Benefits: no cold-start latency, CDN-cacheable, avoids `@vercel/og` dependency.
- **Biome security linting suppression**: the `biome-ignore` comment must appear on the exact line containing the flagged attribute, not the line above. Placing it one line before produces "unused suppression" warning.
- **FAQ SEO pattern**: `<details>/<summary>` renders open content in HTML — Googlebot indexes it without JavaScript. Combined with `FAQPage` JSON-LD this targets FAQ rich results in SERPs.
- **`lang="en-IN"`**: tells Google India the content is Indian English; affects language-specific ranking signals and local SERP placement.
- **Image generation via OpenRouter**: endpoint `/api/v1/chat/completions`, model `google/gemini-3-pro-image-preview`, response at `choices[0].message.images[0].image_url.url` as `data:image/png;base64,...`. Free-tier Gemini keys hit quota — OpenRouter is the reliable fallback at $0.000002/image.

### 2026-07-03 — Cloud Run Deployment Live, Local Testing Retired, Live DB Wired Up

**What was built:**

Backend deployed to Google Cloud Run for the first time; local dev-server workflow retired in favor of Vercel (frontend) + Cloud Run (backend) as the only real testing surfaces; the frontend's database connection — never previously configured for any live environment — was discovered missing and wired up.

**Cloud Run deployment (Phase 2/3 of `docs/plans/2026-07-02-cloud-run-deployment-implementation-plan.md`):**
- GCP project `thermal-well-451906-b0`, region `us-central1`; Neon project `planforge` (id `plain-brook-17631682`)
- Backend live at `https://planforge-backend-hoiaqu2xbq-uc.a.run.app` ($0-tier: `min-instances=0`, `max-instances=3`)
- WIF-based GitHub Actions deploy (`.github/workflows/deploy-backend.yml`), no service account keys
- Setup automated via `scripts/gcp-cloud-run-setup.sh` (idempotent — GCP auth/project, APIs, Artifact Registry, Neon project + connection string via `neonctl`, WIF trust, budget alert, GitHub secrets, Vercel `INTERNAL_AUTH_SECRET` sync)
- Frontend redeployed with `BACKEND_URL` / `NEXT_PUBLIC_API_URL` pointed at the Cloud Run URL

**Real bugs found and fixed live (not caught by any prior review):**
1. WIF authentication needs **two distinct IAM roles** on the same principal, not one: `roles/iam.workloadIdentityUser` (lets the WIF principal exchange its GitHub OIDC token for federated credentials — enough for `google-github-actions/auth@v3` itself) and separately `roles/iam.serviceAccountTokenCreator` (lets it actually impersonate the service account to mint a real access token — needed specifically by Docker's credential helper for `docker push`). Missing the second role fails with `iam.serviceAccounts.getAccessToken denied`, one step *after* auth already succeeded.
2. Neon's connection string (`sslmode=require&channel_binding=require`) is **libpq syntax that asyncpg doesn't understand**. SQLAlchemy's asyncpg dialect passes every URL query param straight through as a kwarg (`opts.update(url.query)` in `sqlalchemy/dialects/postgresql/asyncpg.py`), and asyncpg's `ssl` kwarg — when given as a string — is validated against `SSLMode` (`disable|allow|prefer|require|verify-ca|verify-full`) only. Fix: strip `sslmode`/`channel_binding`, append `?ssl=require` (not `ssl=true` — that fails the same enum check).
3. **`DATABASE_URL` was never set on Vercel production, for any environment, ever.** `neonctl projects list` confirmed `plain-brook-17631682` (created today) is the *only* Neon project this app has ever had — the "test users" documented below were pure aspiration, never actually seeded against a live database. Confirmed via a real sign-in attempt against production: `ECONNREFUSED 127.0.0.1:5432` (the `postgres` npm package silently defaults to localhost when given `undefined`, rather than throwing at import time).
4. Once `DATABASE_URL` was set, Better Auth's own tables didn't fully exist: the backend's `Base.metadata.create_all()` had already run against the fresh Neon DB (during the Cloud Run deploy) and created a **partial** `"user"` table — only `id`/`plan_tier`/`plan_expires_at`/`project_credits` (its own `extend_existing=True` model, see the gotcha below) — before Drizzle ever defined the full Better Auth columns. `session`/`account`/`verification` didn't exist at all. `drizzle-kit push`'s interactive rename-detection prompt (`is "account" a rename from "project_revisions"?`) isn't scriptable via piped stdin (it's a TUI select, not line-based) and hung under `yes ""`. Fixed by applying the exact DDL from `frontend/src/db/schema.ts` directly via `asyncpg` — safe since the table was still empty (0 rows).
5. **`plan_tier`/`project_credits` had no database-level default** — SQLAlchemy's `default="free"` / `default=0` on `backend/app/models/user.py` are Python-side-only and were never pushed to the actual column. This meant *any* real Better Auth sign-up (not just the seed script) would have hit `null value in column "project_credits" violates not-null constraint` the moment it tried to write a real user row. Fixed with `ALTER TABLE "user" ALTER COLUMN ... SET DEFAULT`.
6. `frontend/scripts/seed-test-users.mjs` then ran successfully against the live DB — the 3 test accounts below are now real and confirmed working via a live `POST /api/auth/sign-in/email` (200, session token returned).

**Local testing workflow retired:**
- Removed `docker-compose.yml`, `dev-start.sh`, `dev-stop.sh` — their only purpose (local multi-service orchestration for manual testing) no longer applies
- `frontend/Dockerfile` moved to `frontend/archive/Dockerfile` and untracked (`frontend/.gitignore`) — unused by the actual deploy path (Vercel builds Next.js natively)
- What still runs locally/in CI: `uv run pytest` (in-memory SQLite, no Neon needed), `ruff`, `bun test`, `biome`, `docker build ./backend` (Dockerfile sanity check only)
- No local dev server, no local Playwright/e2e — real end-to-end checks happen against a Vercel preview deploy (frontend) or Cloud Run (backend)

**Key files changed:** `scripts/gcp-cloud-run-setup.sh` (new), `backend/.env.example`, `frontend/.env.example`, `frontend/.env.local.example`, `CLAUDE.md`, `README.md`, this file.

---

### 2026-07-04 → 2026-07-18 — Structural Design, Async Jobs, CAD v2, PDF Parity, UX Overhaul (consolidated)

**What was built** (spans ~15 sessions and PRs #9–#37, all merged to `main`; grouped here by
theme rather than session — see per-topic memory notes referenced in commit messages for
full blow-by-blow detail):

**Async job architecture:**
- Layout generation and AI rendering moved from synchronous in-request solving to
  **Inngest-backed durable jobs** (`backend/app/api/routes/jobs.py`, `app/inngest_app.py`) —
  root cause was Cloud Run cold starts (~23s measured) blowing past the frontend's original
  15s fetch timeout. Falls back to inline solving when Inngest isn't configured (dev/CI).
- `fetchBackend` (frontend) now accepts a per-call `timeoutMs`; agent tools pass 45s.
- **Gotcha hit in production:** `main` and the `v2` staging lane shared the same Inngest
  `app_id: "planforge"` — jobs from one deployment silently no-op'd against the other's
  event stream. Fixed by giving each its own app id.

**Structural design (StructAgent):**
- New `backend/app/api/routes/structural.py` + `app/services/structagent_client.py` call an
  external IS-code structural design service (`structapi`), gated behind `approve` (freezes
  layout geometry as an immutable revision) → `POST /structural` (design run) →
  `GET /structural/design` (latest non-stale result, matched by geometry hash). Entirely
  optional — off with a clear message when no API key is configured.
- CI byte-diffs the vendored/pinned `structapi` tag on every push/PR and files a weekly
  freshness issue if it drifts.

**CAD & PDF quality (Lane A/B → "v2" → merged to main):**
- Both PDF generators (standard + approval) matched to a reference architectural drawing set
  across all pages: dual-unit dimension labels, area + openings schedule tables, setback
  callouts, scale bars, canonical structural pages.
- New **`SECTION A-A`** (cross-section) and **`FRONT ELEVATION`** pages in both PDFs, built
  from `backend/app/engine/section_geometry.py` → `section_render.py` (IS 962 hatching,
  `vertical_standards.py` dimensions). Front elevation always uses the road-facing (y-min)
  wall regardless of `road_side`, so the correct facade is drawn; main door shown full height.
  A-A cut markers are drawn on the plan pages themselves.
- **Main entrance door (MD)** now a dedicated GF-only pass in `plan_geometry.py`: entry room
  priority living > passage > dining (never parking/stair/wet), door centred toward the
  facade midpoint to align with the compound gate. `Opening.is_main` flag +
  `OpeningStandards.main_door_width_m` (1070mm leaf, NBC min clear 900mm) from
  `compliance_rules.json`.
- R3F 3D canvas labels (solver-produced room/column grid) brought to parity with the solver's
  actual grid — Stage 2 Phase 1A of the structural-automation roadmap.

**Agent chat / AI SDK v6 hardening (recurring source of "connection error" reports):**
- Fixed invalid Anthropic model IDs (`claude-sonnet-4-6`/`claude-opus-4-6` never existed →
  404s) and a fallback predicate that only matched billing/quota errors, not 404s. Provider
  chain now advances on 401/402/404/429/5xx/network errors, with human-readable final
  messages (`frontend/src/lib/agent-errors.ts`, `agent-model-chain.ts`).
- **Gotcha:** AI SDK v6 emits provider failures as stream **error chunks**, not thrown
  exceptions — a `try/catch` around the stream call is dead code for this; fallback must
  inspect stream chunks.
- Fixed v4→v6 tool-part parsing in `chat-panel.tsx` (`part.type === "tool-invocation"` no
  longer exists in v6) via `frontend/src/lib/chat-parts.ts`, built on the SDK's
  `isToolUIPart`/`getToolName` helpers — this is why AI-driven room edits stopped updating
  the canvas preview until fixed.

**Bug-hunt rounds (production-reported issues, fixed via parallel tiered subagents):**
- Solver growth pressure, overlap-safe blank-area fill, per-floor render caching keyed
  correctly, wet-zone (kitchen/toilet) adjacency rule added to the compliance/scorer engine,
  column-grid alignment fix between the solver and the R3F structural overlay. 21 bugs closed
  across PRs #30–#35 in the largest single round (Phase 3 bug hunt, closed 2026-07-18).

**UX / accessibility / platform:**
- Toasts, error boundaries, `not-found` pages, skeleton loading states, inline PDF/DXF
  preview (react-pdf / a dxf-viewer), a11y pass (Phase 4, PR #36).
- Vastu engine test coverage completed (22 new tests covering zone rotation × 4 road sides,
  prohibit/avoid rules), `VASTU_RULES` externalized into `compliance_rules.json`'s
  `vastu_zones` key (was hardcoded Python), dead-code cleanup, a real gallery "use this
  template" CTA bug fixed (was slugifying the display name instead of using the stable
  `plan.id`), 3-step onboarding modal with a `hasSeenOnboarding` DB column (Phase 5, PR #37).

**Deployment:**
- `main` reached parity with the `v2` staging lane (PR #15) and became the sole
  production-deployed branch. A missing `NEXT_PUBLIC_BETTER_AUTH_URL` was found and fixed —
  production auth had been silently posting to `localhost` since launch.
- `v2` staging lane and all its associated branches/worktrees were fully decommissioned on
  2026-07-18 after PR #36 + #37 merged and CI went green — `main` is now the only branch,
  locally and on GitHub.

**Known repo-hygiene gotcha (unresolved, flag before any future schema change):**
`frontend/src/db/migrations/meta/_journal.json` has always had empty `entries` — no real
Drizzle migration history has ever existed for this project. `drizzle-kit generate` therefore
can't produce incremental `ALTER TABLE` migrations; it emits a full baseline `CREATE TABLE`
for all 7 tables every time. The `hasSeenOnboarding` column (Phase 5) had to be applied by
hand via the Neon SQL console instead. Fix this properly (seed the journal against an empty
DB, or hand-write a scoped migration) before the next schema change, rather than repeating
the manual-console workaround.

**Patterns established:**
- Async job endpoints must offer an inline-fallback code path for dev/CI where the job queue
  isn't provisioned — never make Inngest a hard dependency of the endpoint's happy path.
- Any shared infrastructure identifier (Inngest `app_id`, cron names, webhook paths) that two
  deployments of the same codebase both reference must be deployment-scoped, not hardcoded.
- AI SDK v6 provider fallback must be implemented at the stream-chunk level, not via
  `try/catch` around the initial call.
