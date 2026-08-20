"""Bug #1 (2026-07-12): first-floor space utilization.

The pro-tester's plot produced a 5.25 m² Study surrounded by unused gaps
while a Passage ballooned to 38.61 m². These tests pin the invariants:

1. No "usable" leftover gap (≥ 1.5 m² with both bbox sides ≥ 1.2 m) remains
   on any occupied floor after generation — residual space must be absorbed
   into adjacent rooms or become a real room (Utility/Store/Open Terrace).
2. A generated Study meets its spec minimum area (room_specs.json: 6.0 m²).
3. Passages never balloon: spec caps them at 6 m²; post-processing may
   stretch that slightly, but an order-of-magnitude blowup is a bug.
"""

import pytest
from shapely.geometry import box
from shapely.ops import unary_union

from app.engine.generator import generate
from app.engine.models import PlotConfig

EWT = 0.23  # external_wall_thickness_mm / 1000 (compliance_rules.json)

MIN_USABLE_AREA = 1.5
MIN_USABLE_SIDE = 1.2
PASSAGE_CAP_SQM = 12.0  # 2x spec max — generous, catches only blowups


def _cfg(**kw) -> PlotConfig:
    # Mirrors the reported plot: 60' x 40' (18.3 m x 12.2 m), road south
    defaults = dict(
        plot_y_extent=12.2,
        plot_x_extent=18.3,
        setback_front=1.5,
        setback_rear=1.5,
        setback_left=0.9,
        setback_right=0.9,
        num_bedrooms=4,
        toilets=2,
        parking=False,
        city="other",
        road_side="S",
        vastu_enabled=False,
        has_study=True,
    )
    defaults.update(kw)
    return PlotConfig(**defaults)


CONFIGS = [
    _cfg(),
    _cfg(plot_x_extent=9.0, plot_y_extent=12.0, num_bedrooms=2),
]


def _plate(cfg: PlotConfig):
    ox = cfg.setback_left + EWT
    oy = cfg.setback_front + EWT
    w = cfg.plot_x_extent - cfg.setback_left - cfg.setback_right - 2 * EWT
    d = cfg.plot_y_extent - cfg.setback_front - cfg.setback_rear - 2 * EWT
    return box(ox, oy, ox + w, oy + d)


def _usable_gaps(fp, plate):
    occupied = unary_union(
        [box(r.x, r.y, r.x + r.width, r.y + r.depth) for r in fp.rooms]
    )
    leftover = plate.difference(occupied)
    if leftover.is_empty:
        return []
    if leftover.geom_type in ("MultiPolygon", "GeometryCollection"):
        regions = [g for g in leftover.geoms if g.geom_type == "Polygon"]
    else:
        regions = [leftover]
    gaps = []
    for g in regions:
        if g.area < MIN_USABLE_AREA:
            continue
        # "Usable" = a ~1.3 m square fits inside the region with room to
        # spare (bbox checks misclassify concave chains of narrow slivers,
        # and exact-width erosions leave degenerate zero-area specks).
        eroded = g.buffer(-(MIN_USABLE_SIDE / 2 + 0.05))
        if not eroded.is_empty and eroded.area > 1e-4:
            gaps.append(g)
    return gaps


def _floors(layout):
    for fp in (layout.ground_floor, layout.first_floor, layout.second_floor):
        if fp is not None and fp.rooms:
            yield fp


@pytest.mark.parametrize("cfg", CONFIGS, ids=["bug-plot-60x40", "small-9x12"])
def test_no_usable_leftover_gaps(cfg):
    layouts = generate(cfg)
    assert layouts, "expected at least one passing layout"
    for layout in layouts:
        plate = _plate(cfg)
        for fp in _floors(layout):
            gaps = _usable_gaps(fp, plate)
            details = [
                f"{g.area:.2f} m2 @ {tuple(round(v, 2) for v in g.bounds)}"
                for g in gaps
            ]
            assert not gaps, (
                f"layout {layout.id} floor {fp.floor} has usable unfilled gaps: "
                f"{details}; rooms={[(r.name, round(r.area, 2)) for r in fp.rooms]}"
            )


