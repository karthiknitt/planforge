"""
Three parametric layout archetypes for rectangular G+1 plots.

Coordinate system:
  x — east (left to right, 0 at plot left edge)
  y — north (front to rear, 0 at road/front edge)

Floor plate origin (ox, oy) is the inner face of the external walls.
All room coordinates are inner-face to inner-face (wall thickness excluded).

Wall constants (from compliance_rules.json defaults):
  EWT = 0.23 m  (external wall)
  IWT = 0.115 m (internal partition)
"""

from __future__ import annotations

from .models import Column, FloorPlan, FloorPlate, Layout, PlotConfig, Room

EWT = 0.23    # external wall thickness (m)
IWT = 0.115   # internal wall thickness (m)
STAIR_W = 0.9  # staircase clear width (m)
STAIR_D = 3.0  # staircase + landing depth (m)
PARK_W = 2.5   # car parking bay width (m)


def _floor_plate(cfg: PlotConfig) -> FloorPlate:
    ox = cfg.setback_left + EWT
    oy = cfg.setback_front + EWT
    width = cfg.plot_width - cfg.setback_left - cfg.setback_right - 2 * EWT
    depth = cfg.plot_length - cfg.setback_front - cfg.setback_rear - 2 * EWT
    return FloorPlate(ox=ox, oy=oy, width=width, depth=depth)


def _r(room_id: str, name: str, rtype, x, y, w, d) -> Room:
    return Room(
        id=room_id,
        name=name,
        type=rtype,
        x=round(x, 3),
        y=round(y, 3),
        width=round(w, 3),
        depth=round(d, 3),
    )


def _columns_from_rooms(rooms: list[Room]) -> list[Column]:
    """Place columns at every intersection of room wall lines."""
    xs = sorted({r.x for r in rooms} | {r.x + r.width for r in rooms})
    ys = sorted({r.y for r in rooms} | {r.y + r.depth for r in rooms})
    return [Column(x=round(x, 3), y=round(y, 3)) for x in xs for y in ys]


# ---------------------------------------------------------------------------
# Layout A — Front Staircase
# ---------------------------------------------------------------------------

def layout_a(cfg: PlotConfig) -> Layout:
    fp = _floor_plate(cfg)
    ox, oy, W, D = fp.ox, fp.oy, fp.width, fp.depth

    # Zone depths (front → rear)
    d_stair = STAIR_D
    d_service = max(2.8, 7.0 / max(W * 0.55, 0.1))   # ensure kitchen ≥ 7 sqm
    d_living = D - d_stair - d_service - 2 * IWT

    # Kitchen/toilet width split
    k_w = max(W * 0.55, 7.0 / d_service)
    t_w = W - k_w - IWT

    # ── Ground Floor ──────────────────────────────────────────────────────
    gf_rooms: list[Room] = []

    # Front zone: staircase + (parking or entry foyer)
    gf_rooms.append(_r("gf_stair", "Staircase", "staircase", ox, oy, STAIR_W, d_stair))

    if cfg.parking:
        gf_rooms.append(_r("gf_parking", "Parking", "parking",
                           ox + STAIR_W + IWT, oy, PARK_W, d_stair))
        foyer_x = ox + STAIR_W + IWT + PARK_W + IWT
        foyer_w = W - STAIR_W - IWT - PARK_W - IWT
        if foyer_w > 0.3:
            gf_rooms.append(_r("gf_foyer", "Foyer", "utility", foyer_x, oy, foyer_w, d_stair))
    else:
        entry_w = W - STAIR_W - IWT
        gf_rooms.append(_r("gf_entry", "Entry / Foyer", "utility",
                           ox + STAIR_W + IWT, oy, entry_w, d_stair))

    # Living zone (middle)
    living_y = oy + d_stair + IWT
    gf_rooms.append(_r("gf_living", "Living / Hall", "living", ox, living_y, W, d_living))

    # Service zone (rear): kitchen + toilet
    svc_y = oy + D - d_service
    gf_rooms.append(_r("gf_kitchen", "Kitchen", "kitchen", ox, svc_y, k_w, d_service))
    if t_w > 0.5:
        gf_rooms.append(_r("gf_toilet_1", "Toilet 1", "toilet",
                           ox + k_w + IWT, svc_y, t_w, d_service))

    # ── First Floor ───────────────────────────────────────────────────────
    ff_rooms: list[Room] = []

    # Front zone: staircase landing + optional 2nd toilet
    ff_rooms.append(_r("ff_stair", "Staircase", "staircase", ox, oy, STAIR_W, d_stair))
    wc2_w = W - STAIR_W - IWT
    if cfg.toilets >= 2:
        ff_rooms.append(_r("ff_toilet_2", "Toilet 2", "toilet",
                           ox + STAIR_W + IWT, oy, wc2_w, d_stair))
    else:
        ff_rooms.append(_r("ff_landing", "Landing", "utility",
                           ox + STAIR_W + IWT, oy, wc2_w, d_stair))

    # Bedroom zone (rest of first floor depth)
    bed_y = oy + d_stair + IWT
    d_bed = D - d_stair - IWT

    if cfg.bhk == 2:
        bw = (W - IWT) / 2
        ff_rooms.append(_r("ff_bed_1", "Bedroom 1", "bedroom", ox, bed_y, bw, d_bed))
        ff_rooms.append(_r("ff_bed_2", "Bedroom 2", "bedroom", ox + bw + IWT, bed_y, W - bw - IWT, d_bed))
    else:  # 3 BHK
        bw = (W - 2 * IWT) / 3
        ff_rooms.append(_r("ff_bed_1", "Bedroom 1", "bedroom", ox, bed_y, bw, d_bed))
        ff_rooms.append(_r("ff_bed_2", "Bedroom 2", "bedroom", ox + bw + IWT, bed_y, bw, d_bed))
        ff_rooms.append(_r("ff_bed_3", "Bedroom 3", "bedroom",
                           ox + 2 * (bw + IWT), bed_y, W - 2 * (bw + IWT), d_bed))

    gf = FloorPlan(floor=0, rooms=gf_rooms, columns=_columns_from_rooms(gf_rooms))
    ff = FloorPlan(floor=1, rooms=ff_rooms, columns=_columns_from_rooms(ff_rooms))

    from .models import ComplianceResult
    return Layout(id="A", name="Front Staircase", ground_floor=gf, first_floor=ff,
                  compliance=ComplianceResult(passed=True))


