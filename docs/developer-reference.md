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
16. [UI/UX design system](#uiux-design-system)
17. [Known patterns & gotchas](#known-patterns--gotchas)

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
| Node.js | 20+ |
| Python | 3.12+ |
| uv | latest — `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### Steps

```bash
# 1. Copy env files
cp frontend/.env.local.example frontend/.env.local
# Fill in BETTER_AUTH_SECRET, API keys (see Environment Variables section)

# 2. Install dependencies
npm install --prefix frontend
cd backend && uv sync

# 3. Start (all-in-one)
./dev-start.sh

# 4. First run: push Better Auth schema
cd frontend
DATABASE_URL="postgresql://planforge:planforge@localhost:5432/planforge" \
  npx drizzle-kit push
```

Access the app at `http://localhost:3001`. API docs at `http://localhost:8002/docs`.

### Manual start

```bash
docker compose up db -d
cd backend && uv run uvicorn app.main:app --reload --port 8002
cd frontend && PORT=3001 npm run dev
```

---

## Environment Variables

### `frontend/.env.local`

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✓ | PostgreSQL for Drizzle — `postgresql://planforge:planforge@localhost:5432/planforge` |
| `BETTER_AUTH_SECRET` | ✓ | ≥32-char random secret — run `npx @better-auth/cli secret` |
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
npm run test:e2e          # headless
npm run test:e2e:ui       # interactive
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
npx biome check .             # lint + format check
npx biome format --write .    # auto-format
npx tsc --noEmit              # type check
```

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
  npx drizzle-kit push
```

### ThemeToggle client component

Even if the parent is a Server Component, `ThemeToggle` must be `"use client"` since it calls `useTheme()`.

### Layout IDs from solver

The CP-SAT solver assigns IDs like `"solver-front-0"`, `"solver-mid-0"`, `"solver-rear-0"`. Do not assume `"A"`, `"B"`, `"C"`. All UI code and tests use the IDs from the generate response.
