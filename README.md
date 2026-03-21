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
- **SVG preview** — double-line walls, door arcs, window markers, columns, north arrow, dimension lines
- **Section view** — parametric 2D cross-section with floor slabs and parapet
- **Interior furniture overlay** — 11 furniture symbols (bed, sofa, dining, kitchen slab, etc.)
- **Electrical overlay** — switch, socket, light point, fan positions per NBC residential standard
- **Plumbing overlay** — supply spine + drain routing for bathrooms and kitchen
- **Side-by-side comparison** — 2 layouts at same scale with diff highlights
- **Manual room edit mode** — drag shared walls to resize adjacent rooms; live compliance badges (Pro)
- **Room annotations** — sticky notes on rooms, exported to PDF

### Export
- **PDF export** — ReportLab A4 at 1:100; professional double-line walls, boxed window symbols, single door arcs, chain dimensions in ft-in, room schedule, north arrow (free)
- **Approval drawing PDF** — municipality-format 4-page package; solid B&W walls, setback dims, FAR table, owner info, engineer seal, CMDA/BBMP/GHMC/PMC/MCGM submission ready (per-submission add-on)
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
| Database | PostgreSQL 16 |
| Payments | Razorpay |
| Tooling | Bun (package manager + runtime + test runner), Biome, Drizzle ORM, uv, Docker Compose |

---

## Quick Start

### Prerequisites

| Tool | Version |
|------|---------|
| Docker | 24+ |
| Bun | 1.3+ — `curl -fsSL https://bun.sh/install \| bash` |
| Python | 3.12+ |
| uv | latest — `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### Setup

```bash
# 1. Configure environment
cp frontend/.env.local.example frontend/.env.local
# Fill in: BETTER_AUTH_SECRET, DATABASE_URL, NEXT_PUBLIC_API_URL

# 2. Install dependencies
cd frontend && bun install
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
  bunx drizzle-kit push
```

### Manual start (without the script)

```bash
docker compose up db -d
cd backend && uv run uvicorn app.main:app --reload --port 8002
cd frontend && bun dev
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
| `OPENROUTER_API_KEY` | optional | Agentic chat via OpenRouter (any model) |
| `OPENROUTER_MODEL` | optional | e.g. `deepseek/deepseek-chat-v3-0324` |

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
│   │   ├── engine/            # solver, archetypes, scorer, compliance, Vastu, pdf, approval_pdf, BOQ
│   │   ├── models/            # SQLAlchemy ORM models
│   │   └── schemas/           # Pydantic I/O schemas
│   └── tests/                 # 159 pytest tests (API e2e, engine, solver, scorer, L-shaped, CAD)
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── (app)/         # Dashboard, projects, account (auth-gated)
│       │   ├── (auth)/        # Sign-in, sign-up
│       │   ├── (marketing)/   # Landing, pricing, how-it-works, gallery, privacy, terms
│       │   ├── share/         # Public read-only share view
│       │   └── api/           # Better Auth handler, agent chat, transcription
│       ├── components/        # SVG renderer, section view, BOQ viewer, chat panel, overlays
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
uv run pytest tests/ -v          # run 159 tests
uv run uvicorn app.main:app --reload --port 8002

# Frontend
cd frontend
bun dev                           # dev server on :3001
bun run build                     # production build
bun run lint                      # lint + format check (Biome)
bun run format                    # auto-format (Biome)
bun test                          # unit tests (Bun test runner)
bun run test:e2e                  # Playwright e2e (headless)
bun run test:e2e:ui               # Playwright interactive
bun run seed                      # seed 3 test users (free/basic/pro)
```

### Test users (dev/QA only)

After running `bun run seed`, three accounts are available:

| Email | Password | Plan |
|-------|----------|------|
| `free@planforge.dev` | `Test@1234` | Free |
| `basic@planforge.dev` | `Test@1234` | Basic |
| `pro@planforge.dev` | `Test@1234` | Pro |

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

**[docs/developer-reference.md](docs/developer-reference.md)** — full architecture, API reference, engine internals, database schema, feature gating, testing guide, and UI design system.

---

## License

MIT © Karthikeyan Natarajan
