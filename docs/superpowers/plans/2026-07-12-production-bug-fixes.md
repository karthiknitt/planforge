# Production Bug Fixes (Planforge_bug_fixes.pdf) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 11 production bugs reported by the pro-tester on 2026-07-12 (layout space waste, section view, BOQ totals, Excel export, per-floor renders, stale AI images, navbar overflow, PDF composition, marketing auth state, dark dropdown contrast, AI render accuracy).

**Architecture:** Branch `fix/prod-bugs-2026-07-12` off `origin/main` (contains merged PR #23). Fable (orchestrator) implements the two hardest tasks inline in the main checkout; Opus/Sonnet/Haiku subagents run in parallel isolated git worktrees on disjoint files, each committing to its own branch; orchestrator reviews and merges each into the feature branch, then runs the full gate.

**Tech Stack:** FastAPI + Shapely + ReportLab + openpyxl (backend, uv/pytest/ruff); Next.js App Router + R3F + ShadCN + Tailwind v4 (frontend, bun/Biome).

## Global Constraints

- Never commit secrets; conventional commits; never delete branches.
- Backend gates: `uv run ruff format && uv run ruff check` + scoped `uv run pytest`.
- Frontend gates: `bun run lint` (Biome) + `tsc --noEmit` via `bun run build` check + `bun test`.
- Neon schema: new `LayoutRender.floor` column is added via the existing `auto_migrate_missing_columns` startup path — no Alembic/Drizzle migration needed (backend-only SQLAlchemy table).
- All parallel write-subagents get the worktree steering preamble from `~/.claude/agent-steering.md`.

---

## Model-Tier Assignment Summary

| Task | Bug(s) | Complexity | Model | Mode | Wave |
|---|---|---|---|---|---|
| F1 FF layout space optimization | #1 | Very high (geometry algorithm) | **Fable** (orchestrator, inline) | main checkout | 1 |
| F2 Per-floor renders + top-down view + stale-image fix | #5, #6 | Very high (cross-stack, DB keying) | **Fable** (inline) | main checkout | 2 (after F1) |
| F3 AI render accuracy verification (PR #23 follow-up) | #11 | High (investigation) | **Fable** (inline) | main checkout | 3 (after F2) |
| O1 PDF page composition + title-block standardization | #8 | High (2 large ReportLab files) | Opus | worktree subagent | 1 |
| S1 Section view centering | #2 | Medium | Sonnet | worktree subagent | 1 |
| S2 Marketing pages auth state | #9 | Medium | Sonnet | worktree subagent | 1 |
| H1 BOQ total formatting + Excel export | #3, #4 | Low | Haiku | worktree subagent | 1 |
| H2 Tab-strip scrollbar + dark dropdown contrast | #7, #10 | Low (CSS) | Haiku | worktree subagent | 1 |

Wave 1 runs fully in parallel (disjoint files except a trivial `layout-viewer.tsx` className touch in H2, resolved at merge). Fable finishes F1 → F2 → F3 sequentially while wave-1 subagents run in background.

---

### Task F1: First-floor layout space optimization (Bug #1) — Fable

**Files:**
- Modify: `backend/app/engine/archetypes.py:435-499` (FF construction, Study placement at 468-481)
- Modify: `backend/app/engine/generator.py:77-227` (`_fill_blank_areas`), `generator.py:299-361` (`_absorb_into_adjacent`)
- Test: `backend/tests/test_ff_space_optimization.py` (new)

**Root cause:** Study depth hard-capped at `min(d_bed, 3.0)` and width fixed to `STUDY_W = 2.5`, leaving a rectangular gap in the FF band. `_fill_blank_areas` only creates new rooms when leftover fills ≥70% of its bbox, else `_absorb_into_adjacent` grows the single *largest* neighbour (usually the Passage → 38.61 m²) instead of the adjacent habitable room the gap belongs to.

- [ ] Write failing tests: generated FF layouts have (a) no leftover rectangle > 1.0 m² adjacent to a habitable room that could legally absorb it, (b) Study area grows to fill its band when space allows, (c) Passage area ≤ a sane share (e.g. ≤ 15% of floor area when habitable neighbours exist).
- [ ] Fix archetypes: let `d_study = d_bed` (fill band depth) and fit `study_w` to residual width between the bedroom block and plot edge (respect min 2.2 m / compliance).
- [ ] Fix generator: in `_absorb_into_adjacent`, prefer the neighbour whose shared edge fully covers a side of the gap and is habitable (bedroom/study/living/dining) before falling back to largest; never balloon `passage` when a habitable neighbour is eligible.
- [ ] Run scoped tests: `uv run pytest tests/test_ff_space_optimization.py tests/test_plan_geometry.py tests/test_multi_floor.py tests/test_solver.py -q` → all pass; full `uv run pytest` before commit.
- [ ] Commit: `fix(engine): expand FF rooms to fill residual space; stop passage ballooning`

### Task F2: Per-floor renders, top-down R3F view, stale AI image (Bugs #5, #6) — Fable

**Files:**
- Modify: `frontend/src/components/plan-3d-scene.tsx` (camera preset prop: `view: "iso" | "top"`, default top-down plan view)
- Modify: `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx` (RenderTab ~190-401, offscreen scene 1883-1903, r3f tab 2442-2480): per-floor capture + per-floor AI render sections, distinct display per floor
- Modify: `frontend/src/lib/render-tab.ts` (URL builder gains `floor`), `frontend/src/app/api/backend/[...path]/route.ts` (add `Cache-Control: no-store` for render GETs)
- Modify: `backend/app/models/render.py` (add `floor` column), `backend/app/services/render_runner.py` (`find_render`/`perform_render` keyed by **project_id + layout_id + floor** + hash/provider/model; pass `floor` to prompt), `backend/app/engine/render_prompt.py` (use floor param), `backend/app/api/routes/render.py` + `jobs.py` (accept `floor`)
- Test: `backend/tests/test_render_endpoint.py`, `test_render_jobs.py`, `test_render_prompt.py` (extend); `frontend/src/lib/render-tab.test.ts` (extend)

**Root cause (stale image):** `find_render` filters by `layout_id` only — layout IDs are short codes ("A", "S1") shared across projects, so project B gets project A's PNG. Frontend never resets the `?v=` cache-buster on project change and the proxy sends no `Cache-Control`.

- [ ] Backend: add `floor` column; scope `find_render` by `project_id` (+ floor); GET render returns 404 when no render exists for this project/layout/floor (frontend shows blank + generate CTA — never another project's image).
- [ ] Frontend: default R3F camera top-down plan view with iso toggle; enumerate `availableFloors` (GF/FF/…); one 3D snapshot + one AI render per floor, viewable distinctly (per-floor selector inside Render/AI Render tabs); `version` state resets on project/layout change; render URLs include floor.
- [ ] Tests green (`uv run pytest` scoped + `bun test`), lint both stacks.
- [ ] Commit: `fix(render): per-floor top-down renders; scope render cache by project+layout+floor`

### Task F3: AI render accuracy verification (Bug #11) — Fable

**Files:** `backend/app/engine/render_prompt.py`, analysis notes in `docs/plans/2026-07-12-ai-render-accuracy-notes.md`

- [ ] Verify PR #23's R3F conditioning actually reaches gpt-image-2 (multipart path fixed in `e7125f1`); confirm with tests, not prod calls.
- [ ] Improve prompt fidelity: inject per-room labels + dimensions + floor into the prompt; forbid inventing parking/paving where the plan has none; assert staircase position; leverage F2's top-down reference (a plan-view reference should constrain geometry far better than the iso view).
- [ ] Document findings: what was PR #23 gap vs model limitation; recommended follow-ups.
- [ ] Commit: `fix(render): tighten AI render prompt fidelity (rooms, dims, no invented parking)`

### Task O1: PDF composition + title blocks (Bug #8) — Opus

**Files:**
- Modify: `backend/app/engine/pdf.py` — `_draw_floor_projected` (1766-1876, plot `oy` at 1786-87), `_draw_structural_floor` (1244-1447, `oy` at 1261-62), table calls (1856-1862), `_draw_title_block` (1450-1563), constants (177-181)
- Modify: `backend/app/engine/approval_pdf.py` — `_draw_approval_floor_plan` (495-614, `oy` 531-32, tables 602-606), `_draw_professional_title_block` (810), `_draw_approval_title_block` (938)
- Test: `backend/tests/test_pdf_section_pages.py` + new `test_pdf_page_composition.py`

**Root cause:** plan pages bottom-anchor the plot (`oy = TITLE_H + MARGIN + ROAD_H + ROAD_GAP`) while section/elevation pages (page 6 — the reference look) center within a region.

- [ ] Vertically center the plot in the band between title block and top margin on all plan/structural/approval pages (mirror the section-region math).
- [ ] Move area/openings schedule tables from top corners to bottom-right, stacked above the title block (keep north arrow top-right); no overlap with plot at any plot aspect ratio (guard: shrink scale if needed).
- [ ] Standardize on ONE title-block renderer shared by both PDFs (unify `_draw_title_block` and approval variants; same fields/geometry, per-PDF title text).
- [ ] Golden/regression tests pass (`uv run pytest tests/test_pdf_section_pages.py tests/test_pdf_page_composition.py` + full suite); ruff clean.
- [ ] Commit: `fix(pdf): center plots on all pages, move schedules to bottom-right, unified title block`

### Task S1: Section tab centering (Bug #2) — Sonnet

**Files:** `frontend/src/components/section-view-svg.tsx` (fix at line 64); caller `layout-viewer.tsx:2337-2341`

**Root cause:** `oy = PAD_T + FOUND_D * scale + (drawH - totalHPx) / 2` — offsets ground line by foundation depth (0.6 m) instead of parapet top (7.3 m), pushing the drawing to the top.

- [ ] Fix `oy` to `PAD_T + EL_PARAPET_TOP * scale + (drawH - totalHPx) / 2`; pass setback-reduced building width from the caller so the section isn't artificially narrow; visually match the PDF section styling (centered, proportionate).
- [ ] `bun test` + lint green. Commit: `fix(ui): center section view and use building width after setbacks`

### Task S2: Marketing pages auth state (Bug #9) — Sonnet

**Files:** `frontend/src/app/(marketing)/layout.tsx`, `frontend/src/app/(marketing)/mobile-nav.tsx` (reference pattern: `src/app/(app)/layout.tsx:10-11`)

**Root cause:** marketing layout is a non-async server component that hardcodes "Sign In"/"Get Started" — it never fetches the Better Auth session.

- [ ] Make layout async, `await auth.api.getSession({ headers: await headers() })`; when logged in show Dashboard link + `UserMenu` instead of Sign In/Get Started; same for mobile nav. Ensure the layout isn't statically cached into an anonymous state (dynamic rendering via `headers()` is sufficient).
- [ ] `bun test` + lint green. Commit: `fix(auth): show logged-in state on marketing pages (pricing/gallery/how-it-works)`

### Task H1: BOQ total format + Excel export (Bugs #3, #4) — Haiku

**Files:** `frontend/src/components/boq-viewer.tsx` (line 26 divisor; `downloadExcel` 74-93); `backend/pyproject.toml` (verify `openpyxl`)

**Root cause (#3):** `formatINR` divides by `10_00_000` (10 lakh) but labels "L" → ₹31.16L shows as ₹3.12L. **(#4):** likely `openpyxl` undeclared → endpoint returns 501 and `downloadExcel` silently ignores non-OK responses.

- [ ] Fix divisor to `1_00_000`; render ≥1 crore as `₹X.XXCr`.
- [ ] Verify/add `openpyxl` in backend deps (`uv add openpyxl` if missing); add an `else` branch in `downloadExcel` surfacing the error (toast/message incl. 402 pro-gate text).
- [ ] Backend test asserting `fmt=excel` returns 200 + xlsx content-type for a pro user; `bun test` + scoped pytest green. Commit: `fix(boq): correct lakh formatting; make Excel export work and surface errors`

### Task H2: Tab-strip scrollbar + dark dropdown contrast (Bugs #7, #10) — Haiku

**Files:** `frontend/src/app/globals.css`, `frontend/src/components/ui/tabs.tsx`, `frontend/src/components/ui/select.tsx`, `frontend/src/app/(app)/projects/[id]/layout-viewer.tsx:1908-1911` (className only)

**Root cause (#7):** `scrollbar-none` utility referenced but (verify) not defined → native scrollbar stepper arrows appear in some browsers. **(#10):** native `<select>` options render on the browser default white popup with light text — no `color-scheme: dark`, no option styling.

- [ ] Define `scrollbar-none` (`scrollbar-width:none` + `::-webkit-scrollbar{display:none}`); make TabsList wrap or fit content (`flex-wrap` on narrow viewports) so all tabs are reachable without a scrollbar.
- [ ] Add `color-scheme: dark` under `.dark` in globals; style options `[&>option]:bg-popover [&>option]:text-popover-foreground`; make select bg opaque in dark (`dark:bg-input`).
- [ ] `bun test` + lint green. Commit: `fix(ui): kill tab-strip scrollbar arrows; readable dark-mode select options`

---

## Merge & Verification (Fable, Wave 4)

- [ ] Review each subagent branch diff, merge into `fix/prod-bugs-2026-07-12` (order: H1, H2, S1, S2, O1 — smallest first), resolve trivial `layout-viewer.tsx` overlaps.
- [ ] Full gates: `uv run pytest` (all), `uv run ruff format --check && uv run ruff check`, `cd frontend && bun run lint && bun test && bun run build`.
- [ ] Clean up worktrees (`git worktree remove`), push branch, open PR (what + why) referencing all 11 bugs; watch CI.

## Self-Review Notes
- All 11 PDF bugs map to tasks: 1→F1, 2→S1, 3→H1, 4→H1, 5→F2, 6→F2, 7→H2, 8→O1, 9→S2, 10→H2, 11→F3. No gaps.
- Type consistency: `floor` param naming used consistently across F2 frontend/backend ("ground_floor"/"first_floor" string keys as in `render_prompt.py:23`).
