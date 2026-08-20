"""Bug 3 (prod, 2026-07-17): twin columns 0.115 m apart at wall junctions.

Archetype layouts built columns via _columns_from_rooms — a cross-product of
every room edge line — so each internal partition contributed BOTH wall
faces (0.115 m apart) and non-junction grid crossings got columns too. The
solver path was fixed in PR #26 but the archetype fallback was missed, and
both paths computed columns before the fill passes mutated rooms.

Invariant pinned here: stored FloorPlan.columns must equal the junction-
derived set from the FINAL (post-fill) rooms, and no two same-floor columns
may sit closer than 0.2 m (one wall thickness apart = always a bug).
"""

import itertools

from app.engine.generator import generate
from app.engine.geometry import buildable_polygon
from app.engine.models import PlotConfig
from app.engine.plan_geometry import derive_columns, derive_walls

CFG = PlotConfig(
    plot_x_extent=10.0,
    plot_y_extent=15.2,
    num_bedrooms=3,
    setback_front=1.5,
    setback_rear=1.5,
    setback_left=0.9,
    setback_right=0.9,
    toilets=2,
    parking=True,
    city="other",
    road_side="S",
    vastu_enabled=False,
)

_MIN_COLUMN_SPACING_M = 0.2  # a pair one wall-thickness apart is never intended


def _floors(layout):
    for fp in (layout.ground_floor, layout.first_floor, layout.second_floor):
        if fp is not None and fp.rooms:
            yield fp


def test_no_twin_columns_and_columns_match_final_rooms():
    layouts = generate(CFG)
    assert layouts
    buildable = buildable_polygon(CFG)
    for layout in layouts:
        for fp in _floors(layout):
            cols = [(c.x, c.y) for c in fp.columns]
            assert cols, f"layout {layout.id} floor {fp.floor} has no columns"

            twins = [
                (a, b)
                for a, b in itertools.combinations(cols, 2)
                if ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
                < _MIN_COLUMN_SPACING_M
            ]
            assert not twins, (
                f"layout {layout.id} floor {fp.floor} has twin columns: "
                f"{twins[:5]} ({len(twins)} pairs)"
            )

            walls = derive_walls(fp.rooms, buildable)
            # `rooms=` must be passed here exactly as generate() passes it: it
            # enables the wider staircase-core dedup radius (_near_staircase).
            # Without it this re-derivation is not the one production runs, and
            # the comparison silently drifts the moment a near-duplicate lands
            # next to a stair core — which is a merge generate() is right to do.
            expected = {
                (round(c.cx, 3), round(c.cy, 3))
                for c in derive_columns(walls, rooms=fp.rooms)
            }
            stored = {(round(x, 3), round(y, 3)) for x, y in cols}
            assert stored == expected, (
                f"layout {layout.id} floor {fp.floor}: stored columns diverge "
                f"from junction-derived columns of the final rooms "
                f"(stored-only={sorted(stored - expected)[:6]}, "
                f"missing={sorted(expected - stored)[:6]})"
            )
