# Layout Quality Critique Loop — Design

**Date:** 2026-08-09
**Status:** Approved design, not yet planned/implemented

## Problem

The solver (`backend/app/engine/solver.py`) and scorer (`backend/app/engine/scorer.py`)
produce layouts with two known classes of defect: spatial/functional (awkward
adjacencies, poor circulation, wasted space) and aesthetic/drawing quality (CAD
output conventions). There is no repeatable process to surface *specific* instances
of these defects and turn recurring ones into new deterministic checks.

## Prior art / constraint this design respects

`backend/app/quality/ccqs.py:135-143` documents that CCQS previously included a
5th component: a stochastic vision-judge LLM call scoring layouts 0-20. It was
dropped from the production quality gate because it **plateaued near 16/20
regardless of real drawing-quality changes** — a single scalar LLM-judge score
compresses toward the middle and stops being sensitive to the defects you're
trying to fix. It was replaced by GCS (Geometric Correctness Score), computed
deterministically from the canonical `FloorDrawing` structure.

**This design does not repeat that mistake.** Nothing here asks an LLM to emit a
quality score. Every critique step must emit a structured, falsifiable defect
list instead. Turning recurring defects into deterministic rules (the GCS
pattern) is the intended path from critique to code — not a replacement scoring
gate.

## Goal

A repeatable pipeline, invoked on demand (not continuously), that:
1. Generates a small diverse batch of layouts (~10-15 for the first run).
2. Has Claude critique each rendered layout for specific, actionable defects.
3. Has Claude mine conventions (qualitative + quantitative) from a curated
   folder of reference floor plan images you supply.
4. Synthesizes both lanes into a single report with clustered, recurring
   defects and proposed (unapplied) rule-diff sketches.
5. Leaves all code changes to a separate, manually-triaged follow-up — this
   pipeline never edits `scorer.py`/`compliance.py` itself.

## Explicitly out of scope

- No changes to CCQS/GCS production scoring or the CI quality gate.
- No automatic "solver learns from images" — CP-SAT has no gradient; there is
  no automated path from image feedback to constraint/objective changes. The
  bridge is always a human-gated code edit informed by a structured finding.
- No auto-applied code changes of any kind — this pipeline's terminal artifact
  is a report, full stop.
- No user-facing "upload a reference photo" feature. Image extraction here is
  strictly an internal tool feeding this critique loop's Lane B. A user-facing
  version of image import is a distinct, higher-precision-bar feature to
  brainstorm separately if/when desired.
- First run is intentionally small (~10-15 layouts). Widening the batch matrix
  is a decision for a later run, once the pipeline is proven.

## Architecture

```
Phase 1: Batch generation          Phase 2: Critique (two parallel lanes)         Phase 3: Synthesis
─────────────────────────          ──────────────────────────────────────         ──────────────────
plot/program matrix                Lane A: per-layout defect critique             cluster findings by
  (~10-15 configs,                   -> one Claude vision-agent per rendered      theme + frequency
  varying plot shape                   PDF/PNG, structured defect list
  AND room program)                                                               draft rule-diff
       |                           Lane B: reference rule-mining                    proposals (not
       v                             -> one agent per image in your                 applied) per
  existing generator                  reference folder:                             defect cluster
  (engine/generator.py)                 (a) qualitative conventions                     |
       |                                (b) approximate structured                      v
       v                                    FloorPlan JSON (rectangular         docs/quality-audits/
  rendered PDF/PNG                          approximation, scale from            YYYY-MM-DD-report.md
  per layout                                any legible dimension labels,                |
                                             flagged low_confidence if none)              |
                                                        |                                 |
                                                        v                                 |
                                              structured findings (JSON/TOON)             |
                                                        |                                 |
                                                        +---------------------------------+
                                                                 |
                                                                 v
                                                          you review, approve/
                                                          reject each proposal
                                                                 |
                                                                 v
                                                   separate follow-up task actually
                                                   edits scorer.py/compliance.py
                                                   for approved items only
```

Phase 1 is deterministic (no LLM) — cheap to run at any scale. Phase 2 is where
judgment happens; both lanes emit the same finding shape. Phase 3 is the one
deliberate barrier in an otherwise parallel pipeline, because clustering and
frequency-counting need every finding at once.

