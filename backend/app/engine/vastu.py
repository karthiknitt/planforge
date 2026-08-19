"""Vastu Shastra compliance checker for G+1 residential layouts.

Vastu Shastra divides a plot into 8 directional zones + centre (Brahmasthan).
Room placement is evaluated against classical Vastu principles for Indian homes.

Coordinate system in PlanForge:
  x=0 is the left edge, x=max is the right edge.
  y=0 is the road-facing front, y=max is the rear.

Orientation is expressed as a single continuous angle, `north_angle_deg`:
the CLOCKWISE angle from the plot's +y axis to true north. The four road
sides are the four axis-aligned special cases of it (see
`ROAD_SIDE_NORTH_ANGLE_DEG`):

  roadSide="S" (0°, most common — house faces South):
    y=0 → South,  y=max → North
    x=0 → West,   x=max → East

  roadSide="E" (90°):
    y=0 → East,   y=max → West
    x=0 → South,  x=max → North

  roadSide="N" (180°):
    y=0 → North,  y=max → South
    x=0 → East,   x=max → West   (east/west swap when facing North)

  roadSide="W" (270°):
    y=0 → West,   y=max → East
    x=0 → North,  x=max → South  (north/south swap)

Angles between these are supported directly — 24% of the reference corpus has
a north arrow that is not axis-aligned, and such a plot must not be snapped to
the nearest cardinal orientation.
"""

from __future__ import annotations

import math

from .compliance import load_rules
from .models import FloorPlan, Layout, PlotConfig, Room

# ── Zone labels (compass + centre) ──────────────────────────────────────────
#   Grid layout (3×3):
#   NW | N | NE
#   W  | C | E
#   SW | S | SE
#
# Indexed as zone_grid[row][col] where
#   row 0 = rear (high y relative to road), row 2 = front (low y)
#   col 0 = left side,                       col 2 = right side

ZONE_GRID_ROAD_S = [
    ["NW", "N", "NE"],  # rear zone (y near plot_length)
    ["W", "C", "E"],  # middle zone
    ["SW", "S", "SE"],  # front zone (y near 0)
]

# Zone grid rotated for each road direction
# For road N: y=0 is North, y=max is South → grid flips vertically and L/R swap
ZONE_GRID_ROAD_N = [
    ["SE", "S", "SW"],
    ["E", "C", "W"],
    ["NE", "N", "NW"],
]

# For road E: y=0 is East, y=max is West; +x (right in plan) is +y turned 90°
# clockwise on the compass, i.e. North. So the front row is the East third.
ZONE_GRID_ROAD_E = [
    ["SW", "W", "NW"],  # rear (y near plot_length) = West
    ["S", "C", "N"],
    ["SE", "E", "NE"],  # front (y near 0) = East
]

# For road W: y=0 is West, y=max is East, +x is South.
ZONE_GRID_ROAD_W = [
    ["NE", "E", "SE"],  # rear (y near plot_length) = East
    ["N", "C", "S"],
    ["NW", "W", "SW"],  # front (y near 0) = West
]

ZONE_GRIDS: dict[str, list[list[str]]] = {
    "S": ZONE_GRID_ROAD_S,
    "N": ZONE_GRID_ROAD_N,
    "E": ZONE_GRID_ROAD_E,
    "W": ZONE_GRID_ROAD_W,
}

# The four rotated grids are no longer *used* to resolve a zone — `zone_for_point`
# is the only engine, and it reads ZONE_GRID_ROAD_S alone. The other three are kept
# as the reference encoding of the four axis-aligned orientations: the angles below
# were derived from them, and `tests/test_vastu_zones.py` pins the engine to
# reproduce all 9 cells of all 4 grids, so the two can never drift apart.
#
# These grids are NOT self-justifying: E and W held each other's contents from
# the day they were written, and because the angles below were read off them and
# the tests pinned the engine back to them, engine, table and tests all agreed
# with each other while all three disagreed with a compass (fixed in Task 19).
# The anchor is therefore external — `road_side` names the direction the y-min
# (road-facing) edge faces, so that edge's third of the grid must be that
# direction's third — and it is pinned by
# `tests/test_vastu_zones.py::test_road_facing_row_is_that_compass_directions_third`,
# whose expectations are compass literals that import nothing from this module.
#
# Derivation of each angle — read the grid for the compass direction of +y:
#   S: grid[0][1] == "N"  → north is +y      →   0°
#   E: grid[1][2] == "N"  → north is +x      →  90°
#   N: grid[2][1] == "N"  → north is -y      → 180°
#   W: grid[1][0] == "N"  → north is -x      → 270°
# All four are proper rotations (east = north turned 90° clockwise), which is why
# a single continuous angle can express them.
ROAD_SIDE_NORTH_ANGLE_DEG: dict[str, float] = {
    "S": 0.0,
    "E": 90.0,
    "N": 180.0,
    "W": 270.0,
}

