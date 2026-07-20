# PlanForge — Status (Stage 1 Phase 1: Architectural Hardening)

**Branch:** `worktree-stage1-phase1-hardening` (worktree; NOT merged to main — per Karthik's standing instruction, nothing merges until he says so)
**Phase:** 1 of 3 (foundational bug audit + fix) — COMPLETE, awaiting sign-off
**Plan:** `docs/plans/2026-07-03-fable-stage1-phase0-plan.md` (approved 2026-07-03, expanded to include auth/UI-UX/payments bug hunts)

## Commits on this branch

| Commit | What |
|---|---|
| `ee7a534` | Compliance math (stair min-dim, beam both axes) + single Project→PlotConfig mapper (fixes cutout_width_m drop, export field drift) |
| `ecaa5ec` | Team-access parity, plan-expiry enforcement, INTERNAL_AUTH_SECRET ≥32 chars |
| `7b45710` | Razorpay verify bound to paid order + idempotent grants (consumed_payments) |
| `c171c83` | Geometry input validation + share hardening (note caps, revoke endpoint, NaN→500 fix) |
| `42db337` | **A1 keystone:** persisted layouts table; viewer/share/exports/revisions/rooms read ONE stored geometry; PATCH write-back endpoint |
| `5261681` | Frontend edit-save via PATCH (x/y no longer dropped) + cache revalidation |
| `1099a19` | **A2:** canonical geometry module, per-edge setbacks, trapezoid solved in-shape, live solver objective, coverage/FAR from real rooms |
| `61f1a3c` | Team-member page access, per-user cache key, bun test isolation fix, detectSharedWalls tests |
| (next) | D1: unified adjacency config |

## Test state
- Backend: 263 tests (was 189) — final full run in progress at write time
- Frontend: 35/35 bun tests, 0 fail (was 28 pass + 2 phantom fails from mock leakage)
- `db-migration-safe` gate: run, verdict clean; both mandates applied (explicit model imports, CASCADE FK on layouts.project_id)

## Deployment cautions (BEFORE merge/deploy)
1. `INTERNAL_AUTH_SECRET` in GitHub Actions secrets must be ≥32 chars or the backend will refuse to boot (new validator).
2. First boot creates `layouts` + `consumed_payments` tables via create_all — test on a Neon branch, not prod pooled URL.
3. Frontend edit-save now targets `PATCH /projects/{id}/layouts/{key}` — deploy backend before (or with) frontend.

## Known deferred items
- Rate limiting on public share/approve endpoints (needs infra decision — noted in plan C2)
- Archetype fallback for skewed quads still uses inset bounds (solver path is exact; archetypes are fallback-only)
- Team members' dashboards show team projects via backend list API only; Drizzle dashboard query is owner-only (pre-existing)
- Vision-judged CCQS component stays dev-time until Anthropic billing (locked decision)
---

# Stage 1 Phase 2: Enhanced Outputs (CCQS + AI Render Layer)

**Branch:** `worktree-stage1-phase2-outputs` (stacked on phase-1 branch; PR #11 still open)
**Plan:** `docs/superpowers/plans/2026-07-04-stage1-phase2-enhanced-outputs.md`
**State:** ALL 12 TASKS COMPLETE. Checkpoint resolved: RENDER_PROVIDER=openrouter, RENDER_MODEL=openai/gpt-image-1 (BYOK; OpenAI key fixed in OpenRouter integrations), tier gate pro+. Remaining: final whole-branch review + finish-feature PR (stacked on phase-1 branch).

## Commits on this branch (phase 2)

| Commit | What |
|---|---|
| `6c40452` | CCQS deterministic scorer (0–80) on PDF bytes; pymupdf → main dep |
| `c502fdb` | Frozen CCQS fixture geometry + committed baseline (80.0/80) |
| `8a93f05` | CCQS regression gate in CI pytest (mutation-checked) |
| `359f1b4`+`92c4285` | Layout quality endpoint (scores the annotated PDF) |
| `fac6c21` | Phase 2 implementation plan doc |
| `a4eb6b1` | Frontend CAD-quality badge on layout cards |
| `ee0cbcc` | pdf_page_png helper (PDF → PNG reference images) |
| `d150a55` | Spatial render-prompt builder from persisted geometry |
| `37c01ec` | Provider adapters (gemini/openai/openrouter), doc-verified shapes |
| `8d4b3a8` | Bake-off harness + script sys.path fixes |
| `d976aa5` | OpenRouter input_references object shape + multi-model bake-off |

## Test state (phase 2)
- Backend: 274 passing (was 263) incl. the CCQS CI gate; frontend: 37 bun tests passing (was 35).
- Every task passed an independent spec+quality review; Task 9 reviewed inline (session limits), covered by final whole-branch review before PR.

## Bake-off outcome (Task 10 checkpoint — resolved 2026-07-04)
gpt-image-1 (via OpenRouter BYOK) rendered all 3 test layouts to production quality; picked as default. Gemini comparison deferred — OpenRouter needs a credit balance to route Google AI Studio BYOK calls (402). Renders in `experiments/renders/`; per-image cost billed to the OpenAI account (~$0.03–0.07).

## Follow-up bugs found during review (NOT fixed in this phase)
- **First-generate cold-start timeout (seen live on v2, 2026-07-05)**: fresh project + cold Cloud Run + CP-SAT solve exceeds fetchBackend's 15s timeout → "Layout engine offline"; retry works because the solve persisted. Fix planned as Phase 3 item 3e: Inngest async generation + realtime progress (docs/plans/2026-07-03-fable-stage1-phase0-plan.md §4).
- **Firm-tier users are denied DXF/BOQ**: `export.py` gates use `plan not in ("basic","pro")` / `plan != "pro"` — non-transitive, rejects the top tier. Frontend `layout-viewer.tsx` has matching `planTier === "pro"`-only checks. The new render endpoints use the correct `("pro","firm")` tuple.
- No unique index on layout_renders (layout_id, layout_hash, provider, model) — concurrent cache-miss POSTs can insert duplicate rows (harmless, dead rows).

## Deployment notes (when this merges)
- Production env for renders: RENDER_PROVIDER=openrouter, RENDER_MODEL=openai/gpt-image-1, OPENROUTER_API_KEY (BYOK covers OpenAI billing). All render vars optional: RENDER_PROVIDER, RENDER_MODEL, GEMINI_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY (all default empty; render layer inert without them).
- CI gains no new jobs — the CCQS gate runs inside the existing pytest step.
---

# Stage 1 Phase 3: Canvas Editing + Async Generation (Inngest)

**Branch:** `worktree-stage1-phase3` (worktree off `v2`; PR into `v2`)
**Plan:** `docs/superpowers/plans/2026-07-05-stage1-phase3-canvas-async.md`
**State:** ALL 12 TASKS COMPLETE (Tasks 13/14 inherited from the Lane A CAD-quality-overhaul merge, `b753196` — opening sizes + DXF block inserts already exist on `v2`). Ready for `finish-feature` handoff.

## Commits on this branch (phase 3)

| Commit | What |
|---|---|
| `0ed8d6b` | Task 1 — ranked tier gate (`free<basic<pro<firm`); fixed the firm-tier lockout on edit/DXF/BOQ |
| `4c0b319` | Task 2 — `GET /projects/{id}/layouts` read-only endpoint; page loads never solve |
| `7e671e8` | Task 3 — `generation_jobs` table + jobs service + status endpoint |
| `153f734` | Task 4 — Inngest `layout_generate` function + `POST /generate-jobs` (inline fallback without keys) |
| `2f20047` | Task 5 — `GenerationPanel`: job-status polling, replaces the placeholder empty state |
| `bcfe251` | Task 6 — async render jobs (`render_generate` fn, `RenderTab` polling) |
| `6e5459b` | Task 7 — `canvas-snap.ts` (grid + neighbor-edge snapping, pure module) |
| `8134166` | Task 8 — room selection + snap-aware move-drag in edit mode |
| `54da6e6` | Task 9 — corner resize handles (min-size, edge snapping) |
| `423f3cd` | Task 10 — client-side undo/redo, Ctrl/Cmd+Z shortcuts |
| `bb24459` | Task 11 — agent undo stacks persisted (`undo_stacks` table); chat tab behind `NEXT_PUBLIC_AGENT_CHAT=1` |
| `ca247c3` | Task 12 — live plot/setback preview on the new-project form |

Tasks 13–14 (opening sizes in `compliance_rules.json`, DXF door/window/vent block inserts) shipped on Lane A (`feature/cad-quality-v3`, commits `cd9e875`/`e9fc628`) and are already present on this branch via the `v2` rebase — no additional work needed here.

## Test state
- Backend: 363/363 passing, ruff clean.
- Frontend: 86/86 bun tests passing, biome clean, `next build` green (22 routes).
- `db-migration-safe` gate: run before both schema tasks (3, 11); both clean (Task 11's one flagged "risk" was a false positive against the terse args description — the FK was already present in the actual model).

## Deployment (BEFORE merge to main)
1. Create the Inngest app (inngest.com, free tier) → copy EVENT KEY + SIGNING KEY.
2. GitHub Actions secrets: `INNGEST_EVENT_KEY`, `INNGEST_SIGNING_KEY` → wired into Cloud Run env by `deploy-backend.yml`. WITHOUT them the backend falls back to inline synchronous generation (works, but first generate can still hit the 15s proxy ceiling on cold start).
3. After the first deploy, sync the app in the Inngest dashboard against `https://<cloud-run-url>/api/inngest`.
4. Cloud Run request timeout must stay ≥ 300s (already the deployed value — confirm it wasn't lowered).
5. Vercel: leave `NEXT_PUBLIC_AGENT_CHAT` unset (chat hidden) until Anthropic billing is topped up.

## Known deferred items
- Inngest Realtime replaced by 2s job polling for day one (no realtime dep in frontend, Python SDK's realtime story immature) — revisit post-launch.
- Plot preview (Task 12) only covers `rectangular`/`l_shaped` plot shapes; trapezoid/quadrilateral use separate field sets not modeled by the preview.

---

# Section A-A + Front Elevation (feat/section-elevation-views, 2026-07-12)

Executed per `docs/superpowers/plans/2026-07-11-section-elevation-views.md` (subagent-driven, per-task model tiers; Tasks 3/5/7 finished inline after opus/sonnet session limits).

| Commit | Task |
|---|---|
| `5aea562` | Task 0 — plan doc committed on new branch |
| `8db3e12` | Task 1 — `vertical_standards.py` (single vertical-dims source, foundation 0.6→0.9m) |
| `5efe0db` | Task 2 — cut-line/cut-interval geometry (`section_geometry.py` pt 1) |
| `c6c08f9` | Task 3 — `derive_section()` (11 IS 962 construction rules) |
| `5b2d532` | Task 4 — `derive_elevation()` (facade from `road_side`) |
| `f2243f4` | Task 5 — `section_render.py` (clip-path hatching, levels, vdims, A-A marker) |
| `1f39db4` | review fixes — bounds union + all-road-sides test |
| `33126ea` | Task 6 — standard PDF 4→6 pages + plan cut markers |
| `cbec6a7` | Task 7 — approval PDF 4→5 pages, old schematic section deleted |

## Test state
- Backend: full suite green (see Task 8 run), ruff clean; CCQS gates unchanged (page-0 scoring untouched by new pages).
- Preview PNGs approved-in-flight (sent 2026-07-12); wired-page renders verified at Task 8.

## Review debt (clear before merge)
- Task 5 renderer + Tasks 6/7 wiring reviews died on the session limit (resets 3:30pm IST) — covered by the final whole-branch review before PR.
- Adjudications: stair label keeps true riser count (`n_r`); `ewt_m` stays literal (function deleted in Task 7).

---

# Solver-Navigability Series & Follow-ups (2026-07-20)

**Status:** Tasks 1–4 merged to main (PRs #40–#43); docs wrap-up + verification complete.

| PR | Task | Merged |
|---|---|---|
| #40 | Solver: en-suite toilets (attached_toilets, hard wall-adjacency ≥900mm), per-floor common-toilet guarantee, wet-size objective fix, placement penalties | ✓ main |
| #41 | Config plumbing end-to-end (attached_toilets field: DB/schemas/mapper/forms/i18n) + sizing recalibration (toilet max 4.5, WC max 2.0, master bath 3.2–4.5) | ✓ main |
| #42 | Scorer toilet_placement component (10%; grid_regularity 15%→10%, aspect_ratio 15%→10%) + compliance placement warnings | ✓ main |
| #43 | Door-graph navigability (BFS reachability, wet-room one-door, staircase doored per floor, repair pass + generator gate) | ✓ main |

**Follow-up from current session:**
- Gallery PLANS fetch hotfix merged to main (`/api/gallery/plans` fetch timeout fixed).

**Known open items (do not block):**
- De-flake work running as Task 5a (test determinism on solver + RNG seeding).
- Golden CCQS fixture (`ccqs_fixture.json`, tests in `test_plan_openings.py`) is non-navigable and should eventually be regenerated via Task 5 hunt.
- 3BHK/3T+attached yields only 1 layout — UX watch (acceptable for MVP; soft constraint tuning deferred).

**Test count:** Backend now ~593 passing (was 413 at session start).