## Phase 1 — Batch generation

- Sweep **both** plot geometry (shape, size, orientation, facing) and room
  program (bedroom count, floor count, special rooms) — a small matrix
  crossing 2-3 plot variations x 2-3 program variations, ~10-15 layouts total
  for the first run.
- Generate via the existing `engine/generator.py` path (same code the product
  uses) rather than a separate code path, so findings are representative of
  real output.
- Render each to PDF/PNG using the existing drawing pipeline
  (`plan_geometry.py` → `pdf.py`) — critique needs pixels, not just geometry
  JSON, since aesthetic/drawing-quality defects are a named target.

## Phase 2 — Critique

### Lane A: generated-layout critique
One Claude vision agent per rendered layout. Input: the rendered PDF/PNG plus
the underlying `Layout`/`FloorPlan` data for grounding. Output: a list of
defect findings (schema below) covering both spatial/functional and
aesthetic/drawing-quality categories — the two failure modes actually named as
priorities.

### Lane B: reference rule-mining
One Claude vision agent per image in a folder you curate and supply. Output
per reference image:
- Qualitative conventions: explicit, checkable statements about what the
  reference plan does well (e.g. "kitchen always adjacent to dining", "no
  bedroom door opens directly opposite another bedroom door").
- Approximate structured `FloorPlan` JSON: best-effort reconstruction using
  PlanForge's own `Room(x, y, width, depth)` schema. Every room is
  approximated as its bounding rectangle (real floor plans may have
  non-rectangular rooms — this is a known, accepted lossy step). Absolute
  metre values are only trusted when the image has legible dimension text or
  a scale bar to anchor them; otherwise the reconstruction is flagged
  `low_confidence` and used for proportions/adjacency only, not absolute
  sizes.

### Defect finding schema (both lanes emit this shape)
```
{
  source: "generated" | "reference",
  layout_id | image_id,
  category: "spatial" | "aesthetic",
  element_ref: e.g. "kitchen wall", "corridor between bed2/bath1",
  description: one falsifiable sentence,
  suggested_check: candidate file/function this could become a rule in
                    (e.g. scorer.py adjacency component, compliance.py check),
  confidence: whether this looks like a recurring pattern vs. a one-off quirk
              of this particular plot/reference
}
```

## Phase 3 — Synthesis

One synthesis pass over all Phase 2 findings (both lanes):
- Cluster findings by theme (not by source — a spatial adjacency issue found
  in a generated layout and a matching convention from a reference image
  belong in the same cluster).
- Count frequency per cluster.
- For clusters with a reference-lane `FloorPlan` JSON available, add a
  quantified comparison against the matching generated layout (e.g. "kitchen
  area: reference 9.2m² vs. generated 6.1m²") alongside the prose finding.
- Draft a proposed rule-diff sketch per recurring cluster — which file/function
  it would touch and roughly what the check would assert — without writing or
  applying any actual code.

## Output artifact

`docs/quality-audits/YYYY-MM-DD-critique-run.md`: findings grouped by cluster,
frequency counts, quantified comparisons where available, proposed rule-diff
sketches. No code is changed by this pipeline. You review the report and
decide which proposals to act on; a separate, normal implementation task
(tests-first, PR flow) picks up approved items.

## Invocation / cadence

Repeatable, not continuous — run on demand (e.g. after solver/scorer changes,
or periodically). Phase 2's ~10-15 critique agents (plus Lane B agents, one
per reference image) are naturally parallel and Phase 3 is a single
synthesis step — a good structural fit for the Workflow tool. Per standing
policy, actually invoking Workflow requires the user's own explicit
opt-in *at run time* — this design specifies Workflow as the intended
mechanism but does not itself constitute that opt-in.

## Testing / validation

- Spot-check: you review a sample of individual Lane A/B findings (not just
  the synthesized report) on the first run to sanity-check the critique
  agents aren't hallucinating defects or missing obvious ones.
- Lane B `low_confidence` flag is itself a validation signal — if most
  reference images end up flagged low-confidence (no legible dimensions),
  that's a sign to prefer reference images with visible dimension labels
  going forward, not to trust the proportional-only reconstructions as if
  they were precise.