def test_fill_covers_usable_gap_with_sub_1p2m_legs():
    """Regression (CI failure on PR #29 merge, 2026-07-17): an L-shaped
    leftover whose legs are both just under 1.2 m (1.197 / 1.199 m) passes
    the erosion usability check (a 1.3 m pocket fits at the inner corner)
    but every inscribed rectangle was rejected by _largest_inscribed_rect's
    min_side, and all neighbours were _NO_ABSORB_TYPES — leaving a 5.87 m²
    dead pocket the fill safety net never reclaimed."""
    from app.engine.generator import _fill_blank_areas
    from app.engine.models import FloorPlan, Room

    cfg = CONFIGS[1]  # small-9x12
    plate = _plate(cfg)

    def room(id_, name, rtype, x0, y0, x1, y1):
        return Room(
            id=id_,
            name=name,
            type=rtype,
            x=round(x0, 3),
            y=round(y0, 3),
            width=round(x1 - x0, 3),
            depth=round(y1 - y0, 3),
        )

    # Plate minus these three rooms is exactly the CI gap polygon:
    # (1.13 1.73, 1.13 5.33, 2.327 5.33, 2.327 2.929, 3.631 2.929, 3.631 1.73)
    fp = FloorPlan(
        floor=1,
        rooms=[
            room("ut", "Utility", "utility", 3.631, 1.73, 7.87, 10.27),
            room("st", "Staircase", "staircase", 2.327, 2.929, 3.631, 10.27),
            room("to", "Toilet 2", "toilet", 1.13, 5.33, 2.327, 10.27),
        ],
    )
    gaps_before = _usable_gaps(fp, plate)
    assert gaps_before, "fixture must start with a usable gap"

    _fill_blank_areas(fp, cfg, EWT, is_topmost=True)

    gaps = _usable_gaps(fp, plate)
    details = [
        f"{g.area:.2f} m2 @ {tuple(round(v, 2) for v in g.bounds)}" for g in gaps
    ]
    assert not gaps, f"usable gap survived the fill safety net: {details}"


def test_study_meets_spec_min_area():
    layouts = generate(_cfg())
    studies = [
        r
        for layout in layouts
        for fp in _floors(layout)
        for r in fp.rooms
        if r.type == "study"
    ]
    for r in studies:
        assert r.area >= 6.0 - 1e-6, f"Study only {r.area:.2f} m2 (spec min 6.0)"


@pytest.mark.parametrize("cfg", CONFIGS, ids=["bug-plot-60x40", "small-9x12"])
def test_rooms_never_overlap(cfg):
    """Space filling must never stamp one room over another."""
    for layout in generate(cfg):
        for fp in _floors(layout):
            for i, a in enumerate(fp.rooms):
                box_a = box(a.x, a.y, a.x + a.width, a.y + a.depth)
                for b in fp.rooms[i + 1 :]:
                    box_b = box(b.x, b.y, b.x + b.width, b.y + b.depth)
                    ov = box_a.intersection(box_b).area
                    # The room-edit validator rejects ANY positive-area overlap
                    assert ov <= 1e-6, (
                        f"layout {layout.id} floor {fp.floor}: {a.name} overlaps "
                        f"{b.name} by {ov:.3f} m2"
                    )


@pytest.mark.parametrize("cfg", CONFIGS, ids=["bug-plot-60x40", "small-9x12"])
def test_passages_do_not_balloon(cfg):
    for layout in generate(cfg):
        for fp in _floors(layout):
            for r in fp.rooms:
                if r.type == "passage":
                    assert r.area <= PASSAGE_CAP_SQM, (
                        f"layout {layout.id} floor {fp.floor}: Passage "
                        f"{r.area:.2f} m2 exceeds {PASSAGE_CAP_SQM} m2"
                    )
