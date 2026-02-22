# PlanForge – Project Instructions for Claude Code

## What This Project Is

PlanForge is a G+1 2D residential floor plan generator for Indian small builders and civil engineers.

It generates 3 template-based layout variations for rectangular plots, enforces Indian building compliance rules, and exports professional PDF drawings.

**Active PRD:** Lean MVP (`Lean_MVP_PRD_v1.md`)
**Target timeline:** 6–8 weeks focused solo development

---

## Architecture

### Monorepo Structure

```
PlanForge/
├── frontend/          # Next.js App Router + Better Auth + SVG rendering
├── backend/           # FastAPI + Shapely + ReportLab + uv
├── shared/            # Shared types/constants (if needed)
├── CLAUDE.md
├── Lean_MVP_PRD_v1.md
└── Ambitious_PRD_v1.md
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
- **PostgreSQL** — stores user accounts, projects, and generated layouts
- **Frontend:** Drizzle ORM manages schema + migrations for auth tables (Better Auth Drizzle adapter)
- **Backend:** SQLAlchemy (async) manages project/layout tables

### Deployment
- **Local dev only** for now
- Docker Compose for local orchestration (frontend + backend + postgres)

---

## Key Product Decisions (Lean MVP Constraints)

### Plot Support
- **Rectangular plots only** — no quadrilateral in MVP
- User inputs: length, width, setbacks (4 sides), road-facing side, north direction
- Minimum plot size validation before generation

### Layout Engine
- **3 predefined parametric archetypes** — no dynamic constraint solver:
  - Layout A: Front staircase
  - Layout B: Center staircase
  - Layout C: Rear staircase
- Rooms arranged proportionally using deterministic slicing logic
- Layouts rejected if compliance fails (not adjusted automatically)

### Room Config
- **2BHK or 3BHK only** — no arbitrary room count in MVP
- User selects number of toilets
- Parking: Yes/No

### Compliance Rules (Essential Only)
- Bedroom ≥ 9.5 sqm
- Kitchen ≥ 7 sqm
- Toilet ≥ 3 sqm
- Stair width ≥ 900 mm
- External wall: 230 mm
- Internal wall: 115 mm
- Floor coverage % (FAR)
- Setback enforcement
- Rules stored in configurable JSON

### Structural Awareness
- Columns at outer corners, staircase core, major wall intersections
- Max beam span ≤ 4.5 m (warning flag only)
- No structural calculations

### PDF Output
- Single PDF: Ground floor + First floor
- Column markers, room labels, dimensions, north arrow, title block
- Scale: 1:100

### Vastu
- **NOT in Lean MVP** — deferred to post-launch

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
```bash
# Install deps
uv sync

# Run dev server
uv run uvicorn app.main:app --reload

# Add a package
uv add shapely
```

### Next.js dev
```bash
cd frontend
npm run dev
```

### Frontend tooling
```bash
# Lint + format check
cd frontend && npx biome check .

# Format files
cd frontend && npx biome format --write .

# Add a ShadCN component
cd frontend && npx shadcn@latest add button

# Run Drizzle migrations
cd frontend && npx drizzle-kit migrate
```

---

## Feature Roadmap (Post-MVP)

1. Quadrilateral plot support
2. Vastu toggle
3. Advanced compliance rules
4. Arbitrary room counts
5. Dynamic constraint solver
6. Smarter layout engine

---

## Risks to Watch

- Overengineering layout logic — stay with archetypes in MVP
- Adding quadrilateral plots too early
- Expanding compliance rules prematurely
- Feature creep before launch validation

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
4. **SVG column duplicate keys** — `floorPlan.columns.map` could produce duplicate React keys. Fixed with index-based keys (columns already deduped via Map).

### Needs Verification

- **Voice transcription** — Switched from AI SDK `experimental_transcribe` to direct OpenAI SDK (`openai` package). User reported "returns default text every time" but also noted possible mic issue. Needs retest with working mic.
  - File: `frontend/src/app/api/transcribe/route.ts`
  - Depends on: valid `OPENAI_API_KEY` in `.env.local`

### Open / Deferred

- **Anthropic billing** — User's Anthropic API balance is insufficient. Agent falls back to OpenAI `gpt-5.2` automatically when this happens. Top up Anthropic credits when ready.
- **PydanticDeprecatedSince20 warning** — `backend/app/config/settings.py` uses class-based `config` on `BaseSettings`. Should migrate to `ConfigDict`. Non-blocking.

---

## Testing

- Backend: pytest (via `uv run pytest`) — 49/49 passing
- Frontend: Vitest or Playwright (TBD)
- Compliance rules: unit-tested against known valid/invalid layouts
