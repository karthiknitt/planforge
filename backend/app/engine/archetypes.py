"""
Six parametric layout archetypes for rectangular G+1 plots.

Coordinate system:
  x - east (left to right, 0 at plot left edge)
  y - north (front to rear, 0 at road/front edge)

Floor plate origin (ox, oy) is the inner face of the external walls.
All room coordinates are inner-face to inner-face (wall thickness excluded).

Wall thicknesses are passed in from the caller (read from compliance_rules.json
by generator.py). Module-level EWT/IWT are kept as fallback defaults only.
"""

from __future__ import annotations

from .models import Column, FloorPlan, FloorPlate, Layout, PlotConfig, Room

# Fallback defaults - actual values are read from compliance_rules.json by generator.py
EWT = 0.23  # external wall thickness (m)
IWT = 0.115  # internal wall thickness (m)
STAIR_W = 0.9  # staircase clear width (m)
STAIR_D = 3.0  # staircase + landing depth (m)
PARK_W = 2.75  # car parking bay width (m) — NBC minimum
POOJA_W = 1.5  # pooja room width
POOJA_D = 1.5  # pooja room depth
STUDY_W = 2.5  # study room minimum width


def _inscribed_plate(cfg: PlotConfig, ewt: float) -> FloorPlate:
    """Largest safe axis-aligned rectangle inside the buildable polygon of a
    CONVEX plot (trapezoid/quad): for convex shapes, an x-interval valid at
    both the bottom and top edges is valid at every height in between."""
    from shapely.geometry import LineString

    from app.engine.geometry import buildable_polygon

    inset = buildable_polygon(cfg, wall_clearance=ewt)
    if inset.is_empty:
        raise ValueError("Plot too small for given setbacks and wall thickness")
    minx, miny, maxx, maxy = inset.bounds
    eps = 1e-6
    bot = inset.intersection(
        LineString([(minx - 1, miny + eps), (maxx + 1, miny + eps)])
    )
    top = inset.intersection(
        LineString([(minx - 1, maxy - eps), (maxx + 1, maxy - eps)])
    )
    if bot.is_empty or top.is_empty:
        raise ValueError("Plot too small for given setbacks and wall thickness")
    x_lo = max(bot.bounds[0], top.bounds[0])
    x_hi = min(bot.bounds[2], top.bounds[2])
    if x_hi - x_lo <= 0:
        raise ValueError("Plot too narrow for given setbacks")
    return FloorPlate(
        ox=round(x_lo, 3),
        oy=round(miny, 3),
        width=round(x_hi - x_lo, 3),
        depth=round(maxy - miny, 3),
    )


def _trapezoid_floor_plate(cfg: PlotConfig, ewt: float) -> FloorPlate:
    # Safe inscribed rectangle of the true per-edge inset. The old version
    # anchored min(front,rear) width at the LEFT setback — but trapezoid
    # edges are centred, so rooms could poke out of the slanted side.
    return _inscribed_plate(cfg, ewt)


def _l_shaped_floor_plate(cfg: PlotConfig, ewt: float) -> FloorPlate:
    """Return a rectangular FloorPlate for the main (larger) body of an L-shaped plot.

    The floor plate is derived from the bounding rectangle of the L-shape, then inset
    by setbacks + wall thickness.  Rooms that extend into the cutout zone will be
    clipped by a post-processing step in generator.py.
    """
    ox = cfg.setback_left + ewt
    oy = cfg.setback_front + ewt
    width = cfg.plot_width - cfg.setback_left - cfg.setback_right - 2 * ewt
    depth = cfg.plot_length - cfg.setback_front - cfg.setback_rear - 2 * ewt
    return FloorPlate(ox=ox, oy=oy, width=width, depth=depth)


def _quad_floor_plate(cfg: PlotConfig, ewt: float) -> FloorPlate:
    from shapely.geometry import Polygon

    poly = Polygon(cfg.plot_corners)
    if not poly.is_valid or not poly.is_simple:
        raise ValueError("Quadrilateral corners do not form a valid simple polygon")
    # Safe inscribed rectangle of the true per-edge inset (old version used a
    # uniform averaged-setback buffer and the inset's bounding box, which both
    # under-enforces the front setback and can poke outside slanted edges).
    return _inscribed_plate(cfg, ewt)