# ---------------------------------------------------------------------------
# Layout B — Centre Staircase
# ---------------------------------------------------------------------------

def layout_b(cfg: PlotConfig) -> Layout:
    fp = _floor_plate(cfg)
    ox, oy, W, D = fp.ox, fp.oy, fp.width, fp.depth

    # Zone depths (front → rear)
    d_front = D * 0.40
    d_stair = STAIR_D
    d_rear = D - d_front - d_stair - 2 * IWT

    stair_y = oy + d_front + IWT
    rear_y = stair_y + d_stair + IWT

    # ── Ground Floor ──────────────────────────────────────────────────────
    gf_rooms: list[Room] = []

    # Front zone: living (full width, or split with parking)
    if cfg.parking:
        gf_rooms.append(_r("gf_parking", "Parking", "parking", ox, oy, PARK_W, d_front))
        living_x = ox + PARK_W + IWT
        gf_rooms.append(_r("gf_living", "Living / Hall", "living",
                           living_x, oy, W - PARK_W - IWT, d_front))
    else:
        gf_rooms.append(_r("gf_living", "Living / Hall", "living", ox, oy, W, d_front))

    # Centre zone: staircase + toilet
    gf_rooms.append(_r("gf_stair", "Staircase", "staircase", ox, stair_y, STAIR_W, d_stair))
    wc_w = W - STAIR_W - IWT
    gf_rooms.append(_r("gf_toilet_1", "Toilet 1", "toilet",
                       ox + STAIR_W + IWT, stair_y, wc_w, d_stair))

    # Rear zone: kitchen (full width)
    gf_rooms.append(_r("gf_kitchen", "Kitchen", "kitchen", ox, rear_y, W, d_rear))

    # ── First Floor ───────────────────────────────────────────────────────
    ff_rooms: list[Room] = []

    # Front zone: bedrooms
    if cfg.bhk == 2:
        bw = (W - IWT) / 2
        ff_rooms.append(_r("ff_bed_1", "Bedroom 1", "bedroom", ox, oy, bw, d_front))
        ff_rooms.append(_r("ff_bed_2", "Bedroom 2", "bedroom", ox + bw + IWT, oy, W - bw - IWT, d_front))
    else:  # 3 BHK — 2 beds in front, 1 in rear
        bw = (W - IWT) / 2
        ff_rooms.append(_r("ff_bed_1", "Bedroom 1", "bedroom", ox, oy, bw, d_front))
        ff_rooms.append(_r("ff_bed_2", "Bedroom 2", "bedroom", ox + bw + IWT, oy, W - bw - IWT, d_front))

    # Centre zone: staircase + toilet (aligned with ground)
    ff_rooms.append(_r("ff_stair", "Staircase", "staircase", ox, stair_y, STAIR_W, d_stair))
    if cfg.toilets >= 2:
        ff_rooms.append(_r("ff_toilet_2", "Toilet 2", "toilet",
                           ox + STAIR_W + IWT, stair_y, wc_w, d_stair))
    else:
        ff_rooms.append(_r("ff_landing", "Landing", "utility",
                           ox + STAIR_W + IWT, stair_y, wc_w, d_stair))

    # Rear zone: bedroom 3 (3BHK) or utility (2BHK)
    if cfg.bhk == 3:
        ff_rooms.append(_r("ff_bed_3", "Bedroom 3", "bedroom", ox, rear_y, W, d_rear))
    else:
        ff_rooms.append(_r("ff_utility", "Study / Utility", "utility", ox, rear_y, W, d_rear))

    gf = FloorPlan(floor=0, rooms=gf_rooms, columns=_columns_from_rooms(gf_rooms))
    ff = FloorPlan(floor=1, rooms=ff_rooms, columns=_columns_from_rooms(ff_rooms))

    from .models import ComplianceResult
    return Layout(id="B", name="Centre Staircase", ground_floor=gf, first_floor=ff,
                  compliance=ComplianceResult(passed=True))


