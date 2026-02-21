"""Layout quality scorer for PlanForge.

Scores each Layout on 5 components (weighted sum → 0–100):
  25% Natural light   — % habitable rooms touching plot boundary
  25% Adjacency       — kitchen↔dining, bedroom↔toilet, living↔staircase
  20% Aspect ratio    — penalty when width/depth > 2:1 for habitable rooms
  15% Circulation     — room area / buildable area (fill efficiency)
  15% Vastu           — reuses check_vastu(); −20/violation, −5/warning
"""

from __future__ import annotations

from .models import Layout, LayoutScore, PlotConfig, Room


# ── Habitable room types (rooms that benefit from natural light) ──────────────
_HABITABLE = frozenset(["living", "bedroom", "master_bedroom", "kitchen",
                         "dining", "study", "home_office", "gym", "servant_quarter"])

# ── Adjacency preference table ────────────────────────────────────────────────
_ADJACENCY_PAIRS: list[tuple[str, str, float]] = [
    ("kitchen", "dining", 15.0),
    ("bedroom", "toilet", 12.0),
    ("master_bedroom", "toilet", 12.0),
    ("living", "staircase", 8.0),
    ("living", "dining", 10.0),
]
_MAX_ADJACENCY = sum(pts for _, _, pts in _ADJACENCY_PAIRS)


def _shares_wall(a: Room, b: Room, tol: float = 0.05) -> bool:
    """Pure-Python adjacency check — no Shapely needed for scoring."""
    x_ov = max(0.0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
    y_ov = max(0.0, min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y))
    abuts_x = (abs(a.x + a.width - b.x) < 0.2 or abs(b.x + b.width - a.x) < 0.2)
    abuts_y = (abs(a.y + a.depth - b.y) < 0.2 or abs(b.y + b.depth - a.y) < 0.2)
    return (abuts_x and y_ov > tol) or (abuts_y and x_ov > tol)


def _touches_boundary(room: Room, cfg: PlotConfig, ewt: float, tol: float = 0.1) -> bool:
    """True if any edge of the room is within tol of the buildable boundary."""
    bx_min = cfg.setback_left + ewt
    bx_max = cfg.plot_width - cfg.setback_right - ewt
    by_min = cfg.setback_front + ewt
    by_max = cfg.plot_length - cfg.setback_rear - ewt
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
            penalty += (ratio - 2.0) * 10.0   # 10 pts per unit over 2:1
    return max(0.0, 100.0 - penalty / len(habitable))


def _score_circulation(layout: Layout, cfg: PlotConfig, ewt: float) -> float:
    all_rooms = layout.ground_floor.rooms + layout.first_floor.rooms
    total_room_area = sum(r.area for r in all_rooms)
    bw = cfg.plot_width - cfg.setback_left - cfg.setback_right - 2 * ewt
    bd = cfg.plot_length - cfg.setback_front - cfg.setback_rear - 2 * ewt
    buildable_area = max(bw * bd * 2, 0.01)  # both floors
    fill_ratio = total_room_area / buildable_area
    # Target fill 0.75–0.90; penalty outside this band
    if fill_ratio < 0.6:
        return fill_ratio / 0.6 * 100.0
    if fill_ratio <= 0.90:
        return 100.0
    return max(0.0, 100.0 - (fill_ratio - 0.90) * 200.0)


def _score_vastu(layout: Layout, cfg: PlotConfig) -> float:
    if not cfg.vastu_enabled:
        return 100.0  # neutral when vastu not requested
    from .vastu import check_vastu
    violations, warnings = check_vastu(layout, cfg, road_side=cfg.road_side)
    score = 100.0 - len(violations) * 20.0 - len(warnings) * 5.0
    return max(0.0, score)


def score_layout(layout: Layout, cfg: PlotConfig) -> LayoutScore:
    """Compute a weighted quality score for a layout."""
    from .compliance import load_rules
    rules = load_rules()
    ewt = rules["external_wall_thickness_mm"] / 1000

    nl  = _score_natural_light(layout, cfg, ewt)
    adj = _score_adjacency(layout)
    ar  = _score_aspect_ratio(layout)
    cir = _score_circulation(layout, cfg, ewt)
    vas = _score_vastu(layout, cfg)

    total = 0.25 * nl + 0.25 * adj + 0.20 * ar + 0.15 * cir + 0.15 * vas

    return LayoutScore(
        total=round(total, 1),
        natural_light=round(nl, 1),
        adjacency=round(adj, 1),
        aspect_ratio=round(ar, 1),
        circulation=round(cir, 1),
        vastu=round(vas, 1),
    )


def rank_and_select(layouts: list[Layout], cfg: PlotConfig, top_n: int = 3) -> list[Layout]:
    """Score all layouts, attach scores, return top_n sorted by score descending."""
    scored: list[tuple[float, Layout]] = []
    for layout in layouts:
        s = score_layout(layout, cfg)
        layout.score = s
        scored.append((s.total, layout))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [layout for _, layout in scored[:top_n]]
