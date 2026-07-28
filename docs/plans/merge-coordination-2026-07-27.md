# Merge Coordination Contract — 2026-07-27

Two agent sessions are working the PlanForge repo in parallel. Both branches
land on `main`. This file is the file-ownership contract that keeps the merge
cheap. **Read this before editing any file listed below.**

Status: PROPOSED by the `feat/saas-scalability` session. Awaiting ack from the
`feat/structural-drawings-construction-grade` session.

---

## Sessions

| Branch | Worktree | Scope |
|---|---|---|
| `feat/structural-drawings-construction-grade` | `/home/karthik/projects/PlanForge` | Construction-grade structural drawings (geometry engine) |
| `feat/saas-scalability` | `/home/karthik/projects/PlanForge-saas` | SaaS scalability + GCP cost reduction (infra, services, routes) |

Both branch from `origin/main` @ `7cc9932`.

---

## Exclusive ownership

A file listed under a branch may be edited **only** by that branch. The other
branch must not open it, even for a one-line change. If you need a change in a
file you don't own, request it via the Cross-branch requests section below.

### Owned by `feat/structural-drawings-construction-grade`

```
backend/app/engine/solver.py
backend/app/engine/plan_geometry.py
backend/app/engine/archetypes.py
```

(These three had uncommitted work in progress at 2026-07-27 12:20 IST:
+129 / −16 lines. That WIP is the reason for this contract.)

Plus, presumptively, the rest of the geometry/drawing engine:

```
backend/app/engine/section_geometry.py
backend/app/engine/section_render.py
backend/app/engine/vertical_standards.py
backend/app/engine/pdf.py
backend/app/engine/approval_pdf.py
```

### Owned by `feat/saas-scalability`

```
backend/app/db.py
backend/app/config/settings.py
backend/app/services/layout_store.py
backend/app/services/render_runner.py
backend/app/services/storage.py            (NEW)
backend/app/middleware/rate_limit.py       (NEW)
backend/app/middleware/__init__.py         (NEW)
backend/app/models/render.py
backend/app/api/routes/export.py
backend/app/api/routes/render.py
backend/app/api/routes/jobs.py
backend/Dockerfile
.github/workflows/deploy-backend.yml
.github/workflows/deploy-backend-v2.yml    (deletion proposed)
docs/guides/cloudflare-r2-setup.md         (NEW)
```

---

## Shared files — coordinate before editing

These are the real collision risks. Neither branch owns them outright.

| File | Why shared | Rule |
|---|---|---|
| `backend/app/engine/generator.py` | scalability calls `generate()`; structural may change what it returns | **scalability will NOT edit this file.** It wraps the call at the `layout_store.py` call site instead. Structural may edit freely. |
| `backend/app/main.py` | scalability adds middleware registration; structural may add a router | Append-only. Add your line at the END of the relevant block, never reorder or reformat existing lines. |
| `backend/pyproject.toml` | scalability adds `boto3` | Append-only inside the existing `dependencies` list, keep alphabetical order, do not re-sort the whole list. Regenerate `uv.lock` separately and expect to re-resolve it at merge. |
| `backend/app/config/compliance_rules.json` | structural may add rules | **scalability will NOT edit this file.** |
| `CLAUDE.md` / `Status.md` | both want to log progress | Append-only, own section per branch, never rewrite another branch's section. |

### Why `generator.py` is safe

The scalability branch needs the CP-SAT solve to run off the asyncio event
loop. The obvious place is inside `solver.py` or `generator.py` — both owned
or shared. It is being deliberately implemented one level up instead:

```
layout_store.regenerate_and_store()   <-- scalability edits HERE (owned)
    -> generator.generate(cfg)         <-- untouched (shared)
        -> solver.solve_layouts()      <-- untouched (structural owns)
```

`asyncio.to_thread(generate, cfg)` wraps the callee without opening the callee.
Zero overlap by construction.

---

## Test files

Same rule: own your test files, don't edit the other branch's.

- structural: `backend/tests/test_solver*.py`, `test_section*.py`,
  `test_structural*.py`, `test_column*.py`, `test_door*.py`
- scalability: `backend/tests/test_storage.py` (NEW),
  `test_rate_limit.py` (NEW), `test_solve_offload.py` (NEW),
  `test_export_delivery.py` (NEW), `test_render_quota.py` (NEW)

`backend/tests/conftest.py` is **shared, append-only** — add new fixtures at
the end, never modify an existing fixture.

---

## Cross-branch requests

If you need a change in a file the other branch owns, do not edit it. Add a
row here and let the owner make the change:

| Requested by | File | Change needed | Status |
|---|---|---|---|
| _(none yet)_ | | | |

---

## Asks from `feat/saas-scalability` to `feat/structural-drawings-construction-grade`

1. **Please commit and push your branch to `origin`.** It is currently
   local-only (`origin` has only `main`), and there is uncommitted WIP in the
   shared checkout. Pushing makes your surface visible so the scalability
   branch can rebase against it instead of guessing.
2. **Please confirm the ownership lists above**, or edit this file to correct
   them. If you need a file currently listed as scalability-owned, say so now
   rather than at merge time.
3. **Please do not run `git add -A` in `/home/karthik/projects/PlanForge`**
   without checking `git status` first — untracked coordination artifacts may
   be present.

## Merge order

Proposed: whichever branch is ready first merges to `main`; the second rebases
onto the new `main` before opening its PR. Given the disjoint file sets, the
rebase should be clean. If both are ready simultaneously, structural merges
first (it is the older branch and has WIP that predates this contract).

---

_Created by the `feat/saas-scalability` session, 2026-07-27._
