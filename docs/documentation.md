# PlanForge — Technical Documentation

> Living technical reference and session log. For the full developer guide, see [developer-reference.md](developer-reference.md).

---

## Architecture Overview

```
Browser (Next.js 16 App Router)
  ├── Server Components  — dashboard, project list, static pages
  ├── Client Components  — SVG renderer, overlays, chat panel, drag-resize
  └── API routes
        ├── /api/auth/*          — Better Auth handler
        ├── /api/agent/[id]      — Vercel AI SDK streamText (Claude / GPT-4 / OpenRouter)
        └── /api/transcribe      — OpenAI Whisper voice input

FastAPI (Python 3.12, port 8002)
  └── /api/*
        ├── /projects            — CRUD + list
        ├── /projects/{id}/generate      — OR-Tools CP-SAT layout engine
        ├── /projects/{id}/export/*      — PDF / DXF / BOQ / approval PDF
        ├── /payments/*          — Razorpay order + webhook verify
        └── /rooms/*             — In-memory room editor with undo stack (Pro)

PostgreSQL 16 (Docker, port 5432)
  ├── Better Auth tables (Drizzle ORM)   — user, session, account, verification
  └── App tables (SQLAlchemy async)      — projects, users (with plan_tier)
```

---

## Data Models / Schema

### Core entities (SQLAlchemy)

| Table | Key columns |
|-------|-------------|
| `project` | id, user_id, name, plot_length, plot_width, setbacks×4, num_bedrooms, toilets, parking, plot_shape, plot_corners, cutout_*, vastu_enabled, road_side, annotations, num_floors, has_stilt, has_basement, custom_room_config |
| `user` | id, email, plan_tier (free/basic/pro/team), plan_expires_at |

### Better Auth tables (Drizzle, schema.ts)

`user`, `session`, `account`, `verification` — standard Better Auth schema.

### Drizzle project columns (schema.ts additions)

`plotShape`, `plotFrontWidth`, `plotRearWidth`, `plotSideOffset`, `plotCorners`, `cutoutCorner`, `cutoutWidthM`, `cutoutHeightM`, `numFloors`, `hasStilt`, `hasBasement`, `customRoomConfig`, `municipality`, `vasuEnabled`, `roadWidthM`, `roadSide`, `hasPooja`, `hasStudy`, `hasBalcony`

---

## API Reference

