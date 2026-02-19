"""Vastu Shastra compliance checker for G+1 residential layouts.

Vastu Shastra divides a plot into 8 directional zones + centre (Brahmasthan).
Room placement is evaluated against classical Vastu principles for Indian homes.

Coordinate system in PlanForge:
  x=0 is the left edge, x=max is the right edge.
  y=0 is the road-facing front, y=max is the rear.

Zone mapping depends on which compass direction the road faces (roadSide):

  roadSide="S" (most common — house faces South):
    y=0 → South,  y=max → North
    x=0 → West,   x=max → East

  roadSide="N":
    y=0 → North,  y=max → South
    x=0 → East,   x=max → West   (east/west swap when facing North)

  roadSide="E":
    y=0 → East,   y=max → West
    x=0 → North,  x=max → South  (north/south swap)

  roadSide="W":
    y=0 → West,   y=max → East
    x=0 → South,  x=max → North
"""

from __future__ import annotations

from .models import Layout, PlotConfig

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
    ["NW", "N",  "NE"],   # rear zone (y near plot_length)
    ["W",  "C",  "E" ],   # middle zone
    ["SW", "S",  "SE"],   # front zone (y near 0)
]

# Zone grid rotated for each road direction
# For road N: y=0 is North, y=max is South → grid flips vertically and L/R swap
ZONE_GRID_ROAD_N = [
    ["SE", "S",  "SW"],
    ["E",  "C",  "W" ],
    ["NE", "N",  "NW"],
]

ZONE_GRID_ROAD_E = [
    ["NE", "E",  "SE"],
    ["N",  "C",  "S" ],
    ["NW", "W",  "SW"],
]

ZONE_GRID_ROAD_W = [
    ["SW", "W",  "NW"],
    ["S",  "C",  "N" ],
    ["SE", "E",  "NE"],
]

ZONE_GRIDS: dict[str, list[list[str]]] = {
    "S": ZONE_GRID_ROAD_S,
    "N": ZONE_GRID_ROAD_N,
    "E": ZONE_GRID_ROAD_E,
    "W": ZONE_GRID_ROAD_W,
}


# ── Vastu room preferences per zone ─────────────────────────────────────────
# "preferred" rooms for each zone (informational)
# "avoid"    rooms that are inauspicious in this zone (flagged as warnings)
# "prohibit" hard Vastu violations (flagged as violations)

VASTU_RULES: dict[str, dict] = {
    "NE": {
        "preferred": ["pooja", "utility", "balcony", "staircase"],
        "avoid":     ["bedroom", "parking"],
        "prohibit":  ["kitchen", "toilet"],
        "name":      "Ishanya (NE)",
        "notes":     "Sacred zone — ideal for Pooja, open space, water",
    },
    "E": {
        "preferred": ["bedroom", "dining", "bathroom", "toilet"],
        "avoid":     [],
        "prohibit":  [],
        "name":      "Purva (E)",
        "notes":     "East — sunrise zone, good for bedrooms and dining",
    },
    "SE": {
        "preferred": ["kitchen"],
        "avoid":     ["bedroom", "pooja"],
        "prohibit":  ["toilet"],
        "name":      "Agni (SE)",
        "notes":     "Fire zone — kitchen must be here or NW",
    },
    "S": {
        "preferred": ["bedroom", "parking"],
        "avoid":     ["pooja", "living"],
        "prohibit":  [],
        "name":      "Yama (S)",
        "notes":     "South — guest bedroom, parking; avoid main entrance",
    },
    "SW": {
        "preferred": ["bedroom"],
        "avoid":     ["pooja", "balcony"],
        "prohibit":  ["toilet", "kitchen"],
        "name":      "Nairutya (SW)",
        "notes":     "Most stable corner — master bedroom, heavy storage",
    },
    "W": {
        "preferred": ["bedroom", "study", "dining"],
        "avoid":     [],
        "prohibit":  [],
        "name":      "Varuna (W)",
        "notes":     "West — children's bedroom, study",
    },
    "NW": {
        "preferred": ["bedroom", "toilet", "utility", "parking"],
        "avoid":     [],
        "prohibit":  [],
        "name":      "Vayu (NW)",
        "notes":     "Air zone — guest room, toilet, storage acceptable",
    },
    "N": {
        "preferred": ["living", "study", "dining"],
        "avoid":     ["kitchen", "toilet"],
        "prohibit":  [],
        "name":      "Kubera (N)",
        "notes":     "Wealth direction — living, study, treasury",
    },
    "C": {
        "preferred": ["utility"],
        "avoid":     ["bedroom", "kitchen"],
        "prohibit":  ["toilet"],
        "name":      "Brahmasthan (Centre)",
        "notes":     "Sacred centre — should remain open or light use only",
    },
}


def _get_zone(cx: float, cy: float, plot_w: float, plot_l: float, road_side: str) -> str:
    """Map a room centre point to one of 9 Vastu zones."""
    grid = ZONE_GRIDS.get(road_side.upper(), ZONE_GRID_ROAD_S)

    # Column: 0 = left (x < W/3), 1 = middle, 2 = right (x > 2W/3)
    if cx < plot_w / 3:
        col = 0
    elif cx < 2 * plot_w / 3:
        col = 1
    else:
        col = 2

    # Row: 0 = rear (y > 2L/3), 1 = middle, 2 = front (y < L/3)
    if cy > 2 * plot_l / 3:
        row = 0
    elif cy > plot_l / 3:
        row = 1
    else:
        row = 2

    return grid[row][col]


def check_vastu(layout: Layout, cfg: PlotConfig, road_side: str = "S") -> tuple[list[str], list[str]]:
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

    # Check ground floor rooms (Vastu is primarily for ground floor)
    for room in layout.ground_floor.rooms:
        cx = room.x + room.width / 2
        cy = room.y + room.depth / 2
        zone = _get_zone(cx, cy, plot_w, plot_l, road_side)
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
        zone = _get_zone(cx, cy, plot_w, plot_l, road_side)
        if zone not in ("SE", "NW", "E"):
            warnings.append(
                f"[Vastu] Kitchen is in {zone} zone — prefer Southeast (Agni) or Northwest for kitchen"
            )

    # Pooja room: prefer NE — warn if not in NE, E, or N
    poojas = [r for r in layout.ground_floor.rooms if r.type == "pooja"]
    for p in poojas:
        cx = p.x + p.width / 2
        cy = p.y + p.depth / 2
        zone = _get_zone(cx, cy, plot_w, plot_l, road_side)
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
        zone = _get_zone(cx, cy, plot_w, plot_l, road_side)
        if zone not in ("SW", "S", "W"):
            warnings.append(
                f"[Vastu] {b.name} is in {zone} zone — Southwest (Nairutya) is ideal for master bedroom"
            )

    return violations, warnings
