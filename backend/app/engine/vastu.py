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

  roadSide="W" (90°):
    y=0 → East,   y=max → West
    x=0 → South,  x=max → North

  roadSide="N" (180°):
    y=0 → North,  y=max → South
    x=0 → East,   x=max → West   (east/west swap when facing North)

  roadSide="E" (270°):
    y=0 → West,   y=max → East
    x=0 → North,  x=max → South  (north/south swap)

Angles between these are supported directly — 24% of the reference corpus has
a north arrow that is not axis-aligned, and such a plot must not be snapped to
the nearest cardinal orientation.
"""

from __future__ import annotations

import math

from .compliance import load_rules
from .models import Layout, PlotConfig, Room

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

ZONE_GRID_ROAD_E = [
    ["NE", "E", "SE"],
    ["N", "C", "S"],
    ["NW", "W", "SW"],
]

ZONE_GRID_ROAD_W = [
    ["SW", "W", "NW"],
    ["S", "C", "N"],
    ["SE", "E", "NE"],
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
# Derivation of each angle — read the grid for the compass direction of +y:
#   S: grid[0][1] == "N"  → north is +y      →   0°
#   W: grid[1][2] == "N"  → north is +x      →  90°
#   N: grid[2][1] == "N"  → north is -y      → 180°
#   E: grid[1][0] == "N"  → north is -x      → 270°
# All four are proper rotations (east = north turned 90° clockwise), which is why
# a single continuous angle can express them.
ROAD_SIDE_NORTH_ANGLE_DEG: dict[str, float] = {
    "S": 0.0,
    "W": 90.0,
    "N": 180.0,
    "E": 270.0,
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
    """
    counts: dict[str, int] = {}
    for i in range(samples):
        px = room.x + room.width * (i + 0.5) / samples
        for j in range(samples):
            py = room.y + room.depth * (j + 0.5) / samples
            zone = zone_for_point(px, py, plot_w, plot_l, north_angle_deg)
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


def _get_zone(
    cx: float, cy: float, plot_w: float, plot_l: float, road_side: str
) -> str:
    """Map a point to one of 9 Vastu zones, given a road side.

    Thin delegation to `zone_for_point` so there is exactly one zone engine.
    Kept for the road-side-shaped callers that predate `north_angle_deg`.
    """
    return zone_for_point(cx, cy, plot_w, plot_l, north_angle_for_road_side(road_side))


def check_vastu(
    layout: Layout, cfg: PlotConfig, road_side: str = "S"
) -> tuple[list[str], list[str]]:
    """
    Check Vastu compliance for a layout.

    Returns (violations, warnings) lists with [Vastu] prefix messages.
    """
    violations: list[str] = []
    warnings: list[str] = []

    if not cfg.vastu_enabled:
        return violations, warnings

    plot_w = cfg.plot_width
    plot_l = cfg.plot_length
    # One orientation resolved once for the whole check: an explicit
    # `north_angle_deg` (including 0.0) wins; `None` means "not surveyed", so
    # fall back to the road side, preserving every pre-existing caller.
    north = (
        cfg.north_angle_deg
        if cfg.north_angle_deg is not None
        else north_angle_for_road_side(road_side)
    )

    # Check ground floor rooms (Vastu is primarily for ground floor)
    for room in layout.ground_floor.rooms:
        cx = room.x + room.width / 2
        cy = room.y + room.depth / 2
        zone = zone_for_point(cx, cy, plot_w, plot_l, north)
        rules = VASTU_RULES.get(zone, {})

        if room.type in rules.get("prohibit", []):
            violations.append(
                f"[Vastu] {room.name} in {rules['name']} zone — "
                f"{room.type.title()} is strictly prohibited here. {rules.get('notes', '')}"
            )
        elif room.type in rules.get("avoid", []):
            warnings.append(
                f"[Vastu] {room.name} in {rules['name']} zone — "
                f"{room.type.title()} is inauspicious here. {rules.get('notes', '')}"
            )

    # Kitchen-specific: must be in SE or NW — violation if elsewhere
    kitchens = [r for r in layout.ground_floor.rooms if r.type == "kitchen"]
    for k in kitchens:
        cx = k.x + k.width / 2
        cy = k.y + k.depth / 2
        zone = zone_for_point(cx, cy, plot_w, plot_l, north)
        if zone not in ("SE", "NW", "E"):
            warnings.append(
                f"[Vastu] Kitchen is in {zone} zone — prefer Southeast (Agni) or Northwest for kitchen"
            )

    # Pooja room: prefer NE — warn if not in NE, E, or N
    poojas = [r for r in layout.ground_floor.rooms if r.type == "pooja"]
    for p in poojas:
        cx = p.x + p.width / 2
        cy = p.y + p.depth / 2
        zone = zone_for_point(cx, cy, plot_w, plot_l, north)
        if zone not in ("NE", "N", "E"):
            warnings.append(
                f"[Vastu] Pooja Room is in {zone} zone — Northeast (Ishanya) is ideal for prayer space"
            )

    # Master bedroom: prefer SW — warn if not in SW or S
    bedrooms = [r for r in layout.ground_floor.rooms if r.type == "bedroom"]
    if bedrooms:
        b = bedrooms[0]  # first bedroom = master bedroom on ground floor
        cx = b.x + b.width / 2
        cy = b.y + b.depth / 2
        zone = zone_for_point(cx, cy, plot_w, plot_l, north)
        if zone not in ("SW", "S", "W"):
            warnings.append(
                f"[Vastu] {b.name} is in {zone} zone — Southwest (Nairutya) is ideal for master bedroom"
            )

    return violations, warnings