def _l_shaped_floor_plate(cfg: PlotConfig, ewt: float) -> FloorPlate:
    """Return a FloorPlate for the PRIMARY rectangle of an L-shaped plot.

    The L-shape is decomposed into two overlapping rectangles.  The PRIMARY
    rectangle is the one that covers the full plot dimension in at least one
    axis (the larger "arm").  All archetype rooms are placed within this safe
    rectangle — the secondary arm's area is later filled by _fill_blank_areas.

    Corner → primary rectangle mapping (plot_width W, plot_length L,
    cutout_width cw, cutout_height ch):
      NE: full-width × (L − ch) strip from front  [ox, oy, W−sb, L−ch−sb]
      NW: full-width × (L − ch) strip from front  (same)
      SE: full-width × (L − ch) strip from rear   [ox, oy+ch, W−sb, L−ch−sb]
      SW: same as SE

    The secondary arm (partial-width strip near the cutout) is intentionally
    excluded so archetype room placement stays inside the valid polygon.
    """
    sb_l = cfg.setback_left + ewt
    sb_f = cfg.setback_front + ewt

    W = cfg.plot_width
    L = cfg.plot_length
    cw = cfg.cutout_width
    ch = cfg.cutout_height
    corner = (cfg.cutout_corner or "NE").upper()

    # Two candidate decomposition rects (before setback):
    # Rect1: full-width strip, height = L − ch  (strips near front or rear)
    # Rect2: (W − cw) strip,  height = full L   (strips near left or right)
    r1_area = W * (L - ch)
    r2_area = (W - cw) * L

    if corner in ("NE", "NW"):
        # Cutout at rear — primary is the front full-width strip (front to cutout line).
        # The "top" of this strip faces the cutout interior, NOT the plot boundary,
        # so no rear setback is applied there — only ewt (internal wall face).
        # R2 is the side column (left for NW, right for NE) spanning the full depth.
        if r1_area >= r2_area:
            ox = sb_l
            oy = sb_f
            w = W - cfg.setback_left - cfg.setback_right - 2 * ewt
            # depth up to cutout line (inner face): L - ch - ewt, minus front setback/ewt
            d = (L - ch - ewt) - sb_f
        else:
            if corner == "NE":
                ox = sb_l  # left column avoids cutout on right
            else:  # NW
                ox = cw + sb_l  # right column avoids cutout on left
            oy = sb_f
            w = (W - cw) - cfg.setback_left - cfg.setback_right - 2 * ewt
            d = L - cfg.setback_front - cfg.setback_rear - 2 * ewt
    else:  # SE, SW
        # Cutout at front — primary is the rear full-width strip (cutout line to rear).
        if r1_area >= r2_area:
            ox = sb_l
            oy = ch + ewt + sb_f  # start at cutout line inner face
            w = W - cfg.setback_left - cfg.setback_right - 2 * ewt
            d = (L - ch) - cfg.setback_front - cfg.setback_rear - 2 * ewt
        else:
            if corner == "SE":
                ox = sb_l
            else:  # SW
                ox = cw + sb_l
            oy = sb_f
            w = (W - cw) - cfg.setback_left - cfg.setback_right - 2 * ewt
            d = L - cfg.setback_front - cfg.setback_rear - 2 * ewt

    if w <= 0 or d <= 0:
        raise ValueError(
            "L-shaped plot too small for given setbacks and wall thickness"
        )

    return FloorPlate(
        ox=round(ox, 3), oy=round(oy, 3), width=round(w, 3), depth=round(d, 3)
    )


def _floor_plate(cfg: PlotConfig, ewt: float) -> FloorPlate:
    if cfg.plot_shape == "quadrilateral" and cfg.plot_corners:
        return _quad_floor_plate(cfg, ewt)
    if cfg.plot_shape == "l_shaped":
        return _l_shaped_floor_plate(cfg, ewt)
    if (
        cfg.plot_shape == "trapezoid"
        and cfg.plot_front_width > 0
        and cfg.plot_rear_width > 0
    ):
        return _trapezoid_floor_plate(cfg, ewt)
    if cfg.plot_shape == "l_shaped" and cfg.cutout_width > 0 and cfg.cutout_height > 0:
        return _l_shaped_floor_plate(cfg, ewt)
    ox = cfg.setback_left + ewt
    oy = cfg.setback_front + ewt
    width = cfg.plot_width - cfg.setback_left - cfg.setback_right - 2 * ewt
    depth = cfg.plot_length - cfg.setback_front - cfg.setback_rear - 2 * ewt
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


def _bed_rooms_ff(
    n: int,
    ox: float,
    bed_y: float,
    W: float,
    d_bed: float,
    iwt: float,
    floor_prefix: str = "ff",
) -> list[Room]:
    """Allocate n bedrooms across the first floor width."""
    rooms: list[Room] = []
    if n == 1:
        rooms.append(
            _r(f"{floor_prefix}_bed_1", "Bedroom 1", "bedroom", ox, bed_y, W, d_bed)
        )
    elif n == 2:
        bw = (W - iwt) / 2
        rooms.append(
            _r(f"{floor_prefix}_bed_1", "Bedroom 1", "bedroom", ox, bed_y, bw, d_bed)
        )
        rooms.append(
            _r(
                f"{floor_prefix}_bed_2",
                "Bedroom 2",
                "bedroom",
                ox + bw + iwt,
                bed_y,
                W - bw - iwt,
                d_bed,
            )
        )
    elif n == 3:
        bw = (W - 2 * iwt) / 3
        rooms.append(
            _r(f"{floor_prefix}_bed_1", "Bedroom 1", "bedroom", ox, bed_y, bw, d_bed)
        )
        rooms.append(
            _r(
                f"{floor_prefix}_bed_2",
                "Bedroom 2",
                "bedroom",
                ox + bw + iwt,
                bed_y,
                bw,
                d_bed,
            )
        )
        rooms.append(
            _r(
                f"{floor_prefix}_bed_3",
                "Bedroom 3",
                "bedroom",
                ox + 2 * (bw + iwt),
                bed_y,
                W - 2 * (bw + iwt),
                d_bed,
            )
        )
    else:  # 4 bedrooms — 3 across + one extra occupying rear strip
        bw = (W - 2 * iwt) / 3
        half_d = d_bed / 2 - iwt / 2
        for i, label in enumerate(["Bedroom 1", "Bedroom 2", "Bedroom 3"]):
            rooms.append(
                _r(
                    f"{floor_prefix}_bed_{i + 1}",
                    label,
                    "bedroom",
                    ox + i * (bw + iwt),
                    bed_y,
                    bw,
                    half_d,
                )
            )
        rooms.append(
            _r(
                f"{floor_prefix}_bed_4",
                "Bedroom 4",
                "bedroom",
                ox,
                bed_y + half_d + iwt,
                W,
                d_bed - half_d - iwt,
            )
        )
    return rooms


