# Structural Drawing Set — Design

**Date:** 2026-07-19
**Status:** Approved, ready for implementation planning
**Reference:** `~/projects/Thalakudy/Thalakudy/Structural Drawings/*.pdf` — a real G+1 residential
RCC structural set (Column & Footing Plan, Footing Details, Plinth Beam Plan, Plinth Beam
Details, Roof Beam & Slab Plan, Roof Beam Details), signed by a licensed structural consultant.

## Goal

Extend PlanForge (product feature, not a one-off) with a **Structural Drawing Set** PDF export —
CAD-style plan-view + cross-section-detail sheets matching the reference set's fidelity — built
on top of the existing StructAgent (`structapi`) integration, which already computes IS 456 LSM
member design (footings, columns, beams) but has never rendered CAD drawing sheets from it.

## Scope: 6 sheets, PDF-only v1

1. **Column & Footing Plan** — real column x,y from approved layout geometry, each tagged with
   footing type (T1/T2/T3 via corner/edge/interior classification — reuses `pdf.py`'s
   `_column_class`), footing outlines to scale, grid dimensions, north arrow.
2. **Footing Details** — schedule table (type → column c/s, footing size L×B, depth, mat
   reinforcement dia/spacing) + one typical dimensioned footing cross-section pictorial (PCC bed,
   mat rebar, column dowel/starter bars).
3. **Plinth Beam Plan** — plan view of plinth-level beams over the same column grid, each segment
   labeled (PB1, PB2, …) by unique size/reinforcement group.
