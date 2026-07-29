# PlanForge Documentation

## Start here

| Doc | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | How PlanForge and structapi fit together, and why the calculation engine is deterministic rather than agentic |
| [developer-reference.md](developer-reference.md) | Environment variables, local setup, deployment, API reference, engine internals, DB schema, seeded test users |
| [product-roadmap.md](product-roadmap.md) | Shipped features (P0–P3) and the remaining backlog |
| [documentation.md](documentation.md) | End-user feature documentation |

## Setup guides

| Doc | What it covers |
|---|---|
| [guides/cloudflare-r2-setup.md](guides/cloudflare-r2-setup.md) | R2 bucket setup for generated artifacts (PDF, DXF, XLSX, AI renders) |
| [guides/neon-pooling.md](guides/neon-pooling.md) | Neon pooled connection string setup |
| [guides/solver-service-split.md](guides/solver-service-split.md) | Manual rollout steps for the `planforge-solver` Cloud Run service |

Internal design research and dated implementation plans are kept locally
(gitignored) rather than in the repo — they're working notes, not reference
material for contributors.

## Related repositories

The structural design engine lives in a separate repo:
**[karthiknitt/structapi](https://github.com/karthiknitt/structapi)** — the deterministic
`iscodes` library (IS 456/875/1893/13920/3370/10262), the `structapi` REST service that
PlanForge calls, and StructAgent, the multi-agent natural-language layer over the same
engine. The canonical integration architecture document lives there:
[docs/PLANFORGE-INTEGRATION.md](https://github.com/karthiknitt/structapi/blob/main/docs/PLANFORGE-INTEGRATION.md).
