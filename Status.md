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
