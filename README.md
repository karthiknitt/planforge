# PlanForge

> CAD-grade G+1 residential floor plan generator for Indian small builders and civil engineers.

PlanForge takes a plot's dimensions, setbacks, and room configuration and instantly generates three compliant layout variations — complete with SVG preview, section view, Bill of Quantities, PDF drawing, and DXF export.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.129-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Tests](https://img.shields.io/badge/backend%20tests-21%20passed-22c55e)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## Table of Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Environment variables](#environment-variables)
- [API reference](#api-reference)
- [Running tests](#running-tests)
- [Compliance rules](#compliance-rules)
- [Pricing plans](#pricing-plans)
- [Roadmap](#roadmap)

---

## Features

### Layout & Planning
- **Three layout archetypes** — Front staircase (A), Centre staircase (B), Rear staircase (C), generated deterministically from plot inputs
- **Rectangular and trapezoid plots** — supports standard rectangular and trapezoidal plots with differing front/rear widths
- **2BHK and 3BHK** — user selects bedroom count, number of toilets, and parking
- **Plot input in feet** — all dimensions entered in feet; automatically converted to metres internally with 3-decimal precision

### Compliance Engine
- Indian building compliance: bedroom ≥ 9.5 m², kitchen ≥ 7 m², toilet ≥ 3 m², stair width ≥ 900 mm
- Floor coverage percentage (FAR) validation
- Setback enforcement on all four sides
- Ventilation and kitchen window checks
- Beam span warnings at > 4.5 m
- City-specific rule presets (Bangalore, Chennai, Mumbai, Hyderabad)
- Rules stored in `compliance_rules.json` — adjustable without code changes

### Vastu Shastra Engine
- 8-zone Vastu analysis (N / NE / E / SE / S / SW / W / NW)
- Road-side aware room placement scoring
- Per-room Vastu violations and warnings surfaced in the UI

### CAD-Grade Drawing Output
- **SVG floor plan preview** — colour-coded rooms, double-line walls (230 mm external / 115 mm internal), door arcs with D-label, window frame symbols with W-delimiters, column markers, dimension lines, scale bar, north arrow
- **Section view** — parametric 2D section (ground floor, slab, first floor, parapet) with height annotations
- **PDF export** — two-page A4 drawing (ground + first floor) at 1:100 scale with title block, room labels, dimensions, and north arrow
- **DXF export** — AutoCAD-compatible with named layers: `WALL_EXT`, `WALL_INT`, `DOORS`, `WINDOWS`, `COLUMNS`, `DIMENSIONS`, `TEXT`

### Bill of Quantities (BOQ)
- Per-room area breakdown
- Estimated concrete, brick, and plaster quantities
- Excel export (Pro plan)

### Product & Auth
- **Marketing site** — landing page, pricing page, how-it-works walkthrough
- **Email/password auth** — sign-up, sign-in, sign-out via Better Auth
- **Project management** — create, edit, save, and regenerate layouts per project
- **Dark / light mode** — system-aware theme toggle
- **Razorpay payments** — Basic (₹499/month) and Pro (₹999/month) plans with HMAC-verified webhook
- **Feature gating** — Free: 3 projects max; Basic: DXF export unlocked; Pro: Excel BOQ export unlocked
- **Account page** — plan badge, expiry date, upgrade CTA

---

## How it works

```
Plot inputs  →  Layout engine  →  Compliance + Vastu  →  SVG/Section preview  →  PDF / DXF export
(feet input,    (3 archetypes,      (violations,            (browser, tabs:          (download)
 setbacks,       parametric          warnings,               Floor Plan |
 BHK, city)      slicing)            Vastu zones)            Section View | BOQ)
```

1. User enters plot dimensions in feet, setbacks, road side, BHK count, toilets, parking, and city.
2. Backend generates three layouts using parametric proportional room slicing.
3. Each layout is validated against compliance rules and Vastu zone rules.
4. The frontend renders SVG floor plans with CAD-standard wall and door/window symbols.
5. User switches between Floor Plan, Section View, and BOQ tabs.
6. User selects a layout and downloads a PDF drawing or DXF file.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript |
| Styling | Tailwind CSS v4, ShadCN UI |
| Auth | Better Auth (session-based, Drizzle adapter, `nextCookies` plugin) |
| Frontend ORM | Drizzle ORM + drizzle-kit |
| Backend | FastAPI, Python 3.12 |
| Layout engine | Pure Python + Shapely |
| PDF rendering | ReportLab |
| DXF export | ezdxf |
| Database | PostgreSQL 16 |
| Backend ORM | SQLAlchemy (async) + asyncpg |
| Payments | Razorpay (order creation + HMAC verification) |
| Linter / formatter | Biome (frontend) |
| Package managers | npm (frontend), uv (backend) |
| E2E testing | Playwright (Chromium) |
| Infrastructure | Docker Compose |

---

## Project structure

```
PlanForge/
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   │   ├── export.py        # PDF + DXF + BOQ export endpoints
│   │   │   ├── generate.py      # Layout generation endpoint
│   │   │   ├── health.py        # Health check
│   │   │   ├── payments.py      # Razorpay order + verify
│   │   │   └── projects.py      # CRUD /api/projects
│   │   ├── config/
│   │   │   └── compliance_rules.json
│   │   ├── engine/
│   │   │   ├── archetypes.py    # Layout A / B / C room placement
│   │   │   ├── compliance.py    # Rule checker
│   │   │   ├── dxf.py           # ezdxf DXF renderer
│   │   │   ├── generator.py     # Orchestrates all 3 layouts + Vastu
│   │   │   ├── models.py        # Dataclasses: Room, Column, FloorPlan, Layout
│   │   │   ├── pdf.py           # ReportLab PDF renderer
│   │   │   └── vastu.py         # Vastu Shastra zone engine
│   │   ├── models/
│   │   │   ├── project.py       # SQLAlchemy Project model
│   │   │   └── user.py          # SQLAlchemy User model (plan_tier, plan_expires_at)
│   │   ├── schemas/             # Pydantic I/O schemas
│   │   ├── db.py                # Async engine + session factory
│   │   └── main.py              # FastAPI app + router registration + lifespan
│   ├── tests/
│   │   ├── conftest.py          # Async client fixture (SQLite in-memory)
│   │   ├── test_api_e2e.py      # Full workflow API tests (9 tests)
│   │   ├── test_engine.py       # Layout engine unit tests (10 tests)
│   │   └── test_health.py       # Health endpoint tests (2 tests)
│   └── pyproject.toml
│
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── (app)/            # Authenticated routes
│       │   │   ├── account/      # Plan badge, expiry, upgrade CTA
│       │   │   ├── dashboard/    # Project list with plan badge
│       │   │   └── projects/
│       │   │       ├── [id]/     # Layout viewer (Floor Plan | Section View | BOQ)
│       │   │       ├── [id]/edit # Edit project + regenerate
│       │   │       └── new/      # Create project form (feet input)
│       │   ├── (auth)/           # Sign-in / sign-up pages
│       │   ├── (marketing)/      # Landing, pricing, how-it-works
│       │   └── api/auth/         # Better Auth Next.js handler
│       ├── components/
│       │   ├── floor-plan-svg.tsx    # SVG renderer (walls, doors, windows, columns)
│       │   ├── section-view-svg.tsx  # Parametric section view renderer
│       │   ├── boq-viewer.tsx        # Bill of Quantities table + Excel export
│       │   ├── layout-viewer.tsx     # Tabbed viewer (Floor Plan | Section | BOQ)
│       │   ├── pricing-checkout-button.tsx  # Razorpay checkout client component
│       │   └── ui/               # ShadCN components
│       ├── db/                   # Drizzle schema + client
│       ├── proxy.ts              # Next.js 16 route protection
│       └── lib/
│           ├── auth.ts           # Better Auth server instance
│           └── auth-client.ts    # Better Auth browser client
│
├── frontend/tests/e2e/           # Playwright E2E tests
│   ├── auth.setup.ts             # Creates test user, saves session
│   ├── public-routes.unauth.spec.ts   # 8 unauthenticated tests
│   └── app-flows.auth.spec.ts         # 9 authenticated tests
│
├── docker-compose.yml
├── dev-start.sh                  # Start full dev stack in one command
├── dev-stop.sh                   # Stop everything cleanly
└── CLAUDE.md                     # AI coding assistant context
```

---

## Getting started

### Prerequisites

| Tool | Version | Install |
|---|---|---|
| Docker | 24+ | [docker.com](https://www.docker.com) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| Python | 3.12+ | [python.org](https://www.python.org) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### 1. Clone

```bash
git clone https://github.com/karthiknitt/planforge.git
cd planforge
```

### 2. Configure environment

```bash
cp frontend/.env.local.example frontend/.env.local
```

Open `frontend/.env.local` and fill in the required values — see [Environment variables](#environment-variables).

> **Generate a secure auth secret before running:**
> ```bash
> npx @better-auth/cli secret
> # Paste the output as BETTER_AUTH_SECRET in .env.local
> ```

### 3. Install dependencies

```bash
# Frontend
npm install --prefix frontend

# Backend
cd backend && uv sync
```

### 4. Start the dev stack

```bash
./dev-start.sh
```

Starts PostgreSQL (waits for health check), then launches the backend and frontend. PIDs saved to `.dev.pids`; logs stream to `.dev-logs/`.

```bash
tail -f .dev-logs/backend.log
tail -f .dev-logs/frontend.log
./dev-stop.sh   # stop everything
```

> **First run only** — push the Better Auth schema to the database:
> ```bash
> cd frontend
> DATABASE_URL="postgresql://planforge:planforge@localhost:5432/planforge" \
>   npx drizzle-kit push
> ```

### 5. Manual start (optional)

```bash
# 1. Database
docker compose up db -d

# 2. Backend  →  http://localhost:8002
cd backend && uv run uvicorn app.main:app --reload --port 8002

# 3. Frontend →  http://localhost:3001
cd frontend && PORT=3001 npm run dev
```

### 6. Open the app

| Service | URL |
|---|---|
| App | http://localhost:3001 |
| Backend API | http://localhost:8002 |
| Swagger / OpenAPI docs | http://localhost:8002/docs |

---

## Environment variables

### `frontend/.env.local`

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL URL for Drizzle (schema migrations) | `postgresql://planforge:planforge@localhost:5432/planforge` |
| `BETTER_AUTH_SECRET` | ≥ 32-char random secret for session signing | run `npx @better-auth/cli secret` |
| `BETTER_AUTH_URL` | Canonical base URL of the frontend | `http://localhost:3001` |
| `NEXT_PUBLIC_BETTER_AUTH_URL` | Same value, exposed to the browser | `http://localhost:3001` |
| `NEXT_PUBLIC_API_URL` | FastAPI backend base URL | `http://localhost:8002` |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID` | Razorpay test/live key (optional — payments only) | `rzp_test_...` |

### `backend/.env`

| Variable | Description |
|---|---|
| `DATABASE_URL` | Async PostgreSQL URL for SQLAlchemy |
| `RAZORPAY_KEY_ID` | Razorpay key ID (required for payments) |
| `RAZORPAY_KEY_SECRET` | Razorpay secret (required for payment HMAC verification) |

---

## API reference

All endpoints are prefixed with `/api`. Authenticated endpoints require the user's ID in an `X-User-Id` header.

### Health

```
GET  /api/health  →  200  { "status": "ok" }
```

### Projects

```
POST /api/projects          Create a project
GET  /api/projects          List projects for authenticated user
GET  /api/projects/{id}     Get a single project
PUT  /api/projects/{id}     Update project inputs
```

**POST / PUT body example:**

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
  "bhk": 2,
  "toilets": 2,
  "parking": false,
  "city": "Chennai",
  "vastu_enabled": true
}
```

`road_side` accepts `"N"`, `"S"`, `"E"`, `"W"`. `bhk` accepts `2` or `3`. `plot_shape` accepts `"rectangular"` or `"trapezoid"`.

### Layout generation

```
GET /api/projects/{id}/generate
→ 200  { "project_id": "...", "layouts": [ ... ] }
```

Returns all three layouts. Each includes `ground_floor` and `first_floor` (rooms + columns), a `compliance` result, and an optional `vastu` result.

### Exports

```
GET /api/projects/{id}/export/pdf?layout_id=A       → application/pdf   (all plans)
GET /api/projects/{id}/export/dxf?layout_id=A       → application/dxf   (Basic+ plans)
GET /api/projects/{id}/export/boq?layout_id=A       → application/json  (all plans)
GET /api/projects/{id}/export/boq/excel?layout_id=A → application/xlsx  (Pro plan)
```

`layout_id` accepts `A`, `B`, or `C`.

### Payments

```
POST /api/payments/order    Create a Razorpay order
POST /api/payments/verify   Verify HMAC + activate plan tier
```

Full interactive docs: [`http://localhost:8002/docs`](http://localhost:8002/docs)

---

## Running tests

### Backend (21 tests)

```bash
cd backend
uv run pytest tests/ -v
```

Uses an in-memory SQLite database via `tests/conftest.py` — no running PostgreSQL needed.

### Frontend E2E tests (Playwright — 17 tests)

Requires the full dev stack running.

```bash
docker compose up db -d
cd frontend
PORT=3001 npm run dev &

npm run test:e2e          # headless Chromium
npm run test:e2e:ui       # Playwright interactive UI
npm run test:e2e:debug    # step-through debugger
```

**Test suites:**

| Suite | Coverage |
|---|---|
| `auth.setup.ts` | Creates E2E test user, saves session cookies |
| `public-routes.unauth.spec.ts` | Landing/pricing/how-it-works load without auth; /dashboard redirects; wrong credentials error; duplicate sign-up error; short password blocked |
| `app-flows.auth.spec.ts` | Dashboard loads; auth redirect from /sign-in; account page plan badge; new project form; sign-out; /pricing accessible when logged in |

### Frontend type check + lint

```bash
cd frontend
npx tsc --noEmit
npm run lint
```

---

## Compliance rules

Stored in `backend/app/config/compliance_rules.json`:

```json
{
  "min_bedroom_sqm": 9.5,
  "min_kitchen_sqm": 7.0,
  "min_toilet_sqm": 3.0,
  "min_stair_width_mm": 900,
  "external_wall_thickness_mm": 230,
  "internal_wall_thickness_mm": 115,
  "max_beam_span_m": 4.5,
  "max_floor_coverage_pct": 70
}
```

City-specific overrides adjust setback and coverage rules per local bylaws. Layouts failing hard rules are rejected; beam span and ventilation issues surface as warnings.

---

## Pricing plans

| Feature | Free | Basic (₹499/mo) | Pro (₹999/mo) |
|---|---|---|---|
| Projects | 3 max | Unlimited | Unlimited |
| Layout generation | ✓ | ✓ | ✓ |
| SVG + Section View | ✓ | ✓ | ✓ |
| BOQ (view) | ✓ | ✓ | ✓ |
| PDF export | ✓ | ✓ | ✓ |
| DXF / AutoCAD export | ✗ | ✓ | ✓ |
| BOQ Excel export | ✗ | ✗ | ✓ |

Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `backend/.env` to enable checkout.

---

## Roadmap

MVP is shipped. Planned post-launch expansions:

- [ ] Full quadrilateral (arbitrary 4-sided) plot support
- [ ] Dynamic constraint solver — replace fixed archetypes with adaptive room placement
- [ ] Arbitrary room counts and custom room names
- [ ] Reinforcement BOQ — steel takeoff for columns, beams, and slabs
- [ ] Location-aware building bylaw engine — per-city regulation packs
- [ ] Shareable project links / public plan viewer
- [ ] Mobile-responsive layout viewer

---

## License

MIT © Karthikeyan Natarajan
