# PlanForge Stage 1 — Phase 0 Audit & Prioritized Plan

**Prepared:** 2026-07-03 (Fable 5)
**Status:** AWAITING KARTHIK'S APPROVAL — no code written yet
**Governing filter:** every item judged by *"does this survive the pivot to structural (Stage 2)?"*
**Locked decisions (Q&A 2026-07-03):** render-model bake-off before productizing · CCQS CI gate =
deterministic 4 components only · canvas replaces wall-drag edit mode (Pro gating carries over) ·
one PR per phase · work in a git worktree.

---

## 0. How this audit was done

Four lenses: layout engine, API/auth/payments, frontend/edit path, exports/CCQS. The engine lens ran
as a dedicated audit agent (full report received); the other three were completed inline with targeted
reads of every security- or geometry-critical file after the remaining agents hit the session limit.
Backend: 27 test files / 189 tests. Frontend: 5 test files (all auth/proxy from PR #10) — zero
component/geometry logic tests.

---

## 1. The central architectural finding (keystone for all three phases)

**PlanForge has no persisted layout.** Every consumer re-runs the CP-SAT solver independently:

| Consumer | Evidence | Consequence |
|---|---|---|
| `GET /projects/{id}/generate` | `generate.py:117` | Every page load re-solves (5s budget) |
| Public share view | `share.py:259` | Client may see a **different plan** than the engineer shared; anonymous solver CPU burn on Cloud Run |
| PDF / approval PDF / DXF / BOQ exports | `export.py:92,137,195,563` | **What you see is not what you export** |
| Revision snapshots | `revisions.py:195,306` | "Snapshots" record a fresh solver re-run, not the user's state |
| Agent-chat room edits | `rooms.py:33-34` module-level dicts | Edits vanish on Cloud Run cold start (`min-instances=0`) and aren't shared across instances (`max=3`) |
| Edit-mode "Save" | `layout-viewer.tsx:546-564` | Sends only `new_width/new_depth` to the in-memory resize endpoint — **x/y wall-drag positions are silently dropped**, and the in-memory state was initialized from `layouts[0]` of a *fresh* solve, not the layout being edited |

**Why this is the Phase 1 keystone:** canvas-first editing (Phase 3) is impossible to build correctly
on this foundation; AI renders (Phase 2) must render the layout the user actually sees; and Stage 2
structural automation needs one canonical stored geometry to compute loads against. Fixing this is the
single most durable investment in the codebase.

---

## 2. Phase 1 — Foundational bug audit + fix (prioritized)

Each item ships with a regression test (TDD). One worktree branch, one PR.

### Tier A — Architectural correctness (the durable foundation)

**A1. Persist generated layouts (keystone).**
New `layout` table (SQLAlchemy, JSON geometry column storing the existing `LayoutOut` shape + a
`source` field: `solver | edited`). `generate` writes 3 rows; viewer, share, exports, revisions, BOQ,
and room edits all **read the stored row** instead of re-solving. Regenerate becomes an explicit user
action. The in-memory `_layout_state`/undo dicts in `rooms.py` are replaced by DB reads/writes.
*Pivot-durability: Stage 2 computes structure from a canonical stored geometry — this IS the seam.*
*Fixes en passant: share-view nondeterminism, export mismatch, Cloud Run state loss, revision lie.*
Effort: L. **Uses `db-migration-safe` workflow before the schema change.**

**A2. Single canonical geometry module — `engine/geometry.py`.**
One `buildable_polygon(cfg) -> Polygon` used by solver, archetypes, compliance, and rooms.py.
Replaces **four** divergent implementations (`solver.py:76-89`, `archetypes.py:63-66`,
`compliance.py:370-439`, `rooms.py:79-85`). Implements **per-edge setbacks** (current code averages
the 4 setbacks and applies a uniform `buffer(-avg)` — front setback under-enforced, sides
over-enforced, and compliance validates against the same wrong boundary so it never flags it).
Guards `MultiPolygon`/empty results explicitly.
*Pivot-durability: structural loads are computed from this exact boundary; four disagreeing copies is
a Stage 2 blocker.* Effort: M.

**A3. L-shape attribute-name bug (immediate, user-visible).**
`share.py:104-105` and `rooms.py:202-203` read `project.cutout_width_m` / `cutout_height_m`; the DB
columns are `cutout_width` / `cutout_height` (`models/project.py:84-88`). `getattr` defaults to 0.0 →
**L-shaped projects silently render as full rectangles in the share view and agent-edit state.**
Largely subsumed by A1, but gets its own regression test. Effort: XS.

### Tier B — Compliance math (wrong answers today)

**B1. Staircase width uses AND instead of min-dimension** (`compliance.py:349-354`): a 0.8m × 3.0m
stair passes the 0.9m NBC minimum. The test at `test_engine.py:102` encodes the same bug. Fix to
`min(width, depth)`. *Pivot: stair geometry feeds Stage 2 stair design.* XS.

**B2. Beam-span check only tests one axis** (`compliance.py:356-362`): a 3×6m room's 6m span is
unflagged. Fix to `max(width, depth)`. *Pivot: this IS a structural check.* XS.

**B3. FAR floor count ignores `num_floors`/stilt** (`compliance.py:403-409`): G-only plots counted as
2 floors; stilt counted as habitable. *Pivot: FAR/floor semantics carry into structural load combos.* S.

**B4. Coverage/FAR computed from buildable envelope, not actual rooms** (`compliance.py:373-392`):
reported numbers disconnected from the drawing. *Pivot: BOQ/structural quantities derive from real
built area.* S.

**B5. Trapezoid silently mishandled end-to-end**: solver has no trapezoid branch (falls through to
full rectangle, `solver.py:256-260`), compliance likewise (`compliance.py:387-391,455-459`); only the
archetype fallback shrinks to `min(front,rear)` width. Zero tests exist. Fix by routing trapezoid
through A2's polygon path (same half-plane machinery the quad path already has). M.

**B6. Solver adjacency objective is dead code** (`solver.py:369-404`): the maximized expression is a
constant — the solver returns the first feasible packing and "optimizes" nothing. Fix the objective
(real overlap-based adjacency) or delete it honestly and document that scoring is post-hoc. *Pivot:
layout quality is the product's core claim; also unblocks meaningful Phase 3 re-solves.* M.

### Tier C — Security / robustness (trust and revenue)

**C1. Razorpay verification doesn't bind plan/amount to the order** (`payments.py:86-115,164-197`):
signature covers only `order_id|payment_id`; `body.plan` is trusted → pay ₹499 basic, verify with
`plan:"firm"` → firm tier for ₹499. Same for credit packs. **Plus no idempotency**: replaying one
valid payment adds credits repeatedly. Fix: fetch the order from Razorpay (or store order→plan at
creation), verify amount+notes match, and record consumed `payment_id`s. *Worth doing regardless of
pivot — it's revenue.* M.

**C2. Public share/approval endpoints hardening** (`share.py:274-318`): unauthenticated
approve/request-changes with no rate limit and unbounded `note` length; approval state can be flipped
by anyone with the token forever. Cap note length, add per-token rate limiting, optional token
regenerate/revoke. S.

**C3. Input validation on PlotConfig ingestion**: no guard against negative setbacks, zero/negative
dims, cutout ≥ plot, >50m dims (`MAX_DIM_MM` declared but unused, `solver.py:25`). Reject at the
Pydantic schema layer. *Pivot: garbage geometry in → garbage structure out.* S.

### Tier D — Config & test-debt

**D1. Hardcoded rules → JSON** per project convention: wall thicknesses & stair dims duplicated in
`archetypes.py:20-27` vs `compliance_rules.json`; two *different* adjacency tables
(`solver.py:35-42` vs `scorer.py:32-38`); inconsistent aspect-ratio caps (solver 3:1, scorer 2:1);
~20 inline `rules.get(..., default)` fallbacks that silently diverge from the JSON. S.

**D2. Frontend test baseline.** Recommend **bun:test, not Vitest** (deviation from the brief:
repo already runs bun:test with 28 passing tests; your global rules say "prefer bun native"; adding
Vitest would mean two runners). Cover: `detectSharedWalls` (`floor-plan-svg.tsx:824`), edit-save
logic, compliance-issue mapping, unit conversions. Backend: add the roadmap's named gaps
(compliance-check endpoint, share token, revision lifecycle, BOQ city rates, blank-area auto-fill,
`_absorb_into_adjacent` overlap bug). M.

*Explicitly skipped:* cosmetic UI bugs, everything in `docs/issues_15_03_26.md`, Vastu rule-table
extraction (logic-heavy, low churn).

---

## 3. Phase 2 — Enhanced outputs from existing geometry

**2a. AI render layer** (headline image-quality deliverable).
- `engine/render_prompt.py`: builds a structured spatial prompt from the **persisted layout JSON**
  (room polygons, dims, adjacencies, north, plot orientation) + the SVG rendered to PNG as the
  reference/control image. Pure function — testable without any API.
- Provider adapter (config-driven, like the OpenRouter pattern): **bake-off first** — Gemini image
  API vs OpenAI gpt-image vs an OpenRouter image model on 2–3 real layouts; I present renders +
  per-image cost; you pick. Then productize behind `RENDER_PROVIDER`/`RENDER_API_KEY` env.
- Output: "Render" tab in the layout viewer + "Export as Render" alongside "Export as CAD".
  Renders cached per layout-hash (regenerate only when geometry changes). Tier-gated (Pro or
  per-render add-on — decided at bake-off review when we know unit cost).
- *Pivot-durability: the same SVG→prompt→image pipeline renders structural sections in Stage 2 —
  the design doc names this explicitly.*

**2b. CCQS productization.**
- Extract the 4 deterministic components of `experiments/eval.py` into `backend/app/quality/ccqs.py`
  (pymupdf only, no API). CI job: generate a fixture project's PDF → score → fail if below the
  `experiments/scores.json` baseline minus tolerance. TDD: the regression test is written against the
  known-good baseline *before* wiring the gate.
- User-facing badge: deterministic subscore computed at PDF-generation time, displayed on the layout
  card ("CAD Quality 76/80"). Vision VQ stays a dev-time tool (OpenRouter-first fallback already in
  `eval.py:132-191`) until billing allows.
- *Pivot-durability: the gate protects drawing quality through Stage 2's heavy DXF/PDF churn — it's a
  ratchet for both stages.*

---

## 4. Phase 3 — Canvas-first editing + drafted-class UX

**3a. Canvas editor (PRIMARY edit surface, replaces wall-drag mode).**
- Extend the existing SVG surface into full direct manipulation: select room → drag to move,
  handles to resize, snap to wall grid (115/230mm) and to neighbors. Keep the proven pieces:
  debounced stateless `compliance-check` endpoint (`rooms.py:596`) and per-room issue highlighting.
- **Write-back:** `PATCH /projects/{id}/layouts/{layout_id}` persists the full edited geometry to the
  A1 layout row (`source: "edited"`), server-side validated with Shapely (`_check_placement` logic
  generalized to the A2 canonical boundary). DXF/PDF/BOQ/share automatically export the edited
  geometry because after A1 they all read the stored layout. Undo/redo moves client-side.
- Pro gating carries over from the old edit mode (your call, locked).
- *Pivot-durability: edited geometry is still Shapely polygons in the DB — Stage 2 consumes it
  identically to solver output.*

**3b. Agentic/AI edit (SECONDARY, optional, default-off).**
Refactor the 10 agent tools in `rooms.py` to operate on the persisted layout (same PATCH path as the
canvas) instead of `_layout_state`. Feature-flagged off until Anthropic billing; OpenRouter fallback
already exists. S (mostly deletion once A1 lands).

**3c. Input re-expression on canvas (no new inputs).**
The generate form's existing inputs (plot dims, setbacks, road side, north) get a visual plot preview
on the same canvas component — draw nothing new, just render the config interactively before solving.

**3d. Drawing-output polish (drafted parity).**
DXF walls/doors/windows grouped into blocks and snapped to standard sizes (900mm doors, 1200mm
windows, 115/230mm walls) via config table; renders + clean CAD as co-equal tabs in
`layout-viewer.tsx`. CCQS gate (2b) protects against regressions while doing this.

**3e. Async generation pipeline — Inngest (added 2026-07-05, Karthik's call after v2 field testing).**
*Problem observed live on v2:* first generate on a fresh project = Cloud Run cold start + full
CP-SAT solve > the 15s `fetchBackend` timeout → user sees "Layout engine offline" while the solve
either dies (client disconnect cancels the request) or silently succeeds. A plain 202 +
background task is NOT viable on Cloud Run `min-instances=0`: CPU is throttled to ~0 after the
response is sent, so in-process background solves stall. A durable runner is required — Inngest,
per the standing stack rule.
- **Backend:** serve Inngest functions from FastAPI (`inngest-py`'s FastAPI integration) — a
  `layout/generate.requested` function that runs `regenerate_and_store()` with retries and a
  sane timeout, then emits `layout/generate.completed`. Cloud Run needs `--cpu-always-allocated`
  OR (cleaner) Inngest invokes a dedicated HTTP endpoint so the solve runs inside a normal
  request lifecycle with the executor holding the connection.
- **Frontend:** generate becomes non-blocking — POST enqueues the event and returns 202 with a
  job id immediately; the project page renders a "Generating your 3 layouts…" progress state.
  Realtime updates via Inngest Realtime (publish per-stage progress: solving → scoring →
  compliance → stored) with SWR polling of `GET /projects/{id}/layouts` as the fallback path.
- **Same pipeline for AI renders (Phase 2's endpoint):** `render/requested` event wraps the
  10–30s gpt-image-1 call; the Render tab subscribes for progress instead of a spinner on a
  blocking POST. Two consumers on day one justifies the abstraction.
- **Scope guard:** Inngest wraps the two provably-slow paths only (generate, render). Everything
  else stays synchronous — no event-sourcing rewrite, no queue-all-the-things.
- *Pivot-durability: Stage 2 structural computation is strictly heavier than layout solving —
  the async pipeline is a prerequisite there anyway; building it in Phase 3 pays forward.*

---

## 5. Sequencing, risks, logistics

- **Order within Phase 1:** A1 → A2/A3 → B* (parallelizable) → C* → D*. A1 first because nearly every
  other fix's regression test wants a stable layout to assert against.
- **Risk — A1 scope:** persisting layouts touches viewer, share, exports, revisions, rooms, agent
  chat. Mitigation: the stored JSON is byte-shaped like today's `GenerateResponse`, so consumers
  change from "call generate()" to "read row" with no shape change; `db-migration-safe` gates the
  schema.
- **Risk — solver objective (B6)** may change generated layouts and thus `scores.json`/CCQS baselines;
  do it before wiring the CI gate, re-baseline once.
- **Session-limit note:** subagent-heavy execution (parallel test-writing, pr-quality-gate) resumes
  after the plan limit resets (6:50pm IST today).
- Worktree per phase; one PR per phase via `finish-feature`; conventional commits.

## 6. What I need from you

1. **Approve / amend this Phase 0 plan** (especially Tier A — A1 is the big structural bet).
2. Confirm B6 choice: fix the solver objective properly (M) vs. delete it and rely on post-hoc
   scoring (S). My recommendation: fix it — it's the product's core "3 scored options" claim.
3. Phase 2 bake-off needs at most: a Gemini API key (free tier) — OpenAI/OpenRouter keys you already
   have. No spend beyond a few test renders (~₹50 total) without your sign-off.
