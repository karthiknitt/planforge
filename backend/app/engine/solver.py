"""CP-SAT constraint solver for PlanForge layout generation.

Replaces the purely deterministic archetype slicer with an optimisation-based
approach. All spatial values use millimetre integers (SCALE = 1000) because
OR-Tools CP-SAT only handles integer domains.

Three diverse layouts are produced by forcing the staircase position to
different thirds of the buildable area on each solver run (symmetry breaking).

Falls back gracefully — caller should catch all exceptions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from math import ceil, cos, gcd, lcm, radians, sin
from pathlib import Path
from typing import Callable, NamedTuple

from ortools.sat.python import cp_model

from .corpus_priors import (
    get_adjacency_prior,
    get_position_prior,
    get_shape_usage_prior,
    get_size_prior,
)
from .models import Column, FloorPlan, Layout, PlotConfig, Room
from .shapes import SHAPE_TEMPLATES, ShapeTemplate, parts_for
from .vastu import ZONE_GRID_ROAD_S, _rule_for, _verdict, resolve_north_angle
from app.engine.adjacency import load_adjacency_pairs

SCALE = 1000  # 1 metre = 1000 mm units
SOLVE_TIME_S = 70.0  # per-solve wall-clock budget (generation runs async)
# Wall cap for the penalty-free phase-1 warm start: it only needs A feasible
# solution to hint phase 2, not a good one, so it doesn't get the full
# SOLVE_TIME_S (which would let one zone double to ~28 s worst case).
#
# Both budgets were widened from 8.0/3.0 (2026-07-19, Task 5a): the wall
# clock cap is meant to be a pure safety net for pathologically slow
# machines — max_deterministic_time=1.5/0.7 is the value that's supposed to
# bind on any normal machine, which is what makes repeated solves return the
# SAME incumbent. Measured directly (debug instrumentation on this task):
# under ordinary CPU contention (a handful of concurrent local processes),
# a single zone's 1.5 deterministic-time-unit solve took 6.7-8.0+ real
# seconds, i.e. the OLD 8.0 s cap was already binding before the
# deterministic budget finished — non-deterministically truncating the
# incumbent depending on machine load. Because generate() ranks solver AND
# archetype layouts together and relabels the top 3 "A"/"B"/"C" purely by
# rank, a truncated solver layout can land in any of those slots and
# intermittently fail downstream geometry invariants (e.g.
# test_cross_floor_columns_stack) that assume a fully-worked incumbent.
# Widening the caps doesn't make the search itself faster, it just gives
# the deterministic budget more real-world headroom to actually be the
# thing that binds, which is what restores reproducibility.
#
# Widened AGAIN 2026-08-19 (14.0/5.0 -> 70.0/25.0), and this time the sizing is
# measured rather than doubled-and-hoped. Wrapping CpSolver.solve to time every
# call on the 18.3 x 12.2 m G+1 config, with the wall caps lifted to 600 s so
# only the deterministic budget bound:
#
#   phase1 (det=0.7, cap was  5.0s): n=3  max= 5.92s  median= 4.82s  over-cap 1/3
#   phase2 (det=1.5, cap was 14.0s): n=3  max=16.58s  median=15.37s  over-cap 2/3
#
# That was at load average 3.75 — a QUIET box. Phase 2's *median* solve already
# exceeded its cap, so the wall clock was the binding constraint in the normal
# case, not a pathological one, and the deterministic budget almost never got to
# do its job. Measured consequence, 8 runs at the old caps vs 2 with them lifted:
# four of the eight returned ONE layout instead of three, with three DIFFERENT
# geometry fingerprints between them, while every lifted-cap run produced the
# same three layouts bit-for-bit. Users were being handed one plan instead of a
# choice of three, roughly half the time, with no error.
#
# The new values give ~4x headroom over the measured quiet-box need. The
# phase1:phase2 ratio is unchanged because the measurement vindicated it:
# 5.92/16.58 = 0.36, and the old caps were 5/14 = 0.36. The proportion was
# right; only the magnitude was wrong.
#
# Cost: on a box so slow the deterministic budget genuinely cannot finish, one
# generate() can now spend 3*25 + 3*70 = 285 s of wall clock instead of 57 s.
# That is acceptable because generation is an async Inngest job, and because the
# cap only binds in exactly the regime where the old behaviour returned wrong
# output rather than slow output.
#
# Validated separately from the 2 timing/diagnostic runs above: 5/5 full
# generate() runs at the new 70.0/25.0 caps returned the same 3-layout,
# bit-for-bit-identical fingerprint (vs the 4/8-degraded baseline at the old
# caps quoted above) — see this PR's test plan.
PHASE1_TIME_S = 25.0
# Deterministic (machine-independent) work budgets — see the comment above
# PHASE1_TIME_S. These are the values meant to actually bind; module-level so
# a test that needs the search to fully escape a penalty zone can raise them
# without needing a proportionally larger wall-clock cap too.
PHASE1_DET_BUDGET = 0.7
PHASE2_DET_BUDGET = 1.5
MAX_DIM_MM = 50_000  # safety cap: 50 m per dimension

# Wall-coalignment bonus (objective units = mm) per exactly-aligned edge
# pair. Must beat the per-mm size term (so the solver gives up room growth
# to land partitions on shared grid lines) and typical adjacency-distance
# trades — popular grid lines earn quadratically (C(n,2) pairs), which is
# exactly the pressure that consolidates walls onto few lines.
ALIGN_BONUS = 2500
# Cross-floor pairs used to share ALIGN_BONUS with same-floor pairs — the
# wrong weighting on the merits, since a same-floor near-miss just costs an
# untidy mid-span T column while an unstacked upper-floor column is a
# structural defect (floating column). Swept 7500/25000/60000/150000 on the
# grid-alignment test's own config: 60000 is the measured peak (worst solver
# layout 0.55 -> 0.67 stacked); 150000 over-weights and regresses to 0.55.
# Must be applied together with the stair/circulation snap protection (see
# `_stair_circulation_protect_ids`) — at this weight the solver's incumbent
# shifts enough that unprotected post-solve snapping could otherwise break
# the stair-door-access guarantee (issue #50).
CROSS_FLOOR_ALIGN_BONUS = 60_000
# Post-solve wall-line snapping reach. Facing edge pairs (the two faces of
# one wall) are detected and moved rigidly as a unit, so a large tolerance
# can never collapse a wall gap — it only merges genuinely distinct wall
# LINES, i.e. exactly the near-miss offsets that split the column grid.
SNAP_TOL_M = 0.45
_IWT_M = 0.115  # internal wall thickness (mirrors plan_geometry.IWT)
_IWT_MM = 115

# Wet rooms are excluded from the size-growth objective: they should settle
# at min-compliant size, not balloon toward spec max (mirrors
# plan_geometry._WET_TYPES, including "utility").
_WET_TYPES = {"toilet", "wc_only", "bathroom_master", "utility"}

# En-suite ↔ bedroom shared wall must fit a door (900 mm min clear width).
_ENSUITE_MIN_OVERLAP_MM = 900
# The stair core must share this much wall with a circulation room: a 900 mm
# door leaf plus its two 115 mm jambs, i.e. exactly plan_geometry's per-wall
# door-fit test (`adj.hi - adj.lo < width + 2 * _JAMB`). Without it the solver
# is free to box the stair in behind a toilet — observed in production, where
# a 0.90 m wide stair's only partition long enough for a door was a WC, so
# derive_openings had no legal wall left and put the toilet door on the
# landing. No door-placement rule can repair that: ban the toilet wall and the
# staircase is simply left with no door at all.
_STAIR_DOOR_MIN_OVERLAP_MM = 900 + 2 * 115
# NOTE: plan_geometry.py's _CIRCULATION_TYPES also carries foyer/courtyard — intentionally NOT mirrored here; the solver never emits those types.
_CIRCULATION_TYPES = {"passage", "living", "dining"}
# Repulsion guard bands: the solver otherwise games hard thresholds (parks a
# toilet 1 mm past the wall gap) and post-solve snapping (±SNAP_TOL_M) can
# close a raw clearance into real contact. Penalise anything within a
# 600 mm moat with >= 100 mm of facing overlap, so the snapped result can
# never end up genuinely wall-sharing.
_REPULSION_GAP_MM = 600
_MIN_SHARE_OVERLAP_MM = 100

# In-model area cap for wet rooms, aligned with generator._WET_CAP_SQM (4.6):
# anything larger would be split into toilet+passage post-solve anyway.
_WET_AREA_CAP_MM2 = 4_600_000

# Soft toilet-placement penalties (objective units). Must dominate not just
# ALIGN_BONUS (2500) but realistic adjacency-distance trades: bedroom↔toilet
# is 12 pts on DOUBLED centre distance (~24 units/mm), so relocating a
# toilet ~1-2 m costs 24k-48k — penalties below that get ignored. Soft so
# tight plots stay feasible (a boolean penalty can never go infeasible).
TOILET_FRONT_PENALTY = 150_000
TOILET_FRONT_MID_PENALTY = 100_000  # extra when centre-x faces the gate axis
# Stair/parking repulsion needs to be large enough to pull the search out of
# the packed-next-to-stair basin even when the incumbent is only FEASIBLE
# (measured: at 60k the mid-zone solve kept both toilets on the stair wall).
TOILET_STAIR_PENALTY = 200_000
TOILET_PARKING_PENALTY = 200_000
# Per-mm shrink pressure on wet rooms. Must beat BOTH the alignment bonus a
# stretch can buy (2500 per edge) and the adjacency centre-pull: growing a
# toilet toward its bedroom/kitchen partner moves its centre at half the
# growth rate against ~24 units/mm pair weights (~12-20/mm effective gain,
# measured ballooning at weight 8). 30/mm makes growth strictly unprofitable
# so wet rooms settle at their min-compliant size.
WET_SHRINK_WEIGHT = 30
# Parking road-facing penalty must dominate size/align terms — same order of
# magnitude as the toilet penalties above, since it fights the same packing
# pressure.
PARKING_ROAD_PENALTY = 250_000

_PARKING_TYPES = {"parking", "parking_4w", "parking_2w"}

# ── Vastu placement steering ─────────────────────────────────────────────────
# Cost (objective units) of putting a room in a zone its rule marks `avoid`;
# lesser tiers pay `VASTU_WEIGHT * (1 - verdict)`, i.e. 0 for `preferred`,
# 0.30x for `acceptable`, 0.55x for a zone the rule is silent about.
#
# Scale: the objective is a MINIMISATION whose live terms are the
# points-weighted adjacency pull (up to 12 pts on a DOUBLED centre distance,
# so ~24 units per mm — moving a room 1 m trades ~24k, and a whole plan's
# pairs sum into the millions), the size terms (~1 per mm, ~85k total),
# ALIGN_BONUS (2500 per aligned edge pair) and the toilet/parking placement
# penalties (150k-250k per offending toilet).
#
# Measured, not guessed. 12 configs (4 road sides, 2 off-axis north angles,
# tight/big/square/wide plots, 2-5 bedrooms), each solved with Vastu off as
# the baseline and on at each weight, scored by the mean centroid verdict
# (what this term actually optimises) and by `vastu_layout_score`:
#
#     weight      centroid mean   area-weighted mean   wins/losses vs off
#     off             46.61              49.54               —
#      40k            ~ same             worse              3 / 5
#     120k            ~ same             ~ same             4 / 4
#     200k            54.87              49.83              7 / 4
#     300k            60.34              54.46             11 / 1
#     800k            no further gain, area-weighted mean regressed
#
# Below ~200k the term is inert: it is a per-room cost competing with an
# objective whose adjacency mass is in the millions, so the solver spends its
# budget elsewhere and Vastu placement is indistinguishable from chance.
# Above ~300k it stops buying anything and starts costing the other terms.
#
# It reads as larger than TOILET_FRONT_PENALTY (150k), but it is not the same
# unit: that is a penalty on ONE boolean for ONE offending toilet, this is a
# per-room cost spread over every ruled room. The two also mostly point the
# same way — a toilet's remaining soft `avoid` zones after the hard exclusions
# are SE/SW/N, which on the common road_side="S" plot IS the front band the
# toilet penalty is already pushing it out of.
VASTU_WEIGHT = 300_000

# ── Corpus-mined size priors (opt-in via cfg.corpus_priors_enabled) ──────────
# The mined corpus is imperial: 1 sqft = 0.09290304 m² = 92903.04 mm².
_SQFT_TO_MM2 = 92903.04
# Resolution the size deviation is quantised to, in units per standard
# deviation — 100 means 0.01 sigma. See `_add_size_prior_terms` for why the
# inverse-std weighting has to live in this divisor rather than in the
# objective coefficient.
SIZE_PRIOR_UNITS_PER_STD = 100
# Cost of one 0.01-sigma unit, so a full 1-sigma miss costs 10 000: above
# ALIGN_BONUS (2 500), well below VASTU_WEIGHT (300 000) and the placement
# penalties. But the term it actually competes with for control of a room's
# size is `size_terms`' growth reward of 1 per mm, not those placement terms
# -- and at this weight the size prior wins that contest by roughly 12-16x
# (marginal cost ~0.005-0.007 per mm^2 vs. the reward's 1 per mm on a ~3 m
# room dimension), so with the flag on it is the dominant sizing force, not
# a mere nudge. Task 13 tunes this against the GCS regression baseline; rough
# parity with the growth reward sits closer to SIZE_PRIOR_WEIGHT ~= 10.
SIZE_PRIOR_WEIGHT = 100
# Reward for a room pair the corpus finds typical actually sharing a wall,
# scaled by that pair's observed frequency (so 1.0 pays the full weight).
#
# Scale: the nearest neighbours are the coalignment bonuses, but neither is
# the term this one competes with. ALIGN_BONUS (2 500) rewards two rooms
# agreeing on a grid LINE and CROSS_FLOOR_ALIGN_BONUS (60 000) rewards a
# column stacking — both are orthogonal to contact, and a shared wall with
# the usual 115 mm cavity earns neither. What this term actually has to
# outbid is the centre-distance pull `dist_terms` already exerts on a room's
# other partners (~24 units/mm at 12 pts). At 5 000 the bonus buys roughly a
# 200 mm reposition against one such partner: enough to close a near-miss
# cavity into real contact, an order of magnitude short of the ~24 000 it
# would take to drag a room across the plan, and far below the toilet and
# parking placement penalties (150 000–250 000) it must never overturn.
# Task 13 tunes this against the GCS regression baseline — not here.
ADJACENCY_PRIOR_WEIGHT = 5_000
# Reward for a room landing in a zone its style's corpus histogram favours,
# scaled by that zone's observed frequency (so 1.0 pays the full weight).
#
# Scale: this term is gated on the SAME cols/rows bools `_vastu_zone_cost` is
# gated on, so for the half of corpus-known room types that have a Vastu rule
# the two are not neighbours, they are rival bids on one decision. That makes
# VASTU_WEIGHT the yardstick — but not VASTU_WEIGHT itself. What must never
# happen is the corpus REORDERING two Vastu tiers, and the tiers are only
# 0 / 90 000 / 165 000 / 300 000 apart (VERDICT_* x VASTU_WEIGHT), so the
# binding number is the narrowest gap between them, 75 000. The largest swing
# this term can produce for ONE ROOM between two cells is one full weight, so
# below 75 000 no single room's Vastu ranking can be reordered by this term
# alone. This is a per-room bound, not a global one -- several rooms' rewards
# can jointly exceed 75 000 (e.g. ~79k across a Kerala 2BHK's C-favoured
# rooms), it just isn't realizable here since those rooms can't all occupy
# one cell without overlapping.
#
# The floor comes from the OTHER half — courtyard, verandah, foyer, terrace
# and friends have no Vastu rule at all, so there the only rival positional
# force is `dist_terms` (2 x pts per mm, i.e. 12-30 units/mm). 25 000 buys
# roughly 0.8-2 m of repositioning against one adjacency partner: enough to
# settle a room already near a band boundary into the favoured cell, nowhere
# near the ~3-5 m a zone is wide on a typical plot. It also sits 6-10x below
# the toilet and parking placement penalties (150 000-250 000).
# Task 13 tunes this against the GCS regression baseline — not here.
POSITION_PRIOR_WEIGHT = 25_000

# Zones that may carry a HARD exclusion at all (spec: Safety / Global
# Constraints). Everything outside this pair stays soft on every room type.
VASTU_HARD_EXCLUDE_ZONES = frozenset({"NE", "C"})
# Room types eligible for a hard exclusion. The zones themselves are NOT
# listed here — they are read from each type's `avoid` tier in
# `vastu_room_rules` (see `_vastu_hard_excluded_zones`), so a hard constraint
# can never contradict the data the scorer reads.
#
# `staircase` is deliberately absent even though the plan's draft listed it:
# its rule is {"preferred": ["NE"], "acceptable": [], "avoid": []}, so NE is
# its ONLY opinionated zone and it is a preference, not an avoidance. Hard-
# excluding it would have the constraint fight the objective term on every
# solve and cap every staircase at the neutral verdict. If a staircase in the
# NE is wrong Vastu, that is an edit to `vastu_zones` re-derived through the
# transpose, not a solver constraint that silently disagrees with the rules.
VASTU_HARD_EXCLUDE_TYPES = frozenset({"toilet", "wc_only", "bathroom_master"})
# Fixed-point scale for cos/sin in the zone half-planes. Exact (no rounding
# at all) at every multiple of 90 degrees, which is where band ties actually
# land on real plots.
_VASTU_TRIG_SCALE = 1_000_000

# ── Shape templates (opt-in via cfg.allow_shape_templates) ────────────────────
# Which room types may be given a non-RECT footprint, and which template.
# Deliberately narrow: an L-shaped bedroom or toilet has nowhere to put a bed
# or a WC, whereas a social/circulation room folding around a neighbour is the
# common non-rectangular room in the reverse_engr corpus. Anything not listed
# here stays RECT even with the flag on.
_TEMPLATE_TYPES: dict[str, ShapeTemplate] = {
    "living": "L",
    "dining": "L",
    "passage": "L",
}
# Fraction of the bounding box kept by the narrow leg (shapes.parts_for).
_TEMPLATE_RATIO = 0.6
# Denominator of the fixed part offsets. Each part's origin/size is
# `u / _FRACTION_SCALE` of the room's bbox, so it stays an affine expression
# over the room's EXISTING x/y/w/d decision vars — the model gains intervals,
# not degrees of freedom.
_FRACTION_SCALE = 1000


def _shape_usage_allows_template(cfg: PlotConfig, room_id: str, room_type: str) -> bool:
    """Should this room be templated, given the corpus's non-rectangularity rate?

    SHAPE USAGE IS NOT A DECISION VARIABLE.

    The other three corpus priors (Tasks 8-10) are `_add_*_prior_terms`
    builders returning `(cost, IntVar)` pairs, because size, adjacency and
    position are all things CP-SAT decides. Template choice is not. It is
    resolved in plain Python at the `_fit_template` call in `_solve_one`,
    before the model exists: a room is templated iff `allow_shape_templates`
    is on AND its type is in `_TEMPLATE_TYPES` AND the templated bounds fit.
    There is no `is_rect` BoolVar anywhere in the model to attach an objective
    term to, and `_TEMPLATE_RATIO` is a module constant that `_fit_template`
    passes through untouched -- so there is no free geometry to steer either.
    Building one would mean constructing both a RECT and a templated variant
    of every eligible room behind a reified choice, doubling that room's
    variables and constraints to express a preference the corpus data does
    not need expressed that precisely (see the rates below).

    So the prior is applied where the decision actually happens: here, as a
    pre-model gate on the SAME Python expression that already decides
    eligibility. It only ever turns templating OFF for a room the old code
    would have templated -- it can never template an ineligible type.

    Why this is the useful direction. In `corpus_priors.json` the three
    templatable types sit at or near zero almost everywhere: `living` is 0.0
    in 9 of the 16 styles and never exceeds 0.2 (Tibetan-Buddhist), `dining`
    is 0.0 in 15 of 16 (highest 0.2, Rajasthani-Haveli), and `passage` is
    recorded in only 4 styles at all.
    The pre-change code templated those rooms 100% of the time whenever the
    flag was on. That gap -- always vs almost never -- is precisely the
    "nothing in the model cared" finding that parked uplift Task 9's ruling
    and left `allow_shape_templates` default-off. Matching the corpus rate is
    what makes the flag defensible to turn on; Task 13 owns that call.

    Determinism. `hashlib.sha256` over stable per-request strings, never
    `random` (`app/` contains no RNG at all) and never `hash()` (salted per
    process). Identical inputs always produce the identical verdict, so
    `solve_layout` stays as reproducible as it was. The seed carries the plot
    as well as the room because a plan holds at most one `living`: seeding on
    room id alone would freeze one verdict per style forever and the rate
    would never materialise across a user's plans.
    """
    p_nonrect = get_shape_usage_prior(cfg, room_type)
    if p_nonrect <= 0.0:
        return False
    if p_nonrect >= 1.0:
        return True
    seed = "|".join(
        (
            str(cfg.style_preset),
            f"{cfg.plot_x_extent:.3f}",
            f"{cfg.plot_y_extent:.3f}",
            str(cfg.num_bedrooms),
            room_id,
            room_type,
        )
    )
    digest = hashlib.sha256(seed.encode()).digest()
    draw = int.from_bytes(digest[:8], "big") / float(1 << 64)
    return draw < p_nonrect


_SPECS_PATH = Path(__file__).parent.parent / "config" / "room_specs.json"


def _load_specs() -> dict:
    return json.loads(_SPECS_PATH.read_text())


# ── Adjacency preference pairs ────────────────────────────────────────────────

_ADJACENCY_PAIRS: list[tuple[str, str, int]] = [
    (a, b, int(pts)) for a, b, pts in load_adjacency_pairs()
]


@dataclass
class _RoomVar:
    """All CP-SAT variables for one room on one floor."""

    room_id: str
    room_type: str
    room_name: str
    floor: int
    x: cp_model.IntVar
    y: cp_model.IntVar
    w: cp_model.IntVar
    d: cp_model.IntVar
    xe: cp_model.IntVar  # x + w (explicit end var, OR-Tools 9.x affine rule)
    ye: cp_model.IntVar  # y + d
    template: ShapeTemplate
    shape_ratio: float
    # Plot-relative wall-less edges carried from the room definition (the open
    # car porch is the only producer today). Empty for every other room.
    open_sides: frozenset[str] = field(default_factory=frozenset)


class _PartVars(NamedTuple):
    """The CP-SAT vars of ONE occupied rectangle of a room.

    A RECT room contributes exactly one of these, holding the room's own
    x/y/w/d vars; an L/T/U room contributes one per part. `_solve_one` keeps
    the full list (`part_vars`) so later passes can constrain the rectangles a
    room actually occupies rather than its bounding box — e.g. forbidding the
    notch region of an L-shaped PLOT, where a bbox test would either leak a
    part into the notch or reject a room that only overhangs it with a hole.

    `room_id`/`room_type` identify the owning room, so such a pass can EXEMPT
    rooms rather than apply itself blindly — parking above all: PR #81 already
    had to exempt parking from the connectivity repair pass, because a car
    porch is legitimately reachable only from the driveway. They are last in
    the field order so `pv[:4]` and `pv.px` both keep working.
    """

    px: cp_model.IntVar
    py: cp_model.IntVar
    pw: cp_model.IntVar
    pd: cp_model.IntVar
    room_id: str
    room_type: str


def _mm(metres: float) -> int:
    return int(round(metres * SCALE))


def _unit_parts_mm(
    template: ShapeTemplate, ratio: float
) -> tuple[tuple[int, int, int, int], ...]:
    """The template's parts over a unit bbox, as integer /_FRACTION_SCALE fractions.

    Returns (x, y, width, depth) per part. Rounding is validated, not assumed:
    two parts of the SAME room go into the same add_no_overlap_2d call, so a
    rounding error that made them overlap by one unit would not produce a
    slightly-wrong plan — it would make the whole model infeasible.
    """
    scale = _FRACTION_SCALE
    parts = parts_for(0.0, 0.0, 1.0, 1.0, template, ratio)
    ints = tuple(
        (
            round(p.x * scale),
            round(p.y * scale),
            round(p.width * scale),
            round(p.depth * scale),
        )
        for p in parts
    )
    for x, y, w, d in ints:
        if w <= 0 or d <= 0 or x < 0 or y < 0 or x + w > scale or y + d > scale:
            raise ValueError(
                f"template {template!r} at ratio {ratio} rounds to a part "
                f"outside its own bounding box: {(x, y, w, d)}"
            )
    for i, (ax, ay, aw, ad) in enumerate(ints):
        for bx, by, bw, bd in ints[i + 1 :]:
            if min(ax + aw, bx + bw) > max(ax, bx) and min(ay + ad, by + bd) > max(
                ay, by
            ):
                raise ValueError(
                    f"template {template!r} at ratio {ratio} rounds to "
                    "overlapping parts — the model would be infeasible"
                )
    return ints


def _grid_step(fractions: tuple[int, ...]) -> int:
    """Smallest k such that `dim * u` is divisible by _FRACTION_SCALE for all u.

    A part's coordinate is `dim * u / _FRACTION_SCALE`, which must land on a
    whole millimetre because CP-SAT is integer-only. Restricting the room's
    dimension to multiples of k is what makes every such division exact (5 mm
    for the default 0.6 ratio — two orders of magnitude below any construction
    tolerance).
    """
    step = 1
    for u in fractions:
        step = lcm(step, _FRACTION_SCALE // gcd(_FRACTION_SCALE, u))
    return step


@dataclass(frozen=True)
class _ShapeFit:
    """How a shape template changes one room's dimension/area bounds.

    A non-RECT room's real area is the part union, a fixed fraction of its
    bounding box, and its narrow leg is `ratio` of the bbox — but the solver's
    area and min-width constraints are written on the bbox. Both minima are
    therefore inflated here; when the inflated version no longer fits the
    room's spec, the fit degrades to RECT rather than going infeasible.
    """

    template: ShapeTemplate
    ratio: float
    min_w: int
    min_d: int
    min_area: int
    max_area: int
    grid_x: int
    grid_y: int


def _fit_template(
    template: ShapeTemplate,
    ratio: float,
    min_w: int,
    max_w: int,
    min_d: int,
    max_d: int,
    min_area: int,
    max_area: int,
) -> _ShapeFit:
    """Bounds for `template`, or the plain RECT bounds when it cannot fit."""
    rect = _ShapeFit("RECT", ratio, min_w, min_d, min_area, max_area, 1, 1)
    if template == "RECT":
        return rect

    unit = _unit_parts_mm(template, ratio)
    frac = sum(w * d for _, _, w, d in unit) / float(_FRACTION_SCALE**2)
    grid_x = _grid_step(tuple(u for x, _, w, _ in unit for u in (x, w)))
    grid_y = _grid_step(tuple(u for _, y, _, d in unit for u in (y, d)))

    def _round_up(value: int, step: int) -> int:
        return -(-value // step) * step

    t_min_w = _round_up(ceil(min_w / ratio), grid_x)
    t_min_d = _round_up(ceil(min_d / ratio), grid_y)
    t_min_area = ceil(min_area / frac)
    t_max_area = int(max_area / frac)
    # Largest bbox the room can actually reach: max_w/max_d quantised DOWN to
    # the template's grid, because w/d are pinned to multiples of it.
    reach_w = (max_w // grid_x) * grid_x
    reach_d = (max_d // grid_y) * grid_y
    if (
        t_min_w > reach_w
        or t_min_d > reach_d
        or t_min_area > t_max_area
        or t_min_w * t_min_d > t_max_area
        # The inflated area minimum must be reachable at all. Without this the
        # template can demand more bbox area than max_w*max_d can supply and
        # make a room infeasible that was perfectly feasible as a RECT —
        # breaking the "a template is never the reason a solve fails" rule,
        # and (worse) surfacing as an unexplained infeasibility in the passes
        # layered on top of this one.
        or t_min_area > reach_w * reach_d
    ):
        return rect
    return _ShapeFit(
        template, ratio, t_min_w, t_min_d, t_min_area, t_max_area, grid_x, grid_y
    )


def _add_room_parts(
    model: cp_model.CpModel,
    rid: str,
    rtype: str,
    xv: cp_model.IntVar,
    yv: cp_model.IntVar,
    wv: cp_model.IntVar,
    dv: cp_model.IntVar,
    xe: cp_model.IntVar,
    ye: cp_model.IntVar,
    template: ShapeTemplate,
    ratio: float,
    bw: int,
    bd: int,
    x_ivs: list[cp_model.IntervalVar],
    y_ivs: list[cp_model.IntervalVar],
    part_vars: list[_PartVars],
) -> None:
    """Append this room's no-overlap intervals — one pair PER PART, not per room.

    Part offsets are fixed fractions of the room's bbox, so each part's
    position is an affine expression over the room's existing anchor/size
    decision vars: no new degrees of freedom, the model just gets more
    intervals over the same unknowns. That is what lets two templated rooms
    interlock — an L's notch can be filled by a neighbour, which a single
    bbox-level interval pair per room can never express.

    `part_vars` is the caller's list and is appended to for EVERY part,
    including a RECT room's single one (where the "part" vars are the room's
    own x/y/w/d), each tagged with `rid`/`rtype` so a later pass can constrain
    occupied rectangles directly and still exempt rooms by type.
    """
    if template == "RECT":
        x_ivs.append(model.new_interval_var(xv, wv, xe, f"ix_{rid}"))
        y_ivs.append(model.new_interval_var(yv, dv, ye, f"iy_{rid}"))
        part_vars.append(_PartVars(xv, yv, wv, dv, rid, rtype))
        return

    scale = _FRACTION_SCALE
    for k, (ux, uy, uw, ud) in enumerate(_unit_parts_mm(template, ratio)):
        px = model.new_int_var(0, bw, f"px_{rid}_{k}")
        py = model.new_int_var(0, bd, f"py_{rid}_{k}")
        pw = model.new_int_var(1, bw, f"pw_{rid}_{k}")
        pd = model.new_int_var(1, bd, f"pd_{rid}_{k}")
        # px = xv + wv*ux/scale, exact in integers because the room's w/d
        # domains are restricted to multiples of the template's grid step
        # (see _ShapeFit.grid_x / grid_y) — every product below is divisible
        # by `scale`, so no solution is lost to a rounding-driven infeasibility.
        model.add(px * scale == xv * scale + wv * ux)
        model.add(py * scale == yv * scale + dv * uy)
        model.add(pw * scale == wv * uw)
        model.add(pd * scale == dv * ud)
        # OR-Tools 9.x: an interval's end must be an IntVar, never a start+size
        # expression (two-var sum is not affine).
        pxe = model.new_int_var(0, bw, f"pxe_{rid}_{k}")
        pye = model.new_int_var(0, bd, f"pye_{rid}_{k}")
        model.add(pxe == px + pw)
        model.add(pye == py + pd)
        x_ivs.append(model.new_interval_var(px, pw, pxe, f"pxi_{rid}_{k}"))
        y_ivs.append(model.new_interval_var(py, pd, pye, f"pyi_{rid}_{k}"))
        part_vars.append(_PartVars(px, py, pw, pd, rid, rtype))


def _plate_and_planes_from_polygon(
    inset,
) -> tuple[int, int, int, int, list[tuple[int, int, int]]]:
    """Solver plate bounds + half-plane constraints from a buildable polygon.

    half_planes is a list of (dx, dy, rhs) where for every room corner
    (rx, ry) in solver coords (mm, relative to plate origin):
    dx*ry - dy*rx >= rhs.  Interior must be left of each CCW edge.
    """
    minx, miny, maxx, maxy = inset.bounds
    bw = _mm(maxx - minx)
    bd = _mm(maxy - miny)
    ox = _mm(minx)
    oy = _mm(miny)

    coords = list(inset.exterior.coords)[:-1]
    n_c = len(coords)
    area2 = sum(
        coords[i][0] * coords[(i + 1) % n_c][1]
        - coords[(i + 1) % n_c][0] * coords[i][1]
        for i in range(n_c)
    )
    if area2 < 0:  # CW — reverse to CCW
        coords = coords[::-1]

    planes: list[tuple[int, int, int]] = []
    n = len(coords)
    for i in range(n):
        p1 = coords[i]
        p2 = coords[(i + 1) % n]
        dx = round((p2[0] - p1[0]) * SCALE)
        dy = round((p2[1] - p1[1]) * SCALE)
        cx = round(p1[0] * SCALE)
        cy = round(p1[1] * SCALE)
        rhs = dx * cy - dy * cx - dx * oy + dy * ox
        planes.append((dx, dy, rhs))

    return bw, bd, ox, oy, planes


def _plate_geom_mm(
    cfg: PlotConfig, ewt: float
) -> tuple[int, int, int, int, list[tuple[int, int, int]]] | None:
    """(bw, bd, ox, oy, half_planes) of the buildable plate, in millimetres.

    Extracted from `_solve_one` so the pre-solve envelope validation measures
    exactly the plate the solve will use. The arithmetic is unchanged.

    A `plot_template` notch stays on the RECTANGULAR branch on purpose: the
    plate is the full setback-inset rectangle and the notch is carved out of it
    by `_forbid_notch`, exactly. Routing it through the polygon branch instead
    would hand `_plate_and_planes_from_polygon` a NON-CONVEX polygon, and a
    half-plane intersection of a non-convex outline collapses to its convex
    core — for the 12x15 m L fixture, 91.8 m² of plate down to 37.1 m².
    """
    if cfg.plot_shape != "rectangular":
        from app.engine.geometry import buildable_polygon

        inset = buildable_polygon(cfg, wall_clearance=ewt)
        if inset.is_empty:
            return None
        return _plate_and_planes_from_polygon(inset)
    bw = _mm(cfg.plot_x_extent - cfg.setback_left - cfg.setback_right - 2 * ewt)
    bd = _mm(cfg.plot_y_extent - cfg.setback_front - cfg.setback_rear - 2 * ewt)
    ox = _mm(cfg.setback_left + ewt)
    oy = _mm(cfg.setback_front + ewt)
    return bw, bd, ox, oy, []


# ── Rectilinear PLOT envelope: the notch ──────────────────────────────────────

# `ShapeTemplate` is shared with ROOM shapes, where all four names are real.
# As a PLOT template only "RECT" and "L" have geometry here; see `notch_rect_m`.
_UNIMPLEMENTED_PLOT_TEMPLATES: frozenset[str] = frozenset({"T", "U"})


def _unimplemented_plot_template_msg(template: str) -> str:
    shape = "two rear-corner notches" if template == "T" else "a central notch"
    return (
        f"plot_template={template!r} is not supported: a {template} plot has "
        f"{shape}, and only the single rear-right cutout of an L plot is "
        'implemented. Use plot_template="L" (or the legacy '
        'plot_shape="l_shaped" cutout) instead.'
    )


def notch_rect_m(cfg: PlotConfig) -> tuple[float, float, float, float] | None:
    """The off-plot cutout rectangle (x0, y0, x1, y1) in PLOT metres, or None.

    Two config surfaces describe the same thing and both resolve here:

    * `plot_template == "L"` with `notch_width`/`notch_depth` — the cutout is
      the plot's REAR-RIGHT corner.
    * the legacy `plot_shape == "l_shaped"` with
      `cutout_corner`/`cutout_width`/`cutout_height`, whose cutout may sit at
      any of the four corners. `generator.py` used to service that surface by
      DELETING rooms that landed in the cutout after the solve; covering it
      here is what makes removing that pass an upgrade rather than a
      regression.

    `plot_template` wins when both are set.

    "T" and "U" are NOT implemented: a T plot has a notch in each rear corner
    and a U plot a central one, so returning the single rear-right rectangle
    for them would silently under-constrain the model and hand the user a plan
    that builds on land they do not own. They raise instead — see
    `validate_plot_envelope`, which rejects them before any solve begins; this
    raise is the defence-in-depth behind it.
    """
    if cfg.plot_template in _UNIMPLEMENTED_PLOT_TEMPLATES:
        raise ValueError(_unimplemented_plot_template_msg(cfg.plot_template))
    if cfg.plot_template != "RECT":
        return (
            cfg.plot_x_extent - cfg.notch_width,
            cfg.plot_y_extent - cfg.notch_depth,
            cfg.plot_x_extent,
            cfg.plot_y_extent,
        )
    if cfg.plot_shape == "l_shaped" and cfg.cutout_width > 0 and cfg.cutout_height > 0:
        cw, ch = cfg.cutout_width, cfg.cutout_height
        pw, pl = cfg.plot_x_extent, cfg.plot_y_extent
        corner = (cfg.cutout_corner or "NE").upper()
        notches = {
            "NE": (pw - cw, pl - ch, pw, pl),
            "NW": (0.0, pl - ch, cw, pl),
            "SE": (pw - cw, 0.0, pw, ch),
            "SW": (0.0, 0.0, cw, ch),
        }
        if corner not in notches:
            # Do not silently default to NE here: geometry.compute_l_shaped_polygon
            # rejects the same unrecognised value instead of guessing SW, and a
            # mismatched guess would forbid one corner in the solver while the
            # drawn/compliance boundary cuts out a different one.
            raise ValueError(
                f"unknown cutout_corner {cfg.cutout_corner!r}; expected one of "
                "'NE', 'NW', 'SE', 'SW'"
            )
        return notches[corner]
    return None


def _forbid_notch(
    model: cp_model.CpModel,
    cfg: PlotConfig,
    parts: list[_PartVars],
    *,
    ox_mm: int,
    oy_mm: int,
    bw: int,
    bd: int,
    ewt: float = 0.0,
) -> None:
    """Forbid every room PART from intersecting the plot's notch.

    Replaces generator.py's post-hoc "delete rooms in the cutout zone" pass,
    which silently dropped programme instead of never placing it there.

    A part avoids an axis-aligned notch iff it lies wholly to one side of it —
    a disjunction of (at most) four linear constraints, one reified BoolVar
    each. Disjuncts that no part could ever satisfy inside the plate are not
    emitted at all, so the ordinary rear-right cutout costs exactly two
    BoolVars per part: "left of the notch" or "in front of it".

    This runs over parts, not bounding boxes, so it is exact for an L/T/U ROOM
    too — a bbox test would either leak a part into the notch or reject a room
    that merely overhangs the notch with its hole. Plot shape and room shape
    stay independent; nothing here needs `cfg.allow_shape_templates`.

    NO ROOM TYPE IS EXEMPT. The notch is land that is not part of the site, so
    unlike PR #81's parking exemption (about reachability from a driveway — a
    car porch still stands on your own plot) there is no type, open or roofed,
    that may occupy it: not parking, not a balcony overhanging it, not a
    garden or terrace. `room_type` is still used, to name the BoolVars so an
    infeasible model can be read.

    The region forbidden is the notch GROWN by the setbacks its two new plot
    edges attract (`geometry.notch_keepout`) — the very region
    `buildable_polygon` subtracts — so the solver, `compliance.check` and
    generator.py's fill passes share one definition of where the notch starts.
    Constraining the raw notch instead would let the solver park a room flush
    against a plot boundary that compliance then fails it for.
    """
    from app.engine.geometry import notch_keepout

    keepout = notch_keepout(cfg, wall_clearance=ewt)
    if keepout is not None:
        rect: tuple[float, float, float, float] | None = keepout.bounds
    else:
        rect = notch_rect_m(cfg)  # legacy l_shaped cutout, or nothing
    if rect is None:  # plot_template == "RECT" and no legacy cutout
        return
    nlo_x = _mm(rect[0]) - ox_mm
    nlo_y = _mm(rect[1]) - oy_mm
    nhi_x = _mm(rect[2]) - ox_mm
    nhi_y = _mm(rect[3]) - oy_mm
    if nlo_x >= bw or nlo_y >= bd or nhi_x <= 0 or nhi_y <= 0:
        return  # the notch misses the buildable plate entirely

    for k, pv in enumerate(parts):
        escapes: list[cp_model.IntVar] = []
        candidates = (
            ("left", nlo_x > 0, pv.px + pv.pw <= nlo_x),
            ("front", nlo_y > 0, pv.py + pv.pd <= nlo_y),
            ("right", nhi_x < bw, pv.px >= nhi_x),
            ("rear", nhi_y < bd, pv.py >= nhi_y),
        )
        for tag, reachable, expr in candidates:
            if not reachable:
                continue  # unsatisfiable inside the plate — do not emit
            lit = model.new_bool_var(f"notch_{tag}_{pv.room_type}_{pv.room_id}_{k}")
            model.add(expr).only_enforce_if(lit)
            escapes.append(lit)
        if not escapes:
            raise ValueError(
                "the plot notch covers the entire buildable plate — no room "
                "can be placed; reduce the notch or the setbacks"
            )
        model.add_bool_or(escapes)


def validate_plot_envelope(
    cfg: PlotConfig,
    ewt: float,
    room_defs: list[dict] | None = None,
    specs: dict | None = None,
) -> None:
    """Raise ValueError when the notch makes the requested programme impossible.

    **Scope: the `plot_template` surface ONLY.** A `plot_template == "RECT"`
    config returns immediately, which deliberately leaves the legacy
    `plot_shape == "l_shaped"` + `cutout_*` surface on exactly the path it had
    before this task. That surface is user-reachable and DB-persisted, and no
    route along `generate` -> `layout_store.solve_layouts_async` -> the
    generate/export/share/revisions/structural routes handles a `ValueError`,
    so validating it here turned realistic saved projects (12x15 m, 3BHK, a
    3x4 m NE cutout) into an uncaught HTTP 500 where they used to degrade
    gracefully to an empty layout list. Legacy configs still get the hard
    `_forbid_notch` constraint — they just are not gated on it.

    For the new surface the error is raised UP FRONT rather than letting CP-SAT
    return INFEASIBLE: an INFEASIBLE status is indistinguishable from "the
    solver ran out of budget", and `solve_layout`, `solve_layouts` and
    `generate` all swallow exceptions from the solve itself, so the user would
    only ever see an empty result. Relaxing the constraint instead is not an
    option — the notch is land the user does not own.

    The area test is a NECESSARY condition only (rooms cannot overlap, so the
    sum of their minimum areas must fit on the floor), never a sufficient one.
    It measures `_plate_geom_mm`, and on the `plot_template` surface that is
    also what the archetype fallback measures — `archetypes._floor_plate` falls
    through to `_inscribed_plate`, whose bounds come from the same
    `buildable_polygon`. (This is NOT true of the legacy surface, whose
    archetype plate is the larger `_l_shaped_floor_plate`; gating that surface
    would have over-rejected by ~24 m². Another reason the scope above is what
    it is.)
    """
    if cfg.plot_template == "RECT":
        return
    if cfg.plot_template not in SHAPE_TEMPLATES:
        raise ValueError(
            f"unknown plot_template {cfg.plot_template!r}; expected one of "
            f"{sorted(SHAPE_TEMPLATES)}"
        )
    if cfg.plot_template in _UNIMPLEMENTED_PLOT_TEMPLATES:
        raise ValueError(_unimplemented_plot_template_msg(cfg.plot_template))
    if cfg.notch_width <= 0 or cfg.notch_depth <= 0:
        raise ValueError(
            f"plot_template={cfg.plot_template!r} needs a positive notch; got "
            f"notch_width={cfg.notch_width} m, notch_depth={cfg.notch_depth} m "
            '(use plot_template="RECT" for a plain rectangular plot)'
        )
    if cfg.notch_width >= cfg.plot_x_extent or cfg.notch_depth >= cfg.plot_y_extent:
        raise ValueError(
            f"the {cfg.notch_width:g}x{cfg.notch_depth:g} m notch is as large as "
            f"the {cfg.plot_x_extent:g}x{cfg.plot_y_extent:g} m plot — nothing is left "
            "to build on"
        )

    from app.engine.geometry import notch_keepout

    keepout = notch_keepout(cfg, wall_clearance=ewt)
    if keepout is None:
        return
    rect = keepout.bounds  # the same region `_forbid_notch` will constrain
    geom = _plate_geom_mm(cfg, ewt)
    if geom is None:
        return  # setbacks already consume the plot; the solve returns None
    bw, bd, ox, oy, _ = geom
    if bw <= 0 or bd <= 0:
        return

    # keep-out ∩ plate is itself a rectangle (both are axis-aligned), so the
    # buildable area lost to it is exact, not an estimate.
    lost_w = max(0, min(ox + bw, _mm(rect[2])) - max(ox, _mm(rect[0])))
    lost_d = max(0, min(oy + bd, _mm(rect[3])) - max(oy, _mm(rect[1])))
    usable_mm2 = bw * bd - lost_w * lost_d

    if specs is None:
        specs = _load_specs()
    if room_defs is None:
        room_defs = _build_room_list(cfg, specs)

    needed: dict[int, int] = {}
    counts: dict[int, int] = {}
    for rd in room_defs:
        spec = specs.get(rd["type"], specs.get("utility"))
        raw = rd.get("custom_min_area") or spec["min_area_sqm"]
        floor = rd["floor"]
        needed[floor] = needed.get(floor, 0) + int(raw * SCALE * SCALE)
        counts[floor] = counts.get(floor, 0) + 1

    for floor, required in sorted(needed.items()):
        if required > usable_mm2:
            raise ValueError(
                f"the {cfg.notch_width:g}x{cfg.notch_depth:g} m plot notch (plus its "
                f"own setbacks) leaves only "
                f"{usable_mm2 / (SCALE * SCALE):.1f} m² buildable per "
                f"floor, but floor {floor}'s programme ({counts[floor]} rooms for "
                f"{cfg.num_bedrooms} bedrooms / {cfg.toilets} toilets) needs at "
                f"least {required / (SCALE * SCALE):.1f} m² — shortfall "
                f"{(required - usable_mm2) / (SCALE * SCALE):.1f} m². Reduce the "
                "notch, the setbacks, or the programme."
            )


def ensuite_attachment(room_id: str) -> str | None:
    """Map an en-suite room id (``toilet_ens_<i>``) to its bedroom id.

    The Room dataclass has no metadata field, so en-suite attachment is
    encoded in the id convention; later pipeline stages import this helper
    instead of re-parsing ids.
    """
    if room_id.startswith("toilet_ens_"):
        suffix = room_id.removeprefix("toilet_ens_")
        if suffix.isdigit():
            return f"bedroom_{suffix}"
    return None


def _build_room_list(cfg: PlotConfig, specs: dict) -> list[dict]:
    """Determine which rooms to solve for based on PlotConfig."""
    rooms = []

    # Living room (always)
    rooms.append(
        {"id": "living_0", "type": "living", "name": "Living Room", "floor": 0}
    )

    # Kitchen (always, GF)
    rooms.append({"id": "kitchen_0", "type": "kitchen", "name": "Kitchen", "floor": 0})

    # Bedrooms — distribute across GF and FF. With attached_toilets each
    # bedroom gets an en-suite on its own floor (bathroom_master for the
    # master, i.e. bedroom 0); en-suites are ADDITIVE to cfg.toilets, which
    # then counts common toilets only.
    bedroom_floors: set[int] = set()
    for i in range(cfg.num_bedrooms):
        floor = 0 if i == 0 else 1
        bedroom_floors.add(floor)
        rooms.append(
            {
                "id": f"bedroom_{i}",
                "type": "bedroom",
                "name": f"Bedroom {i + 1}",
                "floor": floor,
            }
        )
        if cfg.attached_toilets:
            rooms.append(
                {
                    "id": f"toilet_ens_{i}",
                    "type": "bathroom_master" if i == 0 else "toilet",
                    "name": "Master Bath" if i == 0 else f"Toilet (Bed {i + 1})",
                    "floor": floor,
                    "attached_to": f"bedroom_{i}",
                }
            )

    # Common toilets — distribute across floors, then guarantee every floor
    # that has rooms but no bedroom gets >= 1 (the solver always populates
    # floors 0 and 1 via the staircase). Redistribute, never add: pull one
    # toilet from the most-served floor.
    toilet_floors = [
        0 if i < max(1, cfg.num_bedrooms // 2) else 1 for i in range(cfg.toilets)
    ]
    for f in (0, 1):
        if f not in bedroom_floors and toilet_floors and f not in toilet_floors:
            donor = max(set(toilet_floors), key=toilet_floors.count)
            toilet_floors[toilet_floors.index(donor)] = f
    for i, floor in enumerate(toilet_floors):
        rooms.append(
            {
                "id": f"toilet_{i}",
                "type": "toilet",
                "name": f"Toilet {i + 1}",
                "floor": floor,
            }
        )

    # Staircase on both floors
    rooms.append(
        {"id": "stair_0", "type": "staircase", "name": "Staircase", "floor": 0}
    )
    rooms.append(
        {"id": "stair_1", "type": "staircase", "name": "Staircase", "floor": 1}
    )

    # Optional rooms
    if cfg.has_pooja:
        rooms.append(
            {"id": "pooja_0", "type": "pooja", "name": "Pooja Room", "floor": 0}
        )
    if cfg.has_study:
        rooms.append(
            {"id": "study_0", "type": "study", "name": "Study Room", "floor": 1}
        )
    if cfg.has_balcony:
        rooms.append(
            {"id": "balcony_0", "type": "balcony", "name": "Balcony", "floor": 1}
        )
    if cfg.parking:
        parking: dict = {
            "id": "parking_0",
            "type": "parking",
            "name": "Parking",
            "floor": 0,
        }
        if cfg.open_parking:
            # The road-facing edge is y-min ("S") in plot coordinates whatever
            # the surveyed north angle is — plot +y always runs front→rear.
            parking["open_sides"] = ("S",)
        rooms.append(parking)

    # Programme flags from the wizard (Task 25) — one room per required type.
    # has_pooja/has_study above already cover those types; skip duplicates so a
    # caller setting both never gets two poojas. Terrace lands on the top
    # floor the solver models (floor 1) when there is one, else the ground
    # floor; verandah's road-side anchoring is deferred — see the Task 25
    # rulings in the plan.
    covered = {r["type"] for r in rooms}
    for rtype in sorted(cfg.required_types):
        if rtype in covered:
            continue
        top_floor = 1 if cfg.num_floors > 1 else 0
        floor = top_floor if rtype == "terrace" else 0
        rooms.append(
            {
                "id": f"{rtype}_0",
                "type": rtype,
                "name": rtype.replace("_", " ").title(),
                "floor": floor,
            }
        )

    # Custom rooms from Phase C
    if cfg.custom_room_config:
        for idx, custom in enumerate(cfg.custom_room_config):
            rtype = custom.get("type", "utility")
            pref = custom.get("floor_preference", "either")
            floor = 1 if pref == "ff" else 0
            rooms.append(
                {
                    "id": f"custom_{idx}",
                    "type": rtype,
                    "name": custom.get("name") or rtype.replace("_", " ").title(),
                    "floor": floor,
                    "custom_min_area": custom.get("min_area_sqm"),
                }
            )

    return rooms


def _rooms_overlap(a: Room, b: Room) -> bool:
    """Do the two rooms' OCCUPIED rectangles overlap?

    Part-level, not bounding-box: two interlocked templated rooms (one sitting
    in the other's notch) have overlapping bboxes and disjoint footprints, and
    a bbox test would wrongly call that a collision. Reduces to the plain
    rectangle test for RECT rooms, which is every room unless
    cfg.allow_shape_templates is on.
    """
    for pa in a.rects:
        for pb in b.rects:
            x_ov = min(pa.x + pa.width, pb.x + pb.width) - max(pa.x, pb.x)
            y_ov = min(pa.y + pa.depth, pb.y + pb.depth) - max(pa.y, pb.y)
            if x_ov > 1e-6 and y_ov > 1e-6:
                return True
    return False


@dataclass
class _SnapEdge:
    key: tuple[int, str, str, str]  # (floor_idx, room_id, axis, "lo"|"hi")
    coord: float
    lo: float  # perpendicular interval (for facing detection)
    hi: float
    pinned: bool = False
    unit: int = -1  # union-find root index, -1 = solitary
    line: float = 0.0  # implied wall-line coordinate used for clustering


def _stair_circulation_protect_ids(rooms: list[Room]) -> set[str]:
    """Room ids (stair + its qualifying circulation neighbour) whose shared
    wall already meets the solver's hard stair-door-access overlap
    (``_STAIR_DOOR_MIN_OVERLAP_MM``).

    Mirrors the CP-SAT reified overlap test in ``_solve_one`` (same four-side
    cases, same gap/overlap thresholds) but as plain post-hoc geometry, so
    ``snap_rooms_to_shared_grid`` can pin both rooms and guarantee the
    invariant survives snapping — a hard CP-SAT constraint at solve time was
    still silently undone downstream because the circulation room next to a
    pinned staircase was itself free to move (issue #50).
    """
    stairs = [r for r in rooms if r.type == "staircase"]
    if not stairs:
        return set()
    targets = [r for r in rooms if r.type in _CIRCULATION_TYPES]
    if not targets:
        targets = [
            r
            for r in rooms
            if r.type not in _WET_TYPES
            and r.type not in _PARKING_TYPES
            and r.type != "staircase"
        ]
    min_overlap = _STAIR_DOOR_MIN_OVERLAP_MM / SCALE
    protect: set[str] = set()
    for st in stairs:
        st_xe, st_ye = st.x + st.width, st.y + st.depth
        for tgt in targets:
            tgt_xe, tgt_ye = tgt.x + tgt.width, tgt.y + tgt.depth
            cases = (
                (tgt.x - st_xe, st.y, st_ye, tgt.y, tgt_ye),  # stair left
                (st.x - tgt_xe, st.y, st_ye, tgt.y, tgt_ye),  # stair right
                (tgt.y - st_ye, st.x, st_xe, tgt.x, tgt_xe),  # stair in front
                (st.y - tgt_ye, st.x, st_xe, tgt.x, tgt_xe),  # stair behind
            )
            for gap, a_lo, a_hi, b_lo, b_hi in cases:
                # -0.01/+0.01 mirrors _adjacencies in plan_geometry.py (the
                # test derive_openings actually uses): post-solve rooms are
                # rounded to 3dp and later passes make them flush, so a pair
                # that derive_openings treats as sharing a wall could fall a
                # fraction of a millimetre outside a tighter range and be
                # left unpinned — exactly the drift this function exists to
                # prevent.
                if -0.01 <= gap <= _IWT_M + 0.01 and (
                    min(a_hi, b_hi) - max(a_lo, b_lo) >= min_overlap - 1e-6
                ):
                    protect.add(st.id)
                    protect.add(tgt.id)
    return protect


def _ensuite_protect_ids(rooms: list[Room]) -> set[str]:
    """Room ids (ensuite toilet + its bedroom) whose shared wall already
    meets the solver's hard ensuite-adjacency overlap (``_ENSUITE_MIN_OVERLAP_MM``).

    Sibling to ``_stair_circulation_protect_ids`` — the CP-SAT ensuite
    constraint is just as hard as the stair one, but snapping only ever
    protected the stair pair, so an ensuite toilet was still free to drift
    off its bedroom wall (test_solved_ensuite_shares_wall_with_bedroom failing
    intermittently, root-caused by this gap rather than solver search quality).
    """
    protect: set[str] = set()
    by_id = {r.id: r for r in rooms}
    min_overlap = _ENSUITE_MIN_OVERLAP_MM / SCALE
    for r in rooms:
        bed_id = ensuite_attachment(r.id)
        if bed_id is None:
            continue
        bed = by_id.get(bed_id)
        if bed is None:
            continue
        r_xe, r_ye = r.x + r.width, r.y + r.depth
        bed_xe, bed_ye = bed.x + bed.width, bed.y + bed.depth
        cases = (
            (bed.x - r_xe, r.y, r_ye, bed.y, bed_ye),  # ensuite left of bed
            (r.x - bed_xe, r.y, r_ye, bed.y, bed_ye),  # ensuite right of bed
            (bed.y - r_ye, r.x, r_xe, bed.x, bed_xe),  # ensuite in front
            (r.y - bed_ye, r.x, r_xe, bed.x, bed_xe),  # ensuite behind
        )
        for gap, a_lo, a_hi, b_lo, b_hi in cases:
            if -0.01 <= gap <= _IWT_M + 0.01 and (
                min(a_hi, b_hi) - max(a_lo, b_lo) >= min_overlap - 1e-6
            ):
                protect.add(r.id)
                protect.add(bed_id)
    return protect


def snap_rooms_to_shared_grid(
    floors: list[list[Room]],
    min_dims: dict[str, dict],
    tol: float = SNAP_TOL_M,
    plate_bounds: tuple[tuple[float, float], tuple[float, float]] | None = None,
    pin_room_types: set[str] | None = None,
) -> list[list[Room]]:
    """Best-effort post-solve pass: merge near-aligned wall LINES (across
    ALL floors, so columns stack vertically) onto shared grid lines.

    Facing edge pairs — a room's hi edge and a neighbour's lo edge within
    one wall thickness, with perpendicular overlap — are the two faces of
    ONE wall and move rigidly together, so the pass can never collapse a
    wall gap regardless of tolerance. Edges on the buildable plate boundary
    are pinned and act as cluster anchors.

    Guarantees, in order:
    - wall faces keep their gap (rigid units)
    - no room shrinks below its spec minimums (per-room revert)
    - no room overlap (participants of an overlap revert)

    Feasibility beyond that (setbacks, compliance) is the caller's problem:
    _solve_one re-runs the compliance check and falls back to the unsnapped
    rooms if the snapped layout fails.
    """
    originals = {(fi, r.id): r for fi, rooms in enumerate(floors) for r in rooms}
    # Rooms of pinned types anchor their wall lines: neighbours merge ONTO
    # them, they never move. Used for the staircase core in the post-fill
    # snap — per-floor fill rooms cluster the stair with different
    # neighbours on each floor, and independent deltas broke the exact
    # GF/FF stair stacking the solver guarantees.
    pinned_ids = {
        r.id
        for rooms in floors
        for r in rooms
        if pin_room_types and r.type in pin_room_types
    }
    # Unconditional (not opt-in via pin_room_types): a stair/circulation pair
    # or ensuite/bedroom pair that already clears its hard CP-SAT overlap
    # constraint must not be allowed to drift apart by this best-effort pass,
    # on either snap call site.
    for rooms in floors:
        pinned_ids |= _stair_circulation_protect_ids(rooms)
        pinned_ids |= _ensuite_protect_ids(rooms)

    edges: list[_SnapEdge] = []
    for fi, rooms in enumerate(floors):
        for r in rooms:
            edges.append(_SnapEdge((fi, r.id, "x", "lo"), r.x, r.y, r.y + r.depth))
            edges.append(
                _SnapEdge((fi, r.id, "x", "hi"), r.x + r.width, r.y, r.y + r.depth)
            )
            edges.append(_SnapEdge((fi, r.id, "y", "lo"), r.y, r.x, r.x + r.width))
            edges.append(
                _SnapEdge((fi, r.id, "y", "hi"), r.y + r.depth, r.x, r.x + r.width)
            )

    for e in edges:
        if e.key[1] in pinned_ids:
            e.pinned = True

    if plate_bounds is not None:
        (px1, px2), (py1, py2) = plate_bounds
        for e in edges:
            bounds = (px1, px2) if e.key[2] == "x" else (py1, py2)
            if any(abs(e.coord - b) <= 0.02 for b in bounds):
                e.pinned = True
        # Virtual anchors at the plate bounds themselves: a lone edge that
        # stops just short of the plate (orphan sliver strip) snaps onto it
        # even when no real room edge sits there to pin the cluster.
        for axis, (b1, b2) in (("x", (px1, px2)), ("y", (py1, py2))):
            for b in (b1, b2):
                anchor = _SnapEdge((-1, "__plate__", axis, "lo"), b, 0.0, 0.0)
                anchor.pinned = True
                edges.append(anchor)

    # Facing pairs (same floor, hi face meets lo face across <= one wall
    # gap, perpendicular overlap) -> rigid wall units via union-find.
    parent = list(range(len(edges)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_axis_floor: dict[tuple[str, int], list[int]] = {}
    for idx, e in enumerate(edges):
        by_axis_floor.setdefault((e.key[2], e.key[0]), []).append(idx)
    for group in by_axis_floor.values():
        for i in group:
            a = edges[i]
            if a.key[3] != "hi":
                continue
            for j in group:
                b = edges[j]
                if b.key[3] != "lo" or b.key[1] == a.key[1]:
                    continue
                gap = b.coord - a.coord
                if -0.02 <= gap <= _IWT_M + 0.02 and (
                    min(a.hi, b.hi) - max(a.lo, b.lo) >= 0.05
                ):
                    parent[find(i)] = find(j)

    # Cluster on the wall-unit centre for paired faces, on the raw edge
    # coordinate for solitary edges. (No +-IWT/2 orphan-wall estimates:
    # coordinate-level equality already puts DERIVED wall lines within
    # half a wall thickness of each other — far below any structural bay —
    # and the micro-shuffles those estimates cause trigger min-dim/overlap
    # revert cascades that destroy the real merges.)
    members: dict[int, list[int]] = {}
    for idx in range(len(edges)):
        members.setdefault(find(idx), []).append(idx)
    for root, idxs in members.items():
        if len(idxs) > 1:
            line = sum(edges[i].coord for i in idxs) / len(idxs)
            for i in idxs:
                edges[i].unit = root
                edges[i].line = line
        else:
            edges[idxs[0]].line = edges[idxs[0]].coord

    # Cluster wall lines per axis (chain gap AND diameter <= tol), then move
    # every member line to the cluster target — anchored on a pinned edge's
    # line when one is present. Units translate rigidly (same delta for all
    # faces), so gaps are preserved exactly.
    deltas: dict[tuple[int, str, str, str], float] = {}

    def cluster_feasible(cluster: list[_SnapEdge], target: float) -> bool:
        # Per-edge min-dims pre-check (approximate: ignores the room's other
        # edge moving in a different cluster — build() remains the exact
        # safety net). Lets flush() pick a target every member can reach
        # instead of the mean, which one starved room vetoes via revert,
        # leaving the near-miss lines the merge existed to remove.
        for e in cluster:
            if e.pinned:
                continue
            fi, rid, axis, side = e.key
            r = originals.get((fi, rid))
            if r is None:
                continue
            delta = target - e.line
            dim = r.width if axis == "x" else r.depth
            new_dim = dim + (delta if side == "hi" else -delta)
            mins = min_dims.get(rid, {})
            min_dim = mins.get("min_width_m" if axis == "x" else "min_depth_m", 0.0)
            other = r.depth if axis == "x" else r.width
            if (
                new_dim < min_dim - 1e-9
                or new_dim * other < mins.get("min_area_sqm", 0.0) - 1e-9
                or new_dim * other > mins.get("max_area_sqm", float("inf")) + 1e-9
            ):
                return False
        return True

    def flush(cluster: list[_SnapEdge]) -> None:
        lines = sorted({round(e.line, 6) for e in cluster})
        if len(lines) < 2:
            return  # already one line — nothing to merge
        pinned = [e for e in cluster if e.pinned]
        if pinned:
            target = pinned[0].line  # plate lines are immovable
        else:
            mean = sum(lines) / len(lines)
            target = next(
                (t for t in [mean, *lines] if cluster_feasible(cluster, t)),
                mean,
            )
        for e in cluster:
            if not e.pinned:
                deltas[e.key] = target - e.line

    def split(chunk: list[_SnapEdge]) -> list[list[_SnapEdge]]:
        # Enforce the diameter cap by splitting at the LARGEST internal gap
        # (greedy left-to-right splitting can separate two near-identical
        # lines just because an unrelated line started the chain earlier).
        if chunk[-1].line - chunk[0].line <= tol:
            return [chunk]
        gi = max(range(1, len(chunk)), key=lambda i: chunk[i].line - chunk[i - 1].line)
        return split(chunk[:gi]) + split(chunk[gi:])

    for axis in ("x", "y"):
        axis_edges = sorted(
            (e for e in edges if e.key[2] == axis), key=lambda e: e.line
        )
        chain: list[_SnapEdge] = []
        for e in axis_edges:
            if chain and e.line - chain[-1].line > tol:
                for cluster in split(chain):
                    flush(cluster)
                chain = []
            chain.append(e)
        if chain:
            for cluster in split(chain):
                flush(cluster)

    def build(fi: int, r: Room) -> Room:
        x_lo = r.x + deltas.get((fi, r.id, "x", "lo"), 0.0)
        x_hi = r.x + r.width + deltas.get((fi, r.id, "x", "hi"), 0.0)
        y_lo = r.y + deltas.get((fi, r.id, "y", "lo"), 0.0)
        y_hi = r.y + r.depth + deltas.get((fi, r.id, "y", "hi"), 0.0)
        cand = replace(
            r,
            x=round(x_lo, 3),
            y=round(y_lo, 3),
            width=round(x_hi - x_lo, 3),
            depth=round(y_hi - y_lo, 3),
        )
        mins = min_dims.get(r.id, {})
        eps = 1e-9
        # Area is the PART UNION, not the bounding box — a templated room's
        # bbox overstates its area by up to half. Summed unrounded (identical
        # to width*depth for a RECT room, so the pre-template snap decisions
        # are bit-for-bit unchanged; Room.area would round to 2 dp and could
        # flip a borderline revert).
        cand_area = sum(p.area for p in cand.rects)
        if (
            cand.width < mins.get("min_width_m", 0.0) - eps
            or cand.depth < mins.get("min_depth_m", 0.0) - eps
            or cand_area < mins.get("min_area_sqm", 0.0) - eps
            or cand_area > mins.get("max_area_sqm", float("inf")) + eps
        ):
            return r  # revert: snap would violate this room's spec min/max
        return cand

    result = [[build(fi, r) for r in rooms] for fi, rooms in enumerate(floors)]

    # Overlap guard: revert every participant of an overlap, repeat until
    # stable (reverting one room can only remove overlaps, never add them,
    # because originals were overlap-free — but a revert can pair an
    # original with a still-snapped neighbour, so re-check).
    for _ in range(3):
        dirty = False
        for fi, rooms in enumerate(result):
            for i, ra in enumerate(rooms):
                for j in range(i + 1, len(rooms)):
                    rb = rooms[j]
                    if _rooms_overlap(ra, rb):
                        rooms[i] = originals[(fi, ra.id)]
                        rooms[j] = originals[(fi, rb.id)]
                        ra = rooms[i]
                        dirty = True
        if not dirty:
            break
    return result


# ── Vastu zone reification ───────────────────────────────────────────────────


class _VastuBands(NamedTuple):
    """Integer half-planes that reproduce `vastu.zone_for_point` on a plot.

    `zone_for_point` normalises the point by the plot extents *before* rotating
    it, so both of its band coordinates stay LINEAR in the raw (x, y):

        east  = (x - W/2)/W * cos t - (y - L/2)/L * sin t
        north = (x - W/2)/W * sin t + (y - L/2)/L * cos t

    That is what makes the 3x3 grid reifiable for ANY north angle and not only
    the axis-aligned ones — the *cells* are rotated squares once the angle is
    off-axis, but the four boundaries between them are still straight lines, so
    each is one CP-SAT linear constraint on the room centroid.

    Fields hold `east`/`north` rescaled so that the +-1/6 band boundary lands on
    +-`band` == +-`_VASTU_BAND_SCALE`, as a function of the DOUBLED centroid
    `cx2 = 2*x + w` (doubling keeps the centroid integral without an extra var):

        east_scaled  = ex * cx2 + ey * cy2 + ec
        north_scaled = nx * cx2 + ny * cy2 + nc

    A fixed band scale matters: the obvious formulation (multiply through by
    `12 * W * L * trig_scale`) produces coefficients around 1e15 on a 9x15 m
    plot, and CP-SAT could no longer solve an off-axis plot inside its budget
    at all (measured: `north_angle_deg=37.5` went from a 15 s solve to no
    solution). Here the coefficients stay around 3e4.

    `margin` is the exact worst-case error the six roundings can introduce into
    `east_scaled`/`north_scaled`, so a caller that needs a CONSERVATIVE test
    (the hard exclusions) can widen the region by it and stay a strict superset
    of the float original.
    """

    ex: int
    ey: int
    ec: int
    nx: int
    ny: int
    nc: int
    band: int
    margin: int


# room_id -> (cols, rows) from `_zone_membership_bools`. One per solve, shared
# by every term that asks which Vastu cell a room is in.
_ZoneCache = dict[str, tuple[list[cp_model.IntVar], list[cp_model.IntVar]]]


# Integer value the +-1/6 Vastu band boundary is mapped onto. Tuned, not
# arbitrary: this constant sets the magnitude of every coefficient the zone
# half-planes put into the model, and CP-SAT is sensitive to it. At 1e8 the
# expressions reach ~2e9 and the search could no longer find ANY feasible
# solution inside its deterministic budget on two of three orientations
# (road_side="N" and north_angle_deg=37.5 both returned UNKNOWN, having solved
# fine without Vastu). 1e6 keeps them near 1e7 and all three solve. The cost is
# a coarser rounding margin — ~2.4% of a band, i.e. the hard-excluded region is
# inflated by ~12 cm on a 15 m plot — which is immaterial for a placement
# preference. `_vastu_feasibility_fallback` covers the residual risk.
_VASTU_BAND_SCALE = 1_000_000


def _vastu_bands(plot_w_mm: int, plot_l_mm: int, north_angle_deg: float) -> _VastuBands:
    """Half-plane coefficients for a plot's Vastu grid, in millimetre units."""
    theta = radians(north_angle_deg)
    cos_t, sin_t = cos(theta), sin(theta)
    k = 3 * _VASTU_BAND_SCALE
    w, ln = plot_w_mm, plot_l_mm
    # Derivation: east * 6 * _VASTU_BAND_SCALE / (2*_VASTU_BAND_SCALE) ... i.e.
    # substitute u = (cx2 - w) / (2w), v = (cy2 - ln) / (2ln) into the two
    # projections above and scale so that 1/6 maps to _VASTU_BAND_SCALE.
    ex = round(k * cos_t / w)
    ey = round(-k * sin_t / ln)
    ec = round(k * (sin_t - cos_t))
    nx = round(k * sin_t / w)
    ny = round(k * cos_t / ln)
    nc = round(-k * (sin_t + cos_t))
    # Each of the six coefficients carries at most 0.5 of rounding error, and
    # cx2 <= 2w, cy2 <= 2ln.
    margin = int(0.5 * (2 * w + 2 * ln + 1)) + 1
    return _VastuBands(ex, ey, ec, nx, ny, nc, _VASTU_BAND_SCALE, margin)


def _vastu_zone_of_centroid_mm(cx2: int, cy2: int, bands: _VastuBands) -> str:
    """Zone of a doubled-centroid point under `bands`.

    The reference implementation of what the CP-SAT constraints below encode;
    `tests/test_solver_vastu.py` pins it against `vastu.zone_for_point`. The
    asymmetric `<` / `>` mirrors `zone_for_point`'s tie handling.
    """
    east = bands.ex * cx2 + bands.ey * cy2 + bands.ec
    north = bands.nx * cx2 + bands.ny * cy2 + bands.nc
    col = 0 if east < -bands.band else (1 if east < bands.band else 2)
    row = 0 if north > bands.band else (1 if north > -bands.band else 2)
    return ZONE_GRID_ROAD_S[row][col]


def _vastu_hard_excluded_zones(room_type: str) -> frozenset[str]:
    """Zones a room type is structurally forbidden from, derived from the rules.

    Only `VASTU_HARD_EXCLUDE_TYPES` are eligible, and even for those only the
    zones their own `avoid` tier already names — so every hard constraint the
    solver adds corresponds to an `avoid` cell in `vastu_room_rules` and cannot
    drift from it when the rules file is edited.
    """
    if room_type not in VASTU_HARD_EXCLUDE_TYPES:
        return frozenset()
    rule = _rule_for(room_type)
    if rule is None:
        return frozenset()
    return VASTU_HARD_EXCLUDE_ZONES & frozenset(rule.get("avoid", []))


def _vastu_zone_cost(room_type: str, zone: str) -> int:
    """Objective cost of placing `room_type` in `zone`.

    Deliberately takes NO area: `vastu_layout_score` is area-weighted, and
    mirroring that here would hand the solver a way to improve the objective by
    SHRINKING a badly-placed room instead of moving it — room width and depth
    are decision variables, unlike the room type. A per-room constant cost
    makes relocation the only way to pay less.
    """
    return int(round(VASTU_WEIGHT * (1.0 - _verdict(room_type, zone))))


def _vastu_escape_bounds(
    index: int, bands: _VastuBands, is_row: bool
) -> list[tuple[int, int]]:
    """Ways for a coordinate to leave the CLOSED band `index`, as (sign, bound).

    `sign == -1` means `expr <= bound`, `sign == +1` means `expr >= bound`. Any
    one of the returned options being satisfied puts the coordinate outside the
    band, so a caller ORs them (across both axes) to forbid a grid cell.

    The band is CLOSED, i.e. inflated by one integer unit past each boundary,
    on purpose. `zone_for_point` computes its bands in floating point, where
    `cos(radians(90))` is 6.1e-17 rather than 0; that epsilon is far below one
    integer unit here but it decides the verdict for a centroid sitting exactly
    ON a band boundary (measured: 266-409 boundary points of 54481 on a 9x15
    plot at 90/180/270 degrees). Inflating by a unit makes the forbidden region
    a strict superset of the float one, so a hard exclusion can never be
    satisfied by a room the scorer still reads as being in the excluded zone.

    WARNING for whoever widens `VASTU_HARD_EXCLUDE_ZONES`. Swapping the two
    axes at the call site — passing the row index with `is_row=False` and vice
    versa — is currently a NO-OP, and a mutation that does so survives the
    suite. That is a coincidence of the only two zones in the set today: NE is
    the high-north/high-east corner (row index 0, column index 2, whose escape
    sets mirror each other) and C is symmetric (index 1 on both axes). Add a
    third zone — SE, say — and the same swap becomes a real inversion that no
    current test catches, including the leak test, which derives its own axis
    pairing the same way the code does rather than independently. Pin the
    pairing with a dedicated test before widening the set.
    """
    hi = bands.band + bands.margin
    lo = -bands.band - bands.margin
    if is_row:
        # row 0: n > band | row 1: -band < n <= band | row 2: n <= -band
        return {
            0: [(-1, bands.band - bands.margin - 1)],
            1: [(-1, lo - 1), (1, hi + 1)],
            2: [(1, -bands.band + bands.margin + 1)],
        }[index]
    # col 0: e < -band | col 1: -band <= e < band | col 2: e >= band
    return {
        0: [(1, -bands.band + bands.margin + 1)],
        1: [(-1, lo - 1), (1, hi + 1)],
        2: [(-1, bands.band - bands.margin - 1)],
    }[index]


def _var_min(var: cp_model.IntVar) -> int:
    """Declared lower bound of an IntVar, as a plain int.

    Used to lift a room's minimum extent out of the model and into the
    coefficients of the SOFT Vastu predicate, so that predicate contains no
    decision variable that the solver could shrink — see `_add_vastu_terms`.
    """
    return int(var.proto.domain[0])


def _var_max(var: cp_model.IntVar) -> int:
    """Declared upper bound of an IntVar, as a plain int.

    The `tuple(...)` is load-bearing: `proto.domain` is a protobuf repeated
    scalar container and `[-1]` on one silently returns 0 rather than the
    bound (see app/engine/CLAUDE.md).
    """
    return int(tuple(var.proto.domain)[-1])


def _add_size_prior_terms(
    model: cp_model.CpModel,
    cfg: PlotConfig,
    room_vars: list[_RoomVar],
) -> list[tuple[int, cp_model.IntVar]]:
    """Soft penalty for a room's area straying from its style's corpus mean.

    Mirrors `_add_vastu_terms`: pure (cost, var) soft terms for `base_objective`,
    no hard bound, and room types the corpus has no data for are skipped
    entirely rather than given a middling cost. Only built when
    `cfg.corpus_priors_enabled`.

    THE INVERSE-STD WEIGHTING LIVES IN THE UNIT, NOT IN THE COEFFICIENT.

    The natural formulation — weight the raw mm² deviation by `K / std` —
    cannot work here, because an objective coefficient must be a positive
    integer. One standard deviation is *millions* of mm² (a 20 sqft std is
    1.86e6 mm²), so the smallest legal coefficient, 1, already prices a
    1-sigma miss at ~2 000 000: an order of magnitude above `VASTU_WEIGHT`,
    turning an intended nudge into the dominant term in the whole model.

    So the deviation is DIVIDED instead, by `std / SIZE_PRIOR_UNITS_PER_STD`,
    which re-expresses it in hundredths of a standard deviation. That is where
    the z-score-style weighting comes from: a room type the corpus is
    consistent about (small std) buys fewer mm² per unit, so the same absolute
    miss costs proportionally more than it would for a type the corpus itself
    disagrees on. Every room then shares one flat `SIZE_PRIOR_WEIGHT`.
    """
    terms: list[tuple[int, cp_model.IntVar]] = []
    for rv in room_vars:
        prior = get_size_prior(cfg, rv.room_type)
        if prior is None or prior.area_std <= 0:
            continue
        target_mm2 = round(prior.area_mean * _SQFT_TO_MM2)
        unit = max(1, round(prior.area_std * _SQFT_TO_MM2 / SIZE_PRIOR_UNITS_PER_STD))
        # Bounds derived from the room's own declared w/d domains, so these
        # vars are never wider than the values they can actually take.
        max_area = _var_max(rv.w) * _var_max(rv.d)
        max_dev = max(target_mm2, max_area)
        area = model.new_int_var(0, max_area, f"size_prior_area_{rv.room_id}")
        model.add_multiplication_equality(area, [rv.w, rv.d])
        dev = model.new_int_var(0, max_dev, f"size_prior_dev_{rv.room_id}")
        model.add_abs_equality(dev, area - target_mm2)
        dev_units = model.new_int_var(
            0, max_dev // unit, f"size_prior_devu_{rv.room_id}"
        )
        model.add_division_equality(dev_units, dev, unit)
        terms.append((SIZE_PRIOR_WEIGHT, dev_units))
    return terms


def _add_adjacency_prior_terms(
    model: cp_model.CpModel,
    cfg: PlotConfig,
    room_vars: list[_RoomVar],
) -> list[tuple[int, cp_model.IntVar]]:
    """Reward for room pairs the corpus finds typical actually sharing a wall.

    A BONUS, so the costs are negative and `base_objective` adds them with the
    same plain `+` the size penalty uses. Only built when
    `cfg.corpus_priors_enabled`; pairs the corpus never observed are skipped
    rather than given a zero-weight term.

    THIS DELIBERATELY DOES NOT REUSE `align_bools`.

    Those reify `e1 == e2` on a pair of edge coordinates — exact equality.
    The mixed `xhl`/`xlh`/`yhl`/`ylh` forms DO fire at the zero-gap case, but
    `add_no_overlap_2d` never forces a nonzero gap, so they capture only that
    one point of the `[0, _IWT_MM]` range genuine wall-sharing spans, and none
    of the eight forms tests perpendicular overlap — so even a corner-to-corner
    touch with zero shared wall length would score. Worse, the `xll`/`yhh`
    same-side forms hold between rooms at opposite ends of the plot that
    merely landed on one grid line and carry no adjacency information at all.
    Attaching a reward to this bucket would pay for coalignment, which
    `ALIGN_BONUS` already prices, and for corner touches, rather than for
    actually sharing a wall.

    What it reuses instead is the four-side shared-wall PATTERN the hard
    en-suite and stair-access constraints already use: facing edges within one
    wall thickness AND real overlap on the perpendicular axis.

    THE REIFICATION RUNS ONE WAY, AND THAT DIRECTION IS THE OPPOSITE OF THE
    PENALTY BLOCKS'.

    The toilet-repulsion block only ever forces its literal TRUE, because
    under a penalty the solver's incentive is to escape the cost and a free
    literal settles false on its own. A reward inverts that incentive: the
    solver wants the boolean true, so what has to be enforced is `share` ⇒ the
    geometry. Left free in that direction it would simply help itself to every
    bonus in the model. Nothing forces `share` false when the rooms ARE
    adjacent — the solver does that for us — which is why full reification
    would be wasted propagation here.
    """
    terms: list[tuple[int, cp_model.IntVar]] = []
    for i, a in enumerate(room_vars):
        for b in room_vars[i + 1 :]:
            # A wall cannot be shared across a slab. Also keeps this to one
            # term per unordered pair: the slice above never revisits (b, a).
            if a.floor != b.floor:
                continue
            freq = get_adjacency_prior(cfg, a.room_type, b.room_type)
            reward = round(ADJACENCY_PRIOR_WEIGHT * freq)
            if reward <= 0:
                continue
            share = model.new_bool_var(f"adjp_{a.room_id}_{b.room_id}")
            side_bools = []
            # (gap between the facing edges, then both rooms' extents on the
            # perpendicular axis) — same four cases as the en-suite block.
            cases = (
                (b.x - a.xe, a.y, a.ye, b.y, b.ye),  # a left of b
                (a.x - b.xe, a.y, a.ye, b.y, b.ye),  # a right of b
                (b.y - a.ye, a.x, a.xe, b.x, b.xe),  # a in front of b
                (a.y - b.ye, a.x, a.xe, b.x, b.xe),  # a behind b
            )
            for ci, (gap, a_lo, a_hi, b_lo, b_hi) in enumerate(cases):
                sb = model.new_bool_var(f"adjps_{a.room_id}_{b.room_id}_{ci}")
                model.add(gap >= 0).only_enforce_if(sb)
                model.add(gap <= _IWT_MM).only_enforce_if(sb)
                # The en-suite block's pair of half-tests rather than the
                # stair block's exact min/max: they agree whenever both rooms
                # are at least the threshold wide on that axis, which at
                # 100 mm every real room is, and this costs no extra IntVars.
                model.add(a_hi - b_lo >= _MIN_SHARE_OVERLAP_MM).only_enforce_if(sb)
                model.add(b_hi - a_lo >= _MIN_SHARE_OVERLAP_MM).only_enforce_if(sb)
                side_bools.append(sb)
            model.add_bool_or(side_bools).only_enforce_if(share)
            terms.append((-reward, share))
    return terms


def _zone_membership_bools(
    model: cp_model.CpModel,
    rv: _RoomVar,
    bands: _VastuBands,
    ox: int,
    oy: int,
    cache: _ZoneCache,
) -> tuple[list[cp_model.IntVar], list[cp_model.IntVar]]:
    """Reify which of the 3x3 zone bands a room's SOFT anchor point sits in.

    Returns `(cols, rows)`, each a triple of mutually-exclusive BoolVars, so
    "room is in zone `ZONE_GRID_ROAD_S[ri][ci]`" is `rows[ri] AND cols[ci]`.

    Carries NO cost policy of its own. It is shared verbatim by
    `_add_vastu_terms` (which charges disfavoured cells) and
    `_add_position_prior_terms` (which rewards corpus-favoured ones); each
    caller decides independently what a cell is worth, and neither restricts
    which rooms get reified. That separation is what lets position priors
    cover the half of corpus-known room types Vastu has no rule for at all
    (courtyard, verandah, foyer, terrace, ...) without a second, parallel
    transcription of the same band arithmetic.

    `cache` is keyed by `room_id` and is what keeps the reification to one
    build per room per solve when both callers run — CP-SAT reification is not
    free, and two independent copies would also let the two terms disagree
    about which zone a room is in.
    """
    hit = cache.get(rv.room_id)
    if hit is not None:
        return hit

    # SOFT path — the true-centroid expressions with the VARIABLE half-extent
    # replaced by the room's constant minimum one, so no decision variable but
    # the anchor survives into the steering predicate. See `_add_vastu_terms`'s
    # docstring for why the two points differ.
    min_w, min_d = _var_min(rv.w), _var_min(rv.d)
    east_soft = cp_model.LinearExpr.weighted_sum(
        [rv.x, rv.y], [2 * bands.ex, 2 * bands.ey]
    ) + (
        2 * ox * bands.ex
        + 2 * oy * bands.ey
        + bands.ec
        + min_w * bands.ex
        + min_d * bands.ey
    )
    north_soft = cp_model.LinearExpr.weighted_sum(
        [rv.x, rv.y], [2 * bands.nx, 2 * bands.ny]
    ) + (
        2 * ox * bands.nx
        + 2 * oy * bands.ny
        + bands.nc
        + min_w * bands.nx
        + min_d * bands.ny
    )

    cols = [model.new_bool_var(f"vcol{i}_{rv.room_id}") for i in range(3)]
    rows = [model.new_bool_var(f"vrow{i}_{rv.room_id}") for i in range(3)]
    # The three bands partition the line, so `exactly_one` plus the forward
    # implications is already a full reification — the reverse direction would
    # be redundant clauses.
    model.add_exactly_one(cols)
    model.add_exactly_one(rows)
    model.add(east_soft <= -bands.band - 1).only_enforce_if(cols[0])
    model.add(east_soft >= -bands.band).only_enforce_if(cols[1])
    model.add(east_soft <= bands.band - 1).only_enforce_if(cols[1])
    model.add(east_soft >= bands.band).only_enforce_if(cols[2])
    model.add(north_soft >= bands.band + 1).only_enforce_if(rows[0])
    model.add(north_soft <= bands.band).only_enforce_if(rows[1])
    model.add(north_soft >= -bands.band + 1).only_enforce_if(rows[1])
    model.add(north_soft <= -bands.band).only_enforce_if(rows[2])

    cache[rv.room_id] = (cols, rows)
    return cols, rows


def _add_position_prior_terms(
    model: cp_model.CpModel,
    cfg: PlotConfig,
    room_vars: list[_RoomVar],
    ox: int,
    oy: int,
    *,
    zone_cache: _ZoneCache | None = None,
) -> list[tuple[int, cp_model.IntVar]]:
    """Reward for a room landing in a zone its style's corpus histogram favours.

    A BONUS, so the costs are negative and `base_objective` adds them with a
    plain `+`, like the adjacency term. Only built when
    `cfg.corpus_priors_enabled`; zones the corpus never put this room type in
    are skipped rather than given a zero-weight term, which keeps this well
    under the O(rooms x 9) reifications a dense build would cost.

    THE REIFICATION IS SHARED WITH VASTU, NOT REBUILT.

    "Which of the 9 Vastu cells is this room in" is one question, and
    `_zone_membership_bools` answers it once per room per solve via
    `zone_cache`. This term is therefore live even with `vastu_enabled=False`,
    where `_add_vastu_terms` never runs and the cache arrives empty — the two
    flags are independent knobs, and a corpus position prior is not a Vastu
    opinion.

    THE ANCHOR POINT IS NOT THE CENTROID THE CORPUS WAS MINED FROM.

    `mine_position_priors` bucketed real bbox centroids; the shared reification
    reads Vastu's soft anchor (`x + min_w/2`, `y + min_d/2`) instead. Accepted
    deliberately, for the same reason Vastu accepts it and one more: a
    predicate containing `w`/`d` lets the solver buy its way into a zone by
    RESIZING rather than moving, and under a reward that gaming is if anything
    more attractive than under Vastu's penalty — grow into the rewarded cell,
    collect, and let `_add_size_prior_terms` eat the size cost. With `w`/`d`
    fixed out of the predicate there is no resize incentive at all. The
    anchor-vs-true-centroid gap this leaves is `(w - min_w) / 2`, bounded by
    half the room's SIZE SLACK (max extent minus min extent), not by its
    minimum extent -- a room pinned at its minimum has zero gap regardless of
    how large that minimum is. Only matters for a room already sitting on a
    band boundary.

    HARD-EXCLUDED CELLS ARE NEVER REWARDED.

    Kerala's corpus puts a toilet in C 47% of the time — its largest bucket,
    and a cell toilets are hard-excluded from. Paying there would price a
    placement the model forbids, and because the anchor and the true centroid
    (which the exclusion tests) can straddle a boundary, the solver could
    actually collect it. Skipped unconditionally, not just when
    `cfg.vastu_enabled`: these cells are the product's safety posture, and the
    corpus is not the right source to override it from.

    THE REIFICATION RUNS ONE WAY, TOWARD THE ZONE.

    Same direction as the adjacency reward and the opposite of Vastu's cost
    bool: under a reward the solver wants the literal true, so `zb` must imply
    the membership. Nothing forces `zb` false when the room IS in the zone —
    the objective does that for us.
    """
    if zone_cache is None:
        zone_cache = {}
    bands = _vastu_bands(
        _mm(cfg.plot_x_extent), _mm(cfg.plot_y_extent), resolve_north_angle(cfg)
    )
    terms: list[tuple[int, cp_model.IntVar]] = []

    for rv in room_vars:
        excluded = _vastu_hard_excluded_zones(rv.room_type)
        for ri in range(3):
            for ci in range(3):
                zone = ZONE_GRID_ROAD_S[ri][ci]
                if zone in excluded:
                    continue
                reward = round(
                    POSITION_PRIOR_WEIGHT * get_position_prior(cfg, rv.room_type, zone)
                )
                if reward <= 0:
                    continue
                # Built lazily, so a room the corpus knows nothing about (or
                # any room at all with no style set) costs no vars.
                cols, rows = _zone_membership_bools(
                    model, rv, bands, ox, oy, zone_cache
                )
                zb = model.new_bool_var(f"posp_{rv.room_id}_{zone}")
                model.add_implication(zb, rows[ri])
                model.add_implication(zb, cols[ci])
                terms.append((-reward, zb))

    return terms


def _add_vastu_terms(
    model: cp_model.CpModel,
    cfg: PlotConfig,
    room_vars: list[_RoomVar],
    ox: int,
    oy: int,
    *,
    zone_cache: _ZoneCache | None = None,
) -> list[tuple[int, cp_model.IntVar]]:
    """Reify each room's Vastu zone and return (cost, bool) objective terms.

    Rooms whose type has no rule are skipped entirely (no vars, no terms), the
    same exclusion `vastu_layout_score` applies: a room Vastu has no opinion
    about should carry zero weight rather than a middling one.

    THE SOFT TERM AND THE HARD EXCLUSION DELIBERATELY READ DIFFERENT POINTS.

    * The **hard exclusion** tests the TRUE centroid, `2*ox + 2*x + w` /
      `2*oy + 2*y + d`, exactly as `check_vastu` and `vastu_room_score` do. It
      is the guarantee users depend on ("a toilet is never in NE"), so it must
      agree with the scorer on the room's real centre — and a toilet that
      shrinks its way out of NE has genuinely left NE, which is a legitimate
      way to satisfy the constraint and is bounded below by the room's spec
      minima.
    * The **soft steering term** tests an anchor point, `2*ox + 2*x + min_w` /
      `2*oy + 2*y + min_d`, where `min_w`/`min_d` are the room's CONSTANT
      minimum extents. `w`/`d` are decision variables, so leaving them inside
      the soft predicate lets the solver buy a cheaper zone by SHRINKING the
      room instead of moving it: shrinking by D moves the centroid by D/2, and
      one zone change is worth up to `VASTU_WEIGHT` (300 000) against a growth
      reward of 1 per mm (`size_terms`), so shrinking wins wherever a band
      boundary is in reach. Measured before this split: a bedroom pinned at
      (3.0 m, 4.0 m) went 4.0 x 4.0 m -> 4.0 x 2.0 m, 16 m2 -> 8 m2, purely to
      drag its centroid from C into S. With `w`/`d` out of the predicate the
      only way to pay less is to move.

    The obvious simplification — one size-independent point for BOTH — is
    rejected on purpose: for a large room the anchor point can sit in a
    different cell than the true centre, which would let the hard exclusion
    leak. That trades a quality bug for a correctness bug.

    The asymmetry has one benign consequence: a room whose ANCHOR point falls
    in a hard-excluded cell pays no soft cost for that cell (no `zb` is built
    for it), while its true centroid is still forbidden from it outright.
    """
    if zone_cache is None:
        zone_cache = {}
    bands = _vastu_bands(
        _mm(cfg.plot_x_extent), _mm(cfg.plot_y_extent), resolve_north_angle(cfg)
    )
    terms: list[tuple[int, cp_model.IntVar]] = []

    for rv in room_vars:
        if _rule_for(rv.room_type) is None:
            continue
        excluded = _vastu_hard_excluded_zones(rv.room_type)

        # HARD path — the true centroid, size included:
        # cx2 = 2*ox + 2*x + w, cy2 = 2*oy + 2*y + d.
        east = cp_model.LinearExpr.weighted_sum(
            [rv.x, rv.w, rv.y, rv.d],
            [2 * bands.ex, bands.ex, 2 * bands.ey, bands.ey],
        ) + (2 * ox * bands.ex + 2 * oy * bands.ey + bands.ec)
        north = cp_model.LinearExpr.weighted_sum(
            [rv.x, rv.w, rv.y, rv.d],
            [2 * bands.nx, bands.nx, 2 * bands.ny, bands.ny],
        ) + (2 * ox * bands.nx + 2 * oy * bands.ny + bands.nc)

        # SOFT path — see `_zone_membership_bools`, which this shares with the
        # corpus position-prior term, and the docstring above for why the soft
        # anchor point and the hard centroid differ.
        cols, rows = _zone_membership_bools(model, rv, bands, ox, oy, zone_cache)

        for ri in range(3):
            for ci in range(3):
                zone = ZONE_GRID_ROAD_S[ri][ci]
                if zone in excluded:
                    # Structurally impossible, not penalised. Expressed against
                    # the CLOSED cell and on the TRUE centroid (`north`/`east`,
                    # not the `_soft` anchor point) rather than via the
                    # cols/rows bools above, so a boundary-sitting centroid is
                    # forbidden too — see `_vastu_escape_bounds`.
                    escapes = []
                    for expr, index, is_row in ((north, ri, True), (east, ci, False)):
                        for sign, bound in _vastu_escape_bounds(index, bands, is_row):
                            eb = model.new_bool_var(
                                f"vout_{rv.room_id}_{zone}_{'r' if is_row else 'c'}{sign}"
                            )
                            if sign < 0:
                                model.add(expr <= bound).only_enforce_if(eb)
                            else:
                                model.add(expr >= bound).only_enforce_if(eb)
                            escapes.append(eb)
                    model.add_bool_or(escapes)
                    continue
                row_b, col_b = rows[ri], cols[ci]
                cost = _vastu_zone_cost(rv.room_type, zone)
                if cost <= 0:
                    continue
                zb = model.new_bool_var(f"vz_{rv.room_id}_{zone}")
                # Half-reified: the objective is minimised and `cost` is
                # positive, so the solver only ever wants zb == 0; forcing
                # zb == 1 when the room IS in the zone is the direction that
                # has to hold.
                model.add_bool_or([row_b.Not(), col_b.Not(), zb])
                terms.append((cost, zb))

    return terms


def _solve_one(
    cfg: PlotConfig,
    ewt: float,
    room_defs: list[dict],
    specs: dict,
    stair_zone: str,  # "front" | "mid" | "rear"
    layout_id: str,
    layout_name: str,
    span_caps: dict[str, float] | None = None,
    seed_rooms: dict[str, Room] | None = None,
    deviation_weight: int = 0,
    vastu_steering: bool = True,
) -> Layout | None:
    """Run a single CP-SAT solve and return a Layout if successful.

    `vastu_steering=False` drops the Vastu zone vars, hard exclusions and
    objective terms even when `cfg.vastu_enabled` — the retry arm of
    `_vastu_feasibility_fallback`.

    Stage 2 closed-loop knobs:
    - span_caps: {"x": metres, "y": metres} — cap every room's dimension on
      that axis (structapi found a beam span the section iteration couldn't
      satisfy; splitting the span forces an extra aligned wall/grid line).
      Rooms whose spec minimum exceeds the cap keep their minimum — the
      loop's cap-exhaustion path reports those instead of going infeasible.
    - seed_rooms: room_id -> approved Room; adds CP-SAT hints AND a
      deviation penalty so the re-solve stays as close as possible to the
      user-approved plan (drift minimisation).
    """

    # Buildable plate dimensions in mm
    geom = _plate_geom_mm(cfg, ewt)
    if geom is None:
        return None
    bw, bd, ox, oy, quad_planes = geom

    if bw <= 0 or bd <= 0:
        return None

    model = cp_model.CpModel()
    room_vars: list[_RoomVar] = []
    gf_vars: list[_RoomVar] = []
    ff_vars: list[_RoomVar] = []
    # No-overlap intervals, one pair PER PART (a RECT room has exactly one).
    part_ivs: dict[int, tuple[list, list]] = {0: ([], []), 1: ([], [])}
    # Every part's (px, py, pw, pd) vars, both floors — retained for passes
    # that must constrain occupied rectangles rather than bounding boxes.
    part_vars: list[_PartVars] = []

    for rd in room_defs:
        rtype = rd["type"]
        spec = specs.get(rtype, specs.get("utility"))

        min_w = _mm(spec["min_width_m"])
        max_w = min(_mm(spec["max_width_m"]), bw)
        custom_min_area = rd.get("custom_min_area")
        raw_min_area = custom_min_area if custom_min_area else spec["min_area_sqm"]
        # 1 sqm = SCALE*SCALE mm² = 1_000_000 mm²
        min_area_mm2 = int(raw_min_area * SCALE * SCALE)
        max_area_mm2 = int(spec["max_area_sqm"] * SCALE * SCALE)
        # Wet rooms are capped at the generator's wet cap (4.6 sqm — rooms
        # above it get split into toilet+passage anyway) so the solver never
        # emits ballooned toilets; guard against custom minima above the cap.
        if rtype in _WET_TYPES:
            max_area_mm2 = max(min(max_area_mm2, _WET_AREA_CAP_MM2), min_area_mm2)

        min_d = _mm(spec["min_width_m"])  # use min_width as min depth too
        max_d = min(_mm(spec.get("max_width_m", 8.0)), bd)

        if span_caps:
            if span_caps.get("x"):
                max_w = min(max_w, max(_mm(span_caps["x"]), min_w))
            if span_caps.get("y"):
                max_d = min(max_d, max(_mm(span_caps["y"]), min_d))

        # Shape template (opt-in). `fit` carries the RECT bounds verbatim when
        # the feature is off OR the room type is not eligible OR the templated
        # variant would not fit the spec — so the default path builds exactly
        # the model that existed before shape templates.
        # `corpus_priors_enabled` is a SECOND, inner gate (Task 11): with it
        # off the expression is the pre-change one verbatim, and with
        # `allow_shape_templates` off the gate is not consulted at all.
        templated = (
            cfg.allow_shape_templates
            and rtype in _TEMPLATE_TYPES
            and (
                not cfg.corpus_priors_enabled
                or _shape_usage_allows_template(cfg, rd["id"], rtype)
            )
        )
        fit = _fit_template(
            _TEMPLATE_TYPES[rtype] if templated else "RECT",
            _TEMPLATE_RATIO,
            min_w,
            max_w,
            min_d,
            max_d,
            min_area_mm2,
            max_area_mm2,
        )

        if max_w < fit.min_w or max_d < fit.min_d:
            return None

        floor = rd["floor"]
        x = model.new_int_var(0, bw - fit.min_w, f"x_{rd['id']}")
        y = model.new_int_var(0, bd - fit.min_d, f"y_{rd['id']}")
        w = model.new_int_var(fit.min_w, max_w, f"w_{rd['id']}")
        d = model.new_int_var(fit.min_d, max_d, f"d_{rd['id']}")
        # OR-Tools 9.x: new_interval_var end must be an IntVar (affine), not x+w (two-var sum)
        ex = model.new_int_var(fit.min_w, bw, f"ex_{rd['id']}")
        ey = model.new_int_var(fit.min_d, bd, f"ey_{rd['id']}")
        model.add(ex == x + w)
        model.add(ey == y + d)
        x_ivs, y_ivs = part_ivs[0 if floor == 0 else 1]
        _add_room_parts(
            model,
            rd["id"],
            rtype,
            x,
            y,
            w,
            d,
            ex,
            ey,
            fit.template,
            fit.ratio,
            bw,
            bd,
            x_ivs,
            y_ivs,
            part_vars,
        )

        # Bounds: x+w <= bw, y+d <= bd
        model.add(x + w <= bw)
        model.add(y + d <= bd)

        # Area lower bound (linearised product via AddMultiplicationEquality)
        area = model.new_int_var(0, fit.max_area, f"area_{rd['id']}")
        model.add_multiplication_equality(area, [w, d])
        model.add(area >= fit.min_area)

        # Aspect ratio max 3:1
        model.add(w * 3 >= d)
        model.add(d * 3 >= w)

        # Templated rooms only: pin w/d to the template's millimetre grid so
        # every part offset divides exactly (see _add_room_parts).
        for dim, lo, hi, step, tag in (
            (w, fit.min_w, max_w, fit.grid_x, "wq"),
            (d, fit.min_d, max_d, fit.grid_y, "dq"),
        ):
            if step > 1:
                q = model.new_int_var(-(-lo // step), hi // step, f"{tag}_{rd['id']}")
                model.add(dim == step * q)

        rv = _RoomVar(
            room_id=rd["id"],
            room_type=rtype,
            room_name=rd["name"],
            floor=floor,
            x=x,
            y=y,
            w=w,
            d=d,
            xe=ex,
            ye=ey,
            template=fit.template,
            shape_ratio=fit.ratio,
            open_sides=frozenset(rd.get("open_sides", ())),
        )
        room_vars.append(rv)
        (gf_vars if floor == 0 else ff_vars).append(rv)

    # Quadrilateral half-plane constraints — all 4 corners of each room inside inset polygon
    if quad_planes:
        for rv in room_vars:
            for corner_x, corner_y in [
                (rv.x, rv.y),
                (rv.x + rv.w, rv.y),
                (rv.x, rv.y + rv.d),
                (rv.x + rv.w, rv.y + rv.d),
            ]:
                for dx, dy, rhs in quad_planes:
                    model.add(dx * corner_y - dy * corner_x >= rhs)

    # No-overlap per floor, over PARTS rather than rooms: a RECT room still
    # contributes exactly one interval pair (so this is the pre-template model
    # when no template is active), while a templated room contributes one per
    # part and may therefore interlock with its neighbours.
    for x_ivs, y_ivs in part_ivs.values():
        if x_ivs:
            model.add_no_overlap_2d(x_ivs, y_ivs)

    # Rectilinear plot: keep every part out of the off-plot notch. A no-op
    # (returns before touching the model) on the default RECT plot.
    _forbid_notch(model, cfg, part_vars, ox_mm=ox, oy_mm=oy, bw=bw, bd=bd, ewt=ewt)

    # Staircase alignment across floors
    gf_stairs = [v for v in gf_vars if v.room_type == "staircase"]
    ff_stairs = [v for v in ff_vars if v.room_type == "staircase"]
    if gf_stairs and ff_stairs:
        gs, fs = gf_stairs[0], ff_stairs[0]
        model.add(gs.x == fs.x)
        model.add(gs.y == fs.y)
        model.add(gs.w == fs.w)
        model.add(gs.d == fs.d)

    # Symmetry-breaking: force staircase to a third of plot depth
    if gf_stairs:
        stair = gf_stairs[0]
        third = bd // 3
        if stair_zone == "front":
            model.add(stair.y + stair.d <= third)
        elif stair_zone == "rear":
            model.add(stair.y >= 2 * third)
        else:  # mid
            model.add(stair.y >= third)
            model.add(stair.y + stair.d <= 2 * third)

    # Hard en-suite adjacency: each en-suite must share a wall segment with
    # its bedroom — facing edges within one internal wall thickness AND
    # perpendicular overlap >= 900 mm (door width), OR'd over the four side
    # cases (mirrors the reified align_bools pattern below).
    by_id = {rv.room_id: rv for rv in room_vars}
    for rd in room_defs:
        bed_id = rd.get("attached_to")
        if not bed_id:
            continue
        ens = by_id.get(rd["id"])
        bed = by_id.get(bed_id)
        if ens is None or bed is None or ens.floor != bed.floor:
            continue
        side_bools = []
        # (gap, a_lo, a_hi, b_lo, b_hi): gap between the facing edges, then
        # the two rooms' extents on the perpendicular axis.
        cases = (
            (bed.x - ens.xe, ens.y, ens.ye, bed.y, bed.ye),  # ens left of bed
            (ens.x - bed.xe, ens.y, ens.ye, bed.y, bed.ye),  # ens right of bed
            (bed.y - ens.ye, ens.x, ens.xe, bed.x, bed.xe),  # ens in front
            (ens.y - bed.ye, ens.x, ens.xe, bed.x, bed.xe),  # ens behind
        )
        for ci, (gap, a_lo, a_hi, b_lo, b_hi) in enumerate(cases):
            sb = model.new_bool_var(f"ens_{ens.room_id}_{ci}")
            model.add(gap >= 0).only_enforce_if(sb)
            model.add(gap <= _IWT_MM).only_enforce_if(sb)
            model.add(a_hi - b_lo >= _ENSUITE_MIN_OVERLAP_MM).only_enforce_if(sb)
            model.add(b_hi - a_lo >= _ENSUITE_MIN_OVERLAP_MM).only_enforce_if(sb)
            side_bools.append(sb)
        model.add_bool_or(side_bools)

    # Hard staircase-access adjacency: every stair core shares at least a
    # door's worth of wall with a circulation room on its own floor. Same
    # four-side reified pattern as the en-suite block above, but the overlap
    # is measured exactly (min of the far edges minus max of the near ones)
    # rather than via the en-suite block's looser pair of half-tests — here
    # the number IS the door-fit threshold plan_geometry will re-apply, so an
    # approximation that can pass at 0.9 m would put us straight back into the
    # production failure this constraint exists to prevent.
    for floor_no in {rv.floor for rv in room_vars}:
        on_floor = [rv for rv in room_vars if rv.floor == floor_no]
        stairs = [rv for rv in on_floor if rv.room_type == "staircase"]
        targets = [rv for rv in on_floor if rv.room_type in _CIRCULATION_TYPES]
        # A floor with no circulation room at all (e.g. an all-bedroom upper
        # plate) would make this infeasible; fall back to any ordinary room
        # rather than fail the solve — a bedroom door is poor practice, an
        # unsolvable plan is worse.
        if not targets:
            targets = [
                rv
                for rv in on_floor
                if rv.room_type not in _WET_TYPES
                and rv.room_type not in _PARKING_TYPES
                and rv.room_type != "staircase"
            ]
        if not stairs or not targets:
            continue
        for st in stairs:
            side_bools = []
            for tgt in targets:
                cases = (
                    (tgt.x - st.xe, st.y, st.ye, tgt.y, tgt.ye),  # stair left
                    (st.x - tgt.xe, st.y, st.ye, tgt.y, tgt.ye),  # stair right
                    (tgt.y - st.ye, st.x, st.xe, tgt.x, tgt.xe),  # stair in front
                    (st.y - tgt.ye, st.x, st.xe, tgt.x, tgt.xe),  # stair behind
                )
                for ci, (gap, a_lo, a_hi, b_lo, b_hi) in enumerate(cases):
                    tag = f"stair_{st.room_id}_{tgt.room_id}_{ci}"
                    sb = model.new_bool_var(tag)
                    model.add(gap >= 0).only_enforce_if(sb)
                    model.add(gap <= _IWT_MM).only_enforce_if(sb)
                    lo = model.new_int_var(0, max(bw, bd), f"lo_{tag}")
                    hi = model.new_int_var(0, max(bw, bd), f"hi_{tag}")
                    model.add_max_equality(lo, [a_lo, b_lo])
                    model.add_min_equality(hi, [a_hi, b_hi])
                    model.add(hi - lo >= _STAIR_DOOR_MIN_OVERLAP_MM).only_enforce_if(sb)
                    side_bools.append(sb)
            model.add_bool_or(side_bools)

    # ── Objective: pull preferred-adjacency pairs together ───────────────────
    # The previous "objective" forced adj==1 and maximized a constant — the
    # solver returned the first feasible packing with zero optimization
    # pressure. Minimize the points-weighted Manhattan distance between the
    # centres of preferred pairs instead (a linear, solver-friendly proxy
    # for shared-wall adjacency).
    dist_terms = []

    type_to_var: dict[str, list[_RoomVar]] = {}
    for rv in room_vars:
        type_to_var.setdefault(rv.room_type, []).append(rv)

    for t1, t2, pts in _ADJACENCY_PAIRS:
        for a in type_to_var.get(t1, []):
            for b in type_to_var.get(t2, []):
                if a.floor != b.floor:
                    continue
                pair = f"{a.room_id}_{b.room_id}"
                # doubled centres keep everything integral: 2*cx = 2x + w
                dxv = model.new_int_var(0, 2 * bw, f"dx_{pair}")
                dyv = model.new_int_var(0, 2 * bd, f"dy_{pair}")
                model.add_abs_equality(dxv, 2 * a.x + a.w - 2 * b.x - b.w)
                model.add_abs_equality(dyv, 2 * a.y + a.d - 2 * b.y - b.d)
                dist_terms.append(pts * (dxv + dyv))

    # Secondary pressure: grow rooms toward their spec max (w+d is a linear
    # size proxy). Without this the solver returns minimum-area rooms and
    # dumps all slack into leftover space (the "5 sqm Study, 38 sqm Passage"
    # bug). Adjacency terms are points-weighted per mm, so they still dominate.
    # Wet rooms are excluded — growth pressure ballooned toilets to their
    # 6 sqm spec max; they get the opposite (shrink) pressure instead so
    # they settle at min-compliant size.
    size_terms = [rv.w + rv.d for rv in room_vars if rv.room_type not in _WET_TYPES]
    wet_shrink_terms = [
        WET_SHRINK_WEIGHT * (rv.w + rv.d)
        for rv in room_vars
        if rv.room_type in _WET_TYPES
    ]

    # ── Soft toilet-placement penalties ──────────────────────────────────────
    # Common (non-en-suite) toilets/WCs: penalise the front band facing the
    # road (heavier opposite the gate/main door) and sharing a wall with the
    # staircase or parking. Soft terms only — hard versions go infeasible on
    # small plots. En-suites are exempt: their position follows the bedroom.
    penalty_terms = []
    ensuite_ids = {rd["id"] for rd in room_defs if rd.get("attached_to")}
    common_wet = [
        rv
        for rv in room_vars
        if rv.room_type in ("toilet", "wc_only") and rv.room_id not in ensuite_ids
    ]
    repel_targets = [
        rv
        for rv in room_vars
        if rv.room_type == "staircase" or rv.room_type in _PARKING_TYPES
    ]
    for rv in common_wet:
        # (a) front band: toilet within the front 25% of the plate depth
        # (road side is y-min post-rotation). Tested on the FRONT EDGE, not
        # the centre — a centre test is gameable by growing the room until
        # the centre escapes the band (measured: toilets inflated to 6 sqm
        # to dodge the penalty). Band at 30% so post-solve snap jitter
        # (±SNAP_TOL_M) can't push a compliant room back under 25%.
        fb = model.new_bool_var(f"front_{rv.room_id}")
        model.add(10 * rv.y <= 3 * bd).only_enforce_if(fb)
        model.add(10 * rv.y > 3 * bd).only_enforce_if(fb.Not())
        penalty_terms.append(TOILET_FRONT_PENALTY * fb)

        # heavier when centre-x also sits in the middle third of the plate
        # width — straight opposite the compound gate / main door axis
        m1 = model.new_bool_var(f"midx1_{rv.room_id}")
        model.add(3 * (2 * rv.x + rv.w) >= 2 * bw).only_enforce_if(m1)
        model.add(3 * (2 * rv.x + rv.w) < 2 * bw).only_enforce_if(m1.Not())
        m2 = model.new_bool_var(f"midx2_{rv.room_id}")
        model.add(3 * (2 * rv.x + rv.w) <= 4 * bw).only_enforce_if(m2)
        model.add(3 * (2 * rv.x + rv.w) > 4 * bw).only_enforce_if(m2.Not())
        fbm = model.new_bool_var(f"frontmid_{rv.room_id}")
        model.add_bool_and([fb, m1, m2]).only_enforce_if(fbm)
        model.add_bool_or([fb.Not(), m1.Not(), m2.Not()]).only_enforce_if(fbm.Not())
        penalty_terms.append(TOILET_FRONT_MID_PENALTY * fbm)

        # (b)+(c) repulsion: reified "shares a wall with staircase/parking"
        for other in repel_targets:
            if other.floor != rv.floor:
                continue
            weight = (
                TOILET_STAIR_PENALTY
                if other.room_type == "staircase"
                else TOILET_PARKING_PENALTY
            )
            share = model.new_bool_var(f"rep_{rv.room_id}_{other.room_id}")
            rep_cases = (
                (other.x - rv.xe, rv.y, rv.ye, other.y, other.ye),
                (rv.x - other.xe, rv.y, rv.ye, other.y, other.ye),
                (other.y - rv.ye, rv.x, rv.xe, other.x, other.xe),
                (rv.y - other.ye, rv.x, rv.xe, other.x, other.xe),
            )
            # One-direction encoding (exact under minimization): each literal
            # is only forced TRUE when its inequality holds (lb=0 ⇒ inequality
            # violated), and the clause forces `share` when all four hold.
            # The solver zeroes any free literal to dodge the penalty, so no
            # spurious payment — at half the enforcement cost of full
            # reification (which measurably starved the search budget).
            for ci, (gap, a_lo, a_hi, b_lo, b_hi) in enumerate(rep_cases):
                lits = []
                for li, (expr, lo) in enumerate(
                    (
                        (gap, 0),
                        (_REPULSION_GAP_MM - gap, 0),
                        (a_hi - b_lo, _MIN_SHARE_OVERLAP_MM),
                        (b_hi - a_lo, _MIN_SHARE_OVERLAP_MM),
                    )
                ):
                    lb = model.new_bool_var(
                        f"repl_{rv.room_id}_{other.room_id}_{ci}_{li}"
                    )
                    model.add(expr < lo).only_enforce_if(lb.Not())
                    lits.append(lb)
                model.add_bool_or([lb.Not() for lb in lits] + [share])
            penalty_terms.append(weight * share)

    # ── Soft parking-placement penalty ────────────────────────────────────────
    # Parking has no positional constraint otherwise and can end up boxed in
    # with no direct road/exterior access. Soft term only, matching the
    # toilet front-band precedent above — a hard rv.y == 0 constraint would
    # be an even higher infeasibility risk than the toilet case already
    # rejected as hard, given parking's larger min footprint.
    for rv in room_vars:
        if rv.room_type not in _PARKING_TYPES:
            continue
        not_road = model.new_bool_var(f"not_road_{rv.room_id}")
        model.add(rv.y > 0).only_enforce_if(not_road)
        model.add(rv.y <= 0).only_enforce_if(not_road.Not())
        penalty_terms.append(PARKING_ROAD_PENALTY * not_road)

    # Wall-coalignment bonus: reified equalities between room edge
    # coordinates — same floor (partitions land on shared grid lines, no
    # mid-span T columns) and cross-floor (GF/FF columns stack). Without
    # this, size_terms grows every room independently and adjacent rooms
    # almost never share a wall line (pro-tester regression, 2026-07-16).
    align_bools = []
    cross_floor_align_bools = []
    for i, a in enumerate(room_vars):
        for b in room_vars[i + 1 :]:
            if a.room_type == "staircase" and b.room_type == "staircase":
                continue  # already hard-equal across floors
            bucket = align_bools if a.floor == b.floor else cross_floor_align_bools
            # All 4 end combos per axis: rooms pack with gaps anywhere in
            # [0, iwt+], so a shared wall line shows up as lo↔lo, hi↔hi or
            # the mixed hi↔lo forms depending on which side of the gap each
            # room sits.
            for e1, e2, tag in (
                (a.x, b.x, "xll"),
                (a.xe, b.xe, "xhh"),
                (a.xe, b.x, "xhl"),
                (a.x, b.xe, "xlh"),
                (a.y, b.y, "yll"),
                (a.ye, b.ye, "yhh"),
                (a.ye, b.y, "yhl"),
                (a.y, b.ye, "ylh"),
            ):
                bv = model.new_bool_var(f"al_{a.room_id}_{b.room_id}_{tag}")
                model.add(e1 == e2).only_enforce_if(bv)
                model.add(e1 != e2).only_enforce_if(bv.Not())
                bucket.append(bv)

    # Drift minimisation (closed-loop re-solve): hint the solver toward the
    # approved geometry and penalise deviation from it, so a structural
    # constraint changes as little of the user-approved plan as possible.
    deviation_terms = []
    if seed_rooms and deviation_weight > 0:
        for rv in room_vars:
            seed = seed_rooms.get(rv.room_id)
            if seed is None:
                continue
            targets = (
                (rv.x, _mm(seed.x) - ox, bw),
                (rv.y, _mm(seed.y) - oy, bd),
                (rv.w, _mm(seed.width), bw),
                (rv.d, _mm(seed.depth), bd),
            )
            for ti, (var, target, cap) in enumerate(targets):
                clamped = min(max(target, 0), cap)
                model.add_hint(var, clamped)
                dv = model.new_int_var(0, cap, f"dev_{rv.room_id}_{ti}")
                model.add_abs_equality(dv, var - clamped)
                deviation_terms.append(dv)

    # ── Vastu steering ───────────────────────────────────────────────────────
    # Soft costs (plus the data-derived hard exclusions added inside) that pull
    # each ruled room toward a zone its rule prefers. Part of `base_objective`
    # rather than `penalty_terms` on purpose: `penalty_terms` is what the
    # phase-1 warm start deliberately omits, and Vastu placement is exactly the
    # kind of whole-plan trade phase 1 should already be making.
    vastu_terms: list[tuple[int, cp_model.IntVar]] = []
    # Shared by the Vastu terms and the corpus position priors: both ask which
    # of the 9 zone cells a room is in, and neither may reify it twice.
    zone_cache: _ZoneCache = {}
    if cfg.vastu_enabled and vastu_steering:
        vastu_terms = _add_vastu_terms(
            model, cfg, room_vars, ox, oy, zone_cache=zone_cache
        )

    # ── Corpus-mined priors ──────────────────────────────────────────────────
    size_prior_terms: list[tuple[int, cp_model.IntVar]] = []
    adjacency_prior_terms: list[tuple[int, cp_model.IntVar]] = []
    position_prior_terms: list[tuple[int, cp_model.IntVar]] = []
    if cfg.corpus_priors_enabled:
        size_prior_terms = _add_size_prior_terms(model, cfg, room_vars)
        adjacency_prior_terms = _add_adjacency_prior_terms(model, cfg, room_vars)
        position_prior_terms = _add_position_prior_terms(
            model, cfg, room_vars, ox, oy, zone_cache=zone_cache
        )

    base_objective = (
        sum(dist_terms)
        - sum(size_terms)
        - ALIGN_BONUS * sum(align_bools)
        - CROSS_FLOOR_ALIGN_BONUS * sum(cross_floor_align_bools)
        + sum(wet_shrink_terms)
        + deviation_weight * sum(deviation_terms)
        + sum(cost * var for cost, var in vastu_terms)
        + sum(cost * var for cost, var in size_prior_terms)
        # Costs are already negative — a bonus, like the align terms above.
        + sum(cost * var for cost, var in adjacency_prior_terms)
        + sum(cost * var for cost, var in position_prior_terms)
    )

    # ── Solve ─────────────────────────────────────────────────────────────────
    def _make_solver(
        det_budget: float, wall_budget: float = SOLVE_TIME_S
    ) -> cp_model.CpSolver:
        s = cp_model.CpSolver()
        s.parameters.max_time_in_seconds = wall_budget
        # Machine-independent work budget: on fast machines this binds so
        # repeated runs return the SAME incumbent; on slow machines (CI
        # runners, cold Cloud Run) the wall-clock cap above binds so runtime
        # never grows. Wall-clock-only budgets made solution quality depend
        # on machine speed — the source of CI-only/dev-only test failures in
        # the grid-alignment and leftover-gap suites.
        s.parameters.max_deterministic_time = det_budget
        s.parameters.num_search_workers = 1  # deterministic single-thread
        return s

    # Two-phase solve when placement penalties are active: the single-thread
    # deterministic budget is too small to escape a first incumbent that
    # pays the (huge) penalties — measured: 450k of penalties stayed paid,
    # or hint-repair burned the whole budget (status UNKNOWN) when guessed
    # partial hints didn't fit. Phase 1 solves the well-behaved penalty-free
    # model; its solution is a complete, feasible hint for phase 2, which
    # then spends its entire budget relocating toilets out of penalty zones.
    if penalty_terms and not seed_rooms:
        model.minimize(base_objective)
        pre = _make_solver(det_budget=PHASE1_DET_BUDGET, wall_budget=PHASE1_TIME_S)
        pre_status = pre.solve(model)
        if pre_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Hint everything EXCEPT the common toilets' and parking's
            # positions: with the rest of the plan anchored, phase 2 reduces
            # to re-placing just those rooms — a subproblem small enough to
            # escape the penalty zones inside the budget (fully-hinted runs
            # kept them glued to their penalised phase-1 spot).
            free_ids = {rv.room_id for rv in common_wet} | {
                rv.room_id for rv in room_vars if rv.room_type in _PARKING_TYPES
            }
            model.clear_hints()
            for rv in room_vars:
                hinted = (
                    (rv.w, rv.d) if rv.room_id in free_ids else (rv.x, rv.y, rv.w, rv.d)
                )
                for var in hinted:
                    model.add_hint(var, pre.value(var))

    model.minimize(base_objective + sum(penalty_terms))
    solver = _make_solver(det_budget=PHASE2_DET_BUDGET)

    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    # ── Extract solution into Layout ──────────────────────────────────────────
    gf_rooms: list[Room] = []
    ff_rooms: list[Room] = []

    for rv in room_vars:
        rx = ox / SCALE + solver.value(rv.x) / SCALE
        ry = oy / SCALE + solver.value(rv.y) / SCALE
        rw = solver.value(rv.w) / SCALE
        rd = solver.value(rv.d) / SCALE
        room = Room(
            id=rv.room_id,
            name=rv.room_name,
            type=rv.room_type,
            x=round(rx, 3),
            y=round(ry, 3),
            width=round(rw, 3),
            depth=round(rd, 3),
            template=rv.template,
            shape_ratio=rv.shape_ratio,
            open_sides=rv.open_sides,
        )
        (gf_rooms if rv.floor == 0 else ff_rooms).append(room)

    # Structural columns: only at exterior-ring junctions, true 4-way
    # crossings, or interior T-junctions whose removal would leave a beam
    # span exceeding max_beam_span_m — NOT at every room corner (that placed
    # a column on both sides of every internal partition, producing dense,
    # visually cluttered "intermediate" grids that add no structural value).
    def _wall_junction_cols(rooms: list[Room]) -> list[Column]:
        if not rooms:
            return []
        from app.engine.geometry import buildable_polygon
        from app.engine.plan_geometry import (
            derive_columns,
            derive_junctions,
            derive_walls,
        )

        buildable = buildable_polygon(cfg)
        walls = derive_walls(rooms, buildable, ewt=ewt)
        junctions = derive_junctions(walls)
        columns = derive_columns(walls, junctions=junctions, rooms=rooms)
        return [Column(x=c.cx, y=c.cy) for c in columns]

    from .compliance import check, load_rules
    from .models import ComplianceResult

    rules = load_rules()

    def _build_layout(gf_list: list[Room], ff_list: list[Room]) -> Layout:
        layout = Layout(
            id=layout_id,
            name=layout_name,
            ground_floor=FloorPlan(
                floor=0,
                floor_type="ground",
                rooms=gf_list,
                columns=_wall_junction_cols(gf_list),
            ),
            first_floor=FloorPlan(
                floor=1,
                floor_type="first",
                rooms=ff_list,
                columns=_wall_junction_cols(ff_list),
            ),
            compliance=ComplianceResult(passed=True),
        )
        # Bye-law compliance only. Vastu is deliberately NOT checked here: it is
        # a cultural preference, and running it on this path put its findings in
        # `compliance.violations`, flipped `passed`, and made the `return None`
        # below delete the solve result — the same gate Task 16 removed from the
        # archetype path. `generator._attach_vastu` records Vastu as a warning
        # plus a graded score for every layout, solver and archetype alike, on
        # the final post-fill geometry.
        layout.compliance = check(layout, cfg, rules)
        return layout

    # Post-solve snap: coalesce residual near-aligned wall lines (the
    # objective rewards exact alignment, but the solver may stop at a
    # near-miss under its time budget). Falls back to the unsnapped rooms
    # if snapping breaks compliance — the snap is best-effort by design.
    min_dims = {}
    solved_areas = {r.id: r.area for r in gf_rooms + ff_rooms}
    for rd2 in room_defs:
        spec2 = specs.get(rd2["type"], specs.get("utility"))
        # A templated room's narrow leg is `shape_ratio` of the bbox, so the
        # BBOX minimum the snap pass must respect is that much larger — the
        # same inflation _fit_template applied in the model. 1.0 for RECT, so
        # the numbers are unchanged on the default path.
        rv2 = by_id.get(rd2["id"])
        leg = rv2.shape_ratio if rv2 is not None and rv2.template != "RECT" else 1.0
        min_dims[rd2["id"]] = {
            "min_width_m": spec2["min_width_m"] / leg,
            "min_depth_m": spec2["min_width_m"] / leg,
            "min_area_sqm": rd2.get("custom_min_area") or spec2["min_area_sqm"],
        }
        # Wet rooms leave the solve at min-compliant size (WET_SHRINK_WEIGHT)
        # but snapping has no size objective and can inflate them by up to
        # SNAP_TOL_M per edge — cap snap growth so they stay toilet-sized.
        if rd2["type"] in _WET_TYPES:
            min_dims[rd2["id"]]["max_area_sqm"] = round(
                min(
                    spec2["max_area_sqm"],
                    _WET_AREA_CAP_MM2 / (SCALE * SCALE),
                    solved_areas.get(rd2["id"], 1e9) * 1.35,
                ),
                3,
            )
    snapped_gf, snapped_ff = snap_rooms_to_shared_grid(
        [gf_rooms, ff_rooms],
        min_dims,
        plate_bounds=(
            (ox / SCALE, (ox + bw) / SCALE),
            (oy / SCALE, (oy + bd) / SCALE),
        ),
    )

    layout = _build_layout(snapped_gf, snapped_ff)
    if not layout.compliance.passed and (
        snapped_gf != gf_rooms or snapped_ff != ff_rooms
    ):
        layout = _build_layout(gf_rooms, ff_rooms)

    return layout if layout.compliance.passed else None


def resolve_with_constraints(
    cfg: PlotConfig,
    ewt: float,
    approved: Layout,
    span_caps: dict[str, float],
    deviation_weight: int = 3,
) -> Layout | None:
    """Closed-loop re-solve: same room programme as the approved layout,
    with structural span caps applied and drift from the approved geometry
    minimised (hints + deviation penalty). Returns None when infeasible."""
    specs = _load_specs()
    room_defs = _build_room_list(cfg, specs)
    seed_rooms = {
        r.id: r for r in approved.ground_floor.rooms + approved.first_floor.rooms
    }

    stair_zone = "mid"
    stair = next(
        (r for r in approved.ground_floor.rooms if r.type == "staircase"), None
    )
    if stair is not None:
        by1 = cfg.setback_front + ewt
        bd_m = cfg.plot_y_extent - cfg.setback_front - cfg.setback_rear - 2 * ewt
        if bd_m > 0:
            rel = (stair.y + stair.depth / 2 - by1) / bd_m
            stair_zone = "front" if rel < 1 / 3 else ("mid" if rel < 2 / 3 else "rear")

    try:
        return _solve_one(
            cfg,
            ewt,
            room_defs,
            specs,
            stair_zone,
            approved.id,
            approved.name,
            span_caps=span_caps,
            seed_rooms=seed_rooms,
            deviation_weight=deviation_weight,
        )
    except Exception:
        return None


def _vastu_feasibility_fallback(
    cfg: PlotConfig, solve: Callable[[bool], Layout | None]
) -> Layout | None:
    """Run `solve(True)`, and if Vastu steering cost us the layout, retry without.

    Vastu is a preference. Returning no plan at all because the zone
    constraints made the search miss its deterministic budget is strictly worse
    than returning a Vastu-imperfect plan, and it does happen: at the wrong
    coefficient scale two of three orientations went UNKNOWN (see
    `_VASTU_BAND_SCALE`). The retry costs a second solve only in the case that
    would otherwise have returned None, so a healthy plot never pays for it.
    """
    layout = solve(True)
    if layout is not None or not cfg.vastu_enabled:
        return layout
    return solve(False)


def solve_layout(cfg: PlotConfig, ewt: float | None = None) -> Layout | None:
    """One solve, centre-staircase zone. Returns None when infeasible.

    `solve_layouts` runs the same solve three times with the staircase pinned
    to a different third of the plate; callers that want *a* layout (and tests
    that want one reproducible layout) should not pay for all three.
    """
    if ewt is None:
        from .compliance import load_rules

        ewt = load_rules()["external_wall_thickness_mm"] / SCALE
    specs = _load_specs()
    room_defs = _build_room_list(cfg, specs)
    # Outside the try: a notch that cannot house the programme is a user-input
    # error and must reach the caller, not be flattened into `None`.
    validate_plot_envelope(cfg, ewt, room_defs, specs)

    def _run(vastu_steering: bool) -> Layout | None:
        try:
            return _solve_one(
                cfg,
                ewt,
                room_defs,
                specs,
                "mid",
                "S2",
                "Layout S2 — Centre Staircase",
                vastu_steering=vastu_steering,
            )
        except Exception:
            return None

    return _vastu_feasibility_fallback(cfg, _run)


def solve_layouts(cfg: PlotConfig, ewt: float) -> list[Layout]:
    """Generate up to 3 diverse solver layouts. Returns empty list on failure.

    Raises ValueError (rather than returning []) when the plot's notch cannot
    house the requested programme — see `validate_plot_envelope`.
    """
    specs = _load_specs()
    room_defs = _build_room_list(cfg, specs)
    validate_plot_envelope(cfg, ewt, room_defs, specs)

    zones = [
        ("front", "S1", "Layout S1 — Front Staircase"),
        ("mid", "S2", "Layout S2 — Centre Staircase"),
        ("rear", "S3", "Layout S3 — Rear Staircase"),
    ]

    results: list[Layout] = []
    for zone, lid, lname in zones:

        def _run(
            vastu_steering: bool,
            zone: str = zone,
            lid: str = lid,
            lname: str = lname,
        ) -> Layout | None:
            try:
                return _solve_one(
                    cfg,
                    ewt,
                    room_defs,
                    specs,
                    zone,
                    lid,
                    lname,
                    vastu_steering=vastu_steering,
                )
            except Exception:
                return None  # solver failure → skip this zone

        layout = _vastu_feasibility_fallback(cfg, _run)
        if layout is not None:
            results.append(layout)

    return results