# Band boundary in normalized plot coordinates: the outer thirds start at ±1/6 of
# the plot extent from the centroid.
_BAND = 1.0 / 6.0


def north_angle_for_road_side(road_side: str) -> float:
    """Clockwise angle (degrees) from plot +y to true north for a road side.

    `PlotConfig.road_side` is an unvalidated `str`, so an unrecognised value must
    stay tolerated rather than raise: it falls back to South (0°), exactly as the
    superseded grid lookup fell back to `ZONE_GRID_ROAD_S`.
    """
    return ROAD_SIDE_NORTH_ANGLE_DEG.get(road_side.upper(), 0.0)


def road_side_for_north_angle(north_angle_deg: float) -> str | None:
    """Inverse of `north_angle_for_road_side`, or None when the orientation is
    not one of the four cardinal road sides.

    `PlotConfig.north_angle_deg` is a free float (a surveyed bearing), so it need
    not correspond to any road side at all — hence `None` rather than a fallback.
    Callers that key a rule off "which way does the frontage face" must go
    through the RESOLVED angle, not `cfg.road_side`: an explicit `north_angle_deg`
    overrides the road side for zone lookup, so keying a rule off the raw
    `road_side` would pair a rule chosen for one orientation with zones computed
    for another.
    """
    angle = north_angle_deg % 360.0
    for side, cardinal in ROAD_SIDE_NORTH_ANGLE_DEG.items():
        delta = abs(angle - cardinal)
        if min(delta, 360.0 - delta) <= 1e-6:
            return side
    return None


