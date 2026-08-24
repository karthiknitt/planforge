# Solver Capability Gaps — evidence from the `reverse_engr` corpus

**Date:** 2026-08-15
**Corpus:** `docs/superpowers/specs/reverse_engr/` — 18 regional styles, 324 designs,
206 VLM (`*-ocr.json`) extracts, ~1130 plan/elevation images scraped from Tata Steel
Aashiyana.
**Question:** what must PlanForge's solver + render pipeline be able to express in
order to produce output at the fidelity of these reference plans?

This document merges three sources:

1. **New** — quantitative mining of all 206 `*-ocr.json` extracts (this document's
   novel contribution).
2. **New** — visual reading of representative plan images (Kerala-03, Goan-18,
   Rajasthani-Haveli-01) to catch what structured extracts cannot encode.
3. **Prior** — the capability-gap and Vastu analyses from session
   `94aad8b8` (2026-08-14, unrecorded — that session died on a rate limit), plus
   `solver_limitations.md`'s resolution table.

---

## 1. Quantitative findings (206 extracts, 3104 room instances, 363 floors)

| Signal | Measurement | Implication |
|---|---|---|
| Distinct room labels | **231** vs PlanForge's **25** `RoomType` values | Vocabulary gap |
| Floors with a **carved/nested** room (≥80 % bbox-contained in a larger room) | **81 / 363 = 22 %** | Rectangle-tiling can't express it |
| Room instances that are **open/unwalled or have no area** | **685 / 3104 = 22 %** | No `open_sides` concept |
| Floors whose footprint **fill ratio < 0.75** (irregular envelope) | **20 %**, median fill 0.85 | Non-rectangular building footprint |
| Designs with **3 floors** | 29 (plus 100 two-floor, 76 single) | Multi-floor emission already fixed |
| `north_arrow_direction` ≠ "up" | **86 / 365 = 24 %** ("right" 73, "down" 3) | Zone engine is 4-way discrete |
| `plot_dims_is_building_envelope = true` | 41 / 178 resolved | Plot-vs-envelope ambiguity is real |

### Carved-room concentration by style

Styles where the rectangle-only schema fails most often:

```
Mughal            43 %      European-Cottage  36 %
Chettinad         29 %      Tibetan-Buddhist  29 %
Assamese          28 %      Rajasthani-Haveli 28 %
Pahari            27 %      Contemporary      24 %
...
Goan               5 %  (lowest)
```

Irregular footprints cluster elsewhere — Mediterranean-Spanish (median fill 0.79),
Goan-18/first (0.44), Gujrati-03/ground (0.53). **No style is clean on both axes.**

### Room-type vocabulary gap

Labels that normalise to a `RoomType` **that does not exist**, with the number of
distinct styles they appear in:

| Needed type | Instances | Styles | Example source labels |
|---|---|---|---|
| `terrace` | **65** | 16 | `TERRACE`, `SEMI COVERED TERRACE`, `SEM COVERED TERRACE BELOW` |
| `garden` | **27** | 13 | `GARDEN`, `OUTDOOR GARDEN`, `LANDSCAPED GARDEN` |
| `seating` | **20** | 11 | `SEATING`, `OUTDOOR SEATING`, `CONVERSATION PIT` |
| `washbasin_nook` | 6 | 5 | `WASH BASIN`, `W.B.` |
| `verandah` | 3 + regional | 3 | `VERANDAH`, `OSARI` (Kerala), `OTLA` (Gujarati), `ATTOLE` (Bengali) |
| `open_to_sky` | 2 | 2 | `OPEN SKYLIGHT`, `OPEN TO SKY` |
| `duct` | 1 | 1 | `DUCT`, `SHAFT` |
| `pool` | 1 | 1 | `CENTRAL POOL`, `SWIMMING POOL` |

Plus a long tail of **39 unmapped singletons** and recurring compound labels that
need alias handling rather than new types: `C TOILET` / `A TOILET` / `ATTACH T` /
`AT TOILET` / `COM TOILET` (11+8+7+6+5 = attached vs common toilet — an
*attribute*, not a type), `FORMAL` vs `INFORMAL LIVING ROOM`, `DOUBLE HEIGHT
LIVING AREA`, `CIRCULATION SPACE`, `MIXED ROOM`, `TV HALL`, `LOUNGE`, `PATIO`,
`LAUNDRY`, `MUMTY`.

