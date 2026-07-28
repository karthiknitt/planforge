# Architecture

PlanForge is the customer-facing half of a two-repo system. It generates compliant floor
plans; the structural design behind them is computed by a separate service.

```
 plot dimensions, setbacks, room preferences
                  │
                  ▼
 ┌───────────────────────────────┐   OR-Tools CP-SAT + Shapely
 │  PlanForge (this repo)         │   3 scored, compliance-checked layouts
 │  Next.js 16 · FastAPI · Neon   │   Vastu, municipal bye-laws, PDF/DXF/BOQ
 └───────────────┬───────────────┘
                 │  POST /v1/design/building
                 │  frozen v1 envelope, x-api-key, service-to-service
                 ▼
 ┌───────────────────────────────┐   IS 456 · 875 · 1893 · 13920 · 3370 · 10262
 │  structapi                     │   deterministic — no LLM in the calculation path
 │  FastAPI over python/iscodes   │
 └───────────────┬───────────────┘
                 ▼
   member design · reinforcement · BOQ quantities · structural PDF sheets
```

The canonical architecture document — including the "two front doors, one calculation
core" decision, the frozen v1 envelope contract, and the rationale for calling a
deterministic service rather than an LLM agent — lives in the engine repo:

**→ [StructAgent × PlanForge — Integration Architecture](https://github.com/karthiknitt/structapi/blob/main/docs/PLANFORGE-INTEGRATION.md)**

## Why the engine is deterministic

Structural design from a known floor plan is fully parameterised, so the same plan must
always produce the same design. That is a hard requirement for revision history, approval
workflows, and BOQ reproducibility — none of which tolerate a non-deterministic answer.

The LLM layer therefore sits *above* the engine, never inside it:

- PlanForge's Claude chat calls structapi as a **tool**, so conversational edits still work.
- StructAgent (in the engine repo) offers a natural-language front door for humans, via an
  orchestrator that routes to 8 specialist subagents.
- Both paths call the identical `iscodes` functions, so both produce identical numbers.

## PlanForge-side implementation

| Concern | File |
|---|---|
| HTTP client for structapi | `backend/app/services/structagent_client.py` |
| Design request orchestration | `backend/app/services/structural_loop.py` |
| Revision persistence | `backend/app/services/structural_store.py` |
| API routes | `backend/app/api/routes/structural.py` |
| Plinth beam design | `backend/app/services/plinth_beam_design.py` |
| Drawing set export | `backend/app/engine/structural_drawing_set.py` |
| Vendored engine copy | `structapi-service/` (byte-diffed against the pinned tag in CI) |

Tests: `backend/tests/test_structagent_client.py`, `test_structural_loop.py`,
`test_structural_endpoint.py`, `test_structural_revisions.py`,
`test_structural_drawing_set.py`, `test_export_structural_drawing_set.py`,
`test_boq_structural_design.py`, `test_plinth_beam_design.py`.

## Live services

| Component | URL |
|---|---|
| Frontend | https://planforge-mauve.vercel.app |
| Backend | https://planforge-backend-912195238699.us-central1.run.app (`/api/health`, `/docs`) |
| Engine | https://structapi-912195238699.us-central1.run.app (`/v1/health`) |

Local development conventions: [developer-reference.md](developer-reference.md).
