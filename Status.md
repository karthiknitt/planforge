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
- **Firm-tier users are denied DXF/BOQ**: `export.py` gates use `plan not in ("basic","pro")` / `plan != "pro"` — non-transitive, rejects the top tier. Frontend `layout-viewer.tsx` has matching `planTier === "pro"`-only checks. The new render endpoints use the correct `("pro","firm")` tuple.
- No unique index on layout_renders (layout_id, layout_hash, provider, model) — concurrent cache-miss POSTs can insert duplicate rows (harmless, dead rows).

## Deployment notes (when this merges)
- Production env for renders: RENDER_PROVIDER=openrouter, RENDER_MODEL=openai/gpt-image-1, OPENROUTER_API_KEY (BYOK covers OpenAI billing). All render vars optional: RENDER_PROVIDER, RENDER_MODEL, GEMINI_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY (all default empty; render layer inert without them).
- CI gains no new jobs — the CCQS gate runs inside the existing pytest step.
