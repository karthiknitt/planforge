# PlanForge Documentation

## Start here

| Doc | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | How PlanForge and structapi fit together, and why the calculation engine is deterministic rather than agentic |
| [developer-reference.md](developer-reference.md) | Environment variables, local setup, deployment, API reference, engine internals, DB schema, seeded test users |
| [product-roadmap.md](product-roadmap.md) | Shipped features (P0–P3) and the remaining backlog |
| [documentation.md](documentation.md) | End-user feature documentation |

## Design & research

| Doc | What it covers |
|---|---|
| [cad_primitives_plan.md](cad_primitives_plan.md) | CAD primitive design for DXF/drawing output |
| [2026-07-15-drafted-ai-research-and-solver-dataset-sourcing.md](2026-07-15-drafted-ai-research-and-solver-dataset-sourcing.md) | Research notes on AI-assisted layout generation and solver dataset sourcing |

## Plans

`plans/` and `superpowers/plans/` hold dated implementation and design plans, oldest
first. These are **historical working documents** — they record what was decided and
when, not the current state of the system. Where a plan contradicts this index or the
root `README.md`, the plan is out of date.

Current public-release work: [plans/2026-07-27-public-release-docs-overhaul.md](plans/2026-07-27-public-release-docs-overhaul.md).

## Related repositories

The structural design engine lives in a separate repo:
**[karthiknitt/structapi](https://github.com/karthiknitt/structapi)** — the deterministic
`iscodes` library (IS 456/875/1893/13920/3370/10262), the `structapi` REST service that
PlanForge calls, and StructAgent, the multi-agent natural-language layer over the same
engine. The canonical integration architecture document lives there:
[docs/PLANFORGE-INTEGRATION.md](https://github.com/karthiknitt/structapi/blob/main/docs/PLANFORGE-INTEGRATION.md).