def _stair_band_rooms(
    cfg: PlotConfig,
    x: float,
    y: float,
    band_w: float,
    band_d: float,
    iwt: float,
    *,
    prefix: str = "ff",
    toilet_id: str = "ff_toilet_2",
    toilet_name: str = "Toilet 2",
    want_toilet: bool | None = None,
    align_widths: tuple[float, float] | None = None,
) -> list[Room]:
    """Fill the FF strip beside the staircase.

    The old archetypes gave the whole band to Toilet 2 (or Landing); on wide
    plots that made a 13 m x 3 m "toilet" which _split_oversized_wet_rooms
    carved into a ~38 sqm Passage. Cap the toilet at spec-sane size and turn
    the remainder into a real room (Family Lounge) or a small Landing.

    Order within the band matters: the filler room (circulation) sits hard
    against the staircase and the toilet takes the far end. Toilet-first —
    the original order — left the stair core with a WC as its only partition
    long enough to take a door, so `derive_openings` put the stair's door
    into the toilet (production project "MyLatest", 2026-07). The staircase
    needs a circulation neighbour to open onto; the toilet then opens off
    that room, which is also the conventional arrangement.

    ``align_widths``, when given, is the ground floor's own (lead, last) slot
    split for this same x-span (e.g. living/parking) — reusing it here lands
    the filler/toilet joint on the exact same grid line as the GF joint, so
    the two floors' columns stack (issue #51). The toilet still takes the
    leading edge of the LAST (aligned) slot, never the first, preserving the
    staircase's circulation neighbour; an oversized toilet that doesn't fully
    fill the slot is caught by the existing post-fill wet-room split, same as
    the unaligned path below.
    """
    if want_toilet is None:
        want_toilet = cfg.toilets >= 2
    want_t = want_toilet and band_w > 0.5

    if align_widths and want_t:
        lead_w, last_w = align_widths
        aligned_filler = (
            _band_filler_rooms(prefix, x, y, lead_w, band_d) if lead_w > 0.5 else []
        )
        if aligned_filler:
            t_w = min(last_w, 2.0)
            return aligned_filler + [
                _r(toilet_id, toilet_name, "toilet", x + lead_w + iwt, y, t_w, band_d)
            ]
        # Lead slot too narrow to be a real room — fall through to the
        # unaligned default split below.

    t_w = min(band_w, 2.0) if want_t else 0.0
    rem_w = band_w - t_w - iwt if want_t else band_w

    filler = _band_filler_rooms(prefix, x, y, rem_w, band_d) if rem_w > 0.5 else []
    if not want_t:
        return filler
    if not filler:
        # Nothing else fits beside the stair — the toilet takes the whole band
        # and the door placer falls back to its last resort. Rare, and better
        # than dropping a toilet the config asked for.
        return [_r(toilet_id, toilet_name, "toilet", x, y, band_w, band_d)]
    return filler + [
        _r(toilet_id, toilet_name, "toilet", x + rem_w + iwt, y, t_w, band_d)
    ]


def _band_filler_rooms(
    prefix: str, x: float, y: float, w: float, d: float
) -> list[Room]:
    """Turn a leftover band strip into a Family Lounge (if room-sized) or Landing."""
    if w <= 0.5:
        return []
    if w * d >= 9.5:
        return [_r(f"{prefix}_lounge", "Family Lounge", "living", x, y, w, d)]
    # "passage", not "utility": a landing is circulation. `utility` is in
    # plan_geometry._WET_TYPES, so typing it that way gave the landing a
    # 750 mm wet door, a single-door cap, a ventilator, and no-transit status
    # in the reachability BFS — which is why rooms beyond a landing looked
    # unreachable and the navigability gate rejected whole layout sets.
    return [_r(f"{prefix}_landing", "Landing", "passage", x, y, w, d)]


# ---------------------------------------------------------------------------
# Layout A - Front Staircase
# ---------------------------------------------------------------------------