# ---------------------------------------------------------------------------
# Layout C — Rear Staircase
# ---------------------------------------------------------------------------

def layout_c(cfg: PlotConfig) -> Layout:
    fp = _floor_plate(cfg)
    ox, oy, W, D = fp.ox, fp.oy, fp.width, fp.depth

    # Zone depths
    d_stair = STAIR_D
    d_front = D - d_stair - IWT   # living zone takes most of the depth

    stair_y = oy + d_front + IWT

    # Kitchen + toilet + staircase widths in rear zone
    stair_x = ox + W - STAIR_W    # staircase at rear-right
    k_w = max(W * 0.55, 7.0 / d_stair)
    t_w = W - STAIR_W - IWT - k_w - IWT   # toilet between kitchen and staircase

    # ── Ground Floor ──────────────────────────────────────────────────────
    gf_rooms: list[Room] = []

    # Front zone: living + optional parking
    if cfg.parking:
        gf_rooms.append(_r("gf_parking", "Parking", "parking", ox, oy, PARK_W, d_front))
        living_x = ox + PARK_W + IWT
        living_w = W - PARK_W - IWT
        gf_rooms.append(_r("gf_living", "Living / Hall", "living", living_x, oy, living_w, d_front))
    else:
        gf_rooms.append(_r("gf_living", "Living / Hall", "living", ox, oy, W, d_front))

    # Rear zone: kitchen | toilet | staircase
    gf_rooms.append(_r("gf_kitchen", "Kitchen", "kitchen", ox, stair_y, k_w, d_stair))
    if t_w > 0.5:
        gf_rooms.append(_r("gf_toilet_1", "Toilet 1", "toilet",
                           ox + k_w + IWT, stair_y, t_w, d_stair))
    gf_rooms.append(_r("gf_stair", "Staircase", "staircase", stair_x, stair_y, STAIR_W, d_stair))

    # ── First Floor ───────────────────────────────────────────────────────
    ff_rooms: list[Room] = []

    # Front zone: bedrooms
    if cfg.bhk == 2:
        bw = (W - IWT) / 2
        ff_rooms.append(_r("ff_bed_1", "Bedroom 1", "bedroom", ox, oy, bw, d_front))
        ff_rooms.append(_r("ff_bed_2", "Bedroom 2", "bedroom", ox + bw + IWT, oy, W - bw - IWT, d_front))
    else:  # 3 BHK
        bw = (W - 2 * IWT) / 3
        ff_rooms.append(_r("ff_bed_1", "Bedroom 1", "bedroom", ox, oy, bw, d_front))
        ff_rooms.append(_r("ff_bed_2", "Bedroom 2", "bedroom", ox + bw + IWT, oy, bw, d_front))
        ff_rooms.append(_r("ff_bed_3", "Bedroom 3", "bedroom",
                           ox + 2 * (bw + IWT), oy, W - 2 * (bw + IWT), d_front))

    # Rear zone: staircase + toilet(s), aligned with ground
    ff_rooms.append(_r("ff_stair", "Staircase", "staircase", stair_x, stair_y, STAIR_W, d_stair))
    toilet_zone_w = W - STAIR_W - IWT
    if cfg.toilets >= 2:
        ff_rooms.append(_r("ff_toilet_2", "Toilet 2", "toilet",
                           ox, stair_y, toilet_zone_w, d_stair))
    else:
        ff_rooms.append(_r("ff_landing", "Landing", "utility",
                           ox, stair_y, toilet_zone_w, d_stair))

    gf = FloorPlan(floor=0, rooms=gf_rooms, columns=_columns_from_rooms(gf_rooms))
    ff = FloorPlan(floor=1, rooms=ff_rooms, columns=_columns_from_rooms(ff_rooms))

    from .models import ComplianceResult
    return Layout(id="C", name="Rear Staircase", ground_floor=gf, first_floor=ff,
                  compliance=ComplianceResult(passed=True))
