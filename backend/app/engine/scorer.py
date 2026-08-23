"""Layout quality scorer for PlanForge.

Scores each Layout on 7 components (weighted sum → 0–100), see _WEIGHTS:
  20% Natural light    — % habitable rooms touching plot boundary
  25% Adjacency        — kitchen↔dining, bedroom↔toilet, living↔staircase
  10% Aspect ratio     — penalty when width/depth > 2:1 for habitable rooms
  15% Circulation      — room area / buildable area (fill efficiency)
  10% Vastu            — graded vastu_layout_score() over all floors (100 when off)
  10% Grid regularity  — structural_grid confidence + GF/FF column stacking
  10% Toilet placement — penalizes front-facade/stair-parking/no-ventilation toilets
"""

from __future__ import annotations

from .models import FloorPlan, Layout, LayoutScore, PlotConfig, Room
from app.engine.adjacency import load_adjacency_pairs


# ── Habitable room types (rooms that benefit from natural light) ──────────────
_HABITABLE = frozenset(
    [
        "living",
        "bedroom",
        "master_bedroom",
        "kitchen",
        "dining",
        "study",
        "home_office",
        "gym",
        "servant_quarter",
    ]
)

# ── Adjacency preference table ────────────────────────────────────────────────

_ADJACENCY_PAIRS: list[tuple[str, str, float]] = list(load_adjacency_pairs())
_MAX_ADJACENCY = sum(pts for _, _, pts in _ADJACENCY_PAIRS)

# ── Component weights (must sum to 1.0 — see test_scorer_weights_sum_to_one) ──
_WEIGHTS: dict[str, float] = {
    "natural_light": 0.20,
    "adjacency": 0.25,
    "aspect_ratio": 0.10,
    "circulation": 0.15,
    "vastu": 0.10,
    "grid_regularity": 0.10,
    "toilet_placement": 0.10,
}

# ── Toilet placement scoring ───────────────────────────────────────────────────
_WET_TYPES = frozenset(["toilet", "wc_only", "bathroom_master"])
_ADJACENCY_PENALTY_TYPES = frozenset(["staircase", "parking_4w", "parking_2w"])


def _shares_wall(a: Room, b: Room, tol: float = 0.05) -> bool:
    """Pure-Python adjacency check — no Shapely needed for scoring."""
    x_ov = max(0.0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
    y_ov = max(0.0, min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y))
    abuts_x = abs(a.x + a.width - b.x) < 0.2 or abs(b.x + b.width - a.x) < 0.2
    abuts_y = abs(a.y + a.depth - b.y) < 0.2 or abs(b.y + b.depth - a.y) < 0.2
    return (abuts_x and y_ov > tol) or (abuts_y and x_ov > tol)


def _touches_boundary(
    room: Room, cfg: PlotConfig, ewt: float, tol: float = 0.1
) -> bool:
    """True if any edge of the room is within tol of the buildable boundary."""
    bx_min = cfg.setback_left + ewt
    bx_max = cfg.plot_x_extent - cfg.setback_right - ewt
    by_min = cfg.setback_front + ewt
    by_max = cfg.plot_y_extent - cfg.setback_rear - ewt
    return (
        abs(room.x - bx_min) < tol
        or abs(room.x + room.width - bx_max) < tol
        or abs(room.y - by_min) < tol
        or abs(room.y + room.depth - by_max) < tol
    )


def _score_natural_light(layout: Layout, cfg: PlotConfig, ewt: float) -> float:
    all_rooms = layout.ground_floor.rooms + layout.first_floor.rooms
    habitable = [r for r in all_rooms if r.type in _HABITABLE]
    if not habitable:
        return 0.0
    lit = sum(1 for r in habitable if _touches_boundary(r, cfg, ewt))
    return 100.0 * lit / len(habitable)