**`DOUBLE HEIGHT COURTYARD` / `DOUBLE HEIGHT LIVING AREA` / `COURT BELOW` /
`OVERLOOKING LANDSCAPE COURT BELOW`** are a distinct concept the schema has no
word for at all: a **void on floor N over a room on floor N−1**.

---

## 2. Visual findings (what the extracts cannot encode)

Read from `Kerala/Kerala-03/kerala03-ground-plan.webp`,
`Goan/Goan-18/goan18-first-plan.webp`,
`Rajasthani-Haveli/Rajasthani-Haveli-01/rajasthanihaveli01-ground-plan.webp`.

1. **Car porches carry no wall on any open side.** In all three plans the porch is
   a roof + paving + a drawn car, open to the driveway on 2–3 sides. Confirms
   limitation **K** empirically across styles, not just Assamese-07.
2. **Curved geometry exists.** Kerala-03's `OSARI` verandah has an arced front edge
   and the `OPEN SKYLIGHT` boundary is a curve. PlanForge is axis-aligned-rectangle
   only — this is unreachable without a polygon/arc schema. *Rare; document, don't
   chase.*
3. **Compound wall + landscaped setback are drawn.** Rajasthani-Haveli-01 has a
   solid boundary line around the full plot, grass texture filling the setback
   margin, `LANDSCAPED GARDEN` labelled in it, and trees at the corners. Confirms
   limitation **M**.
