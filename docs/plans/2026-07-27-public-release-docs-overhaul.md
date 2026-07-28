# PlanForge + structapi — Public Release & Documentation Overhaul

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `karthiknitt/planforge` and `karthiknitt/structapi` public with documentation rewritten so a Razorpay AI Builder reviewer understands, in under three minutes, that they are one system — a floor-plan SaaS front door over a multi-agent IS-code structural engine.

**Architecture:** Two repos, one narrative. `structapi` holds the deterministic `iscodes` engine plus an Eve multi-agent NL layer; `planforge` is the customer-facing SaaS that calls it service-to-service over a frozen v1 envelope. Docs are restructured so each repo's README opens with the *joint* system and links to a single canonical architecture document, rather than each describing itself in isolation.

**Tech Stack:** Next.js 16 / React 19 / Bun / Better Auth / Drizzle / ShadCN / Tailwind v4 (frontend) · FastAPI / SQLAlchemy async / uv / Shapely / OR-Tools CP-SAT / ReportLab / ezdxf (backend) · Eve + OpenRouter (agent layer) · Vercel + Google Cloud Run + Neon Postgres

## Global Constraints

- **Audience is a hiring reviewer, not a user.** Every doc change is judged by: does this help someone decide in 3 minutes that Karthik can build AI systems?
- **Canonical production URL is `https://planforge-mauve.vercel.app`.** Never `planforge.vercel.app` — that domain belongs to an unrelated third party ("Lovable App"). Verified 2026-07-27 via `vercel project ls`.
- **Canonical structapi URL is `https://structapi-912195238699.us-central1.run.app`.** Health: `/v1/health` → `{"status":"ok","api_version":"1","iscodes_version":"0.3.0"}`.
- **Canonical backend URL is `https://planforge-backend-912195238699.us-central1.run.app`.** Health path is `/api/health` (NOT `/health` — that 404s). OpenAPI at `/docs`.
- **GCP project is `thermal-well-451906-b0`, region `us-central1`.** Any doc saying `planforge-prod` is stale.
- **No real secrets in any committed file, including markdown.** Placeholders only: `STRUCTURAL_API_KEY=<your-key-here>`.
- **Backend test count is 650** (`uv run pytest --collect-only -q`, verified 2026-07-27). Any doc saying 593 is stale.
- **Publishing is irreversible.** Once public, forks and caches persist. Task 3.1 is a hard gate requiring explicit human approval before any visibility flip.

---

## Verified Starting State (2026-07-27)

| Fact | Value |
|---|---|
| planforge visibility | PRIVATE |
| structapi visibility | PRIVATE |
| planforge LICENSE | ✅ present (MIT) |
| structapi LICENSE | ❌ **missing — blocks public release** |
| Secrets in git history | ✅ clean, both repos (only `planforge:planforge@localhost` dev creds + `sk-ant-...` placeholder) |
| planforge backend tests | 650 collected, 87 test files |
| planforge frontend tests | ~0 dedicated test files |
| structapi tests | 9 test files; count unverifiable locally (missing deps outside CI) |
| structapi CI | ✅ green, tags v0.1.0 / v0.2.0 / v0.3.0, GHCR image published |
| planforge CI | ❌ 20 failed runs — GitHub Actions **billing block**, not code failure |
| GitHub plan | free (2,000 private Actions min/month) |
| planforge branch state | on `feat/structural-drawings-construction-grade`, uncommitted changes, only `main` on origin |
| Live frontend | ✅ `planforge-mauve.vercel.app`, prod deploy 2d old |
| Live backend | ✅ revision `planforge-backend-00034-28r`, manual deploy 2026-07-25 16:36 UTC |
| Live structapi | ✅ healthy, iscodes 0.3.0 |
| Root clutter (planforge) | 3 screenshots, 2 PDFs, 4 PRD/prompt files at repo root |
| Known stale docs | root `CLAUDE.md` says "Lean MVP, rectangular-only, no Vastu"; README says 593 tests; plan doc says GCP project `planforge-prod` |

---

# PHASE 0 — Pre-Flight Safety

**Exit criteria:** Both repos provably safe to publish. No visibility change yet.

## Sprint 0.1 — Secrets & Licensing

### Task 0.1.1: Re-verify secret cleanliness with a purpose-built scanner

**Files:**
- Read-only. No files modified.

**Interfaces:**
- Produces: a go/no-go signal consumed by Task 3.1 (the publish gate).

- [ ] **Step 1: Install gitleaks**

```bash
uv tool install gitleaks || (cd /tmp && curl -sSL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_linux_x64.tar.gz | tar xz && mv gitleaks ~/.local/bin/)
gitleaks version
```

- [ ] **Step 2: Scan full history of both repos**

```bash
cd /home/karthik/projects/PlanForge && gitleaks detect --source . --log-opts="--all" --redact --report-path /tmp/leaks-planforge.json
cd /home/karthik/projects/structapi && gitleaks detect --source . --log-opts="--all" --redact --report-path /tmp/leaks-structapi.json
```

Expected: exit 0 on both. The earlier manual regex sweep over 200 commits found only `postgresql://planforge:planforge@localhost:5432/planforge` (local dev credentials, harmless) and `ANTHROPIC_API_KEY=sk-ant-...` (a placeholder, not a key).

- [ ] **Step 3: If gitleaks reports findings, triage before proceeding**

For each finding, classify as: (a) localhost/dev credential → ignore, (b) placeholder → ignore, (c) real credential → **STOP**, rotate the credential first, then decide between `git filter-repo` history rewrite or abandoning the public release for that repo. Do not proceed to Phase 3 with any (c) unresolved.

- [ ] **Step 4: Record the result in the plan**

```bash
echo "gitleaks scan $(date -I): planforge=$(jq length /tmp/leaks-planforge.json) structapi=$(jq length /tmp/leaks-structapi.json)" >> /home/karthik/projects/PlanForge/Status.md
```

- [ ] **Step 5: Commit**

```bash
cd /home/karthik/projects/PlanForge && git add Status.md && git commit -m "chore: record pre-publish gitleaks scan result"
```

---

### Task 0.1.2: Add MIT LICENSE to structapi

**Files:**
- Create: `/home/karthik/projects/structapi/LICENSE`

**Interfaces:**
- Produces: a license file that GitHub's repo sidebar detects, required before Task 3.1.

