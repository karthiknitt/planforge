# PlanForge

> G+1 residential floor plan generator for Indian small builders and civil engineers.

PlanForge takes plot dimensions, setbacks, and room preferences and instantly generates three compliant layout variations — complete with SVG preview, section view, Bill of Quantities, PDF drawing, and DXF export.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.129-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## Overview

PlanForge is a SaaS tool for Indian residential construction. A user enters plot dimensions and room preferences; the engine runs an OR-Tools CP-SAT constraint solver to produce 3 scored, compliant layout options with staircase positions varied (front / mid / rear). Each layout can be previewed as SVG, exported as a professional PDF drawing or DXF CAD file, and accompanied by a Bill of Quantities.

**Target users:** Small builders, civil contractors, and independent homeowners in Tier 2/3 Indian cities who want compliance-checked floor plans without hiring an architect for early-stage planning.

---

## Features

- **3-layout generation** — OR-Tools CP-SAT solver with forced staircase diversity; archetypes as fallback
- **2BHK / 3BHK** with 1–6 bedrooms; optional pooja, study, balcony, servant quarter, home office, gym, store
- **Multi-floor support** — G / G+1 / G+2, optional stilt floor, optional basement
- **Rectangular and trapezoid plots** — convex quadrilateral (arbitrary 4-corner) support
- **Indian compliance engine** — bedroom ≥ 9.5 m², kitchen ≥ 7 m², FAR, setbacks, stair width, beam span
- **City presets** — Bangalore, Chennai, Mumbai, Hyderabad (local setback / FAR overrides)
- **Vastu Shastra engine** — 8-zone directional analysis (toggleable)
- **5-component layout scorer** — natural light, adjacency, aspect ratio, circulation, Vastu (0–100)
- **SVG preview** — double-line walls, door arcs, window markers, columns, north arrow, dimension lines
- **Section view** — parametric 2D cross-section with floor slabs and parapet
- **PDF export** — ReportLab A4 at 1:100, title block, room labels, dimensions (free)
- **DXF export** — ezdxf with CAD layers, ANSI hatch fills, door/window symbols (Basic+)
- **Bill of Quantities** — JSON (free) + formatted Excel (Pro)
- **Agentic chat** — Claude-powered room editor with voice input via OpenAI Whisper (Pro)
- **Authentication** — Better Auth (TypeScript-native, session-based)
- **Payments** — Razorpay with plan tiers: Free / Basic / Pro
- **Blueprint Dark theme** — Outfit + Plus Jakarta Sans + JetBrains Mono fonts

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
| Database | PostgreSQL 16 |
| Payments | Razorpay |
| Tooling | Biome, Drizzle ORM, uv, Docker Compose |

---

## Quick Start

### Prerequisites

| Tool | Version |
|------|---------|
| Docker | 24+ |
| Node.js | 20+ |
| Python | 3.12+ |
| uv | latest — `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### Setup

```bash
# 1. Configure environment
cp frontend/.env.local.example frontend/.env.local
# Fill in: BETTER_AUTH_SECRET, DATABASE_URL, NEXT_PUBLIC_API_URL

# 2. Install dependencies
npm install --prefix frontend
cd backend && uv sync

# 3. Start dev stack (PostgreSQL → backend → frontend)
./dev-start.sh
```

App → `http://localhost:3001`
API docs → `http://localhost:8002/docs`

**First run only** — push the Better Auth schema:

```bash
cd frontend
DATABASE_URL="postgresql://planforge:planforge@localhost:5432/planforge" \
  npx drizzle-kit push
```

### Manual start (without the script)

```bash
docker compose up db -d
cd backend && uv run uvicorn app.main:app --reload --port 8002
cd frontend && PORT=3001 npm run dev
```

---

## Environment Variables

### `frontend/.env.local`

| Variable | Required | Example |
|----------|----------|---------|
| `DATABASE_URL` | ✓ | `postgresql://planforge:planforge@localhost:5432/planforge` |
| `BETTER_AUTH_SECRET` | ✓ | 32+ char random string |
| `BETTER_AUTH_URL` | ✓ | `http://localhost:3001` |
| `NEXT_PUBLIC_BETTER_AUTH_URL` | ✓ | `http://localhost:3001` |
| `NEXT_PUBLIC_API_URL` | ✓ | `http://localhost:8002` |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID` | optional | Razorpay test key |
| `OPENAI_API_KEY` | optional | Voice transcription (Whisper) |
| `ANTHROPIC_API_KEY` | optional | Agentic chat (Claude) |

### `backend/.env`

| Variable | Required | Example |
|----------|----------|---------|
| `DATABASE_URL` | ✓ | `postgresql+asyncpg://planforge:planforge@localhost:5432/planforge` |
| `RAZORPAY_KEY_ID` | optional | Razorpay test key |
| `RAZORPAY_KEY_SECRET` | optional | Razorpay secret |

---

## Project Structure

```
PlanForge/
├── backend/
│   ├── app/
│   │   ├── api/routes/        # projects, generate, export, payments, rooms
│   │   ├── config/            # compliance_rules.json, room_specs.json
│   │   ├── engine/            # solver, archetypes, scorer, compliance, Vastu, PDF, BOQ
│   │   ├── models/            # SQLAlchemy ORM models
│   │   └── schemas/           # Pydantic I/O schemas
│   └── tests/                 # 55 pytest tests (API e2e, engine, solver, scorer)
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── (app)/         # Dashboard, projects, account (auth-gated)
│       │   ├── (auth)/        # Sign-in, sign-up
│       │   ├── (marketing)/   # Landing, pricing, how-it-works
│       │   └── api/           # Better Auth handler, agent chat, transcription
│       ├── components/        # SVG renderer, section view, BOQ viewer, chat panel
│       ├── db/                # Drizzle client + schema (Better Auth tables)
│       ├── hooks/             # useVoiceInput
│       └── lib/               # auth config, layout types, utils
├── docs/
│   └── developer-reference.md # Full technical reference
├── docker-compose.yml
├── dev-start.sh / dev-stop.sh
└── CLAUDE.md
```

---

## Development

### Commands

```bash
# Backend
cd backend
uv run pytest tests/ -v          # run 55 tests
uv run uvicorn app.main:app --reload --port 8002

# Frontend
cd frontend
npm run dev                       # dev server on :3001
npm run build                     # production build
npx biome check .                 # lint + format check
npx biome format --write .        # auto-format
npx tsc --noEmit                  # type check
npm run test:e2e                  # Playwright e2e (headless)
npm run test:e2e:ui               # Playwright interactive
npm run seed                      # seed 3 test users (free/basic/pro)
```

### Test users (dev/QA only)

After running `npm run seed`, three accounts are available:

| Email | Password | Plan |
|-------|----------|------|
| `free@planforge.dev` | `Test@1234` | Free |
| `basic@planforge.dev` | `Test@1234` | Basic |
| `pro@planforge.dev` | `Test@1234` | Pro |

### Conventions

- **Frontend:** App Router server components by default; `"use client"` only for interactivity
- **Linting:** Biome (no ESLint, no Prettier)
- **Backend packages:** `uv add <pkg>` — never `pip install`
- **Compliance rules:** edit `backend/app/config/compliance_rules.json`, not Python
- **Layout IDs:** always dynamic (e.g. `"solver-front-0"`), never assume `"A"/"B"/"C"`

---

## Documentation

**[docs/developer-reference.md](docs/developer-reference.md)** — full architecture, API reference, engine internals, database schema, feature gating, testing guide, and UI design system.

---

## License

MIT © Karthikeyan Natarajan