4. **Interior landscape courts are L-shaped**, wrapping around the dining
   (Rajasthani-Haveli-01's `LANDSCAPE COURT`) — a courtyard is not always a
   rectangle punched in the middle.
5. **Furniture and material textures are rendered** — beds, sofas, dining sets,
   kitchen fittings, cars, stair treads with `UP` arrows, wood/tile/grass/paving
   fills per room. PlanForge draws none of this. **This is the single largest
   visual difference** and it is pure presentation, independent of the solver.
6. **Stepped thresholds** at entry (`ENTRY` with drawn steps) — a minor symbol gap.

---

## 3. Merged capability list, with current status

Statuses cross-checked against `solver_limitations.md` and the merged PRs
(#73, #79, #81 at `57e8bc9`).

| # | Capability | Status |
|---|---|---|
| 1 | Multi-floor emission (basement→G→F1→F2) | ✅ Fixed (#6a) |
| 2 | Orientation-aware stairs + floor-aware labelling | ✅ Fixed (#1, #5) |
| 3 | Parking gets no spurious interior door | ✅ Fixed (#2, PR #81) |
| 4 | Wall ring follows room footprint incl. notches/voids | ✅ Fixed (#6c, `53cd29b`, `c4d6928`) |
| 5 | `foyer` / `courtyard` / `wardrobe` RoomTypes | ✅ Fixed (C) |
| **6** | **Open-sided rooms** (carport, verandah, balcony) | ✅ **Fixed (PR #82) — `Room.open_sides: frozenset[str]` supports multiple edges** |
| **7** | **Carved / nested rooms** (toilet inside bedroom) | ✅ **Fixed (PR #82) — `Room.parent_id` + cycle rejection** |
| **8** | **Richer RoomType vocabulary** + label aliasing | ✅ **Fixed (PR #82) — 7 open-programme `RoomType`s + `normalize_room_label()`; still 32 of 231 corpus labels vs the wider tail** |
| **9** | **Compound wall, gate, landscaped setback fill** | ✅ **Fixed — DXF path (Tasks 11–12), PDF mirror, unified into `FloorDrawing.site: SiteContext` (Task 32, PR #99)** |
| **10** | **Rotation-general, area-weighted Vastu zones** | ✅ **Fixed (Task 14) — continuous `north_angle_deg`, 40×40-lattice area-weighted zone membership** |
| **11** | **Graded (3-tier) Vastu rules** | ✅ **Fixed (Task 15) — `preferredZones`/`acceptableZones`/`avoidZones` + `VERDICT_FACTOR`** |
| **12** | **Vastu as a CP-SAT objective term, not a reject filter** | ✅ **Fixed (Tasks 16–17) — rank-don't-reject in `generator.py`; reified soft objective term in CP-SAT; hard-exclusion stays limited to toilet/wc_only/bathroom_master/staircase from C/NE per the safety constraint** |
| **13** | **Vastu on all floors** | ✅ **Fixed (Task 18) — loop extended off ground-floor-only, plus entrance tie-break** |
| 14 | Formal connectivity gate | ✅ Already fixed pre-uplift — `plan_geometry.validate_floor_connectivity()`, wired into `generator.py`'s navigability gate (see `solver_navigability_series` work, 2026-07-20) |
| 15 | Entrance placement for all-frontage-is-parking | ✅ **Fixed (Task 20) — SE-end preference for south-facing, NW-end for west-facing entrance fallback** |
| 16 | `plot_width`/`plot_length` naming footgun | ✅ **Fixed (Task 21) — renamed to `plot_x_extent`/`plot_y_extent` across ~110 files + persisted-schema migration** |
| 17 | Furniture + material-texture rendering | ✅ **Fixed (Task 33, PR #99) — DXF's 12-renderer dispatcher ported to `engine/furniture.py` as canonical `Fixture` entities on `FloorDrawing`; PDF and the frontend SVG overlay now consume the same source, closing the PDF gap and deleting the frontend's parallel copy** |
| 18 | Floor-N void over floor-N−1 room (double-height) | ✅ **Fixed (Task 10) — `void_over` cross-floor reference + render suppression** |
| 19 | Non-rectangular building footprint | ✅ **Landed as RECT + L only (Task 9's ruling) — T/U plot templates were rejected as infeasible; L-shaped plot envelope is rectilinear via Task 9's exact-subtraction region, exposed through the wizard (Task 22–25)** |
| 20 | Curved / arc geometry | ✅ **Fixed as scoped (Task 13) — render-only `Room.edge_arcs` annotation; solver still sees the straight chord** |

**Whole plan status (2026-08-24):** all 33 tasks across P1–P7 shipped on `main` via
18 PRs (#82–#99), merged 2026-08-23 (PR #99, "Phase 7.4 — canonical site context +
furniture on FloorDrawing"). Backend suite: 1,002 fast + 388 slow tests green;
frontend: 275 tests, `tsc`/Biome clean at merge time. This spec's §1 quantitative
gaps and §3 status table above are now historical — **superseded by whatever the
next capability-gap pass finds against the shipped schema**, not a live backlog.
The `2026-08-15-solver-capability-uplift.md` plan file (companion to this spec) is
correspondingly closed; see the completion banner at its head.

---

## 4. Vastu engine gap (from `~/projects/vastu-lens-ai`)

PlanForge's Vastu is **post-hoc and binary — it rejects, it never steers**:

- `generator.py:774-778` runs `check_vastu()` *after* a full layout exists, then
  `passed = len(violations) == 0` drops it. No nudging.
- `scorer.py:142-147` re-runs the same check as a 10 %-weight ranking of
  already-generated candidates.
- `vastu.py:88 _get_zone()` is **centroid-only** on a **4-way discrete grid** keyed
  to `road_side ∈ {N,S,E,W}` — 24 % of the corpus has a north arrow that isn't "up",
  and an SSE-facing plot is silently treated as due-S.
- `VASTU_RULES` (from `compliance_rules.json`'s `vastu_zones`) is binary
  `prohibit`/`avoid`. No partial credit, so no usable optimiser signal.
- Brahmasthan is only implicit via the `"C"` zone's prohibit list — no occupancy
  metric.
- `check_vastu()` iterates `layout.ground_floor.rooms` **only** — a first-floor
  master bedroom is never evaluated.

`vastu-lens-ai/src/lib/vastu/` solves the same 3×3 zone model properly:
`geometry.ts:97-135 zoneForPoint()` rotates by `-northAngle` around the plot
centroid (any compass angle); `zoneDistribution()` samples a 40×40 lattice for
**area-weighted** membership; `rules.ts` has three tiers
(`preferredZones`/`acceptableZones`/`avoidZones`) with a `VERDICT_FACTOR`
(1 / 0.7 / 0 / 0.45-neutral); `evaluate.ts computeScore()` produces a weighted
0–100 across `directional_compliance` / `room_functions` / `brahmasthan` /
`geometry` / `critical_issues`; `elements.ts` derives Pancha Bhoota balance from
the same findings for free.

**The architectural shift required is "scoring function" → "objective term."** The
missing piece is not Vastu knowledge — it is plumbing an existing numeric signal
*into* the CP-SAT objective instead of only using it to accept/reject finished
layouts.

**Safety constraint (load-bearing):** hard-constrain only `toilet`/`wc_only`/
`staircase` out of `C`/`NE`. Keep kitchen-SE and master-SW as **soft** objective
terms. Some plots cannot satisfy kitchen-SE ∧ master-SW ∧ pooja-NE simultaneously
for a given room count and plot shape; hard-constraining all preferences makes the
model infeasible for otherwise-valid plots.

---

## 5. Polygonal rooms — the representation decision

**Decided 2026-08-15 (Karthik): rectilinear rect-union.**

A `Room` gains `parts: list[Rect]` — 1–3 axis-aligned rectangles whose union is a
contiguous **rectilinear polygon** (L, T, U, notched). The plot's buildable
envelope becomes a rectilinear polygon by the same mechanism.

**Why this and not arbitrary polygons:** CP-SAT's `add_no_overlap_2d` operates on
*intervals* — i.e. rectangles. Arbitrary polygons would require pairwise
separating-axis constraints, which scale badly past ~12 rooms and would force a
rewrite of wall derivation, opening placement, and the scorer. A rectilinear
polygon is a union of rectangles, so running `no_overlap_2d` over **parts** rather
than **rooms** buys L/T/U shapes while preserving the entire existing solver,
scorer, and geometry stack.

**Coverage check against the corpus:** every low-fill floor sampled in §1
(Goan-18/first 0.44, Gujrati-03/ground 0.53, Mediterranean-Spanish-17/second 0.50)
is **rectilinear** — the irregularity is notches and wings, not diagonals. The only
non-rectilinear geometry found in the whole visual pass is Kerala-03's arced
`OSARI` and its curved skylight boundary. Arcs are therefore handled as a
**render-only edge annotation** (`Room.edge_arcs`), never as a solver constraint —
the solver sees the chord, the drawing shows the arc.

## 6. Style signatures — evidence, and a caution

Per-style prevalence of programme elements, as a % of that style's designs:

| Style | court | verandah | pooja | porch | terrace | balcony |
|---|---|---|---|---|---|---|
| Goan | **33** | 8 | 16 | 58 | 16 | 58 |
| Kerala | **30** | 10 | 10 | 50 | 30 | 10 |
| Colonial | **30** | 0 | 10 | **70** | 30 | **70** |
| Minimalist | 27 | 11 | 5 | 61 | 16 | 50 |
| Bengali | 23 | **23** | **23** | 38 | 30 | 38 |
| Chettinad | 18 | 9 | 18 | 36 | **45** | 27 |
| Pahari | 12 | 0 | 6 | **68** | 37 | 43 |
| Tibetan-Buddhist | 8 | 0 | 8 | 66 | 16 | 50 |
| **Corpus-wide** | **18** | **5** | **7** | **51** | **27** | **37** |

**Caution — this is a weaker signal than expected.** No style carries a courtyard
in even a third of its designs; verandah tops out at 23 % (Bengali). The 18
regional styles differ far more in **elevation and facade treatment** than in
floor-plan programme. Therefore:

- Style presets must seed **soft defaults the user can override**, presented as
  "typical for this style", never as hard programme constraints.
- Every preset checkbox ships with its corpus percentage in the helper text, so the
  UI is honest about how typical a feature actually is.
- Do **not** build a style classifier or score layouts against a style signature —
  the underlying signal does not support it.

## 7. Input model — how users specify these plans

**Decided 2026-08-15 (Karthik): extend the existing wizard form.** Canvas polygon
drawing, agent-chat extraction, and reference-plan upload are all deferred.

Six new inputs are required by the capabilities above:

| Input | Feeds | Why the form can carry it |
|---|---|---|
| Plot shape: rect / L / T + notch dims | rectilinear envelope | A picker + 2 numbers, not free drawing |
| North angle (0–359°, continuous) | Vastu zone engine | Dial or number input; `road_side` becomes derived |
| Style preset (18) | seeds programme defaults | Single select |
| Programme toggles: courtyard, verandah, pooja, terrace, study, open car porch | room programme | Checkboxes, pre-ticked by style preset |
| Open-sided rooms | `open_sides` | One toggle: "car porch open to driveway" (default on), mapping to a fixed edge per room type — see note below |
| Compound wall + gate side | site rendering | Checkbox + side select, defaults from `road_side` |

**Trapezoid removed from the plot-shape picker (2026-08-23):** §5 decided the solver
only accepts an axis-aligned rectilinear rect-union; a trapezoid has non-axis-aligned
edges the solver cannot represent, and capability 19 (non-rectangular footprint) is
still an open go/no-go. Re-add trapezoid to the picker only alongside a solver/
compliance/render decision for it, not before.

**Open-sided toggle is a simplified default, not per-edge input (2026-08-23):**
`Room.open_sides` is a `frozenset[str]` and already supports multiple open edges
(PR #82). The single wizard toggle deliberately narrows that to one deterministic
mapping — e.g. "car porch open to driveway" → the edge facing `road_side` — for the
common case; it does not expose the full per-edge set. Multi-edge verandah/balcony
configuration stays an editor-only capability until (if ever) the wizard grows a
per-edge control.

**Gate-side selector needs new plumbing, not just UI (2026-08-23):**
`draw_compound_wall()` currently keys the gated wall off `cfg.road_side`; only the
gate's position along that side (`gate_cx`) is configurable today. Shipping the
"Gate on [side]" selector in the wireframe requires adding an independent
`gate_side` field through persistence, the API schema, and `draw_compound_wall()`
before the selector can affect rendered output — track this alongside the Phase 6
input-model work rather than assuming the wireframe's selector is already wired.

### Wireframe — new wizard step, inserted after "Plot & Setbacks"

```
┌─ Step 2 of 5 · Site & Style ────────────────────────────────┐
│                                                              │
│  PLOT SHAPE                                                  │
│   (o) Rectangle   ( ) L-shaped   ( ) T-shaped               │
│                                                              │
│      ┌──────────┐   ┌─────┐        Notch width  [ 3.0 ] m    │
│      │          │   │     └───┐    Notch depth  [ 2.5 ] m    │
│      │          │   │         │    (enabled only for L / T)  │
│      └──────────┘   └─────────┘                              │
│                                                              │
│  ORIENTATION                        ╭───────╮                │
│   North angle  [  0 ]°  ← clockwise │   ▲ N │  road side is  │
│   from plot front to true north     │   │   │  derived: S    │
│                                     ╰───────╯                │
│   [x] Enable Vastu guidance                                  │
│                                                              │
│  STYLE PRESET                                                │
│   [ Kerala          ▾ ]   seeds the programme below          │
│                                                              │
│  PROGRAMME            (% = how often this style has it)      │
│   [x] Central courtyard ....... typical for Kerala (30%)     │
│   [ ] Verandah / osari ........ uncommon (10%)               │
│   [x] Car porch open to drive . typical (50%)                │
│   [ ] Pooja room .............. uncommon (10%)               │
│   [x] Roof terrace ............ typical (30%)                │
│   [ ] Study / library ......... rare (0%)                    │
│                                                              │
│  SITE                                                        │
│   [x] Draw compound wall   Gate on [ Front (S) ▾ ]           │
│   [x] Fill setbacks as landscaped area                       │
│                                                              │
│                              [ Back ]  [ Continue → ]        │
└──────────────────────────────────────────────────────────────┘
```

Behaviour: changing **Style preset** re-ticks the programme boxes and rewrites the
helper percentages, but never locks them — a user who unticks "Central courtyard"
on Kerala keeps that choice. Selecting **Rectangle** disables the notch fields.
**North angle** replaces `road_side` as the source of truth; `road_side` is
computed from it and shown read-only so existing users still recognise it.

**`north_angle` plumbing (2026-08-23):** as of this document's original writing, no
`north_angle` field exists anywhere in the persisted config, API schema, or
`check_vastu()` — only the derived cardinal `road_side` is consumed. Wiring the
dial above end-to-end requires: persisting `north_angle` through the project
config and API, deriving/rounding `road_side` from it for existing cardinal-only
consumers, and updating `vastu.py`, CAD/PDF rendering, and export paths to use the
continuous angle wherever direction actually matters (not just the derived
cardinal). This is Phase 4/6 scope, not something Phase 1 needs to deliver.

## 8. Scope decisions

**In scope** for `docs/superpowers/plans/2026-08-15-solver-capability-uplift.md`:
capabilities **6–16 and 18–20** — i.e. everything in the §3 table except item 17.

**Excluded (Karthik, 2026-08-15):** item **17, furniture + material-texture
rendering**. Largest visual gap versus the references, but purely presentational
and independent of every other item; deserves its own plan.

**Handled as render-only, not solver:** item **20, curved geometry** — an optional
arc annotation per room edge. The solver and all constraints see the straight
chord.

**Accepted limits, documented only:** `solver_limitations.md` items A (now largely
superseded by §5's rect-union), B, D, E.