def layout_a(cfg: PlotConfig, ewt: float = EWT, iwt: float = IWT) -> Layout:
    fp = _floor_plate(cfg, ewt)
    ox, oy, W, D = fp.ox, fp.oy, fp.width, fp.depth

    n_beds = cfg.num_bedrooms

    # Zone depths (front → rear)
    d_stair = STAIR_D
    d_service = max(3.0, 4.5 / max(W * 0.55, 0.1))
    d_living = D - d_stair - d_service - 2 * iwt

    # Kitchen/toilet width split
    k_w = max(W * 0.55, 4.5 / d_service)
    t_w = W - k_w - iwt

    # -- Ground Floor ----------------------------------------------------------
    gf_rooms: list[Room] = []

    gf_rooms.append(_r("gf_stair", "Staircase", "staircase", ox, oy, STAIR_W, d_stair))

    if cfg.parking:
        # Foyer inboard of the parking bay, so it — not the parking — is the
        # staircase's neighbour. Parking is a no-transit room like a wet room,
        # so a stair boxed between the plot edge and a parking bay has no
        # circulation partition to take its door from. Both stay in the front
        # band, so the bay keeps its road access either way.
        band_rest = W - STAIR_W - iwt - PARK_W - iwt
        cur_x = ox + STAIR_W + iwt
        # Foyer capped at a real foyer's size, not the whole leftover band:
        # handing it every spare metre produced a ~36 sqm "passage", which is
        # the oversized-circulation pathology generator._fill_blank_areas
        # exists to undo — it re-absorbed the foyer and put the parking back
        # against the stair. Cap it, then give the remainder to a real room.
        foyer_w = min(band_rest, 2.0) if band_rest > 0.3 else 0.0
        if foyer_w:
            gf_rooms.append(
                _r("gf_foyer", "Foyer", "passage", cur_x, oy, foyer_w, d_stair)
            )
            cur_x += foyer_w + iwt
        gf_rooms.append(
            _r("gf_parking", "Parking", "parking", cur_x, oy, PARK_W, d_stair)
        )
        cur_x += PARK_W + iwt
        gf_rooms += _band_filler_rooms("gf", cur_x, oy, ox + W - cur_x, d_stair)
    else:
        entry_w = W - STAIR_W - iwt
        gf_rooms.append(
            _r(
                "gf_entry",
                "Entry / Foyer",
                "passage",
                ox + STAIR_W + iwt,
                oy,
                entry_w,
                d_stair,
            )
        )

    living_y = oy + d_stair + iwt

    # 4 BHK: add ground-floor bedroom at rear of living zone
    if n_beds == 4:
        d_living_zone = d_living * 0.55
        d_gf_bed = d_living - d_living_zone - iwt
        gf_rooms.append(
            _r("gf_living", "Living / Hall", "living", ox, living_y, W, d_living_zone)
        )
        gf_bed_y = living_y + d_living_zone + iwt
        gf_rooms.append(
            _r("gf_bed_m", "Master Bedroom", "bedroom", ox, gf_bed_y, W * 0.6, d_gf_bed)
        )
        if W * 0.4 - iwt > 1.0:
            gf_rooms.append(
                _r(
                    "gf_dining",
                    "Dining",
                    "dining",
                    ox + W * 0.6 + iwt,
                    gf_bed_y,
                    W * 0.4 - iwt,
                    d_gf_bed,
                )
            )
    else:
        gf_rooms.append(
            _r("gf_living", "Living / Hall", "living", ox, living_y, W, d_living)
        )

    # Optional pooja room (carved from toilet zone)
    svc_y = oy + D - d_service
    if cfg.has_pooja and t_w > POOJA_W + iwt + 1.0:
        gf_rooms.append(
            _r("gf_kitchen", "Kitchen", "kitchen", ox, svc_y, k_w, d_service)
        )
        pooja_w = POOJA_W
        gf_rooms.append(
            _r(
                "gf_pooja",
                "Pooja Room",
                "pooja",
                ox + k_w + iwt,
                svc_y,
                pooja_w,
                d_service,
            )
        )
        remaining_w = t_w - pooja_w - iwt
        if remaining_w > 0.5:
            gf_rooms.append(
                _r(
                    "gf_toilet_1",
                    "Toilet 1",
                    "toilet",
                    ox + k_w + iwt + pooja_w + iwt,
                    svc_y,
                    remaining_w,
                    d_service,
                )
            )
    else:
        gf_rooms.append(
            _r("gf_kitchen", "Kitchen", "kitchen", ox, svc_y, k_w, d_service)
        )
        if t_w > 0.5:
            gf_rooms.append(
                _r(
                    "gf_toilet_1",
                    "Toilet 1",
                    "toilet",
                    ox + k_w + iwt,
                    svc_y,
                    t_w,
                    d_service,
                )
            )

    # -- First Floor -----------------------------------------------------------
    ff_rooms: list[Room] = []

    ff_rooms.append(_r("ff_stair", "Staircase", "staircase", ox, oy, STAIR_W, d_stair))
    ff_rooms += _stair_band_rooms(
        cfg, ox + STAIR_W + iwt, oy, W - STAIR_W - iwt, d_stair, iwt
    )

    bed_y = oy + d_stair + iwt
    d_bed = D - d_stair - iwt

    # Study room on first floor if requested
    if cfg.has_study and d_bed > 3.5 and W > STUDY_W + iwt + 3.0:
        study_w = STUDY_W
        # Fill the full bedroom band depth — a depth cap left a dead gap
        # behind the Study (the "5.25 sqm Study with space around it" bug).
        d_study = d_bed
        ff_rooms.append(
            _r("ff_study", "Study", "study", ox + W - study_w, bed_y, study_w, d_study)
        )
        bed_W = W - study_w - iwt
        ff_rooms += _bed_rooms_ff(
            min(n_beds, 3) if n_beds == 4 else n_beds, ox, bed_y, bed_W, d_bed, iwt
        )
    else:
        bed_count = min(n_beds, 3) if n_beds == 4 else n_beds
        ff_rooms += _bed_rooms_ff(bed_count, ox, bed_y, W, d_bed, iwt)

    # Balcony on first floor road-facing side
    if cfg.has_balcony and d_bed > 2.5:
        bal_d = 1.2
        for rm in ff_rooms:
            if rm.type in ("bedroom", "study") and abs(rm.y - bed_y) < 0.01:
                rm.depth = round(rm.depth - bal_d - iwt, 3)
        ff_rooms.append(
            _r(
                "ff_balcony",
                "Balcony",
                "balcony",
                ox,
                bed_y + (d_bed - bal_d),
                W,
                bal_d,
            )
        )

    gf = FloorPlan(floor=0, rooms=gf_rooms, columns=_columns_from_rooms(gf_rooms))
    ff = FloorPlan(floor=1, rooms=ff_rooms, columns=_columns_from_rooms(ff_rooms))

    from .models import ComplianceResult

    return Layout(
        id="A",
        name="Front Staircase",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )


# ---------------------------------------------------------------------------
# Layout B - Centre Staircase
# ---------------------------------------------------------------------------


