# drafted.ai Competitive Research + Solver Dataset Sourcing (2026-07-15)

Session summary: competitive research on drafted.ai, exploration of options for
improving PlanForge's deterministic solver with real Indian housing data, and
one concrete engine change shipped as a result.

---

## Part 1 — drafted.ai research

**What it is**: YC-backed US startup (founder Nick Donahue, second attempt after
an earlier venture "Atmos"). Consumer/prosumer AI home-design tool — structured
inputs (room list, sqft, lot size, footprint shape) plus an interactive canvas
(drag-and-drop rooms, draw arbitrary footprint, live 3D model updates in-browser).
Generates multiple 2D+3D options in 5-60s; exports PDF/DXF/IFC/GLB.

**Tech**: Custom-trained *image-based generative models* (not a general-purpose
LLM or diffusion text-to-image model), trained specifically on real house plans
that were actually built and passed permitting. Claimed ~65x cheaper per
generation (~0.2¢) than routing through a general-purpose model (~13¢) — the
moat is the curated, permit-validated training corpus, not the algorithm.

**Open source**: No. Confirmed closed/proprietary across every source checked
(official site, founder interview, Product Hunt, YC profile) — no GitHub repo,
license, SDK, or API docs exist. Nothing to explore architecturally.

**Traction/funding**: 120k+ users, 325k+ designs/month at seed announcement;
$16-17.5M seed led by Buckley Ventures (YC, Patrick Collison, Jack Altman, Ben
Silbermann, Samsung NEXT participating). Users: ~50% homeowners, ~15% builders,
~10-15% architects/drafters, ~10% developers/agents/designers. Reported pricing
~$1,000-2,000/complete plan.

**Comparison vs. PlanForge + StructAgent**:

| Dimension | drafted.ai | PlanForge |
|---|---|---|
| Geometry generation | Learned generative model | Deterministic: 3 archetypes + OR-Tools CP-SAT |
| Compliance | None disclosed — "reference point," not permit-ready | NBC-based hard constraints |
| Structural | None | StructAgent: IS-code structural design |
| Plot shapes | Freeform footprint | Rectangular (MVP) + quadrilateral |
| Geography | US, no jurisdiction modeling | India-specific (NBC, IS codes) |
| Editing | Canvas-first, drag-and-drop, live 3D | Agent-chat + canvas, re-solve on edit |

**Similarities**: both generate multiple options from structured input; both
pair generation with downstream CAD/BIM export; both increasingly pair
generation with an editable canvas rather than one-shot output.

**Real differentiation**: compliance automation is PlanForge's moat, not
drafted's (a US competitor, Blueprints AI, exists specifically to fill that gap
— validating it's a real, monetizable wedge). Deterministic/explainable (CP-SAT)
vs. learned/opaque (generative model) matters a lot when a builder needs to
defend a design to a municipal approval authority. Different geographies/building
systems entirely — not really head-to-head competitors today.

