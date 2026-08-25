"""Corpus-similarity diagnostic score — how close a generated `Layout` sits
to the mined `corpus_priors.json` statistics, alongside (never inside) GCS.

DIAGNOSTIC ONLY. Never a gate, never wired into generation or CI — Task 13
reads this to judge whether the corpus-prior CP-SAT terms (Tasks 8-11) move
generated layouts closer to real corpus patterns. Mirrors `ccqs.compute_gcs`'s
shape: a dataclass result with named 0-100 component scores, an `as_dict()`,
and a weighted-average `overall`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.engine.corpus_priors import (
    get_adjacency_prior,
    get_position_prior,
    get_shape_usage_prior,
    get_size_prior,
)
from app.engine.solver import (
    _IWT_MM,
    _MIN_SHARE_OVERLAP_MM,
    _SQFT_TO_MM2,
    _TEMPLATE_TYPES,
)
from app.engine.vastu import ZONE_GRID_ROAD_S, zone_for_point

if TYPE_CHECKING:
    from app.engine.models import FloorPlan, Layout, PlotConfig, Room

# Every distinct zone label the 3x3 Vastu grid can emit, across all four
# road-side rotations (the grid is a relabelled permutation of the same 9
# cells, so ROAD_S's flattened labels already cover the full set).
_ZONES: frozenset[str] = frozenset(z for row in ZONE_GRID_ROAD_S for z in row)

# "How many points off 100 does one full standard deviation of area
# deviation cost." Chosen so a room 5 std-devs from the corpus mean (a
# genuinely wrong size, not sampling noise) floors at 0, while a 1-sigma
# miss -- unremarkable given real corpus spread -- still scores 80.
_SIZE_PENALTY_PER_STD = 20.0

# A corpus room-pair or room/zone frequency below this is not "the corpus
# expects this," it is background noise -- so pairs/zones under the
# threshold are excluded from the expected set rather than penalising a
# layout for not reproducing a rare pattern. 0.3 mirrors the rough order of
# magnitude Task 11's review used to call a rate "high" (its own comparison
# points sat at 0.2-0.6).
_HIGH_FREQ_THRESHOLD = 0.3

# Weighted-average weights for `overall`. size/adjacency/position are the
# three components with real discriminating power; shape is explicitly
# downweighted (see `_shape_score`'s docstring) so its near-degenerate
# near-100 score on almost every layout cannot dominate or silently
# neutralise the other three.
_WEIGHTS: dict[str, float] = {
    "size_score": 0.35,
    "adjacency_score": 0.35,
    "position_score": 0.20,
    "shape_score": 0.10,
}


@dataclass
class CorpusSimilarityScore:
    overall: float
    size_score: float | None
    adjacency_score: float | None
    position_score: float | None
    shape_score: float | None
    debug: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "overall": self.overall,
            "size_score": self.size_score,
            "adjacency_score": self.adjacency_score,
            "position_score": self.position_score,
            "shape_score": self.shape_score,
        }


def _all_rooms(layout: Layout) -> list[tuple[int, Room]]:
    floors: list[FloorPlan | None] = [
        layout.ground_floor,
        layout.first_floor,
        layout.second_floor,
        layout.basement_floor,
    ]
    return [(fp.floor, room) for fp in floors if fp is not None for room in fp.rooms]


def _rooms_share_wall(a: Room, b: Room) -> bool:
    """Same geometric contact test `solver._add_adjacency_prior_terms` uses
    for its CP-SAT reward term (facing edges within one wall thickness AND
    real overlap on the perpendicular axis) -- reused rather than
    reinvented so this score never disagrees with what the solver itself
    optimises for. `_IWT_MM`/`_MIN_SHARE_OVERLAP_MM` are in millimetres;
    `Room` coordinates are in metres, so both are converted once here.
    """
    iwt_m = _IWT_MM / 1000.0
    min_overlap_m = _MIN_SHARE_OVERLAP_MM / 1000.0
    a_xe, a_ye = a.x + a.width, a.y + a.depth
    b_xe, b_ye = b.x + b.width, b.y + b.depth
    cases = (
        (b.x - a_xe, a.y, a_ye, b.y, b_ye),  # a left of b
        (a.x - b_xe, a.y, a_ye, b.y, b_ye),  # a right of b
        (b.y - a_ye, a.x, a_xe, b.x, b_xe),  # a in front of b
        (a.y - b_ye, a.x, a_xe, b.x, b_xe),  # a behind b
    )
    for gap, a_lo, a_hi, b_lo, b_hi in cases:
        if (
            0 <= gap <= iwt_m
            and (a_hi - b_lo) >= min_overlap_m
            and (b_hi - a_lo) >= min_overlap_m
        ):
            return True
    return False


def _size_score(cfg: PlotConfig, rooms: list[tuple[int, Room]]) -> float | None:
    """Average, over rooms with a corpus size prior, of 100 minus a penalty
    scaled by how many std-devs the room's area sits from the prior mean
    (floored at 0). Rooms whose type has no corpus size data (`get_size_prior`
    returns None, or a degenerate zero-std entry) are EXCLUDED from the
    average, not scored as 0 or 100 -- either default would bias the metric
    toward penalising or rewarding programme choices this component has no
    opinion on. `size_score` computes meaningfully even with no
    `style_preset` set, since `get_size_prior` has a corpus-wide fallback.
    """
    scores: list[float] = []
    for _floor, room in rooms:
        prior = get_size_prior(cfg, room.type)
        if prior is None or prior.area_std <= 0:
            continue
        area_sqft = (room.width * 1000.0) * (room.depth * 1000.0) / _SQFT_TO_MM2
        z = abs(area_sqft - prior.area_mean) / prior.area_std
        scores.append(max(0.0, 100.0 - _SIZE_PENALTY_PER_STD * z))
    return (sum(scores) / len(scores)) if scores else None


def _adjacency_score(cfg: PlotConfig, rooms: list[tuple[int, Room]]) -> float | None:
    """Fraction of the layout's high-frequency-corpus-pair expectations that
    are actually satisfied. For every same-floor room pair whose corpus
    adjacency frequency is >= `_HIGH_FREQ_THRESHOLD`, check whether the pair
    actually shares a wall (`_rooms_share_wall`); score is matched/expected,
    scaled to 0-100. A layout with no expected pairs at all (no corpus
    adjacency data clears the threshold) scores None, not 0 -- there was
    nothing to satisfy. Computes meaningfully with no `style_preset`, since
    `get_adjacency_prior` has a corpus-wide fallback.
    """
    expected = 0
    matched = 0
    for i, (floor_a, a) in enumerate(rooms):
        for floor_b, b in rooms[i + 1 :]:
            if floor_a != floor_b:
                continue
            freq = get_adjacency_prior(cfg, a.type, b.type)
            if freq < _HIGH_FREQ_THRESHOLD:
                continue
            expected += 1
            if _rooms_share_wall(a, b):
                matched += 1
    return (100.0 * matched / expected) if expected else None


def _position_score(cfg: PlotConfig, rooms: list[tuple[int, Room]]) -> float | None:
    """Average, over rooms whose type has a high-frequency corpus zone,
    of 100 if the room's centroid zone matches one of those zones else 0.

    `get_position_prior` returns 0.0 for every zone when `cfg.style_preset`
    is None (no corpus-wide position fallback exists -- verified in Tasks
    8-11), so no zone ever clears `_HIGH_FREQ_THRESHOLD` and every room is
    excluded: `position_score` is None whenever no style is set, rather than
    reporting a misleading 0 or 100.

    Zone convention matches `mine_corpus_priors.mine_position_priors`: the
    corpus histograms were built with `zone_for_point`'s own normalisation
    (dividing by plot extent) and a fixed `north_angle_deg=0.0` (that
    function's documented "up == north" fallback for extracts with no
    reliable per-design angle) -- so this reproduces the same normalisation
    against the layout's real plot extents and the same fixed angle, rather
    than the layout's own `cfg.north_angle_deg`, to stay comparable to what
    the priors were actually mined against.
    """
    scores: list[float] = []
    for _floor, room in rooms:
        cx = room.x + room.width / 2.0
        cy = room.y + room.depth / 2.0
        high_zones = {
            z
            for z in _ZONES
            if get_position_prior(cfg, room.type, z) >= _HIGH_FREQ_THRESHOLD
        }
        if not high_zones:
            continue
        actual_zone = zone_for_point(
            cx, cy, cfg.plot_x_extent, cfg.plot_y_extent, north_angle_deg=0.0
        )
        scores.append(100.0 if actual_zone in high_zones else 0.0)
    return (sum(scores) / len(scores)) if scores else None


def _shape_score(cfg: PlotConfig, rooms: list[tuple[int, Room]]) -> float | None:
    """Per-room point estimate of `1 - |corpus p_nonrect - actual is_nonrect|`,
    scaled to 0-100, averaged over rooms whose type is templatable
    (`solver._TEMPLATE_TYPES`: living/dining/passage).

    NEAR-DEGENERATE BY DESIGN, NOT A BUG. Task 11's review found real corpus
    `p_nonrect` for these three types sits at or near 0.0 in 9-15 of 16
    styles -- so almost every real AND generated layout keeps these rooms
    RECT, and this component will score close to 100 for nearly any layout
    regardless of quality. It is also a PER-LAYOUT point estimate against a
    PER-PLOT rate: a single plan holds at most one `living` room, so one
    room's binary RECT-or-not can never validate rate compliance (e.g.
    "20% of plots get a templated living room") on its own -- only a
    multi-plan sweep could. Task 13 should read the discriminating signal
    from `size_score`/`adjacency_score`/`position_score`, NOT from a high
    `shape_score`, which is why `_WEIGHTS` gives this component the lowest
    weight in `overall`.

    Excluded entirely (returns None) when `cfg.style_preset` is None:
    `get_shape_usage_prior` always returns 0.0 with no style (no corpus-wide
    fallback), which would make every RECT room auto-score 100 -- a
    misleadingly high score built from zero real signal, not evidence of
    similarity.
    """
    if cfg.style_preset is None:
        return None
    scores: list[float] = []
    for _floor, room in rooms:
        if room.type not in _TEMPLATE_TYPES:
            continue
        p_nonrect = get_shape_usage_prior(cfg, room.type)
        actual = 0.0 if room.template == "RECT" else 1.0
        scores.append(100.0 * (1.0 - abs(p_nonrect - actual)))
    return (sum(scores) / len(scores)) if scores else None


def compute_corpus_similarity(layout: Layout, cfg: PlotConfig) -> CorpusSimilarityScore:
    """Diagnostic-only similarity between `layout` and the mined corpus
    priors for `cfg.style_preset` (or the corpus-wide stats when unset).
    Never a gate -- see module docstring.
    """
    rooms = _all_rooms(layout)

    size = _size_score(cfg, rooms)
    adjacency = _adjacency_score(cfg, rooms)
    position = _position_score(cfg, rooms)
    shape = _shape_score(cfg, rooms)

    components = {
        "size_score": size,
        "adjacency_score": adjacency,
        "position_score": position,
        "shape_score": shape,
    }
    present = {k: v for k, v in components.items() if v is not None}
    if present:
        weight_sum = sum(_WEIGHTS[k] for k in present)
        overall = round(
            sum(_WEIGHTS[k] * v for k, v in present.items()) / weight_sum, 1
        )
    else:
        # No room had any corpus signal at all (e.g. an empty layout, or a
        # programme entirely of types the corpus never recorded) -- there is
        # nothing to compare, which is neither "similar" nor "dissimilar".
        overall = 0.0

    return CorpusSimilarityScore(
        overall=overall,
        size_score=size,
        adjacency_score=adjacency,
        position_score=position,
        shape_score=shape,
        debug={"n_rooms": len(rooms), "n_scored_components": len(present)},
    )