def _score_adjacency(layout: Layout) -> float:
    all_rooms = layout.ground_floor.rooms + layout.first_floor.rooms
    # Group by type for quick lookup
    by_type: dict[str, list[Room]] = {}
    for r in all_rooms:
        by_type.setdefault(r.type, []).append(r)

    earned = 0.0
    for t1, t2, pts in _ADJACENCY_PAIRS:
        rs1 = by_type.get(t1, [])
        rs2 = by_type.get(t2, [])
        for a in rs1:
            for b in rs2:
                if _shares_wall(a, b):
                    earned += pts
                    break  # count at most once per t1 room
            else:
                continue
            break  # at most one pair per pair-type

    if _MAX_ADJACENCY == 0:
        return 0.0
    return min(100.0, 100.0 * earned / _MAX_ADJACENCY)


def _score_aspect_ratio(layout: Layout) -> float:
    all_rooms = layout.ground_floor.rooms + layout.first_floor.rooms
    habitable = [r for r in all_rooms if r.type in _HABITABLE]
    if not habitable:
        return 100.0
    penalty = 0.0
    for r in habitable:
        ratio = max(r.width, r.depth) / max(min(r.width, r.depth), 0.01)
        if ratio > 2.0:
            penalty += (ratio - 2.0) * 10.0  # 10 pts per unit over 2:1
    return max(0.0, 100.0 - penalty / len(habitable))


def _score_circulation(layout: Layout, cfg: PlotConfig, ewt: float) -> float:
    all_rooms = layout.ground_floor.rooms + layout.first_floor.rooms
    total_room_area = sum(r.area for r in all_rooms)
    bw = cfg.plot_x_extent - cfg.setback_left - cfg.setback_right - 2 * ewt
    bd = cfg.plot_y_extent - cfg.setback_front - cfg.setback_rear - 2 * ewt
    buildable_area = max(bw * bd * 2, 0.01)  # both floors
    fill_ratio = total_room_area / buildable_area
    # Target fill 0.75–0.90; penalty outside this band
    if fill_ratio < 0.6:
        return fill_ratio / 0.6 * 100.0
    if fill_ratio <= 0.90:
        return 100.0
    return max(0.0, 100.0 - (fill_ratio - 0.90) * 200.0)


def layout_floors(layout: Layout) -> list[FloorPlan]:
    """Every populated floor of a layout, in storey order."""
    return [
        fp
        for fp in (
            layout.ground_floor,
            layout.first_floor,
            layout.second_floor,
            layout.basement_floor,
        )
        if fp is not None
    ]


def _score_vastu(layout: Layout, cfg: PlotConfig) -> float:
    """Graded 0–100 Vastu compliance — the channel Vastu ranks through.

    This component (weight 0.10) is the *only* place Vastu influences which
    layouts `rank_and_select` returns; Vastu no longer drops candidates in
    `generator.generate`. It used to score a binary `check_vastu()` by
    subtracting 20 per violation and 5 per warning, which made the signal a
    step function of finding counts — two rooms one metre outside a preferred
    zone outranked nothing at all. `vastu_layout_score` replaces that with an
    area-weighted mean of graded per-room verdicts over every floor.

    The disabled case still returns a neutral 100.0 rather than
    `vastu_layout_score`'s 0.0-for-no-ruled-rooms: with Vastu off this
    component must be inert, not a 10-point penalty on every layout.
    """
    if not cfg.vastu_enabled:
        return 100.0  # neutral when vastu not requested
    from .vastu import vastu_layout_score

    return vastu_layout_score(layout_floors(layout), cfg)


def _score_grid_regularity(layout: Layout) -> float:
    """Regular, stackable column grids design (and cost) better — this is
    what structapi's /v1/design/building consumes. Neutral when a layout
    carries no derived columns (e.g. hand-built test fixtures)."""
    from app.engine.structural_grid import extract_grid

    gf_cols = layout.ground_floor.columns
    if not gf_cols:
        return 100.0
    grid = extract_grid([{"x": c.x, "y": c.y} for c in gf_cols])
    base = 100.0 if grid.confident else max(0.0, 70.0 - 10.0 * len(grid.notes))

    ff_cols = layout.first_floor.columns
    if not ff_cols:
        return base
    stacked = sum(
        1
        for f in ff_cols
        if any(abs(f.x - g.x) <= 0.15 and abs(f.y - g.y) <= 0.15 for g in gf_cols)
    )
    return 0.7 * base + 30.0 * stacked / len(ff_cols)