structapi has **no LICENSE**. Publishing code without one means nobody may legally reuse it, and GitHub shows "No license" in the sidebar — a visible gap on a portfolio repo. PlanForge already has MIT; match it.

- [ ] **Step 1: Write the LICENSE file**

```bash
cat > /home/karthik/projects/structapi/LICENSE <<'EOF'
MIT License

Copyright (c) 2026 Karthikeyan Natarajan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
```

- [ ] **Step 2: Verify it is detected as MIT**

```bash
head -1 /home/karthik/projects/structapi/LICENSE
```
Expected: `MIT License`

- [ ] **Step 3: Add a disclaimer note to the README**

structapi outputs structural engineering designs. A public repo needs an explicit "not a substitute for a licensed engineer" line, both ethically and to limit liability. Append to `/home/karthik/projects/structapi/README.md`:

```markdown
## Disclaimer

structapi and StructAgent produce IS-code-referenced structural calculations for
**preliminary design and estimation only**. Output is not a substitute for review,
stamping, and sign-off by a licensed structural engineer. Do not use it as the sole
basis for construction. Licensed MIT — see [LICENSE](LICENSE).
```

- [ ] **Step 4: Commit**

```bash
cd /home/karthik/projects/structapi
git add LICENSE README.md
git commit -m "chore: add MIT LICENSE and engineering disclaimer ahead of public release"
```

---

## Sprint 0.2 — Unblock CI

### Task 0.2.1: Resolve the GitHub Actions billing block

**Files:**
- Modify: `/home/karthik/projects/PlanForge/.github/workflows/verify-structapi-vendor.yml`

**Interfaces:**
- Produces: green CI on both repos, consumed by Task 3.3 (post-publish verification).

The 20 failed PlanForge runs are all `The job was not started because recent account payments have failed or your spending limit needs to be increased` — a billing block on a free plan, not a code failure. Public repos get unlimited free Actions on standard runners, so publishing may fix this on its own; but Actions **storage** is billable even for public repos, so a $0 budget can still block.

- [ ] **Step 1: Diagnose which cause applies**

Open GitHub → Settings → Billing & Licensing → Budgets. Record which is true:
- Budget pinned at $0, or failed payment method → **account-level lock**; publishing will NOT fix it. Raise the budget above $0 or fix the payment method.
- Budget fine, 2,000 private minutes exhausted → **quota exhaustion**; publishing fixes it permanently, and it also self-heals at the next billing cycle.

- [ ] **Step 2: Cut the recurring minute drain**

`verify-structapi-vendor.yml` runs on a schedule and failed again on 2026-07-27. Cron workflows bill every run regardless of whether anything changed. Convert it to a path-scoped PR trigger.

Replace the `on:` block in `.github/workflows/verify-structapi-vendor.yml` with:

```yaml
on:
  pull_request:
    paths:
      - 'structapi-service/**'
      - '.github/workflows/verify-structapi-vendor.yml'
  workflow_dispatch:
```

- [ ] **Step 3: Delete the 20 stale failed runs**

These are billing artifacts, not real failures, and they will be publicly visible once the repo is public.

```bash
gh run list -R karthiknitt/planforge --status failure --limit 100 --json databaseId \
  --jq '.[].databaseId' | xargs -I{} gh run delete -R karthiknitt/planforge {}
```

- [ ] **Step 4: Verify the Actions tab is clean**

```bash
gh run list -R karthiknitt/planforge --status failure --limit 10
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
cd /home/karthik/projects/PlanForge
git add .github/workflows/verify-structapi-vendor.yml
git commit -m "ci: convert vendor-sync from schedule to path-scoped PR trigger"
```

---

### Task 0.2.2: Land the working branch

**Files:**
- Modify: `backend/app/engine/archetypes.py`, `backend/app/engine/plan_geometry.py`, `backend/app/engine/solver.py` (currently uncommitted)

`origin` has only `main`, and your best recent work sits uncommitted on `feat/structural-drawings-construction-grade`. A public repo whose visible `main` lags the real state undersells you.

- [ ] **Step 1: Review what is uncommitted**

```bash
cd /home/karthik/projects/PlanForge && git status && git diff --stat
```

- [ ] **Step 2: Run the backend suite before committing**

```bash
cd /home/karthik/projects/PlanForge/backend && uv run pytest -q
```
Expected: 650 tests, all passing. If any fail, fix before proceeding — a public repo with a red `main` defeats the purpose.

- [ ] **Step 3: Run lint and format**

```bash
cd /home/karthik/projects/PlanForge/backend && uv run ruff format . && uv run ruff check .
```
Expected: both clean. Never run `ruff format` on `*.json` — it corrupts them.

- [ ] **Step 4: Commit and push the branch**

```bash
cd /home/karthik/projects/PlanForge
git add backend/app/engine/archetypes.py backend/app/engine/plan_geometry.py backend/app/engine/solver.py
git commit -m "fix: solver door placement and archetype geometry refinements"
git push -u origin feat/structural-drawings-construction-grade
```

- [ ] **Step 5: Open and merge the PR**

```bash
gh pr create -R karthiknitt/planforge --fill
```
Merge once CI is green (requires Task 0.2.1 complete).

---

# PHASE 1 — Documentation Overhaul

**Exit criteria:** Both repos' docs tell one coherent story, are internally consistent, and contain no stale claims. Still private.

## Sprint 1.1 — Canonical Architecture Document

### Task 1.1.1: Promote PLANFORGE-INTEGRATION.md to the canonical architecture doc

**Files:**
- Modify: `/home/karthik/projects/structapi/docs/PLANFORGE-INTEGRATION.md`
- Create: `/home/karthik/projects/PlanForge/docs/ARCHITECTURE.md` (a pointer, not a copy)

**Interfaces:**
- Produces: one canonical URL, `https://github.com/karthiknitt/structapi/blob/main/docs/PLANFORGE-INTEGRATION.md`, referenced by both READMEs in Tasks 1.2.1 and 1.2.2.

This document is the single strongest artifact in either repo. It already contains the "two front doors, one calculation core" decision and the reasoning for using a deterministic service rather than the agent API. It needs a status refresh (it says "approved architecture, phased plan" — the integration is now live in production) and a results section.

- [ ] **Step 1: Update the status line**

Replace line 3 of `docs/PLANFORGE-INTEGRATION.md`:

```markdown
Status: **live in production** · Owner: StructAgent repo · Designed 2026-07-12 · Shipped 2026-07-12 · Last verified 2026-07-27
```

