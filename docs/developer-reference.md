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
        ├── /api/agent/*        ← Agentic chat (Vercel AI SDK + Claude)
        ├── /api/transcribe     ← OpenAI Whisper voice input
        └── proxy.ts            ← Session-based route protection

FastAPI (Python 3.12)
  └── /api/*
        ├── /projects           ← CRUD
        ├── /projects/{id}/generate     ← Layout generation
        ├── /projects/{id}/export/*     ← PDF / DXF / BOQ
        ├── /payments/*         ← Razorpay
        └── /rooms/*            ← In-memory room editor (agentic, Pro)

PostgreSQL 16
  ├── Better Auth tables (Drizzle)  ← user, session, account, verification
  └── Backend tables (SQLAlchemy)   ← projects, users (plan_tier)
```

---

## Project Structure

```
PlanForge/
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   │   ├── export.py        # PDF + DXF + BOQ exports
│   │   │   ├── generate.py      # GET /projects/{id}/generate
│   │   │   ├── health.py        # GET /api/health
│   │   │   ├── payments.py      # POST /payments/order + /verify
│   │   │   ├── projects.py      # CRUD /projects
│   │   │   └── rooms.py         # In-memory room editor + undo stack
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
│       │   ├── floor-plan-svg.tsx     # SVG renderer
│       │   ├── section-view-svg.tsx   # Section renderer
│       │   ├── boq-viewer.tsx         # BOQ table + Excel export
│       │   ├── chat-panel.tsx         # Agentic chat UI
│       │   ├── pricing-checkout-button.tsx  # Razorpay client
│       │   └── ui/                    # ShadCN components
│       ├── db/
│       │   ├── index.ts               # Drizzle client
│       │   └── schema.ts              # Better Auth tables + project columns
│       ├── hooks/
│       │   └── use-voice-input.ts     # MediaRecorder + Whisper integration
│       ├── lib/
│       │   ├── auth.ts                # Better Auth server config
│       │   ├── auth-client.ts         # Better Auth browser client
│       │   ├── layout-types.ts        # TypeScript types mirroring backend schemas
│       │   └── utils.ts               # cn() + misc
│       └── proxy.ts                   # Session-based middleware redirect
│
├── docs/                        # This file lives here
├── docker-compose.yml
├── dev-start.sh / dev-stop.sh
└── CLAUDE.md
```

---

## Getting Started

### Prerequisites

| Tool | Version |
|------|---------|
| Docker | 24+ |
| Bun | 1.3+ — `curl -fsSL https://bun.sh/install \| bash` |
| Python | 3.12+ |
| uv | latest — `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### Steps

```bash
# 1. Copy env files
cp frontend/.env.local.example frontend/.env.local
# Fill in BETTER_AUTH_SECRET, API keys (see Environment Variables section)

# 2. Install dependencies
cd frontend && bun install
cd backend && uv sync

# 3. Start (all-in-one)
./dev-start.sh

# 4. First run: push Better Auth schema
cd frontend
DATABASE_URL="postgresql://planforge:planforge@localhost:5432/planforge" \
  bunx drizzle-kit push
```

Access the app at `http://localhost:3001`. API docs at `http://localhost:8002/docs`.

### Manual start

```bash
docker compose up db -d
cd backend && uv run uvicorn app.main:app --reload --port 8002
cd frontend && bun dev
```

---

## Environment Variables

### `frontend/.env.local`

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✓ | PostgreSQL for Drizzle — `postgresql://planforge:planforge@localhost:5432/planforge` |
| `BETTER_AUTH_SECRET` | ✓ | ≥32-char random secret — run `bunx @better-auth/cli secret` |
| `BETTER_AUTH_URL` | ✓ | Canonical frontend URL — `http://localhost:3001` |
| `NEXT_PUBLIC_BETTER_AUTH_URL` | ✓ | Same, exposed to browser |
| `NEXT_PUBLIC_API_URL` | ✓ | Backend base URL — `http://localhost:8002` |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID` | optional | Razorpay test key |
| `OPENAI_API_KEY` | optional | Whisper voice transcription |
| `ANTHROPIC_API_KEY` | optional | Agentic chat (Claude Sonnet/Opus) |

### `backend/.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✓ | Async PostgreSQL — `postgresql+asyncpg://planforge:planforge@localhost:5432/planforge` |
| `RAZORPAY_KEY_ID` | optional | Required to create payment orders |
| `RAZORPAY_KEY_SECRET` | optional | Required for HMAC verification |

---

## Backend — API Reference

All routes are prefixed with `/api`. Authenticated routes expect `X-User-Id: <user_id>` header.

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

### Rooms (Agentic Editor — Pro only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/rooms/{project_id}/state` | Get current in-memory layout state |
| POST | `/api/rooms/{project_id}/move` | Move a room (Shapely validated) |
| POST | `/api/rooms/{project_id}/resize` | Resize a room |
| POST | `/api/rooms/{project_id}/undo` | Undo last action (deque, maxlen=10) |

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
- Hard constraints: rooms fit within floor plate, no overlaps, staircase width ≥ 900 mm
- Soft objectives: adjacency preferences, natural light (exterior wall proximity)
- 3 runs forced with staircase at front / mid / rear for layout diversity
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
| Toilet area | ≥ 3.0 m² | Violation |
| Stair width | ≥ 900 mm | Violation |
| FAR / floor coverage | ≤ 70% | Violation |
| Setbacks | per input | Violation |
| Living room area | ≥ 12 m² | Warning |
| Beam span | ≤ 4.5 m | Warning |
| Kitchen ventilation | external wall access | Warning |
| Bath ventilation | window or mech vent | Warning |

Layouts failing any violation are returned with `compliance.passed = false`. They are still shown to the user with violations listed.

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

Five weighted components, total score 0–100:

| Component | Weight | Method |
|-----------|--------|--------|
| `natural_light` | 25% | Ratio of rooms touching exterior walls |
| `adjacency` | 25% | Preferred room-pair adjacency satisfaction |
| `aspect_ratio` | 20% | Per-room width:depth ratio (target 1:1.5) |
| `circulation` | 15% | Staircase centrality + corridor efficiency |
| `vastu` | 15% | Vastu rule satisfaction ratio |

`rank_and_select()` sorts layouts by `score.total` (descending) and returns top 3. Layout IDs assigned by the solver run (e.g., `"solver-front-0"`) — **not** guaranteed to be `A/B/C`.

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

Three test users are pre-seeded into the database with different plan tiers so you can verify all gated features without going through the Razorpay payment flow.

### Credentials

| Email | Password | Plan | Features accessible |
|-------|----------|------|-------------------|
| `free@planforge.dev` | `Test@1234` | Free | Dashboard, 3 projects max, SVG preview, Section View, BOQ (view), PDF export |
| `basic@planforge.dev` | `Test@1234` | Basic | All Free features + unlimited projects + DXF export |
| `pro@planforge.dev` | `Test@1234` | Pro | All Basic features + BOQ Excel export + Agentic chat (room editor, voice input) |

The `basic` and `pro` accounts have `plan_expires_at` set to 2099-12-31 so they never expire during testing.

### Running the seed

Requires the database to be running first.

```bash
docker compose up db -d
cd frontend && bun run seed
```

Output:
```
PlanForge — Seeding test users
DB: postgresql://<creds>@localhost:5432/planforge

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

The PostgreSQL data is stored in `./data/postgres/` (bind-mount, not a named volume). This directory survives `docker compose down -v` and container restarts. The seed users persist as long as this directory exists.

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

`backend/app/models/user.py` uses `extend_existing=True` because the `"user"` table is owned by Better Auth (Drizzle). SQLAlchemy extends it with `plan_tier` and `plan_expires_at` columns without owning the table.

### Frontend → Backend proxy

The frontend proxies `/api/*` requests to the backend via `NEXT_PUBLIC_API_URL`. The `X-User-Id` header is added by server actions / API route handlers after extracting the session from Better Auth.

### drizzle-kit env loading

`drizzle-kit` does **not** auto-load `.env.local`. Always pass `DATABASE_URL` inline:

```bash
DATABASE_URL="postgresql://planforge:planforge@localhost:5432/planforge" \
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