def _is_ensuite(room: Room, all_rooms: list[Room]) -> bool:
    """En-suite toilets are exempt from the stair/parking-adjacency penalty:
    a solver-tagged en-suite id, or a master bathroom that shares a wall
    with a bedroom (its owning bedroom)."""
    if "_ens_" in room.id:
        return True
    if room.type == "bathroom_master":
        bedrooms = [r for r in all_rooms if r.type in ("bedroom", "master_bedroom")]
        return any(_shares_wall(room, b) for b in bedrooms)
    return False


def _score_toilet_placement(layout: Layout, cfg: PlotConfig, ewt: float) -> float:
    """Penalize toilets facing the front facade (heavier near the main-door
    zone), adjacent to the staircase/parking (unless en-suite), or without
    an external wall for ventilation."""
    all_rooms = layout.ground_floor.rooms + layout.first_floor.rooms
    wet_rooms = [r for r in all_rooms if r.type in _WET_TYPES]
    if not wet_rooms:
        return 100.0

    by_min = cfg.setback_front + ewt
    by_max = cfg.plot_y_extent - cfg.setback_rear - ewt
    bx_min = cfg.setback_left + ewt
    bx_max = cfg.plot_x_extent - cfg.setback_right - ewt
    depth = max(by_max - by_min, 0.01)
    width = max(bx_max - bx_min, 0.01)
    front_band_y = by_min + 0.25 * depth
    mid_x_lo = bx_min + width / 3.0
    mid_x_hi = bx_min + 2.0 * width / 3.0

    penalty = 0.0
    for room in wet_rooms:
        cx = room.x + room.width / 2.0
        cy = room.y + room.depth / 2.0
        ensuite = _is_ensuite(room, all_rooms)

        if cy < front_band_y:
            penalty += 25.0 if mid_x_lo <= cx <= mid_x_hi else 15.0

        if not ensuite and any(
            other.type in _ADJACENCY_PENALTY_TYPES and _shares_wall(room, other)
            for other in all_rooms
            if other is not room
        ):
            penalty += 20.0

        if not _touches_boundary(room, cfg, ewt):
            penalty += 15.0

    return max(0.0, 100.0 - penalty / len(wet_rooms))


def score_layout(layout: Layout, cfg: PlotConfig) -> LayoutScore:
    """Compute a weighted quality score for a layout."""
    from .compliance import load_rules

    rules = load_rules()
    ewt = rules["external_wall_thickness_mm"] / 1000

    nl = _score_natural_light(layout, cfg, ewt)
    adj = _score_adjacency(layout)
    ar = _score_aspect_ratio(layout)
    cir = _score_circulation(layout, cfg, ewt)
    vas = _score_vastu(layout, cfg)
    grid = _score_grid_regularity(layout)
    tp = _score_toilet_placement(layout, cfg, ewt)

    total = (
        _WEIGHTS["natural_light"] * nl
        + _WEIGHTS["adjacency"] * adj
        + _WEIGHTS["aspect_ratio"] * ar
        + _WEIGHTS["circulation"] * cir
        + _WEIGHTS["vastu"] * vas
        + _WEIGHTS["grid_regularity"] * grid
        + _WEIGHTS["toilet_placement"] * tp
    )

    return LayoutScore(
        total=round(total, 1),
        natural_light=round(nl, 1),
        adjacency=round(adj, 1),
        aspect_ratio=round(ar, 1),
        circulation=round(cir, 1),
        vastu=round(vas, 1),
        grid_regularity=round(grid, 1),
        toilet_placement=round(tp, 1),
    )


def rank_and_select(
    layouts: list[Layout], cfg: PlotConfig, top_n: int = 3
) -> list[Layout]:
    """Score all layouts, attach scores, return top_n sorted by score descending."""
    scored: list[tuple[float, Layout]] = []
    for layout in layouts:
        s = score_layout(layout, cfg)
        layout.score = s
        scored.append((s.total, layout))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [layout for _, layout in scored[:top_n]]