- [ ] **Step 2: Add a "Shipped state" section immediately after section 2 (Architecture decision)**

```markdown
## 2a. Shipped state (verified 2026-07-27)

The architecture below is deployed, not aspirational. Both services are live:

| Component | URL | Verify |
|---|---|---|
| structapi | `https://structapi-912195238699.us-central1.run.app` | `curl .../v1/health` → `{"status":"ok","api_version":"1","iscodes_version":"0.3.0"}` |
| PlanForge backend | `https://planforge-backend-912195238699.us-central1.run.app` | `curl .../api/health` → `{"status":"ok","service":"planforge-api"}` |
| PlanForge frontend | `https://planforge-mauve.vercel.app` | browser |

The PlanForge backend exposes five routes implementing the full loop:

```
POST   /api/projects/{id}/structural/design            request a design
GET    /api/projects/{id}/structural/status            poll progress
POST   /api/projects/{id}/structural/approve           approve a revision
GET    /api/projects/{id}/structural                   fetch current design
GET    /api/projects/{id}/export/structural-drawing-set  export drawings
```

Client implementation: `backend/app/services/structagent_client.py` (PlanForge repo).
Orchestration: `backend/app/services/structural_loop.py`.
Contract freeze: `python/tests/fixtures/beam_envelope_v1.json` (structapi repo) — CI fails on any v1 envelope drift.
```

- [ ] **Step 3: Create the PlanForge-side pointer**

Do not duplicate the content — one canonical copy, one pointer. Create `/home/karthik/projects/PlanForge/docs/ARCHITECTURE.md`:

```markdown
# Architecture

PlanForge is the customer-facing half of a two-repo system. The canonical
architecture document — including the "two front doors, one calculation core"
decision, the frozen v1 envelope contract, and the rationale for calling a
deterministic service rather than an LLM agent — lives in the engine repo:

