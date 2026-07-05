# Combined Plan: Stage-1 Phase 3 (3a–3e) + CAD-Quality Drawing Overhaul (v2)

## Context

Two efforts were planned against `v2` independently:

1. **Phase 3 plan** — `docs/superpowers/plans/2026-07-05-stage1-phase3-canvas-async.md`
   (committed on v2, 15 tasks, line refs verified @ `717acd8`): 3e Inngest async
   generation (live cold-start failure — urgent), 3a canvas room editing, 3b agent undo
   persistence, 3c plot preview, 3d opening-size config + DXF blocks, firm-tier gate fix.
2. **CAD overhaul** (this session): the SVG/PDF/DXF output is not professional quality
   and the CCQS loop plateaued (std 96 / appr 96, VQ pinned 16/20, 15+ `delta 0.0`
   experiments). Root cause is architectural: `models.py` has only `Room` rects +
   `Column` points — **no wall/door/window entities** — so four renderers re-derive them
   independently with four tolerances (SVG 0.01 `floor-plan-svg.tsx:824` · DXF 0.05
   `cad_primitives.py:97` · std PDF 0.15 `pdf.py:327` · appr PDF 0.15 `approval_pdf.py:469`).

**Confirmed output defects (verified first-hand on rendered pages):** phantom full-span
internal walls (`pdf.py:448-483`, `cad_elements.py:129-137`); interior columns at raw
coords, colliding with windows (`pdf.py:518-553`); hardcoded door swings (`pdf.py:753`);
`master_bedroom` missing from window sets (`pdf.py:676`, svg `:1098`); truncated/overlapping
text — `[:22]+"…"` (`pdf.py:1219`), `[:190]` (`:1270`), `[:35]` (`approval_pdf.py:1055`);
fit-to-page "1:69" scale (`pdf.py:229-243`); approval floor pages have **no doors, windows,
or dimension chains**, FAR table overlaps the plan, E/W roads get no road strip
(`approval_pdf.py:179-198`); FF band labeled "Toilet 2 — 275 SQFT" (blank-area absorption
in `generator.py:77-230` without type caps); CCQS blind to all of it.

**User decisions (2026-07-05):** backend-computed canonical geometry for all renderers
incl. SVG · strict B/W municipal approval style · include label fix + deterministic metric.

## Mismatch audit (phase-3 plan vs CAD plan) and resolutions

| # | Collision | Resolution |
|---|---|---|
| M1 | **`floor-plan-svg.tsx`**: 3a Tasks 7–10 add selection/move/resize/undo against current internals (`editRooms` :1052, handlers :1137/:1233); CAD rewrites its rendering to project backend geometry | **Phase 3 first.** Its specs are line-verified @`717acd8`; CAD-first would invalidate all of them. Canvas code targets room *rects*, which survive the CAD rewrite. Rule for the CAD pass: **view mode** renders the backend `drawing` payload; **edit mode** keeps simple room-rect rendering (walls dimmed/stale during drag), refreshed `drawing` arrives via the existing PATCH response on save. Don't touch Task 7–10 internals. |
| M2 | **3d overlaps the CAD opening model**: Task 13 creates `standards.py` + `standard_openings` config; Task 14 creates `cad_blocks.py` PF_* blocks; CAD Phase C creates canonical openings + DXF projection | 3d ships first, becomes a **contract**: CAD builder reads sizes ONLY from `get_opening_standards()`; CAD DXF keeps PF_* block inserts, swapping their placement source from `collect_openings()` to the canonical model (then deletes the 3 duplicate detectors). |
| M3 | **Layout JSON**: 3e Task 2 adds read-only `GET /projects/{id}/layouts`; CAD adds a `drawing` payload | Add `drawing` in ONE place — `layout_store.to_generate_response()` (`layout_store.py:159`) — so generate, the Task-2 read endpoint, and the PATCH response all carry it. Computed at serialization from rooms (pure Shapely, fast) — **no schema change** (no `db-migration-safe` needed), **stays synchronous** (respects the phase-3 scope guard: Inngest wraps only generation + AI render). |
| M4 | **`export.py`** edited by Task 1 (tier gate), Task 14 (block inserts), CAD DXF projection | Strict order: Task 1 → Task 14 → CAD DXF. |
| M5 | Branch conventions differ (phase-3: worktree branch off v2, PR into v2; CAD draft said "work on v2 directly") | Adopt the phase-3 convention for everything: one worktree branch per part, PR into `v2` via `finish-feature`, no merges without Karthik's say-so. |
| M6 | 3c plot preview draws its own mini-SVG | No conflict (plot boundary + setbacks only). Leave as-is. |

