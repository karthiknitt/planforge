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
| `engine/pdf.py` | ReportLab standard PDF (1:100, A4); `_dedup_wall_coords()`, `_pdf_draw_double_line_wall()`, `_draw_windows()`, `_draw_doors_in_gaps()` |
| `engine/approval_pdf.py` | Municipality submission PDF (4-page); imports wall/window/door helpers from `pdf.py`; adds setback dims, FAR table, owner/engineer block |
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

---

### 2026-03-21 — PDF CAD Quality: Autoresearch Loop, AI Benchmark, Wall/Window/Door Fixes

**What was built:**

- **Autoresearch CAD quality loop (Phases 1–5)** — iterative CCQS-scored improvement of `pdf.py` and `approval_pdf.py`. CCQS metric: 5 components × 20pts (monochromaticity, dimension density, ft-in labels, layout completeness, visual quality via Claude vision API). Scores rose from 53/66 (baseline) to 96/96 (standard/approval).
- **Monochrome B&W palette** — all room fills `#FFFFFF`; external wall colors desaturated to grays/black; mean pixel saturation = 0.0 (20/20 mono component).
- **Ft-in room labels and chain dimensions** — `metres_to_ftin()` used for room labels (e.g. `12'-0" x 10'-0"`) and perimeter dimension chains in all four directions. 28 ft-in strings in standard PDF → 20/20 ft-in and dimension density components.
- **Title block** — dark header band (`#222222`), room area schedule, TOTAL AREA in SQFT, scale bar, north arrow labelled NORTH.
- **Staircase tread rendering** — floor indicator (thick line), evenly-spaced tread lines in lower half, dashed break line at mid-height, UP arrow with filled arrowhead.
- **Door arc improvement** — `ARC_LW = 0.4pt` (architectural thin-pen convention for swing arc); door leaf at `INT_LW = 1.0pt`.
- **AI benchmark — Nano Banana Pro** — generated a floor plan using Google Gemini 3 Pro Image Preview (`google/gemini-3-pro-image-preview`) via OpenRouter. Our system: 96/100 vs AI: 35.83/100. AI scores 0 on all text-based components (raster pixels, no PDF text). VQ tied at 16/20. Results in `experiments/ai_benchmark.md`.
- **Three structural PDF bugs fixed:**
  1. **Window wall breaks** — external walls were passing window positions as gap intervals to `_pdf_draw_double_line_wall`, physically opening the wall. Fixed by passing `[]` gaps; `_draw_windows()` draws the symbol on top of the solid wall.
  2. **Double door arcs** — door gap was stored at both `ra.x+ra.width` (wx1) and `rb.x` (wx2, the other wall face). Both keys appeared in `vertical_door_gaps`; `_draw_doors_in_gaps` drew two arcs ~4.7pt apart. Fixed by storing gap at wx1 only (removed duplicate `setdefault(wx2, ...)` calls).
  3. **Internal wall overlap / north wall mess** — `xs[1:-1]` contained both faces of each internal wall (two values ~0.115m apart), causing two overlapping `_pdf_draw_double_line_wall` calls → 3–4 lines at every internal wall. Fixed with `_dedup_wall_coords()` which filters coordinates within 0.125m of the previous.
- **Boxed window symbol** — `_draw_window_symbol()` now adds perpendicular jamb cap lines at both ends of the window, closing the symbol into a proper architectural box (3 parallel glass lines + 2 end caps).
- All fixes applied identically to both `pdf.py` and `approval_pdf.py`. Merged to `main` (commit `cf0ca3c`).

**Key files changed:**

- `backend/app/engine/pdf.py` — `_dedup_wall_coords()` added; xs/ys deduplication; external walls pass `[]` gaps; single door gap key per wall; `_draw_window_symbol` with jamb caps; all autoresearch palette/label/dim improvements
- `backend/app/engine/approval_pdf.py` — imports `_dedup_wall_coords` from `pdf.py`; same deduplication, external wall solid, single door gap key; all Phase 1–5 autoresearch improvements
- `experiments/eval.py` — 5-component CCQS metric (monochromaticity, dim density, ft-in labels, layout completeness, Claude vision quality judge)
- `experiments/prepare.py` — fixed PlotConfig test harness; generates `current_standard.pdf` + `current_approval.pdf` + `scores.json`
- `experiments/generate_ai_cad.py` — OpenRouter Nano Banana Pro benchmark script
- `experiments/ai_benchmark.md` — benchmark findings and structural AI image-gen limitations

**Patterns established:**

- **`git checkout <branch> -- <files>`** is the cleanest way to bring specific files from a feature branch to main when commits mix concerns. Avoids pulling in unrelated experiment scripts or dependency changes.
- **`_dedup_wall_coords(coords, tol=0.125)`**: when rooms are separated by a 0.115m wall gap, both `ra.x+ra.width` and `rb.x` appear in the room coordinate set. Keeping both causes doubled walls. The dedup helper drops any coord within `tol` of its predecessor (sorted list), keeping the first (left/bottom face).
- **Window symbol on solid wall**: architecturally correct approach is solid wall + 3 parallel lines + end jamb caps drawn on top. Do NOT open the wall for window positions.
- **Door gap key discipline**: store under the face coordinate of the "first" room only (`ra.x+ra.width` for vertical, `ra.y+ra.depth` for horizontal). The deduplication of xs/ys ensures the matching coordinate is visited exactly once.
- **OpenRouter Gemini response format** (non-standard): images are in `choices[0]["message"]["images"][0]["image_url"]["url"]`, NOT in `message.content` (which is `null`). Standard OpenAI content array does not apply.
- **VQ ceiling at 16/20**: the LLM visual-quality judge has ±1pt stochasticity. Both our system and the AI benchmark hit the same 16/20 ceiling. Cannot improve further without fundamental layout geometry changes (narrow 0.9m staircase, door arcs at wall face = correct architectural convention).
- CCQS scores: Standard **96/100**, Approval **96/100** (Visual Quality 16/20 — geometric ceiling confirmed).
