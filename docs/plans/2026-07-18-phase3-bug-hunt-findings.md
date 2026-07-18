# Phase 3 Bug Hunt — Combined Findings (2026-07-18)

Branch: `fix/targeted-bug-hunt`. Three parallel review lenses (frontend stale-state,
API contracts/error paths, auth/tier gates) plus main-session engine debugging.
Status legend: **FIXED** = landed on this branch with a regression test where
practical; **OPEN** = triaged follow-up with an assigned executor model tier.

Model-tier key (per complexity / capability needed to deliver the fix safely):
- **Fable** — cross-cutting architecture, migration-sensitive contracts, CP-SAT reasoning
- **Opus** — multi-file logic with tricky invariants, adversarial edge cases
- **Sonnet** — well-scoped single-surface implementation work
- **Haiku** — mechanical one-file changes with an obvious test

---

## Fixed on this branch

| # | Bug | Where fixed |
|---|---|---|
| 1 | `fetchLayouts` negative-cached backend failures via `unstable_cache` (5-min false "Layout engine offline"); stale local-dev banner copy | `frontend .../fetch-layouts.ts` + tests, banner + Retry in `layout-viewer.tsx` (`2b1cf1c`) |
| 2 | CI red on PR #29 merge: fill safety net rejected usable L-gap with 1.197/1.199 m legs (producer criterion stricter than the usability checker) | `generator.py` relaxed-carve fallback + exact-CI-polygon regression test (`2e87a7d`) |
| 3 | Twin adjacent columns at wall junctions (prod, Karthik's project): archetype cross-product columns, stale pre-fill columns, fill reintroducing face-offset walls, wall-clock-dependent solver incumbents | `generator.py` post-fill snap + column recompute choke point, `derive_columns` 0.3 m junction merge, staircase-pinned snap, `max_deterministic_time` (`01a84dd`) |
| 4 | AI-chat edits never invalidated structural status/artifacts — stale "DESIGNED" badge, hidden PRELIMINARY notice, stale conditioning PNGs (lens-frontend #1/#3/#5, lens-api #1) | `invalidateAfterGeometryEdit()` in `layout-viewer.tsx`, wired to chat + manual edit paths |
| 5 | Design re-run kept serving the previous design's `final_geometry` to the render source (lens-frontend #2) | `handleDesignComplete()` in `layout-viewer.tsx` |
| 6 | BOQViewer showed the previously selected layout's BOQ after switching layouts (lens-frontend #4) | reset effect in `boq-viewer.tsx` |
| 7 | Backend proxy had no `maxDuration` — Vercel killed long structural POSTs (~120 s structapi + cold start) with a platform 504 (lens-api #2) | `maxDuration = 300` in `app/api/backend/[...path]/route.ts` |
| 8 | `structural_loop` silently dropped resolvable-hint violations lacking `span_m` from both the re-solve and the changelog (lens-api #3) | changelog now logs every unactioned violation + pytest regression |
| 9 | `POST /api/teams` had no plan-tier check — free users could create Firm-plan teams via direct API (lens-auth #2) | server-side `firm` gate + 2 pytest regressions |
| 10 | `/api/projects/[id]/revalidate` let any authed user bust any project's cache tag (lens-auth #4) | owner-or-team-member check in the route |

Verified NOT a bug: gallery signed-out-header for authed users (lens-auth #1) — the
`(marketing)` layout calls `headers()`, forcing dynamic rendering; session is evaluated
per-request. If ever seen in prod, suspect cookie/`BETTER_AUTH_URL` domain mismatch.
Also cleared: share-token surface, DXF/BOQ-Excel/render tier gates (backend-enforced),
free 3-project limit, `(app)` session handling, generation polling cap (MAX_POLLS=150).

---

## Open follow-ups (assigned by model tier)

### Fable
- **Team invites are never claimable** (lens-auth #3). `invite_member` stores
  `user_id=""` + `invited_email`; no claim path ever sets `user_id`, so invited
  members never gain access — the Firm feature's core loop is broken. Fix needs a
  cross-boundary design: backend only knows `user_id` (internal JWT), the email
  lives in the Better Auth session, so claiming must be driven from the frontend
  (e.g. claim-on-login or claim-on-team-page-load posting the session email), plus
  the latent `user_id==""` matching footgun should be hardened. Auth-boundary +
  schema + migration-sensitive.
- **Approval hash covers derived fields** (lens-api #5). `structural_store` hashes
  the whole geometry dict incl. compliance/score/space_notes — scorer float drift or
  an engine change silently un-approves plans (409 `not_approved` on untouched
  geometry). Fix = hash only room geometry, BUT changing hashing invalidates every
  existing approval — needs a migration/back-compat strategy (dual-hash grace or
  re-hash on read).

### Opus
- **Stale-marking is permanent even when geometry returns to an approved hash**
  (lens-api #4). Undoing an edit back to the approved geometry leaves the valid
  design hidden (`latest_design` filters `stale`); user must re-run. Fix = un-stale
  (or resurrect) designs whose revision hash matches current geometry again —
  touchy lifecycle invariants around supersede/audit rows.
- **Render-job poll race on layout switch** (lens-frontend #6). An in-flight poll
  can resolve after `layoutKey` changes and mark the wrong layout "ready". Needs
  an abort-controller/keyed-poll refactor of the job polling effect chain.

### Sonnet
- **GET /structural/design contract** (lens-api #6): 404 used for both
  `not_approved` and `not_designed`, and the same condition is 409 on POST; frontend
  maps every 404 to "no design yet". Align codes (409 for not_approved on both
  verbs) and branch the frontend on `detail.code` — coordinated two-side change,
  well-scoped.
- **Restored-revision preview shows live structural status** (lens-frontend #7):
  suppress/annotate the lifecycle badge while `restoredData` is active.
- **Edit page owner-only inconsistency** (lens-auth #5): widen
  `projects/[id]/edit/page.tsx` to the owner-or-team-member rule used everywhere
  else (mirror `page.tsx`'s membership check).

### Haiku
- **Design run double-submit guard** (lens-api #7): add an in-flight guard so the
  agent tool and the Structural tab can't run two concurrent designs for one
  revision (e.g. reject when a non-superseded design run for the revision is in
  progress, or upsert).
- **Approve idempotency signal ignored** (lens-api #8): read `created:false` in
  `handleApproveStructural`/`handleApproveThenRetry` and skip the redundant status
  refetch / show "already approved".