def layout_b(cfg: PlotConfig, ewt: float = EWT, iwt: float = IWT) -> Layout:
    fp = _floor_plate(cfg, ewt)
    ox, oy, W, D = fp.ox, fp.oy, fp.width, fp.depth

    n_beds = cfg.num_bedrooms

    d_front = D * 0.40
    d_stair = STAIR_D
    d_rear = D - d_front - d_stair - 2 * iwt

    stair_y = oy + d_front + iwt
    rear_y = stair_y + d_stair + iwt

    # -- Ground Floor ----------------------------------------------------------
    gf_rooms: list[Room] = []

    if cfg.parking:
        gf_rooms.append(_r("gf_parking", "Parking", "parking", ox, oy, PARK_W, d_front))
        living_x = ox + PARK_W + iwt
        gf_rooms.append(
            _r(
                "gf_living",
                "Living / Hall",
                "living",
                living_x,
                oy,
                W - PARK_W - iwt,
                d_front,
            )
        )
    else:
        gf_rooms.append(_r("gf_living", "Living / Hall", "living", ox, oy, W, d_front))

    gf_rooms.append(
        _r("gf_stair", "Staircase", "staircase", ox, stair_y, STAIR_W, d_stair)
    )
    # Same band treatment as the upper floor: circulation against the stair,
    # the toilet capped and pushed to the far end. Handing the whole strip to
    # "Toilet 1" made the stair's only side neighbour a wet room (so its door
    # had nowhere legal to go) AND produced a ~9 m wide toilet that
    # _split_oversized_wet_rooms then had to carve up. A distinct `gf_mid`
    # prefix keeps the filler's id clear of any `gf_lounge` the archetype or
    # the wet-room split may already have created.
    gf_rooms += _stair_band_rooms(
        cfg,
        ox + STAIR_W + iwt,
        stair_y,
        W - STAIR_W - iwt,
        d_stair,
        iwt,
        prefix="gf_mid",
        toilet_id="gf_toilet_1",
        toilet_name="Toilet 1",
        want_toilet=True,
    )

    # Rear zone: kitchen + optional pooja
    if cfg.has_pooja and W > 4.0:
        k_w = W - POOJA_W - iwt
        gf_rooms.append(_r("gf_kitchen", "Kitchen", "kitchen", ox, rear_y, k_w, d_rear))
        gf_rooms.append(
            _r(
                "gf_pooja",
                "Pooja Room",
                "pooja",
                ox + k_w + iwt,
                rear_y,
                POOJA_W,
                d_rear,
            )
        )
    else:
        gf_rooms.append(_r("gf_kitchen", "Kitchen", "kitchen", ox, rear_y, W, d_rear))

    # 4 BHK: ground floor gets 1 extra bedroom in rear zone
    if n_beds == 4 and d_rear > 3.0:
        gf_rooms.append(
            _r("gf_dining", "Dining", "dining", ox, rear_y, W, d_rear * 0.5)
        )
        gf_rooms.append(
            _r(
                "gf_bed_m",
                "Master Bedroom",
                "bedroom",
                ox,
                rear_y + d_rear * 0.5 + iwt,
                W,
                d_rear * 0.5 - iwt,
            )
        )

    # -- First Floor -----------------------------------------------------------
    ff_rooms: list[Room] = []

    bed_count = min(n_beds, 3) if n_beds >= 3 else n_beds
    bw = (W - iwt) / 2 if bed_count <= 2 else (W - 2 * iwt) / 3
    if bed_count == 1:
        ff_rooms.append(_r("ff_bed_1", "Bedroom 1", "bedroom", ox, oy, W, d_front))
    elif bed_count == 2:
        ff_rooms.append(_r("ff_bed_1", "Bedroom 1", "bedroom", ox, oy, bw, d_front))
        ff_rooms.append(
            _r(
                "ff_bed_2",
                "Bedroom 2",
                "bedroom",
                ox + bw + iwt,
                oy,
                W - bw - iwt,
                d_front,
            )
        )
    else:
        ff_rooms.append(_r("ff_bed_1", "Bedroom 1", "bedroom", ox, oy, bw, d_front))
        ff_rooms.append(
            _r("ff_bed_2", "Bedroom 2", "bedroom", ox + bw + iwt, oy, bw, d_front)
        )

    ff_rooms.append(
        _r("ff_stair", "Staircase", "staircase", ox, stair_y, STAIR_W, d_stair)
    )
    ff_rooms += _stair_band_rooms(
        cfg, ox + STAIR_W + iwt, stair_y, W - STAIR_W - iwt, d_stair, iwt
    )

    # Rear zone on first floor: bed 3 (3BHK+), study, or utility
    if n_beds >= 3:
        ff_rooms.append(_r("ff_bed_3", "Bedroom 3", "bedroom", ox, rear_y, W, d_rear))
    elif cfg.has_study:
        ff_rooms.append(_r("ff_study", "Study", "study", ox, rear_y, W, d_rear))
    else:
        ff_rooms.append(
            _r("ff_utility", "Study / Utility", "utility", ox, rear_y, W, d_rear)
        )

    gf = FloorPlan(floor=0, rooms=gf_rooms, columns=_columns_from_rooms(gf_rooms))
    ff = FloorPlan(floor=1, rooms=ff_rooms, columns=_columns_from_rooms(ff_rooms))

    from .models import ComplianceResult

    return Layout(
        id="B",
        name="Centre Staircase",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )


# ---------------------------------------------------------------------------
# Layout C - Rear Staircase
# ---------------------------------------------------------------------------