No other overlaps: 3b/3e touch jobs/undo/infra files the CAD work never edits; CAD's
generator/metric/PDF files are untouched by phase 3.

---

## PART 1 — Execute the Phase-3 plan as written (Sprints 1–3)

**Source of truth:** `docs/superpowers/plans/2026-07-05-stage1-phase3-canvas-async.md`.
Execute its Tasks 1–15 in its own order via `superpowers:subagent-driven-development`,
on branch `worktree-stage1-phase3` off `v2`; finish with its Task 15 →
`Workflow({ name: 'finish-feature' })` → PR into `v2`.

- Sprint 1: Task 1 (tier gate) + Tasks 2–6 (**3e** async generation — live failure, urgent).
- Sprint 2: Tasks 7–10 (**3a** canvas), Task 11 (**3b**), Task 12 (**3c**).
- Sprint 3: Tasks 13–14 (**3d** standards + DXF blocks), Task 15 (status/deploy/handoff).

Amendments while executing (forward-compatibility with Part 2): none functional — only
awareness that `standards.py`, `cad_blocks.py`, and the room-rect drag targets are
contracts Part 2 consumes.

## PART 2 — CAD-Quality Overhaul (Sprints 4–7, branch `worktree-cad-quality-v3` off v2 after Part 1 merges)

**No new dependencies required** (shapely, reportlab, ezdxf, pymupdf already present).
Optional: embed one TTF (DejaVu Sans Condensed) via ReportLab `TTFont` for drafting look.
Reference: `docs/Guides/Shapely_Structural_Drawing_Guide_*.pdf`, unmerged
`feature/autoresearch-cad-quality` (commits `948abbe`, `31f9ad6`) for validated stair/tick
conventions.

### Sprint 4 — Canonical drawing model (L, sequential, in-session — core geometry reasoning)

Phase 0 (S): port the experiments fixture (11×12 m 2BHK G+1, `experiments/prepare.py:28-50`)
into `backend/tests/fixtures/`; add a pymupdf render-to-PNG test helper. TDD baseline.

Phase 1 (L): `backend/app/engine/plan_geometry.py` — `build_floor_drawing(floorplan, cfg)
-> FloorDrawing` + `.to_dict()`; extend the dataclasses in `cad_elements.py` (keep names,
fix derivations):
1. **Walls from actual shared room edges** (pairwise interval overlap, ONE tolerance
   0.01 m) + exterior ring from `geometry.buildable_polygon()`; collinear merge;
   EWT 0.23/IWT 0.115; Shapely-union buffered centerlines → clean junctions by
   construction. Tests: no wall crosses a room interior; every room edge covered.
2. **Openings first-class** on wall segments — sizes from `get_opening_standards()`
   (Task 13). Doors: ≥1 per non-passage room, hinge 115 mm from jamb, swing into the
   room. Windows: habitable **incl. `master_bedroom`**; ventilators for wet rooms —
   unify on `collect_openings()` semantics, then delete the other three detectors.
   Constraint pass: zero opening↔column/opening↔opening collisions (shift along wall).
