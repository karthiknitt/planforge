# PlanForge

> G+1 residential floor plan generator for Indian small builders and civil engineers.

PlanForge takes a rectangular plot's dimensions, setbacks, and room configuration, and instantly produces three compliant layout variations — with a downloadable, print-ready PDF drawing for each.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.129-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Tests](https://img.shields.io/badge/tests-21%20passed-22c55e)
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
- [Roadmap](#roadmap)

---

## Features

- **Three layout archetypes** — Front staircase, Centre staircase, Rear staircase — generated deterministically from plot inputs
- **Indian building compliance** — validates bedroom, kitchen, and toilet minimum areas; stair width; setbacks; and floor coverage percentage
- **Structural column grid** — columns placed at outer corners, staircase core, and major wall intersections; beam span warnings at > 4.5 m
- **SVG floor plan preview** — interactive browser preview with colour-coded rooms and a north arrow
- **PDF export** — two-page A4 drawing (ground floor + first floor) with room labels, area annotations, dimension callouts, north arrow, scale bar, and title block
- **Project management** — save and retrieve multiple projects per account
- **Auth** — email/password sign-up and sign-in via Better Auth

---

## How it works

```
Plot inputs  →  Layout engine  →  Compliance check  →  SVG preview  →  PDF export
(dimensions,    (3 archetypes,     (violations /         (browser)       (download)
 setbacks,       parametric         warnings)
 BHK config)     slicing)
```

1. User enters plot dimensions, setbacks, road side, north direction, BHK count, toilets, and parking preference.
2. The backend layout engine generates three layouts (A / B / C) using deterministic proportional room slicing.
3. Each layout is checked against compliance rules loaded from `backend/app/config/compliance_rules.json`.
4. The frontend renders the floor plans as SVG with colour-coded room types.
5. The user selects a layout and downloads a 2-page PDF drawing.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript |
| Styling | Tailwind CSS v4, ShadCN UI |
| Auth | Better Auth (session-based, Drizzle adapter) |
| Frontend ORM | Drizzle ORM |
| Backend | FastAPI, Python 3.12 |
| Layout engine | Pure Python + Shapely |
| PDF rendering | ReportLab |
| Database | PostgreSQL 16 |
| Backend ORM | SQLAlchemy (async) + asyncpg |
| Linter / formatter | Biome (frontend) |
| Package managers | npm (frontend), uv (backend) |
| Infrastructure | Docker Compose |

---

## Project structure

```
PlanForge/
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   │   ├── export.py       # GET /api/projects/{id}/export/pdf
│   │   │   ├── generate.py     # GET /api/projects/{id}/generate
│   │   │   ├── health.py       # GET /api/health
│   │   │   └── projects.py     # CRUD /api/projects
│   │   ├── config/
│   │   │   └── compliance_rules.json
│   │   ├── engine/
│   │   │   ├── archetypes.py   # Layout A / B / C room placement
│   │   │   ├── compliance.py   # Rule checker
│   │   │   ├── generator.py    # Orchestrates all 3 layouts
│   │   │   ├── models.py       # Dataclasses: Room, Column, FloorPlan, Layout
│   │   │   └── pdf.py          # ReportLab PDF renderer
│   │   ├── models/
│   │   │   └── project.py      # SQLAlchemy Project model
│   │   ├── schemas/            # Pydantic I/O schemas
│   │   ├── db.py               # Async engine + session factory
│   │   └── main.py             # FastAPI app + router registration
│   ├── tests/
│   │   ├── conftest.py         # Async client fixture (SQLite in-memory)
│   │   ├── test_api_e2e.py     # Full workflow API tests (9 tests)
│   │   ├── test_engine.py      # Layout engine unit tests (10 tests)
│   │   └── test_health.py      # Health endpoint tests (2 tests)
│   └── pyproject.toml
│
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── (app)/           # Authenticated routes
│       │   │   ├── dashboard/   # Project list
│       │   │   └── projects/
│       │   │       ├── [id]/    # Project detail + layout viewer
│       │   │       └── new/     # Create project form
│       │   ├── (auth)/          # Sign-in / sign-up pages
│       │   └── api/auth/        # Better Auth Next.js handler
│       ├── components/
│       │   ├── floor-plan-svg.tsx   # SVG renderer
│       │   └── ui/                  # ShadCN components
│       ├── db/                  # Drizzle schema + client
│       └── lib/
│           ├── auth.ts          # Better Auth server instance
│           └── auth-client.ts   # Better Auth browser client
│
├── docker-compose.yml
├── dev-start.sh                 # Start the full dev stack in one command
├── dev-stop.sh                  # Stop everything cleanly
└── CLAUDE.md                    # AI coding assistant context
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

Open `frontend/.env.local` and fill in the values — see [Environment variables](#environment-variables).

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

This starts PostgreSQL (waits for the health check), then launches the backend and frontend in the background. Process IDs are saved to `.dev.pids`; logs stream to `.dev-logs/`.

```bash
# Watch logs
tail -f .dev-logs/backend.log
tail -f .dev-logs/frontend.log

# Stop everything
./dev-stop.sh
```

> **First run only** — apply the database schema before starting the frontend:
> ```bash
> cd frontend
> DATABASE_URL="postgresql://planforge:planforge@localhost:5432/planforge" \
>   npx drizzle-kit push
> ```

### 5. Manual start (optional)

If you prefer to run each service yourself:

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

Sign up, create a project, and click **Download PDF** on the project detail page to export a floor plan.

---

## Environment variables

### `frontend/.env.local`

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL URL for Drizzle (schema migrations) | `postgresql://planforge:planforge@localhost:5432/planforge` |
| `BETTER_AUTH_SECRET` | Secret key used to sign sessions (min 32 chars) | `change-me-in-production` |
| `BETTER_AUTH_URL` | Canonical base URL of the frontend | `http://localhost:3001` |
| `NEXT_PUBLIC_BETTER_AUTH_URL` | Same value, exposed to the browser | `http://localhost:3001` |
| `NEXT_PUBLIC_API_URL` | FastAPI backend base URL | `http://localhost:8002` |

### `backend/.env` (optional)

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Async PostgreSQL URL for SQLAlchemy | `postgresql+asyncpg://planforge:planforge@localhost:5432/planforge` |

---

## API reference

All endpoints are prefixed with `/api`. The frontend passes the authenticated user's ID via an `X-User-Id` header.

### Health

```
GET /api/health
→ 200  { "status": "ok" }
```

### Projects

```
POST /api/projects        Create a project
GET  /api/projects        List all projects for the authenticated user
```

**Request body for `POST /api/projects`:**

```json
{
  "name": "My Plot",
  "plot_length": 12.0,
  "plot_width": 9.0,
  "setback_front": 1.5,
  "setback_rear": 1.5,
  "setback_left": 1.0,
  "setback_right": 1.0,
  "road_side": "S",
  "north_direction": "N",
  "bhk": 2,
  "toilets": 2,
  "parking": false
}
```

`road_side` and `north_direction` accept `"N"`, `"S"`, `"E"`, or `"W"`. `bhk` accepts `2` or `3`.

### Layout generation

```
GET /api/projects/{id}/generate
→ 200  { "project_id": "...", "layouts": [ ... ] }
```

Returns all three layouts. Each layout contains `ground_floor` and `first_floor` floor plans (rooms + columns) and a `compliance` result with any violations or warnings.

### PDF export

```
GET /api/projects/{id}/export/pdf?layout_id=A
→ 200  application/pdf
```

`layout_id` accepts `A`, `B`, or `C` (defaults to `A`). The response includes a `Content-Disposition: attachment` header so browsers trigger a file download automatically.

Full interactive API documentation with request/response schemas is available at [`/docs`](http://localhost:8002/docs).

---

## Running tests

### Backend

```bash
cd backend
uv run pytest tests/ -v
```

```
tests/test_api_e2e.py::test_health_check               PASSED
tests/test_api_e2e.py::test_create_and_list_project    PASSED
tests/test_api_e2e.py::test_generate_layouts           PASSED
tests/test_api_e2e.py::test_export_pdf_all_layouts     PASSED
tests/test_api_e2e.py::test_full_workflow              PASSED
tests/test_api_e2e.py::test_missing_user_id_returns_422 PASSED
tests/test_api_e2e.py::test_invalid_layout_id_returns_404 PASSED
tests/test_api_e2e.py::test_validation_rejects_bad_payload PASSED
tests/test_api_e2e.py::test_3bhk_project               PASSED
tests/test_engine.py  (10 tests)                       PASSED
tests/test_health.py  (2 tests)                        PASSED

21 passed
```

The e2e tests use an in-memory SQLite database injected via `tests/conftest.py` — no running PostgreSQL is required.

### Frontend

```bash
cd frontend
npm run lint       # Biome lint
npx tsc --noEmit   # TypeScript type check
```

---

## Compliance rules

Rules are stored in `backend/app/config/compliance_rules.json` and loaded at runtime — adjust thresholds without touching any Python:

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

Layouts that fail any rule are flagged with violation messages shown in the UI. Beam span warnings are surfaced separately and do not block a layout.

---

## Roadmap

The current MVP supports rectangular G+1 plots with 2BHK / 3BHK configurations. Planned expansions:

- [ ] Quadrilateral plot support
- [ ] Vastu compliance toggle
- [ ] Extended compliance rules (NBC, local bylaws)
- [ ] Arbitrary room counts and custom room names
- [ ] Dynamic constraint solver (replace fixed archetypes)
- [ ] DXF / AutoCAD export
- [ ] Shareable project links

---

## License

MIT © Karthikeyan Natarajan
