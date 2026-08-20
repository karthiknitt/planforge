"""Task 18A invariant: the compound-wall gate edge must equal the main-entrance
edge for every road side.

`plan_geometry._place_main_entrance` puts the main door on the y-min (road/front)
exterior wall for ALL four road sides — in drawing coordinates y=0 is always the
road, and `road_side` names which direction that edge faces. `geometry`.
`_compound_wall_sides` used to read `road_side` as a plot-local edge id
(y-min="S", x-max="E", y-max="N", x-min="W"), which gated the x-max run on an
east road, the y-max run on a north road and the x-min run on a west road — all
on a DIFFERENT edge from the door, silently voiding `gate_cx`'s door-alignment
purpose. This module pins the fixed invariant: the gate gap is ALWAYS on the
y-min (plot-local "S") edge, and the main door is ALWAYS on the same y-min wall.

The expected edge per road side is a LITERAL table — `{"S": "S", "N": "S",
"E": "S", "W": "S"}` (the plot-local id of the y-min edge) — deliberately NOT
computed from either function under test, so the test cannot inherit whichever
reading is wrong.
"""

from __future__ import annotations

import pytest

from app.engine.geometry import (
    compound_wall_segments,
)
from app.engine.models import (
    ComplianceResult,
    FloorPlan,
    Layout,
    PlotConfig,
    Room,
)
from app.engine.plan_geometry import EWT, build_floor_drawing


def _cfg(road_side: str) -> PlotConfig:
    return PlotConfig(
        plot_length=15.0,
        plot_width=9.0,
        setback_front=3.0,
        setback_rear=1.5,
        setback_left=1.2,
        setback_right=1.2,
        num_bedrooms=3,
        toilets=2,
        parking=True,
        road_side=road_side,
    )


def _gate_edge_local_id(segs, pw: float, pl: float) -> str:
    """Plot-local id of the edge that carries the gate gap (the run split into
    two pieces), classified by the FIXED plot-coordinate convention y-min="S",
    x-max="E", y-max="N", x-min="W" — not by anything the functions under test
    compute.
    """
    eps = 1e-6
    edges: dict[str, list] = {"S": [], "E": [], "N": [], "W": []}
    for x1, y1, x2, y2 in segs:
        if abs(y1) < eps and abs(y2) < eps:
            edges["S"].append((x1, y1, x2, y2))
        elif abs(x1 - pw) < eps and abs(x2 - pw) < eps:
            edges["E"].append((x1, y1, x2, y2))
        elif abs(y1 - pl) < eps and abs(y2 - pl) < eps:
            edges["N"].append((x1, y1, x2, y2))
        elif abs(x1) < eps and abs(x2) < eps:
            edges["W"].append((x1, y1, x2, y2))
        else:
            raise AssertionError(f"segment on no plot edge: {(x1, y1, x2, y2)}")
    gated = [eid for eid, runs in edges.items() if len(runs) == 2]
    assert len(gated) == 1, (
        f"expected exactly one gate-split edge, got {gated}: "
        f"{ {k: len(v) for k, v in edges.items()} }"
    )
    return gated[0]


# LITERAL expectation per road side: the gate is always on the y-min edge, whose
# plot-local id is "S" under the fixed plot-coordinate convention. Deliberately
# a constant table — deriving it from either function under test would let the
# test inherit whichever reading is wrong.
EXPECTED_GATE_EDGE_BY_ROAD_SIDE = {"S": "S", "N": "S", "E": "S", "W": "S"}


@pytest.mark.parametrize("road_side", ["S", "N", "E", "W"])
def test_gate_gap_is_always_on_the_y_min_edge(road_side):
    cfg = _cfg(road_side)
    segs = compound_wall_segments(cfg)
    expected = EXPECTED_GATE_EDGE_BY_ROAD_SIDE[road_side]
    assert _gate_edge_local_id(segs, cfg.plot_width, cfg.plot_length) == expected, (
        f"road_side='{road_side}': the gate gap must be on the y-min edge "
        f"(plot-local '{expected}'), the same edge the main entrance is on"
    )


def _layout_with_main_door_at(cx: float) -> Layout:
    """A ground floor whose derived main entrance sits near plot-x ``cx`` on the
    y-min (road/front) edge. Rooms stay inside the buildable envelope for
    ``_cfg()`` — x [1.2, 7.8], y [3.0, 13.5] — so the geometry pass runs on a
    realistic plan.
    """
    return Layout(
        id="gate-edge-test",
        name="Gate Edge Test",
        ground_floor=FloorPlan(
            floor=0,
            floor_type="ground",
            rooms=[
                Room(
                    id="living-1",
                    name="Living",
                    type="living",
                    x=cx - 1.2,
                    y=3.0,
                    width=2.4,
                    depth=3.5,
                ),
            ],
        ),
        first_floor=FloorPlan(floor=1, floor_type="first", rooms=[]),
        compliance=ComplianceResult(passed=True),
    )


@pytest.mark.parametrize("road_side", ["S", "N", "E", "W"])
def test_main_door_sits_on_the_y_min_wall_for_every_road_side(road_side):
    """Cross-module: build_floor_drawing places the main door on the y-min
    (front) exterior wall at the same front-wall line for all four road sides —
    never on the x-max/x-min/y-max walls the old plot-local reading gated."""
    cfg = _cfg(road_side)
    drawing = build_floor_drawing(_layout_with_main_door_at(6.5).ground_floor, cfg)
    main = next((o for o in drawing.openings if o.is_main), None)
    assert main is not None, "fixture must derive a main entrance"
    # The living room sits at y=3.0, so its y-min exterior wall centreline is
    # 3.0 - EWT/2 for EVERY road side (y=0 is always the road).
    front_wall_y = 3.0 - EWT / 2
    assert abs(main.cy - front_wall_y) < 1e-6, (
        f"road_side='{road_side}': main door cy={main.cy:.3f} must be on the "
        f"y-min front wall at {front_wall_y:.3f}, not the x-max/x-min/y-max "
        f"edge the old plot-local reading would gate"
    )