3. **Columns from wall-graph junctions only**, snapped to centerlines, deduped.
4. **Dimension chains ×3 levels** (room/overall/setback) on all four sides, lane-allocated.
   Tests: chain sums = overall; every exterior span dimensioned.
5. **Label boxes measured** via ReportLab `stringWidth`; fit rules shrink → 2-line →
   abbreviate → leader. Tests: zero overflow across archetypes A–F.
6. **Stair geometry**: treads/risers, mid-flight break line, arrow with tail, numbering.

### Sprint 5 — Renderers become projections (parallel subagents — disjoint files)

1. **`pdf.py` (M):** consume FloorDrawing; true standard scale (largest of 1:50/1:100/1:200
   fitting A4; honest title block); line-weight hierarchy 0.50/0.25/0.13 mm; extension
   lines + arch ticks; title block with measured text + wrapping + full-width area
   schedule band — remove every `[:n]` truncation.
2. **`approval_pdf.py` (M):** strict B/W (no fills, 45° wall hatch); doors/windows/dim
   chains ON approval floor pages; FAR table in a reserved margin band; road strips for
   all 4 sides; section view from real storey geometry; measured label placement (fixes
   clipped NORTH/setback text).
3. **DXF in `export.py` (S/M):** consume FloorDrawing; keep layers + `ARCH_MM` + PF_*
   blocks (Task 14); delete its private derivation; plain TEXT where MTEXT `\P`/`{\L…}`
   codes garble.
4. **Generator fixes (S, parallel):** cap `_fill_blank_areas`/`_absorb_into_adjacent`
   absorption at per-type max area (toilet ≤ ~6 sqm); relabel over-expanded wet rooms to
   passage/hall/terrace; wet-room aspect-ratio guard. Tests across archetypes + solver.

### Sprint 6 — Frontend projection (M)

- Add `drawing` to `to_generate_response()` (M3) + TS types in `frontend/src/lib/layout-types`.
- `floor-plan-svg.tsx`: **view mode** projects the payload verbatim (keep Blueprint-Dark
  colors/tabs); **edit mode** untouched (3a canvas operates on room rects; drawing layer
  dimmed while dirty, refreshed from the PATCH response via `handleSaveEditedRooms` :751).
  Delete `detectSharedWalls`/wall-grid/window derivation (~600 lines). Fix duplicate React
  key on `columns.map`. `section-view-svg.tsx` consumes real storey geometry.

### Sprint 7 — Metric v2 + regeneration + sign-off

- **Geometric Correctness Score** extending `backend/app/quality/ccqs.py`, computed from
  FloorDrawing (not pixels): phantom walls = 0, collisions = 0, label overflow = 0,
  dimension coverage %, standard-scale bool, doors/room ≥ 1, windows per habitable.
  Becomes the export quality gate.
- `experiments/eval.py`: VQ = median of 3 judge calls, reference-anchored rubric; report
  GCS alongside. Regenerate `current_standard.pdf`/`current_approval.pdf`.
- **Render PNGs and show Karthik for approval** against the defect inventory (global
  artifact-approval rule) before `finish-feature` → PR into `v2`.

---

## Verification (each PR, per stack)

1. `cd backend && uv run pytest` (new geometry/label/metric tests + existing suite);
   `uv run ruff format . && uv run ruff check .`; `docker build ./backend`.
2. `cd frontend && bun test && bun run lint && bun run build`; Vercel preview of `v2`
   for visual checks (canvas editing, SVG projection, all viewer tabs).
3. Part 1 extra: Inngest deploy steps in phase-3 plan Task 15 (event/signing keys,
   dashboard sync) before merge to main.
4. Part 2 extra: `uv run python experiments/prepare.py` → PNG review vs defect list;
   GCS = 100 on the golden fixture; DXF opened via ezdxf `recover`+audit in a test.

**Execution mode:** `superpowers:subagent-driven-development` throughout (per standing
preference) — fresh subagent per task, review between tasks. Nothing merges to `main`
without Karthik's explicit go-ahead.