**→ [StructAgent × PlanForge — Integration Architecture](https://github.com/karthiknitt/structapi/blob/main/docs/PLANFORGE-INTEGRATION.md)**

## PlanForge-side implementation

| Concern | File |
|---|---|
| HTTP client for structapi | `backend/app/services/structagent_client.py` |
| Design request orchestration | `backend/app/services/structural_loop.py` |
| Revision persistence | `backend/app/services/structural_store.py` |
| API routes | `backend/app/api/routes/structural.py` |
| Plinth beam design | `backend/app/services/plinth_beam_design.py` |
| Drawing set export | `backend/app/engine/structural_drawing_set.py` |
| Tests | `backend/tests/test_structagent_client.py`, `test_structural_loop.py`, `test_structural_endpoint.py`, `test_structural_revisions.py`, `test_structural_drawing_set.py`, `test_export_structural_drawing_set.py`, `test_boq_structural_design.py`, `test_plinth_beam_design.py` |

For local development conventions see [developer-reference.md](developer-reference.md).
```

- [ ] **Step 4: Verify both links resolve**

```bash
grep -n "PLANFORGE-INTEGRATION" /home/karthik/projects/PlanForge/docs/ARCHITECTURE.md
ls /home/karthik/projects/structapi/docs/PLANFORGE-INTEGRATION.md
```

- [ ] **Step 5: Commit both repos**

```bash
cd /home/karthik/projects/structapi && git add docs/PLANFORGE-INTEGRATION.md && git commit -m "docs: mark integration architecture as shipped, add verified live state"
cd /home/karthik/projects/PlanForge && git add docs/ARCHITECTURE.md && git commit -m "docs: add architecture pointer to canonical integration doc"
```

---

## Sprint 1.2 — README Rewrites

### Task 1.2.1: Rewrite the top of PlanForge's README for a reviewer

**Files:**
- Modify: `/home/karthik/projects/PlanForge/README.md:1-20`

**Interfaces:**
- Consumes: the canonical architecture URL from Task 1.1.1.

The current README opens with a floor-plan SaaS pitch and never mentions the structural engine. A reviewer reads the first screen and leaves. Insert the joint-system framing above the existing badges.

- [ ] **Step 1: Replace lines 1-8 of README.md**

```markdown
# PlanForge

> G+1 residential floor plan generator for Indian small builders and civil engineers —
> and the front door to a multi-agent IS-code structural design engine.

**[▶ Live demo](https://planforge-mauve.vercel.app)** · **[Architecture](docs/ARCHITECTURE.md)** · **[Engine repo](https://github.com/karthiknitt/structapi)**

```
 plot dims + preferences
          │
          ▼
 ┌──────────────────────┐   OR-Tools CP-SAT + Shapely
 │  PlanForge (this repo)│   3 scored, compliance-checked layouts
 └──────────┬───────────┘
            │  POST /v1/design/building   (frozen v1 envelope, x-api-key)
            ▼
 ┌──────────────────────┐   IS 456/875/1893/13920/3370/10262
 │  structapi            │   deterministic — no LLM in the calculation path
 └──────────┬───────────┘
            ▼
 member design · reinforcement · BOQ quantities · structural PDF sheets
```

PlanForge takes plot dimensions, setbacks, and room preferences and generates three
compliant layout variations — SVG preview, section view, Bill of Quantities, PDF drawing,
DXF export — then hands the resulting column grid to [structapi](https://github.com/karthiknitt/structapi)
for IS-code structural design without the user leaving the app.

**Why the engine is deterministic and not an agent:** structural design from a known floor
plan is fully parameterised, so the same plan must always produce the same design — a hard
requirement for revision history, approvals, and BOQ reproducibility. The LLM layer sits
*above* it: PlanForge's Claude chat calls structapi as a tool, and StructAgent offers a
natural-language front door for humans. Full reasoning in
[the architecture doc](docs/ARCHITECTURE.md).

Verify both services are live right now:

```bash
curl -s https://structapi-912195238699.us-central1.run.app/v1/health
curl -s https://planforge-backend-912195238699.us-central1.run.app/api/health
```
```

- [ ] **Step 2: Fix the stale test count**

Search the README for `593` and replace with `650`. Verified via `uv run pytest --collect-only -q` on 2026-07-27.

```bash
cd /home/karthik/projects/PlanForge && grep -n "593" README.md docs/*.md
```

- [ ] **Step 3: Add a "Known gaps" section before the license footer**

Naming your own gaps reads as engineering maturity; letting a reviewer discover them reads as carelessness.

```markdown
## Known gaps

- **Frontend has no dedicated test files.** Backend is well covered (650 tests across 87
  files); the Next.js frontend is verified via build + type-check + preview deploys only.
  Tracked in [docs/product-roadmap.md](docs/product-roadmap.md).
- **No Alembic migrations.** Backend schema is created and patched at startup via
  `Base.metadata.create_all` + `auto_migrate_missing_columns`. Fine at current scale,
  would need replacing before multi-tenant production.
- **Pre-revenue.** Razorpay checkout is integrated and functional but the product has not
  launched commercially.
```

- [ ] **Step 4: Verify the README renders**

```bash
cd /home/karthik/projects/PlanForge && head -50 README.md
```
Check the ASCII diagram alignment survived, and that no line exceeds ~100 chars.

- [ ] **Step 5: Commit**

```bash
git add README.md && git commit -m "docs: rewrite README opening for joint-system framing, fix stale test count"
```

---

### Task 1.2.2: Rewrite the top of structapi's README

**Files:**
- Modify: `/home/karthik/projects/structapi/README.md:1-12`

The current README already describes the two products well but buries the PlanForge relationship in a parenthetical. Surface it, and lead with the agent architecture — that is what an AI Builder reviewer is screening for.

- [ ] **Step 1: Replace lines 1-10 with**

```markdown
# StructAgent + structapi — IS-Code Structural Design

> A multi-agent structural engineering system: an LLM orchestrator that routes to 8
> specialist subagents, over a deterministic IS-code calculation engine that the agents
> cannot hallucinate around.

**[Architecture](docs/PLANFORGE-INTEGRATION.md)** · **[Consumer app (live)](https://planforge-mauve.vercel.app)** · **[Consumer repo](https://github.com/karthiknitt/planforge)**

```
 Humans (natural language)                PlanForge backend (service-to-service)
          │                                            │
          ▼                                            │
 ┌─────────────────────────────┐                       │
 │ Eve agent layer              │                      │
 │ orchestrator → 8 subagents   │                      │
 │ loads · beam · column        │                      │
 │ footing · slab · tank        │                      │
 │ sump · mixdesign             │                      │
 └──────────────┬──────────────┘                       │
                │ runs in Docker sandbox               │ x-api-key, frozen v1 envelope
                │ (deny-all egress)                    │
                ▼                                      ▼
        ┌───────────────────┐              ┌──────────────────────┐
        │ python/iscodes    │◀─────────────│ structapi (FastAPI)  │
        │ deterministic     │              │ stateless REST       │
        │ IS-code engine    │              └──────────────────────┘
        └───────────────────┘
```

Two runnable products share one calculation core:

1. **StructAgent** — multi-agent NL design app on [Eve](https://eve.dev) (Vercel's durable
   agent framework), self-hosted per the [vercel-labs/steve](https://github.com/vercel-labs/steve)
   pattern: Postgres durability, Docker sandboxes with deny-all egress, TUI + web UI,
   models via OpenRouter.
2. **structapi** — deterministic FastAPI REST service over the same engine, for backend
   callers. Live on Cloud Run, consumed in production by
   [PlanForge](https://github.com/karthiknitt/planforge). Current release **v0.3.0**.

**The design principle:** agents decide *what* to design and in what order; the
`iscodes` library decides *what the numbers are*. No LLM sits in the calculation path,
so results are reproducible and every check is traceable to an IS clause. The v1
response envelope is frozen by a golden fixture (`python/tests/fixtures/beam_envelope_v1.json`)
and CI fails on any drift.

Try the live engine:

```bash
curl -s https://structapi-912195238699.us-central1.run.app/v1/health
# {"status":"ok","api_version":"1","iscodes_version":"0.3.0"}
```
```

- [ ] **Step 2: Verify the test-count claim before publishing it**

The README claims "94 tests" for `iscodes`. Local collection fails (deps unavailable outside CI), so confirm from CI rather than asserting a stale number:

```bash
cd /home/karthik/projects/structapi
gh run list -R karthiknitt/structapi --workflow=ci.yml --limit 1 --json databaseId --jq '.[0].databaseId' \
  | xargs -I{} gh run view -R karthiknitt/structapi {} --log | grep -iE "passed|collected" | tail -3
```
If the number differs from 94, update the README. If CI logs have expired, re-run CI (`gh workflow run ci.yml`) and read the fresh output.

- [ ] **Step 3: Commit**

```bash
git add README.md && git commit -m "docs: lead README with agent architecture and PlanForge relationship"
```

---

## Sprint 1.3 — Stale Content Cleanup

### Task 1.3.1: Fix the contradictory root CLAUDE.md

**Files:**
- Modify: `/home/karthik/projects/PlanForge/CLAUDE.md`

Root `CLAUDE.md` states "Rectangular plots only — no quadrilateral in MVP", "3 predefined parametric archetypes — no dynamic constraint solver", and "2BHK or 3BHK only". All three are false: the repo ships quadrilateral and L-shaped plots, an OR-Tools CP-SAT solver, 1–6 bedrooms, and a Vastu engine. A reviewer who reads both README and CLAUDE.md sees a contradiction.

- [ ] **Step 1: Replace the "Key Product Decisions (Lean MVP Constraints)" heading**

```markdown
## Key Product Decisions (current — supersedes Lean_MVP_PRD_v1.md)

> **Note:** this project outgrew the Lean MVP scope in early 2026. The constraints below
> reflect what is actually built. `Lean_MVP_PRD_v1.md` is retained as a historical record
> only — do not treat it as current scope.
```

- [ ] **Step 2: Correct the three false constraint blocks**

Replace "Rectangular plots only — no quadrilateral in MVP" with:

```markdown
- **Rectangular, trapezoid, convex quadrilateral (arbitrary 4-corner), and L-shaped plots**
```

Replace "3 predefined parametric archetypes — no dynamic constraint solver" with:

```markdown
- **OR-Tools CP-SAT constraint solver** with forced staircase diversity (front / mid / rear);
  the 3 parametric archetypes remain as a fallback when the solver cannot converge
```

Replace "2BHK or 3BHK only — no arbitrary room count in MVP" with:

```markdown
- **2BHK – 4BHK, 1–6 bedrooms**, optional pooja / study / balcony / servant quarter /
  home office / gym / store
```

- [ ] **Step 3: Fix the stale test count**

Replace `~593 passing` with `650 passing (87 test files)`.

- [ ] **Step 4: Verify no remaining contradictions**

```bash
cd /home/karthik/projects/PlanForge
grep -niE "rectangular plots only|no dynamic constraint solver|2BHK or 3BHK only|593" CLAUDE.md README.md
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md && git commit -m "docs: correct stale Lean MVP constraints in CLAUDE.md"
```

---

### Task 1.3.2: Fix remaining stale references in the deployment plan doc

**Files:**
- Modify: `docs/plans/2026-07-02-cloud-run-deployment-implementation-plan.md:467,470`

The three wrong `planforge.vercel.app` URLs were already corrected on 2026-07-27. Two stale GCP references remain.

- [ ] **Step 1: Correct the GCP project name**

Line 467: replace `planforge-deployer@planforge-prod.iam.gserviceaccount.com` with the real service account for project `thermal-well-451906-b0`. Retrieve it:

```bash
gcloud iam service-accounts list --project thermal-well-451906-b0 --format="value(email)"
```

Line 470: replace `gh variable set GCP_PROJECT_ID --body "planforge-prod"` with `--body "thermal-well-451906-b0"`.

- [ ] **Step 2: Verify no stale project name remains**

```bash
grep -rn "planforge-prod" /home/karthik/projects/PlanForge --include="*.md" --include="*.sh" --include="*.yml"
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add docs/plans/2026-07-02-cloud-run-deployment-implementation-plan.md
git commit -m "docs: correct stale GCP project name in deployment plan"
```

---

### Task 1.3.3: Clear repo-root clutter

**Files:**
- Move: 3 screenshots, 2 PDFs, 4 PRD/prompt files out of repo root

Repo root currently shows `Screenshot_2026-03-06_09-59-40.png`, `Screenshot_2026-03-06_10-09-33.png`, `Screenshot_2026-03-06_16-08-56.png`, `Home Planning Guide India.pdf`, `Planforge_bug_fixes.pdf`, `Prompt_19_2_26.md`, `Prompt_19_2_26 -1.md`, `Issues to fix.md`, `Ambitious_PRD_v1.md`, `Ambitious_PRD_v2.md`, `Lean_MVP_PRD_v1.md`. That is the first thing a reviewer sees on the GitHub file listing.

- [ ] **Step 1: Review the two PDFs for third-party copyright**

`Home Planning Guide India.pdf` may be someone else's published material. Open it and check. If it is not yours, **delete it and remove it from history** — republishing a copyrighted PDF is a real problem, unlike the others which are merely untidy.

```bash
cd /home/karthik/projects/PlanForge && ls -la *.pdf
```

- [ ] **Step 2: Create an archive directory and move historical material**

```bash
cd /home/karthik/projects/PlanForge
mkdir -p docs/archive
git mv "Prompt_19_2_26.md" "Prompt_19_2_26 -1.md" "Issues to fix.md" \
       Ambitious_PRD_v1.md Ambitious_PRD_v2.md Lean_MVP_PRD_v1.md docs/archive/
mkdir -p docs/assets
git mv Screenshot_2026-03-06_09-59-40.png Screenshot_2026-03-06_10-09-33.png \
       Screenshot_2026-03-06_16-08-56.png docs/assets/
git mv Planforge_bug_fixes.pdf docs/archive/
```

- [ ] **Step 3: Add an archive README explaining why these are kept**

```bash
cat > docs/archive/README.md <<'EOF'
# Archive

Historical planning documents kept for provenance. **None of these describe current
scope** — see the root [README.md](../../README.md) and [CLAUDE.md](../../CLAUDE.md)
for what is actually built.

- `Lean_MVP_PRD_v1.md` — original scope, superseded in early 2026 (the project shipped
  the CP-SAT solver, quadrilateral/L-shaped plots, and Vastu, all of which this PRD
  excluded)
- `Ambitious_PRD_v1.md` / `Ambitious_PRD_v2.md` — long-range product vision
- `Prompt_19_2_26.md`, `Prompt_19_2_26 -1.md` — early kickoff prompts
- `Issues to fix.md` — superseded by `docs/product-roadmap.md`
EOF
```

- [ ] **Step 4: Verify root is clean**

```bash
cd /home/karthik/projects/PlanForge && ls -1 *.md *.pdf *.png 2>/dev/null
```
Expected: only `README.md`, `CLAUDE.md`, `AGENTS.md`, `Status.md`, `wireframes.md`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "docs: move historical PRDs, prompts, and assets out of repo root"
```

---

## Sprint 1.4 — Full Docs Restructure

### Task 1.4.1: Add a docs index

**Files:**
- Create: `/home/karthik/projects/PlanForge/docs/README.md`

31 markdown files sit under `docs/` with no index. A reviewer cannot tell `developer-reference.md` from `cad_primitives_plan.md`.

- [ ] **Step 1: Write the index**

```markdown
# PlanForge Documentation

## Start here
| Doc | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | How PlanForge and structapi fit together (canonical doc lives in the engine repo) |
| [developer-reference.md](developer-reference.md) | Env vars, local setup, deployment, seeded test users |
| [product-roadmap.md](product-roadmap.md) | Shipped features (P0–P3) and the remaining backlog |
| [documentation.md](documentation.md) | End-user feature documentation |

## Design & analysis
| Doc | What it covers |
|---|---|
| [image-gen-floor-plans-analysis.md](image-gen-floor-plans-analysis.md) | Analysis of AI-rendered client-facing visualisation |
| [cad-quality-improvement.md](cad-quality-improvement.md) | DXF/CAD output quality work |
| [cad_primitives_plan.md](cad_primitives_plan.md) | CAD primitive design |
| [freecad-backend-tradeoffs.md](freecad-backend-tradeoffs.md) | Evaluation of FreeCAD as a geometry backend |

## Plans
`plans/` holds dated implementation and design plans, newest last. These are historical
working documents — they record what was decided and when, not current state.

## Archive
`archive/` holds superseded PRDs and early prompts. Not current scope.
```

- [ ] **Step 2: Link it from the root README**

Add to README.md under the Known gaps section:

```markdown
## Documentation

Full index: **[docs/README.md](docs/README.md)** · Architecture: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**
```

- [ ] **Step 3: Verify every link resolves**

```bash
cd /home/karthik/projects/PlanForge/docs
for f in $(grep -oE '\]\([a-zA-Z0-9_.-]+\.md\)' README.md | tr -d ']()'); do
  [ -f "$f" ] && echo "OK   $f" || echo "DEAD $f"
done
```
Expected: all OK.

- [ ] **Step 4: Commit**

```bash
git add docs/README.md README.md && git commit -m "docs: add documentation index"
```

---

### Task 1.4.2: ~~Add real request/response examples to the API docs~~ — **DROPPED**

**Decision (2026-07-28, Karthik):** do not publish API examples that let a reviewer call
the live service off the shelf. Reviewers evaluate the product through the website
(`https://planforge-mauve.vercel.app`), walked through directly if needed.

**Rationale:**
- Copy-pasteable requests against a live endpoint on a `$0`-tier Cloud Run service
  (`min-instances=0`, `max-instances=3`) invite unmetered traffic and cost.
- It would also require issuing a working `x-api-key`, or publishing example output whose
  provenance a reader cannot verify anyway.
- The auto-generated OpenAPI reference at `/docs` on a running structapi already documents
  every endpoint for anyone who self-hosts, which covers the legitimate need.

No `docs/API-EXAMPLES.md` is created. The v1 envelope shape remains documented in §3 of
`docs/PLANFORGE-INTEGRATION.md`, which is schema documentation rather than a runnable
recipe against production.

**Downstream effect:** the pre-publish checklist item "No API keys in API-EXAMPLES.md"
(Task 3.1.1) is void — there is no such file.

---

### Task 1.4.3: Create Handover.md and refresh Status.md

**Files:**
- Create: `/home/karthik/projects/PlanForge/Handover.md`
- Create: `/home/karthik/projects/structapi/Status.md`, `/home/karthik/projects/structapi/Handover.md`
- Modify: `/home/karthik/projects/PlanForge/Status.md`

Your global convention calls for `README.md`, `Handover.md`, and `Status.md` in every project. PlanForge has Status.md (12k, last touched 2026-07-20) but no Handover.md; structapi has neither.

- [ ] **Step 1: Refresh PlanForge Status.md**

Add a dated entry at the top recording: 650 backend tests passing, structural integration live in production, backend revision `planforge-backend-00034-28r` deployed manually 2026-07-25, CI blocked on GitHub billing, public release in progress per this plan.

- [ ] **Step 2: Create Handover.md in both repos**

Contents: current branch, what is in flight, known blockers, the canonical URLs from Global Constraints, and where to pick up. Keep it short — this is a working handoff, not documentation.

- [ ] **Step 3: Create structapi Status.md**

Contents: v0.3.0 released and tagged, CI green, GHCR image published, live on Cloud Run, consumed in production by PlanForge, LICENSE added ahead of public release.

- [ ] **Step 4: Verify no secrets**

```bash
grep -rIniE "sk-|rzp_|postgresql://[^l]|hf_|Bearer " \
  /home/karthik/projects/PlanForge/Status.md /home/karthik/projects/PlanForge/Handover.md \
  /home/karthik/projects/structapi/Status.md /home/karthik/projects/structapi/Handover.md
```
Expected: no output. This is the exact failure mode that leaked R2/Neon/HF credentials for four months in `multimediagenai`.

- [ ] **Step 5: Commit both repos**

---

### Task 1.4.4: Add CLAUDE.md files to key directories

**Files:**
- Create: `backend/app/engine/CLAUDE.md`, `backend/app/services/CLAUDE.md`, `frontend/src/CLAUDE.md`, `backend/tests/CLAUDE.md` (PlanForge)
- Create: `python/iscodes/CLAUDE.md`, `agent/CLAUDE.md` (structapi)

Per your global convention. These also serve reviewers as orientation — a directory-level note on conventions signals a maintained codebase.

- [ ] **Step 1: Write each file**

Each states: what lives here, the conventions that apply, and the one thing a newcomer gets wrong. Example for `backend/app/engine/CLAUDE.md`:

```markdown
# backend/app/engine — conventions

Geometry and layout generation. Pure functions over Shapely objects where possible.

- **Never do raw float math for polygon operations** — use Shapely. Floating-point edge
  cases in setback/inset logic caused several solver bugs.
- Compliance thresholds live in `backend/config/compliance_rules.json`, never hardcoded.
- **Never run `ruff format` on `*.json`** — it corrupts the rules file.
- `solver.py` (OR-Tools CP-SAT) is the primary path; `archetypes.py` is the fallback when
  the solver cannot converge. Changes to room-adjacency logic usually need touching both.
- PDF generation is ReportLab only — not matplotlib, not cairosvg.
```

- [ ] **Step 2: Verify each file is under 40 lines**

```bash
wc -l backend/app/engine/CLAUDE.md backend/app/services/CLAUDE.md frontend/src/CLAUDE.md backend/tests/CLAUDE.md
```
Long directory notes go unread and drift stale.

- [ ] **Step 3: Commit both repos**

---

### Task 1.4.5: Commit architecture diagrams as SVG

**Files:**
- Create: `/home/karthik/projects/structapi/docs/assets/architecture.svg`
- Create: `/home/karthik/projects/PlanForge/docs/assets/system-flow.svg`

ASCII diagrams work in a terminal but look amateur on GitHub. Committed SVGs render inline and survive.

- [ ] **Step 1: Produce the two diagrams**

`architecture.svg` — the two-front-doors diagram: humans → Eve agent layer → iscodes; PlanForge backend → structapi → iscodes. `system-flow.svg` — the user-facing flow: plot input → CP-SAT → 3 layouts → structural design request → member design + BOQ + drawing set.

Use Excalidraw (available via MCP in this session) or hand-author the SVG. Keep to two colours plus greys, no gradients, readable at 800px wide.

- [ ] **Step 2: Show both to Karthik for approval before committing**

Per the global rule: generated artifacts (diagrams, wireframes, logos) require approval before they are applied. Do not commit unapproved diagrams.

- [ ] **Step 3: Replace the ASCII diagrams in both READMEs with image references**

```markdown
![Architecture](docs/assets/architecture.svg)
```

Keep the ASCII version in the architecture doc as a text fallback.

- [ ] **Step 4: Verify they render on GitHub**

SVGs referenced by relative path render in GitHub markdown; SVGs with embedded scripts do not. Confirm the files contain no `<script>` elements:

```bash
grep -l "<script" docs/assets/*.svg
```
Expected: no output.

- [ ] **Step 5: Commit**

---

# PHASE 2 — Demo Readiness

**Exit criteria:** A reviewer with no account can see the product work.

## Sprint 2.1 — Remove Access Friction

### Task 2.1.1: Provide reviewer access to the live demo

**Files:**
- Modify: `/home/karthik/projects/PlanForge/README.md`
- Possibly modify: `frontend/src/app/` (a no-auth sample route)

Better Auth guards the app. A reviewer will not sign up — this is the single highest drop-off point in the entire funnel. `docs/developer-reference.md:823` records that seeded test users already exist and were verified against production.

- [ ] **Step 1: Confirm the seeded credentials still work**

```bash
curl -s -X POST https://planforge-mauve.vercel.app/api/auth/sign-in/email \
  -H "Content-Type: application/json" \
  -d '{"email":"<seeded-email>","password":"<seeded-password>"}' -o /dev/null -w "%{http_code}\n"
```
Expected: 200. Retrieve the seeded values from `docs/developer-reference.md`.

- [ ] **Step 2: Decide the access mechanism**

Two options — pick one, do not do both:
- **(a) Publish demo credentials in the README.** Simplest. Requires the account to hold only sample projects and the password to be demo-only, never reused.
- **(b) Add a no-auth `/demo` route** that generates layouts from a fixed sample plot without a session. More work, better impression, no credential exposure.

If (a), add to README:

```markdown
## Try it without signing up

Demo account on the [live app](https://planforge-mauve.vercel.app):

```
email:    demo@planforge.example
password: <demo-password>
```

Read-only sample projects. Generation is stateless — you can also generate layouts
without logging in; an account is only needed to save them.
```

- [ ] **Step 3: Verify a clean-browser walkthrough**

In a private window, land on the URL, sign in with the demo path, generate layouts, request a structural design, export the drawing set. Every step must work without prior state. Note anything that breaks.

- [ ] **Step 4: Fix whatever the walkthrough broke**

Cold-start latency is a known risk: Cloud Run runs `min-instances=0`, and a measured ~23s cold start previously caused agent-tool timeouts (CLAUDE.md issue 13). If the first request times out for a reviewer, that is the whole impression. Consider `min-instances=1` for the demo period, or a loading state that survives 30s.

- [ ] **Step 5: Commit**

---

### Task 2.1.2: Fix the duplicated page title

**Files:**
- Modify: `frontend/src/app/layout.tsx` (or wherever metadata is defined)

The live site renders `G+1 Floor Plan Generator for Indian Builders — NBC 2016 Compliant | PlanForge | PlanForge` — "PlanForge" appears twice. Likely a `title.template` that also includes the suffix in `title.default`.

- [ ] **Step 1: Find the metadata definition**

```bash
cd /home/karthik/projects/PlanForge/frontend && grep -rn "PlanForge" src/app/layout.tsx src/app/**/metadata.ts 2>/dev/null | head
```

- [ ] **Step 2: Fix the template so the suffix applies once**

```typescript
export const metadata: Metadata = {
  title: {
    default: "PlanForge — G+1 Floor Plan Generator for Indian Builders",
    template: "%s | PlanForge",
  },
};
```

- [ ] **Step 3: Verify locally**

```bash
cd /home/karthik/projects/PlanForge/frontend && bun run build
```

- [ ] **Step 4: Verify on the deployed site after merge**

```bash
curl -s https://planforge-mauve.vercel.app | grep -oE "<title>[^<]*</title>"
```
Expected: exactly one `| PlanForge`.

- [ ] **Step 5: Commit**

---

### Task 2.1.3: Record the demo video

**Files:**
- Create: `docs/assets/demo.md` (link + description; do not commit the video binary)

- [ ] **Step 1: Script the run** — 3–4 minutes, no narration gaps:
  1. (0:00) Enter plot dimensions, setbacks, road side, city → generate
  2. (0:45) Three scored layouts; toggle the Vastu overlay; show compliance findings
  3. (1:30) Request structural design — narrate that this crosses into structapi
  4. (2:15) Member design output, IS clause references, SFD/BMD figures
  5. (3:00) Export the structural drawing set PDF; open it
  6. (3:30) Close on the architecture diagram — one sentence on why the engine is deterministic

- [ ] **Step 2: Record** using the tooling already on the machine; do not commit the file.

- [ ] **Step 3: Upload** (YouTube unlisted or Loom) and add the link to both READMEs under the live-demo line.

- [ ] **Step 4: Verify the link opens in a private window** — an unlisted YouTube link works; a Loom requiring login does not.

- [ ] **Step 5: Commit the link.**

---

# PHASE 3 — Publish

**Exit criteria:** Both repos public, CI green, all links live.

## Sprint 3.1 — The Gate

### Task 3.1.1: Human approval gate — DO NOT AUTOMATE

**Files:** None.

Making a repo public is irreversible in practice: forks, clones, and search-engine caches persist after any re-privatisation. This task requires Karthik's explicit go-ahead.

- [ ] **Step 1: Present the pre-publish checklist and get explicit approval**

Confirm every line before asking:

```
[ ] gitleaks clean on both repos, full history          (Task 0.1.1)
[ ] structapi LICENSE present                            (Task 0.1.2)
[ ] No third-party copyrighted PDFs in either repo       (Task 1.3.3 Step 1)
[ ] No real credentials in any .md, including Status.md  (Task 1.4.3 Step 4)
[ ] No runnable live-service examples published          (Task 1.4.2 — dropped by decision)
[ ] Backend suite green: 650 passing                     (Task 0.2.2 Step 2)
[ ] Working branch merged to main                        (Task 0.2.2 Step 5)
[ ] Stale failed CI runs deleted                         (Task 0.2.1 Step 3)
[ ] Demo access path verified in a clean browser         (Task 2.1.1 Step 3)
[ ] Karthik has reviewed both rewritten READMEs
```

- [ ] **Step 2: Ask explicitly. Do not proceed on inference.**

Publishing is outward-facing and irreversible; a previous approval for docs work does not extend to it.

---

## Sprint 3.2 — Flip and Verify

### Task 3.2.1: Make both repos public

- [ ] **Step 1: Flip structapi first**

Smaller, cleaner, green CI — publish it first and confirm nothing unexpected surfaces before exposing the larger repo.

```bash
gh repo edit karthiknitt/structapi --visibility public --accept-visibility-change-consequences
```

- [ ] **Step 2: Verify from a logged-out perspective**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://github.com/karthiknitt/structapi
```
Expected: 200. Also open it in a private browser window and confirm the README renders, the LICENSE shows "MIT" in the sidebar, and the Actions tab is green.

- [ ] **Step 3: Flip planforge**

```bash
gh repo edit karthiknitt/planforge --visibility public --accept-visibility-change-consequences
```

- [ ] **Step 4: Confirm the Actions billing block cleared**

Public repos get unlimited free standard-runner minutes. Trigger a run and confirm:

```bash
gh workflow run backend-ci.yml -R karthiknitt/planforge
sleep 45 && gh run list -R karthiknitt/planforge --limit 3
```
Expected: the run starts. If it still reports the billing error, the cause was an account-level lock rather than quota (see Task 0.2.1 Step 1) — fix billing directly; publishing will not resolve it.

- [ ] **Step 5: Re-enable branch protection on main**

```bash
gh api -X PUT repos/karthiknitt/planforge/branches/main/protection \
  -f "required_pull_request_reviews[required_approving_review_count]=0" \
  -F "enforce_admins=false" -F "restrictions=null" \
  -f "required_status_checks[strict]=true" -f "required_status_checks[contexts][]=ruff-and-pytest"
```

Branch protection is unavailable on private repos on the free plan — going public is what makes this possible, and it matches your standing convention of never merging directly to `main`.

---

### Task 3.2.2: Post-publish link audit

- [ ] **Step 1: Verify every external link in both READMEs resolves**

```bash
for r in /home/karthik/projects/PlanForge /home/karthik/projects/structapi; do
  grep -ohE 'https?://[^ )"]+' "$r/README.md" | sort -u | while read u; do
    printf "%-70s " "$u"; curl -s -o /dev/null -m 20 -w "%{http_code}\n" -L "$u"
  done
done
```
Expected: all 200. Watch specifically for `planforge.vercel.app` — if that string appears anywhere, it is the wrong third-party domain.

- [ ] **Step 2: Verify cross-repo links now resolve publicly**

Both READMEs link to the other repo. While private these 404'd for anonymous visitors.

```bash
curl -s -o /dev/null -w "planforge=%{http_code}\n" https://github.com/karthiknitt/planforge
curl -s -o /dev/null -w "structapi=%{http_code}\n" https://github.com/karthiknitt/structapi
curl -s -o /dev/null -w "archdoc=%{http_code}\n" https://github.com/karthiknitt/structapi/blob/main/docs/PLANFORGE-INTEGRATION.md
```

- [ ] **Step 3: Add repo topics and descriptions**

```bash
gh repo edit karthiknitt/structapi --description "Multi-agent IS-code RCC structural design: Eve orchestrator + 8 specialist subagents over a deterministic FastAPI engine (IS 456/875/1893/13920/3370/10262). Live on Cloud Run." --add-topic ai-agents --add-topic llm --add-topic fastapi --add-topic structural-engineering --add-topic multi-agent
gh repo edit karthiknitt/planforge --description "G+1 floor-plan generator for Indian builders — OR-Tools CP-SAT solver, municipal compliance + Vastu, PDF/DXF/BOQ export, and IS-code structural design via structapi." --add-topic nextjs --add-topic fastapi --add-topic or-tools --add-topic constraint-solver --add-topic ai-agents
```

Topics are how GitHub search surfaces the repos, and the description is what shows in any link preview a recruiter shares internally.

- [ ] **Step 4: Confirm graphify is current**

```bash
cd /home/karthik/projects/PlanForge && graphify update .
```
Per your convention after pushing to a repo with a knowledge graph.

- [ ] **Step 5: Commit any remaining changes.**

---

# PHASE 4 — Submission Package

**Exit criteria:** Application submitted.

### Task 4.1.1: Assemble and submit

**Files:**
- Create: `/home/karthik/.claude/jobs/<job-dir>/tmp/razorpay-application.md` (draft, not committed to either repo)

- [ ] **Step 1: Write the application blurb**

Structure — 15 years of program management in manufacturing, healthcare, and infrastructure → sabbatical from June 2024 for AI upskilling → built a multi-agent structural design system in a regulated domain, with a deterministic verification layer under the agents, shipped to production and consumed by a live SaaS. Name the judgement explicitly: knowing where the LLM belongs and where it does not.

- [ ] **Step 2: Order the links deliberately**

1. `https://github.com/karthiknitt/structapi` — the agent architecture
2. `https://planforge-mauve.vercel.app` — the live product
3. `https://github.com/karthiknitt/planforge` — the consuming SaaS
4. Demo video
5. `https://github.com/karthiknitt/smart_resume` — 10 stars, public, real users (one line, showing you ship and maintain)

- [ ] **Step 3: Mention the Razorpay integration in one line** — PlanForge already ships Razorpay checkout. Shipping on their own rails is cheap, concrete credibility.

- [ ] **Step 4: Final anonymous check**

In a private browser window, open every link in the order above. This is exactly what the reviewer will do. Any 404, auth wall, or cold-start timeout here costs the application.

- [ ] **Step 5: Submit the form at https://razorpay.com/ai-builders/**

Response is stated as within 48 hours "if it has signal."

---

## Self-Review

**Spec coverage:** Both decisions are covered — "both public" (Phase 3, Tasks 3.2.1–3.2.2, gated by 3.1.1) and "full docs overhaul" (Phase 1 Sprints 1.1–1.4: canonical architecture doc, both README rewrites, stale-content fixes, docs index, real API examples, Status/Handover, directory CLAUDE.md files, committed SVG diagrams). Job-application framing carried through Phase 4.

**Placeholder scan:** Three items intentionally require live lookup rather than a hardcoded value, each with the retrieval command given: the structapi test count (CI log — local collection fails on missing deps), the GCP service-account email (`gcloud iam service-accounts list`), and the seeded demo credentials (`docs/developer-reference.md:823`). These are lookups, not TODOs.

**Consistency:** URLs, GCP project name, health paths, and the 650 test count are stated once in Global Constraints and referenced identically throughout. Task 1.3.2 depends on Task 1.3.3 not having moved the deployment plan doc — it does not; only root-level files move.

**Known risk not yet resolved:** if Task 0.2.1 Step 1 finds an account-level billing lock rather than quota exhaustion, Task 3.2.1 Step 4 will fail and PlanForge CI stays red on a public repo. Mitigation is inside Task 0.2.1; do not defer that diagnosis until after publishing.
