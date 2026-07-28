# PlanForge — Handover

Short, current, working-state notes. Long-form status lives in [Status.md](Status.md);
architecture in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Before you touch anything

```bash
git branch --show-current && pwd -P
```

**Three checkouts are active at once.** Editing the wrong one is the most likely mistake:

| Branch | Directory | Purpose |
|---|---|---|
| `chore/public-release-prep` | `~/projects/PlanForge-release` | public release + docs overhaul |
| `feat/structural-drawings-construction-grade` | `~/projects/PlanForge` | active feature work |
| `feat/saas-scalability` | `~/projects/PlanForge-saas` | scalability/storage work, 10 ahead of main |

## In flight

**Public release + documentation overhaul** (plan kept outside the repo).

**Complete as of 2026-07-28.** Both repos are public (#48 here, #3 in structapi) with
rewritten READMEs, an architecture doc, committed SVG diagrams, a docs index, per-directory
conventions, and branch protection on `main`.

Two items were dropped by decision rather than left undone: runnable live-service API
examples (they would invite unmetered traffic on a free-tier service) and a demo video.
There is no self-serve demo login.

## Gotchas that have bitten before

- **`planforge.vercel.app` is not ours.** It returns HTTP 200 but serves an unrelated
  third-party app. Canonical URL: `planforge-mauve.vercel.app`. Verify with
  `vercel project ls`, never with a bare curl status code.
- **Backend health path is `/api/health`.** `/health` returns 404.
- **CI is blocked on PlanForge** (Actions quota, not code). Backend deploys are manual
  via `gcloud run deploy` until the repo goes public.
- **Never run `ruff format` on `*.json`** — it corrupts `compliance_rules.json`.
- **Do not hand-edit `structapi-service/`** — it is a pinned vendored copy, byte-diffed
  against its tag in CI. Re-vendor instead.
- **Cold starts run ~20–25s** at `min-instances=0`; short client timeouts will appear as
  connection errors.

## Companion repo

Engine: [karthiknitt/structapi](https://github.com/karthiknitt/structapi), branch
`chore/public-release-prep` for the matching release work.