All backend routes require `X-User-Id` header (set by frontend middleware from Better Auth session).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/health` | — | Health check |
| GET | `/api/projects` | ✓ | List user's projects |
| POST | `/api/projects` | ✓ | Create project |
| GET | `/api/projects/{id}` | ✓ | Get project |
| PUT | `/api/projects/{id}` | ✓ | Update project |
| DELETE | `/api/projects/{id}` | ✓ | Delete project |
| GET | `/api/projects/{id}/generate` | ✓ | Run layout engine → 3 layouts |
| GET | `/api/projects/{id}/export/pdf` | ✓ | Download PDF (1:100 A4) |
| POST | `/api/projects/{id}/export/approval-pdf` | ✓ | Municipality approval drawing |
| GET | `/api/projects/{id}/export/dxf` | ✓ Basic+ | Download DXF |
| GET | `/api/projects/{id}/boq` | ✓ | BOQ JSON or Excel (Pro) |
| GET | `/api/projects/{id}/compliance-check` | ✓ | Live compliance validation |
| POST | `/api/payments/order` | ✓ | Create Razorpay order |
| POST | `/api/payments/verify` | ✓ | Verify payment, upgrade plan |
| GET | `/api/rooms/{project_id}/{layout_id}` | ✓ Pro | Get current room state |
| POST | `/api/rooms/{project_id}/{layout_id}` | ✓ Pro | Apply room edits |
| POST | `/api/rooms/{project_id}/{layout_id}/undo` | ✓ Pro | Undo last edit |

---

## Key Components / Modules

### Backend engine

| File | Purpose |
|------|---------|
| `engine/solver.py` | OR-Tools CP-SAT constraint solver; 3 runs with forced staircase diversity |
| `engine/archetypes.py` | Parametric room-slicing fallback (front/mid/rear staircase archetypes) |
| `engine/scorer.py` | 5-component scorer: natural light 25%, adjacency 25%, aspect ratio 20%, circulation 15%, Vastu 15% |
| `engine/compliance.py` | NBC + municipality bye-law checker; returns violations + warnings |
| `engine/vastu.py` | 8-zone Vastu Shastra engine with SVG overlay zone data |
| `engine/cad_primitives.py` | DXF drawing functions: walls, doors, windows, stairs, dimensions, north arrow, scale bar |
| `engine/cad_advanced.py` | DXF building footprint, compound wall, furniture, structural grid, terrace hatch, setback zones |
| `engine/pdf.py` | ReportLab PDF renderer (1:100, A4) |
| `engine/boq.py` | Bill of Quantities with city-linked material rates |

### Frontend components

| File | Purpose |
|------|---------|
| `floor-plan-svg.tsx` | Main SVG renderer — double-line walls, door arcs, windows, columns, hatch fills, overlays |
| `section-view-svg.tsx` | 2D parametric section (GF/FF/slab/parapet) with wall and slab hatch |
| `chat-panel.tsx` | Agentic chat UI — useChat hook, voice input, tool-invocation display |
| `boq-viewer.tsx` | BOQ table + Excel export lock (Pro gate) |

---

## Auth Flow

1. User registers / logs in via Better Auth (`/api/auth/*` handler)
2. Better Auth stores session in PostgreSQL via Drizzle adapter
3. `proxy.ts` (Next.js middleware) reads session cookie; redirects unauthenticated users
4. All backend API calls include `X-User-Id: <userId>` header injected by Next.js server components / route handlers

---

## External Integrations

| Service | Purpose | Config |
|---------|---------|--------|
| Razorpay | Subscription payments + per-project credits | `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` in `backend/.env` |
| OpenAI Whisper | Voice input transcription | `OPENAI_API_KEY` in `frontend/.env.local` |
| Anthropic Claude | Agentic chat (primary) | `ANTHROPIC_API_KEY` in `frontend/.env.local` |
| OpenRouter | Agentic chat fallback / alternative models | `OPENROUTER_API_KEY` + `OPENROUTER_MODEL` |
| OR-Tools | CP-SAT constraint solver | Python package via `uv` |

---

## Configuration

Key config files (not environment variables):

| File | Purpose |
|------|---------|
| `backend/app/config/compliance_rules.json` | Editable rule thresholds (min room sizes, FAR, etc.) |
| `backend/app/config/room_specs.json` | 19 room type specifications for CP-SAT solver |

---

## Session Log

---

### 2026-03-16 — DXF CAD Quality & SVG Hatch Improvements

**What was built:**

- **DXF lineweights on all draw_* functions** — every element in `cad_primitives.py` now carries an explicit `lineweight` value in its `dxfattribs`: walls = 50 (0.50mm), doors/windows/ventilators/stairs/north arrow = 25 (0.25mm), dimension lines = 18 (0.18mm), hatch boundaries = 9 (0.09mm). This ensures line weights survive layer override in any DXF viewer.
- **ARCH_MM dimstyle** — created lazily on first `draw_dimension_chain()` call; sets `dimtxt=0.25`, `dimtad=1` (text above dimension line, per Indian drawing convention), `dimasz=0.15`, extension line offset/extension. Passed as `dimstyle="ARCH_MM"` to all `add_linear_dim()` calls.
- **Graphical scale bar** — new `draw_scale_bar(msp, x, y, layer, z)` function in `cad_primitives.py`; draws a 3m bar subdivided at 0/1/2/3m with tick marks and MTEXT labels; "SCALE 1:100" title above. Called in `_render_dxf()` in `export.py`, positioned below the north arrow.
- **SVG wall hatch patterns** — added `<defs>` block with two SVG `<pattern>` elements (`wall-hatch-floor`: 45° diagonal `#94a3b8`; `int-wall-hatch`: lighter diagonal `#cbd5e1`) to `floor-plan-svg.tsx`.
- **SVG external wall hatch** — added an `evenodd` fill-rule `<path>` that fills only the wall ring between the outer and inner wall boundary rectangles with `url(#wall-hatch-floor)`. Using evenodd avoids needing a clipPath or a hardcoded white fill.
- **SVG internal wall hatch** — each internal wall pair (vertical and horizontal) now includes a `<rect fill="url(#int-wall-hatch)">` between the double lines to show the wall material.
- **SVG internal wall stroke fix** — removed group-level `strokeWidth={0.8}` from the internal wall `<g>`; replaced with per-`<line>` `strokeWidth={0.4}`, matching the correct architectural convention where internal partitions are visually lighter than the building envelope.

**Key files changed:**

- `backend/app/engine/cad_primitives.py` — lineweights on all draw functions, ARCH_MM dimstyle creation, new `draw_scale_bar()` function
- `backend/app/api/routes/export.py` — added `draw_scale_bar` import and call in `_render_dxf()`
- `frontend/src/components/floor-plan-svg.tsx` — `<defs>` with hatch patterns, evenodd external wall hatch path, internal wall hatch rects, per-line stroke weights

**Patterns established:**

- DXF lineweights should always be set **both** on the layer (in `layer_defs` in `export.py`) and on individual entities (in `dxfattribs`). Layer weights apply globally; entity weights win when layers are merged or reassigned.
- SVG hatch for a ring area (two nested rects) is cleanest with `fillRule="evenodd"` on a `<path>` containing both rect outlines — no clipPath or white-fill masking needed.
- `dimstyle` is a direct kwarg to `add_linear_dim()`, not inside `dxfattribs`. The `msp.doc.dimstyles` table supports `in` operator for existence check.
- 159 backend pytest tests pass (up from 108 documented previously — growth from L-shaped, approval PDF, compliance-check, and CAD test additions in recent sessions).