def layout_c(cfg: PlotConfig, ewt: float = EWT, iwt: float = IWT) -> Layout:
    fp = _floor_plate(cfg, ewt)
    ox, oy, W, D = fp.ox, fp.oy, fp.width, fp.depth

    n_beds = cfg.num_bedrooms
    d_stair = STAIR_D
    d_front = D - d_stair - iwt

    stair_y = oy + d_front + iwt
    stair_x = ox + W - STAIR_W  # staircase at rear-right
    k_w = max(W * 0.55, 4.5 / d_stair)
    t_w = W - STAIR_W - iwt - k_w - iwt

    # -- Ground Floor ----------------------------------------------------------
    gf_rooms: list[Room] = []

    if cfg.parking:
        gf_rooms.append(_r("gf_parking", "Parking", "parking", ox, oy, PARK_W, d_front))
        living_x = ox + PARK_W + iwt
        living_w = W - PARK_W - iwt
        gf_rooms.append(
            _r("gf_living", "Living / Hall", "living", living_x, oy, living_w, d_front)
        )
    else:
        # For 4BHK, split front zone: living + master bedroom
        if n_beds == 4 and d_front > 4.0:
            d_lv = d_front * 0.55
            gf_rooms.append(_r("gf_living", "Living / Hall", "living", ox, oy, W, d_lv))
            gf_rooms.append(
                _r(
                    "gf_bed_m",
                    "Master Bedroom",
                    "bedroom",
                    ox,
                    oy + d_lv + iwt,
                    W * 0.65,
                    d_front - d_lv - iwt,
                )
            )
            gf_rooms.append(
                _r(
                    "gf_dining",
                    "Dining",
                    "dining",
                    ox + W * 0.65 + iwt,
                    oy + d_lv + iwt,
                    W * 0.35 - iwt,
                    d_front - d_lv - iwt,
                )
            )
        else:
            gf_rooms.append(
                _r("gf_living", "Living / Hall", "living", ox, oy, W, d_front)
            )

    gf_rooms.append(_r("gf_kitchen", "Kitchen", "kitchen", ox, stair_y, k_w, d_stair))
    if cfg.has_pooja and t_w > POOJA_W + 0.5:
        gf_rooms.append(
            _r(
                "gf_pooja",
                "Pooja Room",
                "pooja",
                ox + k_w + iwt,
                stair_y,
                POOJA_W,
                d_stair,
            )
        )
        rem_w = t_w - POOJA_W - iwt
        if rem_w > 0.5:
            gf_rooms.append(
                _r(
                    "gf_toilet_1",
                    "Toilet 1",
                    "toilet",
                    ox + k_w + iwt + POOJA_W + iwt,
                    stair_y,
                    rem_w,
                    d_stair,
                )
            )
    elif t_w > 0.5:
        gf_rooms.append(
            _r(
                "gf_toilet_1",
                "Toilet 1",
                "toilet",
                ox + k_w + iwt,
                stair_y,
                t_w,
                d_stair,
            )
        )
    gf_rooms.append(
        _r("gf_stair", "Staircase", "staircase", stair_x, stair_y, STAIR_W, d_stair)
    )

    # -- First Floor -----------------------------------------------------------
    ff_rooms: list[Room] = []

    bed_count_ff = min(n_beds, 3) if n_beds == 4 else n_beds
    ff_rooms += _bed_rooms_ff(bed_count_ff, ox, oy, W, d_front, iwt)

    # Balcony
    if cfg.has_balcony:
        bal_d = 1.2
        for rm in ff_rooms:
            if rm.type == "bedroom" and abs(rm.y - oy) < 0.01:
                rm.depth = round(rm.depth - bal_d - iwt, 3)
        ff_rooms.append(
            _r("ff_balcony", "Balcony", "balcony", ox, oy + (d_front - bal_d), W, bal_d)
        )

    ff_rooms.append(
        _r("ff_stair", "Staircase", "staircase", stair_x, stair_y, STAIR_W, d_stair)
    )
    toilet_zone_w = W - STAIR_W - iwt
    ff_rooms += _stair_band_rooms(cfg, ox, stair_y, toilet_zone_w, d_stair, iwt)

    gf = FloorPlan(floor=0, rooms=gf_rooms, columns=_columns_from_rooms(gf_rooms))
    ff = FloorPlan(floor=1, rooms=ff_rooms, columns=_columns_from_rooms(ff_rooms))

    from .models import ComplianceResult

    return Layout(
        id="C",
        name="Rear Staircase",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )


# ---------------------------------------------------------------------------
# Layout D - Corner Entry (staircase at corner)
# ---------------------------------------------------------------------------


def layout_d(cfg: PlotConfig, ewt: float = EWT, iwt: float = IWT) -> Layout:
    fp = _floor_plate(cfg, ewt)
    ox, oy, W, D = fp.ox, fp.oy, fp.width, fp.depth

    n_beds = cfg.num_bedrooms
    d_stair = STAIR_D

    # Staircase occupies front-left corner
    # Living runs the rest of the road-facing frontage
    living_w = W - STAIR_W - iwt
    d_front = max(d_stair, D * 0.35)
    d_rear = D - d_front - iwt

    rear_y = oy + d_front + iwt

    # -- Ground Floor ----------------------------------------------------------
    gf_rooms: list[Room] = []

    gf_rooms.append(_r("gf_stair", "Staircase", "staircase", ox, oy, STAIR_W, d_stair))

    if cfg.parking:
        # Living inboard of the parking bay so it — not the parking — is the
        # staircase's neighbour. Parking is a no-transit room, so a stair
        # sandwiched between the plot edge and a parking bay has no
        # circulation partition its door can legally use. Both stay in the
        # front band, so the bay keeps its road access. Same reasoning as
        # layout_a's entry band and `_stair_band_rooms` on the upper floor.
        hall_w = living_w - PARK_W - iwt
        gf_rooms.append(
            _r(
                "gf_living",
                "Living / Hall",
                "living",
                ox + STAIR_W + iwt,
                oy,
                hall_w,
                d_front,
            )
        )
        gf_rooms.append(
            _r(
                "gf_parking",
                "Parking",
                "parking",
                ox + STAIR_W + iwt + hall_w + iwt,
                oy,
                PARK_W,
                d_stair,
            )
        )
    else:
        gf_rooms.append(
            _r(
                "gf_living",
                "Living / Hall",
                "living",
                ox + STAIR_W + iwt,
                oy,
                living_w,
                d_front,
            )
        )

    # Rear: kitchen + dining + toilet
    k_w = W * 0.55
    din_w = W * 0.30
    t_w = W - k_w - din_w - 2 * iwt

    if cfg.has_pooja and t_w > POOJA_W + 0.5:
        gf_rooms.append(_r("gf_kitchen", "Kitchen", "kitchen", ox, rear_y, k_w, d_rear))
        gf_rooms.append(
            _r("gf_dining", "Dining", "dining", ox + k_w + iwt, rear_y, din_w, d_rear)
        )
        gf_rooms.append(
            _r(
                "gf_pooja",
                "Pooja Room",
                "pooja",
                ox + k_w + iwt + din_w + iwt,
                rear_y,
                POOJA_W,
                d_rear,
            )
        )
        rem = t_w - POOJA_W - iwt
        if rem > 0.5:
            gf_rooms.append(
                _r(
                    "gf_toilet_1",
                    "Toilet 1",
                    "toilet",
                    ox + k_w + iwt + din_w + iwt + POOJA_W + iwt,
                    rear_y,
                    rem,
                    d_rear,
                )
            )
    else:
        gf_rooms.append(_r("gf_kitchen", "Kitchen", "kitchen", ox, rear_y, k_w, d_rear))
        gf_rooms.append(
            _r("gf_dining", "Dining", "dining", ox + k_w + iwt, rear_y, din_w, d_rear)
        )
        if t_w > 0.5:
            gf_rooms.append(
                _r(
                    "gf_toilet_1",
                    "Toilet 1",
                    "toilet",
                    ox + k_w + iwt + din_w + iwt,
                    rear_y,
                    t_w,
                    d_rear,
                )
            )

    # -- First Floor -----------------------------------------------------------
    ff_rooms: list[Room] = []

    ff_rooms.append(_r("ff_stair", "Staircase", "staircase", ox, oy, STAIR_W, d_stair))

    landing_w = W - STAIR_W - iwt
    # Reuse the GF living/parking split (issue #51: GF joint at 7.79 m vs FF's
    # own independent joint at 8.87 m was exactly the unstacked column pair).
    align_widths = (hall_w, PARK_W) if cfg.parking else None
    ff_rooms += _stair_band_rooms(
        cfg, ox + STAIR_W + iwt, oy, landing_w, d_stair, iwt, align_widths=align_widths
    )

    bed_y = oy + d_stair + iwt
    d_bed = D - d_stair - iwt

    bed_count = min(n_beds, 3) if n_beds == 4 else n_beds
    ff_rooms += _bed_rooms_ff(bed_count, ox, bed_y, W, d_bed, iwt, "ff")

    if cfg.has_study and d_bed > 4.0:
        last_bed = [r for r in ff_rooms if r.type == "bedroom"][-1]
        last_bed.depth = round(last_bed.depth - 2.5 - iwt, 3)
        ff_rooms.append(
            _r(
                "ff_study",
                "Study",
                "study",
                last_bed.x,
                last_bed.y + last_bed.depth + iwt,
                last_bed.width,
                2.5,
            )
        )

    gf = FloorPlan(floor=0, rooms=gf_rooms, columns=_columns_from_rooms(gf_rooms))
    ff = FloorPlan(floor=1, rooms=ff_rooms, columns=_columns_from_rooms(ff_rooms))

    from .models import ComplianceResult

    return Layout(
        id="D",
        name="Corner Entry",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )


# ---------------------------------------------------------------------------
# Layout E - Open Plan (kitchen + dining merged, living separate)
# ---------------------------------------------------------------------------


def layout_e(cfg: PlotConfig, ewt: float = EWT, iwt: float = IWT) -> Layout:
    fp = _floor_plate(cfg, ewt)
    ox, oy, W, D = fp.ox, fp.oy, fp.width, fp.depth

    n_beds = cfg.num_bedrooms
    d_stair = STAIR_D

    # Front zone: living (full width) — generous for open feel
    d_front = max(D * 0.38, 4.0)
    # Staircase in centre rear
    d_mid = d_stair
    d_rear = D - d_front - d_mid - 2 * iwt

    stair_y = oy + d_front + iwt
    rear_y = stair_y + d_mid + iwt

    # -- Ground Floor ----------------------------------------------------------
    gf_rooms: list[Room] = []

    if cfg.parking:
        gf_rooms.append(_r("gf_parking", "Parking", "parking", ox, oy, PARK_W, d_front))
        lv_x = ox + PARK_W + iwt
        gf_rooms.append(
            _r(
                "gf_living",
                "Living / Hall",
                "living",
                lv_x,
                oy,
                W - PARK_W - iwt,
                d_front,
            )
        )
    else:
        gf_rooms.append(_r("gf_living", "Living / Hall", "living", ox, oy, W, d_front))

    # Centre: stair + toilet
    gf_rooms.append(
        _r("gf_stair", "Staircase", "staircase", ox, stair_y, STAIR_W, d_mid)
    )
    t_ctr_w = W - STAIR_W - iwt
    t1_w = min(t_ctr_w, 2.0)
    gf_rooms.append(
        _r(
            "gf_toilet_1",
            "Toilet 1",
            "toilet",
            ox + STAIR_W + iwt,
            stair_y,
            t1_w,
            d_mid,
        )
    )
    gf_rooms += _band_filler_rooms(
        "gf", ox + STAIR_W + iwt + t1_w + iwt, stair_y, t_ctr_w - t1_w - iwt, d_mid
    )

    # Rear: open plan kitchen + dining
    kit_w = W * 0.55
    din_w = W - kit_w
    gf_rooms.append(_r("gf_kitchen", "Kitchen", "kitchen", ox, rear_y, kit_w, d_rear))
    gf_rooms.append(
        _r("gf_dining", "Dining", "dining", ox + kit_w, rear_y, din_w, d_rear)
    )

    if cfg.has_pooja and d_rear > 2.0:
        din_w_new = din_w - POOJA_W - iwt
        gf_rooms[-1] = _r(
            "gf_dining", "Dining", "dining", ox + kit_w, rear_y, din_w_new, d_rear
        )
        gf_rooms.append(
            _r(
                "gf_pooja",
                "Pooja Room",
                "pooja",
                ox + kit_w + din_w_new + iwt,
                rear_y,
                POOJA_W,
                d_rear,
            )
        )

    # -- First Floor -----------------------------------------------------------
    ff_rooms: list[Room] = []

    ff_rooms.append(
        _r("ff_stair", "Staircase", "staircase", ox, stair_y, STAIR_W, d_mid)
    )
    ff_rooms += _stair_band_rooms(cfg, ox + STAIR_W + iwt, stair_y, t_ctr_w, d_mid, iwt)

    # Front zone → bedrooms
    bed_count = min(n_beds, 3) if n_beds == 4 else n_beds
    ff_rooms += _bed_rooms_ff(bed_count, ox, oy, W, d_front, iwt, "ff")

    # Rear zone → bedroom 3/4 or study
    if n_beds >= 3:
        ff_rooms.append(_r("ff_bed_3", "Bedroom 3", "bedroom", ox, rear_y, W, d_rear))
    elif cfg.has_study:
        ff_rooms.append(_r("ff_study", "Study", "study", ox, rear_y, W, d_rear))
    else:
        ff_rooms.append(
            _r("ff_utility", "Study / Utility", "utility", ox, rear_y, W, d_rear)
        )

    if cfg.has_balcony and d_front > 3.5:
        bal_d = 1.2
        for rm in ff_rooms:
            if rm.type == "bedroom" and abs(rm.y - oy) < 0.01:
                rm.depth = round(rm.depth - bal_d - iwt, 3)
        ff_rooms.append(
            _r("ff_balcony", "Balcony", "balcony", ox, oy + (d_front - bal_d), W, bal_d)
        )

    gf = FloorPlan(floor=0, rooms=gf_rooms, columns=_columns_from_rooms(gf_rooms))
    ff = FloorPlan(floor=1, rooms=ff_rooms, columns=_columns_from_rooms(ff_rooms))

    from .models import ComplianceResult

    return Layout(
        id="E",
        name="Open Plan Kitchen",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )


# ---------------------------------------------------------------------------
# Layout F - Courtyard (conditional: plot area >= 150 sqm)
# ---------------------------------------------------------------------------


def layout_f(cfg: PlotConfig, ewt: float = EWT, iwt: float = IWT) -> Layout | None:
    """Returns None if plot is too small for courtyard layout."""
    fp = _floor_plate(cfg, ewt)
    ox, oy, W, D = fp.ox, fp.oy, fp.width, fp.depth

    # Require minimum buildable dimensions for courtyard
    if W < 8.0 or D < 10.0:
        return None

    n_beds = cfg.num_bedrooms
    ct_w = W * 0.35  # courtyard width
    ct_d = D * 0.30  # courtyard depth
    ct_x = ox + (W - ct_w) / 2
    ct_y = oy + D * 0.35

    # -- Ground Floor ----------------------------------------------------------
    gf_rooms: list[Room] = []

    # Front: living (full width) up to courtyard
    d_front = ct_y - oy - iwt
    if cfg.parking:
        gf_rooms.append(_r("gf_parking", "Parking", "parking", ox, oy, PARK_W, d_front))
        gf_rooms.append(
            _r(
                "gf_living",
                "Living / Hall",
                "living",
                ox + PARK_W + iwt,
                oy,
                W - PARK_W - iwt,
                d_front,
            )
        )
    else:
        gf_rooms.append(_r("gf_living", "Living / Hall", "living", ox, oy, W, d_front))

    # Left of courtyard: kitchen
    k_w = ct_x - ox - iwt
    gf_rooms.append(_r("gf_kitchen", "Kitchen", "kitchen", ox, ct_y, k_w, ct_d))

    # Right of courtyard: toilet + optional pooja
    right_x = ct_x + ct_w + iwt
    right_w = ox + W - right_x
    if cfg.has_pooja and right_w > POOJA_W + 1.0:
        gf_rooms.append(
            _r("gf_pooja", "Pooja Room", "pooja", right_x, ct_y, POOJA_W, ct_d)
        )
        gf_rooms.append(
            _r(
                "gf_toilet_1",
                "Toilet 1",
                "toilet",
                right_x + POOJA_W + iwt,
                ct_y,
                right_w - POOJA_W - iwt,
                ct_d,
            )
        )
    else:
        gf_rooms.append(
            _r("gf_toilet_1", "Toilet 1", "toilet", right_x, ct_y, right_w, ct_d)
        )

    # Rear: staircase + utility/dining
    rear_y = ct_y + ct_d + iwt
    d_rear = oy + D - rear_y
    gf_rooms.append(
        _r("gf_stair", "Staircase", "staircase", ox, rear_y, STAIR_W, d_rear)
    )
    gf_rooms.append(
        _r(
            "gf_dining",
            "Dining",
            "dining",
            ox + STAIR_W + iwt,
            rear_y,
            W - STAIR_W - iwt,
            d_rear,
        )
    )

    # -- First Floor -----------------------------------------------------------
    ff_rooms: list[Room] = []

    ff_rooms.append(
        _r("ff_stair", "Staircase", "staircase", ox, rear_y, STAIR_W, d_rear)
    )
    ff_rooms += _stair_band_rooms(
        cfg, ox + STAIR_W + iwt, rear_y, W - STAIR_W - iwt, d_rear, iwt
    )

    # Bedrooms around courtyard
    bed_count = min(n_beds, 3) if n_beds == 4 else n_beds
    d_bed = ct_y + ct_d - oy
    ff_rooms += _bed_rooms_ff(bed_count, ox, oy, W, d_bed, iwt, "ff")

    if cfg.has_balcony:
        bal_d = 1.2
        for rm in ff_rooms:
            if rm.type == "bedroom" and rm.y == oy:
                rm.depth = round(rm.depth - bal_d - iwt, 3)
        ff_rooms.append(
            _r("ff_balcony", "Balcony", "balcony", ox, oy + (d_bed - bal_d), W, bal_d)
        )

    gf = FloorPlan(floor=0, rooms=gf_rooms, columns=_columns_from_rooms(gf_rooms))
    ff = FloorPlan(floor=1, rooms=ff_rooms, columns=_columns_from_rooms(ff_rooms))

    from .models import ComplianceResult

    return Layout(
        id="F",
        name="Courtyard",
        ground_floor=gf,
        first_floor=ff,
        compliance=ComplianceResult(passed=True),
    )
