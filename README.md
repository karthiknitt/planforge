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
| Database | PostgreSQL 16 |
| Payments | Razorpay |
| Tooling | Bun (package manager + runtime + test runner), Biome, Drizzle ORM, uv, Docker (build-only) |

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
| `NEXT_PUBLIC_API_URL` | ✓ | Cloud Run backend URL |
| `BACKEND_URL` | ✓ | Cloud Run backend URL (server-side only) |
| `INTERNAL_AUTH_SECRET` | ✓ | Must match the backend's value exactly |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID` | optional | Razorpay test key |
| `OPENAI_API_KEY` | optional | Voice transcription (Whisper) |
| `ANTHROPIC_API_KEY` | optional | Agentic chat (Claude) |
| `OPENROUTER_API_KEY` | optional | Agentic chat via OpenRouter (any model) |
| `OPENROUTER_MODEL` | optional | e.g. `deepseek/deepseek-chat-v3-0324` |

Set via `vercel env add <NAME> production|preview` — not a local `.env.local` in practice, since there's no local dev server. See `frontend/.env.example` for the full reference list.

### `backend/.env`

| Variable | Required | Example |
|----------|----------|---------|
| `DATABASE_URL` | ✓ | `postgresql+asyncpg://user:pass@ep-xxx-pooler.region.aws.neon.tech/dbname?ssl=require` |
| `DB_USE_NULLPOOL` | ✓ | `true` (required for Neon's pooled endpoint) |
| `ALLOWED_ORIGINS` | ✓ | `https://planforge-mauve.vercel.app` |
| `INTERNAL_AUTH_SECRET` | ✓ | Must match the frontend's value exactly |
| `RAZORPAY_KEY_ID` | optional | Razorpay test key |
| `RAZORPAY_KEY_SECRET` | optional | Razorpay secret |

Set via `gh secret set <NAME> --repo karthiknitt/planforge` — injected into Cloud Run at deploy time. See `scripts/gcp-cloud-run-setup.sh` and `backend/.env.example`.

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
│   └── tests/                 # 413 pytest tests (API e2e, engine, solver, scorer, L-shaped, CAD, openings, section)
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
├── scripts/
│   └── gcp-cloud-run-setup.sh # One-time GCP + Neon setup for the Cloud Run backend
└── CLAUDE.md
```

---

## Development

### Commands

```bash
# Backend
cd backend
uv run pytest tests/ -v          # run 413 tests (in-memory SQLite, no Neon needed)
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

After running `bun run seed` (pointed at the Neon database via `DATABASE_URL`), three accounts are available:

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