4. **Plinth Beam Details** — per-mark cross-section pictorial (one section per mark — see
   simplification #7 below) with tension bar count+dia, compression bars if doubly reinforced,
   and stirrup spacing.
5. **Roof Beam & Slab Plan** — extends the existing GF/FF structural floor page with floating-column
   markers and slab-panel labels (S1/S2/…) alongside the beam/column layout already drawn today.
6. **Roof Beam Details** — same cross-section-pictorial renderer as sheet 4, fed from the
   building-chain's slab-driven beam design instead of wall-UDL beams.

Sheets 4 and 6 share one new renderer (one dimensioned box pictorial per beam mark with bar
callouts), parameterized by which beam-design source feeds it. Everything else (title block,
scale, north arrow, schedule tables, column classification) reuses helpers already in
`app/engine/pdf.py`.

## Why plinth beams need separate design (not a reuse of roof beam sizing)

IS 456 has no distinct "plinth beam" clause — a plinth beam is an ordinary RC beam (same Cl 23
flexure / Cl 40 shear checks as any beam). What differs is the **governing load case**:

- Roof/floor beams (`structapi`'s `/v1/design/building` chain) are sized from two-way slab
  reactions (IS 456 Table 26) plus live load.
- Plinth beams in ordinary Indian G+1 residential construction carry no slab load — the ground
  floor rests on filled/compacted earth, not a suspended slab (confirmed by the reference set:
  "PB7/BELT BEAM FOR PARTITION WALLS ... TO BE PROVIDED AT FLOOR LEVEL"). Plinth beams carry the
  masonry wall UDL (wall height × thickness × unit weight per IS 875 Part 1, ~19–20 kN/m³) plus
  self-weight, and tie the isolated footings together against differential settlement.

This is why in the reference set PB2 (0'-9"×1'-6") is deeper than roof beam B2 (0'-9"×1'-0")
despite sharing a grid position — different loads, independently sized.

`structapi` already exposes the right primitive for this: `POST /v1/calc/beam`
(`iscodes/design/beam.py::design_beam()`) takes an arbitrary `w_dl_kn_m`/`w_il_kn_m` UDL directly,
separate from the slab-driven `/v1/design/building` pipeline. No new work needed in `structapi`
itself — PlanForge computes the wall-UDL per plinth-beam span and calls this generic endpoint
once per unique span/load combination.

## Architecture / data flow

```
Approved layout geometry (real column x,y)
        │
        ├─► structural_grid.extract_grid() ──► structapi /v1/design/building
        │                                          │
        │                                          ├─► data.columns  (existing, used today)
        │                                          ├─► data.beams    (existing, roof beams)
        │                                          └─► data.footings (NEW consumption — already
        │                                                              returned, unused today)
        │
        └─► NEW: plinth_loads.py
                 wall UDL per plinth-beam span (from compliance_rules.json wall
                 thickness/height + IS 875-1 unit weight table)
                        │
                        ▼
                 structapi /v1/calc/beam  (per unique span/load — generic endpoint)
                        │
                        ▼
                 plinth beam design results
        │
        ▼
NEW app/engine/structural_drawings.py
  - places footing outlines at real column x,y (footing type ← _column_class)
  - places plinth-beam / roof-beam segments along wall centrelines from build_floor_drawing()
  - renders 6 ReportLab pages reusing pdf.py's title block / scale / schedule-table helpers
        │
        ▼
NEW route: POST /projects/{id}/structural/drawings  →  PDF bytes
```

Gated on the same approval flow as today's `/structural` endpoint: requires an approved
architectural revision (`POST .../structural/approve`) and a completed structapi design run
(`POST .../structural`) for that revision. `structapi` is required, no fallback — same posture as
the existing structural-design feature (503 if `STRUCTURAL_API_URL` isn't configured).

## Known simplifications / assumptions (v1)

These are the deliberate corners cut for v1, and should be echoed as a disclaimer on the rendered
PDF itself (same pattern as `structapi`'s existing `disclaimer` field on `/v1/design/building`
responses) — not just documented here:

1. **Isolated footings only.** Matches the reference set and `structapi`'s
   `design_isolated_footing`. No combined/raft/pile footings — a layout that would need one
   (e.g., columns too close together, or very poor SBC) is out of scope for this drawing set.
2. **Plinth wall-UDL uses a single representative wall height** (plinth-to-sill or
   plinth-to-lintel, whichever `compliance_rules.json` already encodes), applied uniformly per
   span. It does **not** deduct openings punched into that specific wall segment — a real engineer
   would reduce the UDL where a door/window removes wall self-weight. This makes v1
   conservative (over-designed), not cost-optimal.
3. **No seismic/wind overlay on plinth beams.** Plinth beams are designed as self-contained
   gravity-only members via the generic `/v1/calc/beam` endpoint. Roof beams already get the
   seismic/wind overlay from `structapi`'s building-chain (`building.py`), since IS 13920 lateral
   effects matter more at roof/floor level than at plinth level for a G+1.
4. **Regular orthogonal grid assumption carries over** from the existing structural-grid
   extraction (`structural_grid.py`) — same "confident vs. needs review" gate already used by the
   `/structural` endpoint applies here; an irregular layout blocks this export the same way it
   blocks structural design today.
5. **Beams designed as simply supported on the worst span** (conservative vs. true continuous-beam
   Table 12 behavior) — this is an existing `structapi` building-chain simplification (documented
   in its own `iscodes/design/building.py` docstring), not new to this feature, but it does flow
   through to the Roof Beam Details sheet.
6. **Same licensed-engineer disclaimer as the rest of the structural feature** — "for planning
   only," not a substitute for a signed structural drawing set. This is explicitly a decision-
   support / preliminary-design tool, not a replacement for the structural consultant who signs
   off on a real construction drawing.
7. **One reinforcement schedule per beam mark, not a midspan-vs-support split.** `structapi`'s
   `design_beam()` (both the building-chain roof beams and the new plinth-beam calls) returns a
   single tension-steel bar count/dia sized for the worst moment on the span
   (`max(|Mu_sagging|, |Mu_hogging|)`), plus a single stirrup spacing — it does not compute
   distinct top-steel-at-support vs. bottom-steel-at-midspan bar counts the way the reference
   drawings show (e.g. PB4's "+1no-16mmø(ckd)" curtailment detail at support only).
   Sheets 4/6 in v1 draw **one cross-section pictorial per beam mark** (tension bars + stirrup
   spacing + compression bars if doubly reinforced), not two side-by-side midspan/support boxes.
   This is conservative (same steel run the full span, nothing under-designed) but won't match
   the reference set's curtailment-level detail — extending `structapi`'s beam design to emit a
   proper midspan/support split is a real follow-up, not attempted in v1.

## Testing

- Backend: pytest fixtures replaying a recorded `structapi` response (same pattern as
  `tests/test_structural_endpoint.py`) → assert each of the 6 pages renders without error, and
  that footing/beam counts on the page match `data.footings`/`data.beams` (and the new plinth-beam
  design results) counts.
- No golden-PDF byte-diff (ReportLab output isn't stable run-to-run) — assert on extracted
  text/positions instead, following whatever pattern the existing PDF tests already use.

## Next step

Hand off to `writing-plans` for a phased implementation plan (task breakdown, complexity/model-tier
per task, merge-conflict-minimizing sequencing).
