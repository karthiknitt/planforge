# FreeCAD as Backend Server — PM Tradeoff Analysis

## Context
Evaluating whether to replace Shapely + ezdxf with FreeCAD (headless) as the floor plan generation backend, optionally using [CLI-Anything (HKUDS)](https://github.com/HKUDS/CLI-Anything) to make FreeCAD agent-native for LLM-driven edits.

---

## The Latency Problem (This Is the Killer)

| Operation | Shapely (current) | FreeCAD subprocess |
|---|---|---|
| Cold start per request | ~0ms (library imported once) | **5–15 seconds** (Qt + kernel load) |
| Warm operation | <10ms | 100–500ms per command |
| 3 layout generation | ~300ms total | **45s+ cold, 2–5s warm** |

FreeCAD is a desktop Qt application. Even headless, it loads the full GUI framework into memory. For a web product where users expect results in 2–3 seconds, a 15-second cold start is a product-killing UX regression.

**Mitigation:** Keep a persistent FreeCAD process pool alive (like Gunicorn workers). But now you're managing process lifecycle, crash recovery, and warm pool sizing — significant DevOps complexity.

---

## Memory & Infrastructure Cost

| | Shapely (current) | FreeCAD |
|---|---|---|
| RAM per instance | ~50MB (whole FastAPI process) | 300–500MB per FreeCAD process |
| Concurrent users (10) | Fine on 2GB VPS | Needs 5GB+ RAM |
| Estimated server cost | $20/month VPS | $80–150/month minimum |

For a pre-revenue product, the infra cost difference alone is a non-starter.

---

## CLI-Anything + LLM Edit Flow — Full Latency Stack

If you add CLI-Anything so an LLM can edit floor plans via FreeCAD commands:

```
User edit request
  → LLM generates FreeCAD script via CLI-Anything   (+1–3s LLM call)
  → FreeCAD subprocess executes script               (+2–5s warm)
  → Export DXF/PDF                                   (+1–2s)
  → Return to client
  ─────────────────────────────────────────────────
  Total: 4–10s per edit operation
```

Current agent chat (Shapely + rooms.py): **~1–2s per edit.**
You'd be trading 5x responsiveness for better drawing quality.

---

## What FreeCAD Actually Buys You

| Capability | Current (ezdxf) | FreeCAD Arch workbench |
|---|---|---|
| Wall thickness rendering | Manual polygon math | Native wall objects |
| Door/window symbols | Custom draw code | Built-in symbols |
| IFC/BIM export | Not possible | Native |
| DWG export | Not possible | Native (via ODA) |
| Parametric constraints | Not possible | Core feature |
| Drawing quality | Functional | **Professional-grade** |
| Section views | Manual SVG | Auto from 3D model |
| Compliance checking | Custom logic | Still needs custom logic |

The output quality difference is real. FreeCAD's TechDraw + Arch workbench produces drawings indistinguishable from AutoCAD output.

---

## Concurrency: The Architectural Problem

FreeCAD is designed for one user, one session. It is **not thread-safe**. To handle N concurrent users you need N separate OS processes.

Shapely runs safely across async coroutines in a single FastAPI process. FreeCAD requires a full process pool manager (Celery workers or custom), request queuing, and timeout handling. That's **2–3 weeks of infrastructure work** before writing a single floor plan feature.

---

## PM Verdict: When to Switch, When to Stay

### Stay with Shapely + ezdxf if:
- Pre-revenue / still validating product-market fit
- Users are builders (functional output > beautiful output)
- Latency and infra cost are hard constraints

### Switch to FreeCAD if:
- Targeting architects (they reject anything that doesn't look like AutoCAD)
- IFC/BIM export is required (mandatory for some government projects in India)
- Budget allows $150+/month infra and 3–4 weeks to build the process pool
- You're post-revenue and quality is the differentiator

### Recommended Hybrid Approach
Keep Shapely for **generation and compliance** (fast, cheap, reliable).
Add FreeCAD as an **optional export step** — triggered only when user clicks "Export Professional Drawing."

A 10-second wait is acceptable for a one-time export. It is not acceptable for live layout generation.

```
Generate layout  →  Shapely (300ms, always)
Preview in browser  →  SVG (instant)
Export for permit  →  ezdxf (current, fast)
Export professional DXF/IFC  →  FreeCAD (10s, on-demand, post-MVP)
```

---

## Sources
- [CLI-Anything: Making ALL Software Agent-Native (HKUDS)](https://github.com/HKUDS/CLI-Anything)
- [CLI-Anything overview](https://clianything.org/)