def zone_for_point(
    x: float,
    y: float,
    plot_w: float,
    plot_l: float,
    north_angle_deg: float = 0.0,
) -> str:
    """Vastu zone of a point on a plot whose north is `north_angle_deg` clockwise
    from the plot's +y axis.

    The rotation is applied in NORMALIZED plot space — x is divided by `plot_w`
    and y by `plot_l` before rotating — not in metres. That choice matters: the
    3×3 Vastu grid is a division of the *plot* into thirds, so its bands are
    `plot_w/3` wide and `plot_l/3` tall. Rotating in metres mixes those two
    scales, and on a non-square plot (9×15 is routine here) a 90° rotation sends
    a point's y-extent into a band sized by the plot's much smaller width, where
    it clamps — corners fold onto edges and the map stops being a partition of
    the plot. Normalizing first makes the mapping total, corner-preserving and
    aspect-ratio independent, and in exact arithmetic reduces to the historical
    thirds at every multiple of 90°, tie-breaks included.

    In floating point the reduction is exact everywhere except *on* a band
    boundary: comparing `(y - plot_l/2)/plot_l` against `1/6` is not bit-identical
    to the superseded `y > 2*plot_l/3`, so on a plot whose third is not
    binary-representable a point sitting on the exact float boundary may fall in
    the adjacent band (e.g. y == 6.666666666666667 on a 10 m plot: was C, now N).
    Interior points are unaffected — a dense old-vs-new sweep found zero
    off-boundary mismatches — and a room centroid cannot land on such a float
    from the 0.05 m solver grid, so this is not chased for bit-exact parity.
    See `tests/test_vastu_zones.py::test_band_boundary_ties_diverge_when_the_third_is_not_representable`.
    """
    u = (x - plot_w / 2.0) / plot_w
    v = (y - plot_l / 2.0) / plot_l

    theta = math.radians(north_angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    # Components along the compass axes: north = (sin θ, cos θ) in plot space,
    # east = north turned 90° clockwise = (cos θ, -sin θ).
    east = u * cos_t - v * sin_t
    north = u * sin_t + v * cos_t

    # Tie handling matches the superseded `_get_zone`, which was asymmetric: it
    # used `<` on both column comparisons and `>` on both row comparisons, so the
    # low-x and high-y boundaries fall to the MIDDLE band while the high-x and
    # low-y boundaries fall to the OUTER band. The `<`/`>` split below preserves
    # that; all four ties are pinned in test_band_boundaries_match_the_historical_thirds.
    if east < -_BAND:
        col = 0
    elif east < _BAND:
        col = 1
    else:
        col = 2

    if north > _BAND:
        row = 0
    elif north > -_BAND:
        row = 1
    else:
        row = 2

    return ZONE_GRID_ROAD_S[row][col]


def _zone_from_components(east: float, north: float) -> str:
    """Same col/row classification as `zone_for_point`, factored out so
    `zone_distribution` can reuse it against pre-rotated (east, north)
    components instead of re-deriving them per sample point."""
    if east < -_BAND:
        col = 0
    elif east < _BAND:
        col = 1
    else:
        col = 2

    if north > _BAND:
        row = 0
    elif north > -_BAND:
        row = 1
    else:
        row = 2

    return ZONE_GRID_ROAD_S[row][col]


def zone_distribution(
    room: Room,
    plot_w: float,
    plot_l: float,
    north_angle_deg: float = 0.0,
    samples: int = 40,
) -> dict[str, float]:
    """Area-weighted zone membership of a room, as fractions summing to 1.0.

    Samples a `samples` × `samples` lattice over the room's bounding box rather
    than testing only its centroid, so a room 40% inside NE and 60% inside N
    reports both instead of being credited wholly to whichever zone its midpoint
    happens to land in.

    The rotation (`math.radians`/`cos`/`sin` of `north_angle_deg`) is hoisted
    out of the sample loop: `zone_for_point` recomputed it per point, and this
    runs `samples * samples` = 1600 times per room, for every ruled room on
    every floor of every candidate layout — the trigonometry was landing on
    the order of 10^5-10^6 evaluations per generation request for a value
    that is constant across the whole call. `_zone_from_components` shares the
    same col/row classification as `zone_for_point`, so behaviour is unchanged.
    """
    counts: dict[str, int] = {}
    theta = math.radians(north_angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    for i in range(samples):
        px = room.x + room.width * (i + 0.5) / samples
        u = (px - plot_w / 2.0) / plot_w
        for j in range(samples):
            py = room.y + room.depth * (j + 0.5) / samples
            v = (py - plot_l / 2.0) / plot_l
            zone = _zone_from_components(
                u * cos_t - v * sin_t, u * sin_t + v * cos_t
            )
            counts[zone] = counts.get(zone, 0) + 1
    total = float(samples * samples)
    return {zone: count / total for zone, count in counts.items()}


# ── Vastu room preferences per zone ─────────────────────────────────────────
# "preferred" rooms for each zone (informational)
# "avoid"    rooms that are inauspicious in this zone (flagged as warnings)
# "prohibit" hard Vastu violations (flagged as violations)
#
# Sourced from compliance_rules.json's "vastu_zones" key, alongside the
# project's other configurable compliance thresholds.
VASTU_RULES: dict[str, dict] = load_rules()["vastu_zones"]

# ── Graded room rules ───────────────────────────────────────────────────────
# `vastu_room_rules` is the TRANSPOSE of `vastu_zones` above — same information,
# indexed by room type instead of by zone — plus one genuinely new tier.
#
#   vastu_zones[z].preferred            → vastu_room_rules[r].preferred
#   vastu_zones[z].avoid | .prohibit    → vastu_room_rules[r].avoid
#   (nothing)                           → vastu_room_rules[r].acceptable
#
# The prohibit/avoid collapse is deliberate: the binary checker needed to tell a
# violation from a warning, but a *score* only needs "this is wrong here", and
# both tiers already mean that. The split survives untouched in `vastu_zones`,
# which `check_vastu` still reads.
#
# `acceptable` has no source in `vastu_zones` and was therefore populated only
# where the engine already encoded a tolerance elsewhere: `check_vastu`'s
# kitchen check warns unless the zone is SE/NW/E, and its pooja check unless
# NE/N/E — so NW+E and N+E respectively are tolerated-but-not-preferred. The one
# judgement call is toilet in S/W (see the report for Task 15).
#
# `tests/test_vastu_score.py` pins the transpose cell-by-cell in both directions,
# so the two encodings cannot drift apart.
VASTU_ROOM_RULES: dict[str, dict[str, list[str]]] = load_rules().get(
    "vastu_room_rules", {}
)

# Room types that inherit another type's rules. Each key is a post-split
# specialisation of a generic token that `vastu_zones` predates: `models.py` now
# tells new layouts to prefer `parking_4w` over `parking`, and splits the old
# `toilet` into `toilet`/`wc_only`/`bathroom_master`. Without these, the
# *deprecated* token would be the only one carrying a Vastu opinion and every
# modern layout would score neutral.
VASTU_RULE_ALIASES: dict[str, str] = {
    "master_bedroom": "bedroom",
    "wc_only": "toilet",
    "bathroom_master": "toilet",
    "parking_4w": "parking",
    "parking_2w": "parking",
    "garage": "parking",
}

# Verdict factors applied to the fraction of a room's area sitting in a zone.
VERDICT_PREFERRED = 1.0
VERDICT_ACCEPTABLE = 0.7
VERDICT_NEUTRAL = 0.45
VERDICT_AVOID = 0.0


def resolve_north_angle(cfg: PlotConfig, road_side: str | None = None) -> float:
    """Orientation to score with: an explicit `north_angle_deg` (including 0.0)
    wins; `None` means "not surveyed", so fall back to the road side.

    `cfg.north_angle_deg` is `float | None`, so it must never reach the
    trigonometry unresolved.
    """
    if cfg.north_angle_deg is not None:
        return cfg.north_angle_deg
    return north_angle_for_road_side(
        road_side if road_side is not None else cfg.road_side
    )


def _rule_for(room_type: str) -> dict[str, list[str]] | None:
    """Graded rule for a room type, following one alias hop, or None if unknown."""
    rule = VASTU_ROOM_RULES.get(room_type)
    if rule is None:
        alias = VASTU_RULE_ALIASES.get(room_type)
        if alias is not None:
            rule = VASTU_ROOM_RULES.get(alias)
    return rule


def _verdict(room_type: str, zone: str) -> float:
    """Verdict factor for one room type in one zone.

    A room type with no rule, or a zone the rule is silent about, is NEUTRAL —
    Vastu has no opinion, which is not the same as approval or prohibition.
    """
    rule = _rule_for(room_type)
    if rule is None:
        return VERDICT_NEUTRAL
    if zone in rule.get("preferred", []):
        return VERDICT_PREFERRED
    if zone in rule.get("acceptable", []):
        return VERDICT_ACCEPTABLE
    if zone in rule.get("avoid", []):
        return VERDICT_AVOID
    return VERDICT_NEUTRAL


def vastu_room_score(
    room: Room, plot_w: float, plot_l: float, north_angle_deg: float = 0.0
) -> float:
    """Graded 0..1 Vastu compliance for one room, area-weighted across zones.

    Replaces the binary prohibit/avoid verdict with a continuous signal — the
    prerequisite for using Vastu as a CP-SAT objective term rather than only as
    an accept/reject gate.

    Area-weighted via `zone_distribution`, so a room straddling two zones scores
    between their verdicts instead of taking whichever one its centroid lands in.
    Note that `zone_distribution` samples a finite lattice, so the fractions are
    quantised to that lattice rather than exactly geometric.
    """
    dist = zone_distribution(room, plot_w, plot_l, north_angle_deg)
    return round(
        sum(frac * _verdict(room.type, zone) for zone, frac in dist.items()), 6
    )


def vastu_layout_score(floors: list[FloorPlan], cfg: PlotConfig) -> float:
    """0..100 Vastu score across every floor: an **area-weighted** mean over
    **only the rooms that have a rule**.

    Do not "simplify" this back to a plain mean over all rooms. A plain mean was
    measured to have three ranking pathologies, and this function is a ranking
    signal (Task 16) and a CP-SAT objective term (Task 17), not a display number:

    1. *Rule-less rooms shifted the score.* A `duct` has no entry in
       `VASTU_ROOM_RULES` and no alias, so `_verdict` gives it NEUTRAL 0.45. Under
       a plain mean that 0.45 is not neutral at all — it drags every mean toward
       itself. Two prohibited rooms scored 0.0, and adding three ducts took them
       to 27.0; two perfect rooms scored 100.0 and one duct dropped them to 81.67.
       As an objective that rewards filler in bad plans and penalises good ones.
       Excluding rule-less rooms is the fix at the root: a room Vastu has no
       opinion about should carry zero *weight*, not a middling opinion.
    2. *Room area was ignored between rooms.* Each room is area-weighted across
       zones by `vastu_room_score`, but rooms were then averaged one-for-one, so
       four 0.36 m2 utilities outvoted a 16 m2 master bedroom in prohibited NE
       (20.93 alone -> 84.19). Weighting by area is how a consultant reads a plan.
    3. *Scores were incomparable across room counts.* One perfect kitchen scored
       72.5 / 58.75 / 51.88 at 2 / 4 / 8 rooms. With (1) and (2) the denominator
       is ruled floor area rather than a raw count, so padding cannot move it.

    Together (1) and (2) make this exactly "the verdict-weighted fraction of
    ruled floor area": sum over (room, zone) of the room's physical area in that
    zone times its verdict, over the total ruled area. Range is [0, 100] because
    every verdict factor is in [0, 1].

    Returns 0.0 both for an empty layout and for a layout whose rooms all lack a
    rule. Neither is "45% compliant" — there is no Vastu content to credit, and
    0.0 is the incentive-safe choice: retyping the last ruled room away can then
    never *raise* the score. (Room *type* is fixed before the model is built —
    `solver.py` passes `room_type=rtype` as a Python constant — so exclusion is
    not something a solver can game; room *width/depth* are decision variables,
    so area-weighting does let a badly-placed room shrink toward its
    `fit.min_area` floor to shed weight. That floor plus the area-utilisation
    objective bound it, but weigh it when tuning Task 17's objective weights.)

    Ground-floor-only scoring was the old behaviour; a first-floor master bedroom
    is counted.
    """
    rooms = [room for floor in floors for room in floor.rooms]
    if not rooms:
        return 0.0
    north = resolve_north_angle(cfg)
    weighted = 0.0
    ruled_area = 0.0
    for room in rooms:
        if _rule_for(room.type) is None:
            continue
        area = room.width * room.depth
        weighted += area * vastu_room_score(
            room, cfg.plot_width, cfg.plot_length, north
        )
        ruled_area += area
    if ruled_area <= 0.0:
        return 0.0
    return round(100.0 * weighted / ruled_area, 2)


def _get_zone(
    cx: float, cy: float, plot_w: float, plot_l: float, road_side: str
) -> str:
    """Map a point to one of 9 Vastu zones, given a road side.

    Thin delegation to `zone_for_point` so there is exactly one zone engine.
    Kept for the road-side-shaped callers that predate `north_angle_deg`.
    """
    return zone_for_point(cx, cy, plot_w, plot_l, north_angle_for_road_side(road_side))


_FLOOR_LABELS: dict[str, str] = {
    "basement": "basement",
    "stilt": "stilt floor",
    "ground": "ground floor",
    "first": "first floor",
    "second": "second floor",
}


def _floor_label(floor: FloorPlan) -> str:
    """Human-readable identifier for the floor a Vastu finding is about.

    `check_vastu` reads every floor, and stacked floors are the normal case: a
    G+1's first-floor toilet sits directly above the ground-floor one with the
    same `name` and the same (x, y), so both land in the same zone and produce a
    byte-identical sentence. `generator._attach_vastu` extends
    `layout.compliance.warnings` with these strings verbatim, so the duplicate
    reaches the API/UI payload and the user cannot tell which floor is meant.

    `floor_type` is an unvalidated `str` on `FloorPlan`, so an unrecognised value
    falls back to the numeric `floor` rather than raising or silently dropping
    the identifier.
    """
    return _FLOOR_LABELS.get(floor.floor_type, f"floor {floor.floor}")


def check_vastu(
    layout: Layout, cfg: PlotConfig, road_side: str = "S"
) -> tuple[list[str], list[str]]:
    """
    Check Vastu compliance for a layout.

    Returns (violations, warnings) lists with [Vastu] prefix messages.

    Every message carries a trailing `(<floor>)` label. The label is a SUFFIX,
    not an infix, deliberately: `frontend/src/components/status-rail.tsx` does
    `w.startsWith("[Vastu]")` and `w.replace("[Vastu] ", "")`, and the existing
    engine tests substring-match on `"Kitchen is in"`, `"Pooja Room is in"` and
    `"ideal for master bedroom"` — all of which an infix after the room name
    would break. A suffix leaves every one of those intact.
    """
    violations: list[str] = []
    warnings: list[str] = []

    if not cfg.vastu_enabled:
        return violations, warnings

    plot_w = cfg.plot_width
    plot_l = cfg.plot_length
    # One orientation resolved once for the whole check. The explicit
    # `road_side` argument, not `cfg.road_side`, is the fallback — that is what
    # every pre-existing caller passes.
    north = resolve_north_angle(cfg, road_side)

    # Every floor, not just the ground one. A first-floor toilet in the NE is
    # the same Vastu complaint as a ground-floor one; the old ground-only read
    # meant every upper-floor room was silently exempt.
    floors = [
        f
        for f in (
            layout.ground_floor,
            layout.first_floor,
            layout.second_floor,
            layout.basement_floor,
        )
        if f is not None
    ]
    # (floor, room) pairs, not bare rooms: the floor is what disambiguates two
    # otherwise byte-identical messages (see `_floor_label`).
    all_rooms = [(f, r) for f in floors for r in f.rooms]

    for floor, room in all_rooms:
        cx = room.x + room.width / 2
        cy = room.y + room.depth / 2
        zone = zone_for_point(cx, cy, plot_w, plot_l, north)
        rules = VASTU_RULES.get(zone, {})
        # `notes` is optional and often empty; keep the label from growing a
        # double space when it is.
        notes = rules.get("notes", "")
        tail = (
            f"{notes} ({_floor_label(floor)})" if notes else f"({_floor_label(floor)})"
        )

        if room.type in rules.get("prohibit", []):
            violations.append(
                f"[Vastu] {room.name} in {rules['name']} zone — "
                f"{room.type.title()} is strictly prohibited here. {tail}"
            )
        elif room.type in rules.get("avoid", []):
            warnings.append(
                f"[Vastu] {room.name} in {rules['name']} zone — "
                f"{room.type.title()} is inauspicious here. {tail}"
            )

    # Kitchen-specific: must be in SE or NW — violation if elsewhere
    kitchens = [(f, r) for f, r in all_rooms if r.type == "kitchen"]
    for floor, k in kitchens:
        cx = k.x + k.width / 2
        cy = k.y + k.depth / 2
        zone = zone_for_point(cx, cy, plot_w, plot_l, north)
        if zone not in ("SE", "NW", "E"):
            warnings.append(
                f"[Vastu] Kitchen is in {zone} zone — prefer Southeast (Agni) "
                f"or Northwest for kitchen ({_floor_label(floor)})"
            )

    # Pooja room: prefer NE — warn if not in NE, E, or N
    poojas = [(f, r) for f, r in all_rooms if r.type == "pooja"]
    for floor, p in poojas:
        cx = p.x + p.width / 2
        cy = p.y + p.depth / 2
        zone = zone_for_point(cx, cy, plot_w, plot_l, north)
        if zone not in ("NE", "N", "E"):
            warnings.append(
                f"[Vastu] Pooja Room is in {zone} zone — Northeast (Ishanya) "
                f"is ideal for prayer space ({_floor_label(floor)})"
            )

    # Master bedroom: prefer SW — warn if not in SW or S
    # Deliberately NOT `all_rooms`: "the first bedroom" identifies the master
    # bedroom only on the ground floor. On a GF with no bedroom at all,
    # iterating every floor would promote an ordinary upstairs bedroom to
    # "master" and warn about its zone — an advisory the user cannot act on.
    # The cost of staying ground-only is a genuinely upstairs master bedroom
    # going unwarned; a missing advisory beats a wrong one.
    bedrooms = [r for r in layout.ground_floor.rooms if r.type == "bedroom"]
    if bedrooms:
        b = bedrooms[0]  # first bedroom = master bedroom on ground floor
        cx = b.x + b.width / 2
        cy = b.y + b.depth / 2
        zone = zone_for_point(cx, cy, plot_w, plot_l, north)
        if zone not in ("SW", "S", "W"):
            # Labelled too, even though this check is ground-floor-only so the
            # label is constant: a uniform format means the UI (and any future
            # dedupe) needs no special case, and it makes the GF-only scope of
            # this particular advisory visible to the reader of the message.
            warnings.append(
                f"[Vastu] {b.name} is in {zone} zone — Southwest (Nairutya) "
                f"is ideal for master bedroom ({_floor_label(layout.ground_floor)})"
            )

    return violations, warnings