**What PlanForge could borrow**: live-canvas-first direct manipulation as the
primary interaction (agent-chat as secondary/power-user path, since LLM
round-trip + re-solve adds latency drafted's live-3D canvas doesn't have);
explicit fidelity-tier framing (what's compliance-checked vs. still needing a
licensed engineer's sign-off, especially with partial StructAgent coverage);
the cost-engineering lesson (train a narrow model on domain data instead of
routing through a general LLM/diffusion model, if ML-based generation is ever
explored per the "smarter layout engine" roadmap item).

---

## Part 2 — Dataset sourcing for solver improvement

Follow-up question: how to improve the deterministic solver (not train an ML
model — refine archetype/compliance logic) using real Indian housing data.

### Options considered

1. **Self-generated synthetic data** (bootstrap from own CP-SAT solver +
   `scorer.py` as reward function) — cheapest, cleanest, but doesn't capture
   real-world layout conventions beyond what archetypes already encode.
2. **Public/government sources** (PMAY, CPWD, NBC worked examples, DDA) — chosen
   starting point; requirements-mining rather than ML training given low volume.
3. **Academic/institutional partnerships** (SPA/NIT/CEPT architecture schools,
   IIA, CREDAI) — deferred, needs relationship-building, not a quick lookup.
4. **Public academic floor-plan datasets** (RPLAN, CubiCasa5k) — non-Indian,
   useful only for pretraining a geometric backbone, not attempted this session.
5. **Scraping real estate portals** (MagicBricks, 99acres, Housing.com) —
   rejected outright: ToS violations, unclear copyright ownership (sits with the
   builder/architect, not the portal), poor data quality (raster, watermarked,
   no vector data), and reputational risk for a product selling on
   compliance-trustworthiness.

User picked Option 2, then narrowed scope: **RCC-framed, brick-walled
construction only** — ruling out bamboo/mud-block/stone/CSEB vernacular systems.

### Sources tried, in order

**PAHAL / PMAY-Gramin "Compendium of Rural Housing Typologies"**
(`cbri.res.in/wp-content/uploads/2020/11/pahal.pdf`, MoHUA + UNDP + IIT Delhi +
CBRI, 10 states, 130 zone-specific designs). Downloaded and opened multiple
state/zone pages (Assam, Odisha, Rajasthan) — genuinely dimensioned floor plans,
sections, cost estimates, publicly licensed for beneficiary reuse. **Rejected**:
the compendium's own stated brief is to develop alternatives "less costly...
than brick, cement, and steel intensive systems" — every design opened used
bamboo, CSEB, stone masonry, or mud block, never RCC frame + brick. Wrong
construction system by founding intent, not incidentally.

**CPWD "Compendium for Design of Central Government Housing"**
(`cpwd.gov.in/Publication/Compendium_for_Design_of_Central_Government_Housing.pdf`).
Downloaded (215 pages) and read the full table of contents. **Rejected on two
grounds**: (1) zero floor plan drawings anywhere in the document — all 6
chapters are area-norm tables, bye-law extracts, and NBC/fire-safety extracts,
not a plan catalogue despite the title; (2) marked "For internal circulation
only," © 2012 CPWD, no reproduction without permission — restricted-distribution
government document, not licensed for reuse regardless of content.

**UPAVP (UP Awas Vikas Parishad / UP Housing & Development Board) "Designs for
EWS Houses"** (`upavp.in/article/en/designs-for-ews-houses`) — **accepted**.
Direct access from this environment was blocked (connection refused to
`upavp.in`), worked around via the Wayback Machine (`web.archive.org`), which
mirrors both the listing page and several of the individual drawing PDFs. Pulled
5 complete drawing sets:

- `15-25-1a` and `15-25-ALT3` (15'x25' / 25 sqm plot, G+1 EWS house)
- `18-40-ALT1`, `18-40-ALT2`, `18-40-ALT3` (18'x40' / 40.7 sqm plot, G+1)

Each is a full professional architectural set: ground/first floor plans,
sections, front elevation, terrace plan, site plan, schedule of openings, area
statement — drafted by UPAVP's Architecture & Planning Section, Lucknow
(2005-06). Standard-design plans meant for beneficiaries to build from
(lower provenance risk than the CPWD document, though still the board's IP —
used here for pattern-extraction, not reproduction).

### Patterns extracted from the UPAVP drawings

1. Stair dimensions consistently 750-813mm width, 250mm tread, 181-190mm riser
   across all 5 plans.
2. Kitchen + bath + toilet consistently clustered on one contiguous wall run
   (plumbing-stack efficiency) in every single drawing.
3. An internal courtyard/light-well appears on the deeper (18x40) plots but
   never on the shallow (15x25) ones — a plot-depth-triggered pattern.
4. Rooms are consistently narrow-and-deep (~2.4-2.9m wide x 2.7-4.6m deep, max
   observed ratio 1.83:1), matching narrow-frontage Indian urban plot geometry.
5. `18-40-ALT2` and `18-40-ALT3` have ground and first floor as two
   **independent, identical dwelling units** (one family per floor — a
   government density-doubling pattern), not a single-family G+1 house.
   **Explicitly excluded from any engine change** — this doesn't match
   PlanForge's single-family, internally-connected G+1 model and would be
   actively wrong to encode.

---

## Part 3 — What was implemented vs. deferred vs. left alone

### Implemented
**Wet-zone adjacency scoring** — added `kitchen<->toilet` (8 pts) and
`kitchen<->wc_only` (6 pts) to `backend/app/config/adjacency_pairs.json`. Because
solver and scorer already share this one config table (prior "D1" architecture
fix), this single change affects both the CP-SAT objective and the layout
scorer with no code duplication. Shipped test-first: `test_score_adjacency_kitchen_toilet_wetzone`
in `backend/tests/test_scorer.py` (written red, confirmed failing, then made to
pass). Full `test_scorer.py` + `test_adjacency_config.py` + `test_solver.py`
verified green after the change (18 tests passing).

### Verified, no change needed
**Room aspect ratio** (`_score_aspect_ratio` in `scorer.py`, 2:1 cap) — checked
all real room dimensions from the 5 UPAVP drawings; max observed ratio 1.83:1,
comfortably inside the existing threshold. Current rule already matches
real-world practice.

### Verified, deliberately NOT changed
**`min_stair_width_mm: 900`** in `compliance_rules.json` — the UPAVP drawings'
750-813mm stair widths look like a rule-tuning candidate at first glance, but a
follow-up NBC search confirmed the one/two-family dwelling relaxation only
covers tread (250mm) and riser (190mm) — both already correctly set in the
config — not width. No NBC provision permits under-900mm width for single-family
houses; the built precedent reflects 2005-06 UP state bye-laws, not current
national code. Loosening this on precedent alone would have weakened a
life-safety rule without a valid citation, so it was left as-is.

### Deferred (needs its own design pass, not a quick edit)
**Courtyard/light-well for deep narrow plots** — would require a new `RoomType`,
new CP-SAT placement constraints (open-to-sky, anchored to the wet zone), new
compliance rules, and PDF/DXF rendering support for a void space. This is a
genuinely new archetype feature, not a config tweak — per the project's
"stay with archetypes in MVP, avoid overengineering" guardrail, this should go
through brainstorming/planning as its own piece of work rather than being
bolted on ad hoc.
