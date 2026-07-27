# PlanForge – Project Instructions for Claude Code

## What This Project Is

PlanForge is a G+1 2D residential floor plan generator for Indian small builders and civil engineers.

It generates 3 template-based layout variations for rectangular plots, enforces Indian building compliance rules, and exports professional PDF drawings.

It also acts as the front door to `structapi`, a separate multi-agent IS-code structural
design engine ([karthiknitt/structapi](https://github.com/karthiknitt/structapi)) — see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Status:** feature-complete (P0–P3 shipped), pre-revenue. `Lean_MVP_PRD_v1.md` is
historical and no longer describes current scope.

---

## Architecture

### Monorepo Structure

```
PlanForge/
├── frontend/           # Next.js App Router + Better Auth + Drizzle + SVG rendering
├── backend/            # FastAPI + Shapely + OR-Tools + ReportLab + ezdxf + uv
├── structapi-service/  # Vendored copy of structapi, pinned to a tag (CI byte-diffs it)
├── docs/               # Reference docs + dated plans — see docs/README.md
├── scripts/            # Setup/migration helpers (gcp-cloud-run-setup.sh, check_schema.py)
├── experiments/        # Scratch evaluation harness (CCQS scoring, render bake-offs)
├── data/               # Sample/reference data
├── CLAUDE.md           # This file
└── README.md
```

### Frontend (`/frontend`)
- **Framework:** Next.js (App Router, `src/` dir)
- **Auth:** Better Auth (TypeScript-native, session-based) — always
- **ORM:** Drizzle — used for Better Auth's DB adapter and any frontend DB access
- **UI Library:** ShadCN — go-to component library
- **Rendering:** SVG for floor plan preview in browser
- **Styling:** Tailwind CSS (latest, v4+)
- **Linter/Formatter:** Biome — replaces ESLint + Prettier entirely
- **Language:** TypeScript

### Backend (`/backend`)
- **Framework:** FastAPI
- **Geometry:** Shapely
- **PDF export:** ReportLab
- **Package manager:** uv (not pip, not poetry)
- **Language:** Python 3.12+

### Database
- **PostgreSQL via Neon** (cloud, pooled connection) — stores user accounts, projects, and generated layouts
- **Frontend:** Drizzle ORM manages schema + migrations for auth tables (Better Auth Drizzle adapter)
- **Backend:** SQLAlchemy (async) manages project/layout tables — no Alembic; schema is created/patched automatically at startup (`Base.metadata.create_all` + `auto_migrate_missing_columns` in `app/main.py`)

### Deployment & Testing Workflow
- **No local dev servers, no local Playwright/preview testing.** Frontend is tested via Vercel (preview + production deploys); backend is tested via Google Cloud Run. There is no `docker compose up` workflow — `docker-compose.yml` was removed for this reason.
- **What still runs locally (and in CI):** unit tests (`uv run pytest`, `bun test`), linting/formatting (`ruff`, `biome`), type-checking (`tsc --noEmit`), and `docker build ./backend` to validate the Dockerfile. None of these need real Neon/Vercel/Cloud Run credentials — backend tests run against an in-memory SQLite DB (`backend/tests/conftest.py`), frontend tests set their own env vars inline per-test.
- **CI:** GitHub Actions (`.github/workflows/`) runs the same local checks (tests, lint, build) on every push/PR.
- **Backend runtime:** Google Cloud Run, `$0`-tier (`min-instances=0`, `max-instances=3`), deployed via `.github/workflows/deploy-backend.yml` on push to `main` (path-filtered to `backend/**`). WIF-based auth (no service account keys). Setup automated by `scripts/gcp-cloud-run-setup.sh`.
- **Frontend runtime:** Vercel, deployed on push (preview per-branch, production on `main`).
- **Real secrets** live in GitHub Actions secrets (backend/Cloud Run) and Vercel's env store (frontend) — never in a committed or local file. `.env.example` files are reference-only.

---

## Key Product Decisions (current — supersedes `Lean_MVP_PRD_v1.md`)

> **Note:** this project outgrew the Lean MVP scope in early 2026. The constraints below
> reflect what is actually built and shipped. `Lean_MVP_PRD_v1.md` is retained as a
> historical record only — do not treat it as current scope. Where it disagrees with this
> section or `README.md`, it is out of date.

### Plot Support
- **Rectangular, trapezoid, convex quadrilateral (arbitrary 4-corner), and L-shaped**
  (rectangle with cutout corner) plots
- User inputs: length, width, setbacks (4 sides), road-facing side, north direction
- Minimum plot size validation before generation

### Layout Engine
- **OR-Tools CP-SAT constraint solver** with forced staircase diversity
  (front / mid / rear); layouts scored by a 5-component scorer (natural light, adjacency,
  aspect ratio, circulation, Vastu)
- The 3 parametric archetypes remain as a **fallback** when the solver cannot converge
- Layouts rejected if compliance fails (not adjusted automatically)

### Room Config
- **2BHK – 4BHK, 1–6 bedrooms**; optional pooja, study, balcony, servant quarter,
  home office, gym, store
- **Multi-floor** — G / G+1 / G+2, optional stilt floor, optional basement
- User selects number of toilets
- Parking: Yes/No

### Compliance Rules (Essential Only)
- Bedroom ≥ 9.5 sqm
- Kitchen ≥ 7 sqm
- Toilet ≥ 2.8 sqm / max 4.5 sqm (per NBC 2016 + Indian convention)
- WC (water-closet only) ≥ 1.1 sqm
- Stair width ≥ 900 mm
- Main entrance door ≥ 900 mm (default 1070 mm leaf), road-facing
- External wall: 230 mm
- Internal wall: 115 mm
- Floor coverage % (FAR)
- Setback enforcement
- En-suite toilets: hard wall-adjacency ≥ 900 mm when `attached_toilets=True`
- Door-graph navigability: BFS reachability, wet rooms one-door, bedrooms one circulation entry, staircase doored per floor
- Rules stored in configurable JSON

### Structural Design
- Columns at outer corners, staircase core, major wall intersections
- Max beam span ≤ 4.5 m (warning flag only) in the layout engine
- **Full IS-code structural design is shipped** via the `structapi` service
  (IS 456/875/1893/13920/3370/10262): member sizing, reinforcement, BOQ steel/concrete
  quantities, and structural drawing sheets. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
  Client: `backend/app/services/structagent_client.py`; orchestration:
  `backend/app/services/structural_loop.py`. Disabled gracefully when
  `STRUCTURAL_API_KEY` is unset — layout generation still works.

### PDF Output
- Standard PDF (6 pages): GF plan, FF plan, GF structural, FF structural, SECTION A-A, FRONT ELEVATION
- Approval PDF (5 pages): site plan, GF plan, FF plan, SECTION A-A + title block, FRONT ELEVATION + title block
- Column markers, room labels, dimensions, north arrow, title block; A-A cut markers on plan pages
- Section/elevation built from Shapely via `section_geometry.py` → `section_render.py` (IS 962 hatching, `vertical_standards.py` dims)
- Scale: 1:100 nominal (section/elevation pages fit-to-region with computed `SCALE 1:N`)

### Vastu
- Implemented: 8-zone (+ Brahmasthan centre) compliance engine, `backend/app/engine/vastu.py`
- Zone rules configurable in `backend/app/config/compliance_rules.json` under `vastu_zones` (preferred/avoid/prohibit per zone), rotated per `road_side` (N/S/E/W)
- Wired into `generator.py`, `solver.py`, and `scorer.py` — `_score_vastu` is a 10%-weighted layout score component
- Opt-in per project via `PlotConfig.vastu_enabled`; a no-op (returns no findings, neutral 100 score) when disabled
- Tested in `backend/tests/test_vastu.py`

### Auth & Projects
- Users register/login via Better Auth
- Projects saved to PostgreSQL per user
- Stateless generation (no login required to generate), but login required to save/retrieve

---

## Coding Conventions

### General
- Prefer editing existing files over creating new ones
- No premature abstractions — only extract helpers when used 3+ times
- No docstrings/comments unless logic is non-obvious
- Keep compliance rules in JSON config, not hardcoded

### Frontend
- Use App Router conventions (`src/app/`, `layout.tsx`, `page.tsx`)
- Server Components by default; Client Components only when needed (interactivity, state)
- API calls to backend via `/api/` routes or direct fetch from Server Components
- SVG floor plan preview rendered client-side
- Use ShadCN components — do not write raw HTML UI elements when a ShadCN component exists
- Linting/formatting: Biome (`npx biome check`, `npx biome format`) — no ESLint, no Prettier
- Use `frontend-design` skill when building any page UI

### Backend
- FastAPI with Pydantic v2 models for all I/O
- Geometry calculations in Shapely — never raw float math for polygon ops
- PDF generation in ReportLab only (not matplotlib, not cairosvg)
- `uv` for all package management — use `uv add <package>`, `uv run`, etc.
- Compliance rules loaded from `backend/config/compliance_rules.json`

### Python environment
No local dev server / manual testing — see Deployment & Testing Workflow above.
```bash
# Install deps
uv sync

# Run tests
uv run pytest

# Lint + format
uv run ruff check .
uv run ruff format .

# Validate the Dockerfile builds (the only supported local Docker action)
docker build -t planforge-backend ./backend

# Add a package
uv add shapely
```

**⚠️ Gotcha:** Never run `ruff format` on `*.json` files — it corrupts them.

### Next.js dev
No local dev server / manual testing — see Deployment & Testing Workflow above.
Push to a branch for a Vercel preview deploy, or use `bun run build`/`bun test` locally for build/test checks.

### Frontend tooling
```bash
# Lint + format check
cd frontend && bun run lint

# Format files
cd frontend && bun run format

# Run unit tests (Bun test runner)
cd frontend && bun test

# Add a ShadCN component
cd frontend && bunx shadcn@latest add button

# Run Drizzle migrations
cd frontend && bunx drizzle-kit migrate
```

---

## Feature Roadmap

Items 1–5 of the original post-MVP roadmap (quadrilateral plots, advanced compliance
rules, arbitrary room counts, dynamic constraint solver, smarter layout engine) are all
**shipped**. Current backlog lives in [docs/product-roadmap.md](docs/product-roadmap.md).

---

## Risks to Watch

- **Frontend test coverage** — backend has 650 tests across 87 files; the frontend has
  no dedicated test files. Highest-value gap.
- **No Alembic migrations** — schema is created/patched at startup. Fine at current
  scale; needs replacing before multi-tenant production.
- **Cold starts** — Cloud Run at `min-instances=0` means ~20–25s first-request latency
  after idle, which has previously caused agent-tool timeouts (see issue 13 below).
- **Vendored structapi drift** — `structapi-service/` is a pinned copy; CI byte-diffs it
  against the tag on every push and PR. Do not edit it by hand.

---

## Known Issues & Review Backlog

### Fixed (session 8, 2026-02-22) — verify in testing

1. **DXF export crash** — `ezdxf doc.write()` requires `StringIO` (text mode), not `BytesIO`. Fixed in `backend/app/api/routes/export.py`. Also switched `TEXT` → `MTEXT` for multiline labels, 2D points for dimensions, added `.render()`.
2. **Agent chat "Thinking" then disappears** — Multiple AI SDK v6 migration bugs:
   - `convertToModelMessages()` not awaited (was passing Promise to model)
   - `inputSchema` used instead of wrong `parameters` in `tool()`
   - UIMessage `.content` property doesn't exist in v6 (only `.parts[]`)
   - Tool invocation state is `"output-available"` not `"result"`
   - Error responses returned as JSON instead of stream (useChat can't parse)
3. **Agent model fallback** — Added runtime fallback: if Anthropic fails (billing/quota), automatically retries with OpenAI `gpt-5.2`. Uses `createUIMessageStream` with a for-loop over models.
4. **SVG column duplicate keys** — `floorPlan.columns.map` could produce duplicate React keys. Fixed with index-based keys (columns already deduped via Map). Regressed on 2026-07-10 to coordinate-only keys; re-fixed on 2026-07-11 with index-suffixed keys (e.g., `col-${index}`)

### Needs Verification

- **Voice transcription** — Switched from AI SDK `experimental_transcribe` to direct OpenAI SDK (`openai` package). User reported "returns default text every time" but also noted possible mic issue. Needs retest with working mic.
  - File: `frontend/src/app/api/transcribe/route.ts`
  - Depends on: valid `OPENAI_API_KEY` in `.env.local`

### Fixed (session 9, 2026-03-03)

5. **Quadrilateral plot support** — Full convex quad support: `plot_corners` field, Shapely inset geometry, CP-SAT half-plane constraints, compliance boundary consistency fix. 6 new tests added.
6. **DXF CAD layer** — Double-line walls, door symbols (line+arc), window symbols (3 parallel lines), ANSI31/ANSI37 hatch fill for wall areas.
7. **Section view hatching** — SVG `<defs>` with `wall-hatch` (45° diagonal) and `slab-hatch` (crosshatch) patterns applied to wall/slab rects.
8. **OR-Tools solver API (OR-Tools 9.x)** — `new_interval_var(x, w, x+w, name)` broke because `x+w` is a two-IntVar sum (not affine). Fixed by introducing explicit end IntVars: `model.add(ex == x + w)`. Solver now produces 3 layouts.
9. **Pydantic ConfigDict** — Already fixed (uses `model_config = ConfigDict(env_file=".env")`). CLAUDE.md was stale.

### Fixed (session 10, 2026-07-03)

10. **Cloud Run deployment live** — Backend deployed to Google Cloud Run ($0-tier: min-instances=0, max=3): `https://planforge-backend-hoiaqu2xbq-uc.a.run.app`. GCP project `thermal-well-451906-b0` (region `us-central1`), Neon Postgres project `planforge` (id `plain-brook-17631682`), Artifact Registry `planforge-backend`, WIF-based GitHub Actions deploy (`.github/workflows/deploy-backend.yml`, triggers on `backend/**` push to `main`). Frontend redeployed to `https://planforge-mauve.vercel.app` with `BACKEND_URL`/`NEXT_PUBLIC_API_URL` pointed at the Cloud Run URL. Setup automated via `scripts/gcp-cloud-run-setup.sh`.

### Fixed (2026-07-11)

11. **Invalid model IDs + provider fallback gap** — `models.ts` used non-existent Anthropic IDs (`claude-sonnet-4-6`, `claude-opus-4-6`); Anthropic returned 404, and the fallback predicate only matched billing/quota errors, so the raw error streamed to chat as a "connection error". Fixed: current IDs (`claude-sonnet-5` default, `claude-opus-4-8`, `claude-haiku-4-5`), OpenRouter default now `anthropic/claude-sonnet-5` (old `anthropic/claude-3.5-sonnet` is retired), and `frontend/src/lib/agent-errors.ts` (`shouldFallback`) advances the provider chain on 401/402/404/429/5xx/network errors, with human-readable messages when all providers fail.
12. **AI SDK v6 tool-part parsing** — `chat-panel.tsx` still checked v4's `part.type === "tool-invocation"`, so tool outputs were never detected and AI edits never updated the canvas preview. Fixed via `frontend/src/lib/chat-parts.ts` built on the SDK's `isToolUIPart`/`getToolName` (`tool-<name>`/`dynamic-tool` parts, `state === "output-available"`, result in `part.output`).
13. **Agent tools solved synchronously + 15s timeout** — all 11 agent endpoints funnel through `_load_layout_state`, which ran up to 3 CP-SAT solves on a store miss; with Cloud Run cold starts (~23s measured) this blew `fetchBackend`'s 15s abort → "connection errors". Fixed: read-only load returning 409 `{"code": "no_layouts", "help": "Generate layouts first"}` (never solves), agent tools relay that conversationally, and `fetchBackend` accepts per-call `timeoutMs` (agent tools pass 45s).
14. **Render provider env missing on prod** — `deploy-backend.yml` now passes `RENDER_PROVIDER`, `RENDER_MODEL`, `OPENROUTER_API_KEY` to Cloud Run (mirroring `deploy-backend-v2.yml`), so `ensure_provider_configured()` no longer raises on the render tab.

### Fixed (2026-07-12)

15. **StructAgent integration** — IS-code structural design per layout. New `backend/app/api/routes/structural.py` + `backend/app/services/structagent_client.py` call the `structapi` service (configured via `structagent` settings; empty key disables the feature). CI now byte-diffs the vendor/pinned structapi tag on every push/PR and files a weekly freshness issue (`.github/workflows` — PR #21).
16. **SECTION A-A + FRONT ELEVATION pages in both PDF generators** — Standard and approval PDFs now emit both a `SECTION A-A` (cross-section) and a `FRONT ELEVATION` page. `section_geometry.py` builds both views; `pdf.py`/`approval_pdf.py` render them with A-A cut markers on the plan pages (PR #20).
17. **Main entrance door (MD) on road-facing wall** — Dedicated GF-only main-entrance pass in `plan_geometry.py`: entry room priority living > passage > dining (never parking/stair/wet); door centred toward the facade midpoint to align with the compound gate. `Opening.is_main` flag + `OpeningStandards.main_door_width_m` (1070 mm leaf, NBC min clear 900 mm) from `compliance_rules.json`. FRONT ELEVATION always uses the y-min (road) wall so the correct facade is drawn for `road_side` N/E/W; MD shows full height. MD mark + MAIN DOOR schedule row in both PDFs, DXF gate gap aligned to MD x, SVG `MD` tag. 8 new MD tests + elevation regression (PR #22).

### Open / Deferred

- **Anthropic billing** — If the Anthropic key lacks balance, the agent now falls back automatically through OpenAI (`gpt-4o`) then OpenRouter via `agent-errors.ts`. Top up when ready.
- **Voice transcription** — Code uses direct OpenAI SDK (Whisper). Needs retest with working mic + valid `OPENAI_API_KEY` in `.env.local`.
- **StructAgent key** — Structural design feature is off until `structagent` API key/endpoint is configured; layout generation still works without it.

---

## Testing

- Backend: pytest (via `uv run pytest`) — 650 tests across 87 files
- Frontend: Vitest or Playwright (TBD)
- Compliance rules: unit-tested against known valid/invalid layouts

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
