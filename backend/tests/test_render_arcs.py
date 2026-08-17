"""Unit tests for Task 13: render-only edge arcs.

NOTE ON IMPORT PATH: the task brief's sample test imports
`from app.engine.pdf import arc_points`. Following the precedent set (and
reviewer-endorsed) in Tasks 11/12 — see test_render_site.py's own import-path
note — `arc_points` is pure geometry with no ReportLab/ezdxf dependency, so it
lives in `app.engine.geometry` alongside `compound_wall_segments` and friends;
`pdf.py` imports it as a consumer, it does not define it.

NOTE ON SCOPE: this task's brief also names `app/api/routes/export.py` and
`app/engine/cad_advanced.py` (the DXF path) in its Files list. `arc_points`'s
own docstring says its parabola is a deliberate approximation, NOT a true
circular arc — so a DXF `ARC` entity (which is inherently circular) cannot
reuse this curve unchanged; it would be a second, diverging arc definition
for the same feature. That mismatch is judged out of scope for this task and
is left unbuilt; only the PDF polyline path is implemented.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from reportlab.pdfgen import canvas

from app.engine.geometry import arc_points
from app.engine.models import FloorPlan, PlotConfig, Room
from app.engine.pdf import _draw_edge_arcs
from app.engine.plan_geometry import build_floor_drawing


def _cfg() -> PlotConfig:
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
        road_side="S",
    )


# ─────────────────────────────────────────────────────────────────────────────
# arc_points — pure geometry
# ─────────────────────────────────────────────────────────────────────────────


def test_zero_bulge_is_a_straight_chord():
    pts = arc_points((0.0, 0.0), (4.0, 0.0), bulge=0.0, segments=8)
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (4.0, 0.0)
    assert all(abs(y) < 1e-9 for _x, y in pts)


def test_positive_bulge_bows_outward():
    pts = arc_points((0.0, 0.0), (4.0, 0.0), bulge=0.25, segments=8)
    mid_y = max(y for _x, y in pts)
    assert mid_y == pytest.approx(1.0, abs=0.05), "sagitta = bulge * chord length"


def test_negative_bulge_bows_the_other_way():
    pos = arc_points((0.0, 0.0), (4.0, 0.0), bulge=0.25, segments=8)
    neg = arc_points((0.0, 0.0), (4.0, 0.0), bulge=-0.25, segments=8)
    pos_mid_y = pos[len(pos) // 2][1]
    neg_mid_y = neg[len(neg) // 2][1]
    assert pos_mid_y > 0
    assert neg_mid_y < 0
    assert pos_mid_y == pytest.approx(-neg_mid_y, abs=1e-9)


def test_arc_endpoints_always_match_the_chord():
    pts = arc_points((1.0, 2.0), (1.0, 6.0), bulge=0.3, segments=12)
    assert pts[0] == (1.0, 2.0)
    assert pts[-1] == (1.0, 6.0)


def test_interior_points_are_not_collinear_with_the_chord():
    """A degenerate-envelope guard (defect class 5): checking only the
    endpoints or a bounding box would pass even if `arc_points` silently
    ignored `bulge` and returned a straight line. The interesting property is
    strictly in the middle of the curve, so assert on it directly."""
    pts = arc_points((0.0, 0.0), (4.0, 0.0), bulge=0.25, segments=8)
    interior = pts[1:-1]
    assert len(interior) == 7
    assert all(y > 1e-6 for _x, y in interior), (
        "every interior point must have left the chord line (y=0)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Room.edge_arcs validation
# ─────────────────────────────────────────────────────────────────────────────


def test_unknown_side_letter_is_rejected():
    with pytest.raises(ValueError, match="edge_arcs"):
        Room(
            id="a",
            name="A",
            type="verandah",
            x=0,
            y=0,
            width=4,
            depth=3,
            edge_arcs={"NE": 0.2},
        )


def test_absurd_bulge_is_rejected():
    with pytest.raises(ValueError, match="edge_arcs"):
        Room(
            id="a",
            name="A",
            type="verandah",
            x=0,
            y=0,
            width=4,
            depth=3,
            edge_arcs={"S": 5.0},
        )


def test_boundary_bulge_of_exactly_one_is_accepted():
    # ±1.0 is the documented boundary, not "absurd" — must not raise.
    Room(
        id="a",
        name="A",
        type="verandah",
        x=0,
        y=0,
        width=4,
        depth=3,
        edge_arcs={"S": 1.0},
    )


# ─────────────────────────────────────────────────────────────────────────────
# The load-bearing invariant: arcs are decoration, not geometry.
# ─────────────────────────────────────────────────────────────────────────────


def _plan(edge_arcs: dict[str, float]) -> FloorPlan:
    living = Room(
        id="living", name="Living", type="living", x=0.5, y=0.5, width=4, depth=4
    )
    verandah = Room(
        id="ver",
        name="Verandah",
        type="verandah",
        x=0.5,
        y=4.5,
        width=4,
        depth=2,
        edge_arcs=edge_arcs,
    )
    return FloorPlan(floor=0, rooms=[living, verandah])


def test_arcs_do_not_affect_room_area():
    """A dataclass-default comparison proves almost nothing (defect class 2)
    — a field with a default cannot change `.area`/`.rects` on its own. The
    actual claim under test is that the ENTIRE geometry pipeline — wall
    derivation, opening/column placement, dim chains, labels, stair, and
    total floor area — is blind to `edge_arcs`. Assert all of it, not just
    the dataclass."""
    cfg = _cfg()
    straight = _plan({})
    curved = _plan({"S": 0.9})  # large bulge, to make any leak obvious

    straight_room = straight.rooms[1]
    curved_room = curved.rooms[1]
    assert straight_room.area == curved_room.area
    assert curved_room.rects == straight_room.rects

    straight_drawing = build_floor_drawing(straight, cfg)
    curved_drawing = build_floor_drawing(curved, cfg)

    assert straight_drawing.walls, "fixture must actually produce walls"
    assert straight_drawing.walls == curved_drawing.walls
    assert straight_drawing.openings == curved_drawing.openings
    assert straight_drawing.columns == curved_drawing.columns
    assert straight_drawing.junctions == curved_drawing.junctions
    assert straight_drawing.dim_chains == curved_drawing.dim_chains
    assert straight_drawing.labels == curved_drawing.labels
    assert straight_drawing.bounds == curved_drawing.bounds

    straight_total = sum(r.area for r in straight.rooms)
    curved_total = sum(r.area for r in curved.rooms)
    assert straight_total == curved_total


# ─────────────────────────────────────────────────────────────────────────────
# _draw_edge_arcs — PDF path, the new consumer
# ─────────────────────────────────────────────────────────────────────────────


def test_no_op_when_no_room_has_edge_arcs():
    c = canvas.Canvas(BytesIO())
    line_calls = []
    c.line = lambda *a: line_calls.append(a)  # type: ignore[method-assign]
    rooms = [Room(id="a", name="A", type="living", x=0, y=0, width=4, depth=3)]
    _draw_edge_arcs(c, rooms, s=10.0, ox=0.0, oy=0.0)
    assert line_calls == []


def test_draws_a_hiding_stroke_then_the_curve_on_top():
    c = canvas.Canvas(BytesIO())
    line_calls: list[tuple] = []
    path_calls: list[list[tuple]] = []
    c.line = lambda *a: line_calls.append(a)  # type: ignore[method-assign]
    orig_begin_path = c.beginPath

    def spying_begin_path():
        p = orig_begin_path()
        recorded: list[tuple] = []
        orig_move = p.moveTo
        orig_line = p.lineTo

        def move_to(x, y):
            recorded.append((x, y))
            return orig_move(x, y)

        def line_to(x, y):
            recorded.append((x, y))
            return orig_line(x, y)

        p.moveTo = move_to  # type: ignore[method-assign]
        p.lineTo = line_to  # type: ignore[method-assign]
        path_calls.append(recorded)
        return p

    c.beginPath = spying_begin_path  # type: ignore[method-assign]

    rooms = [
        Room(
            id="ver",
            name="Verandah",
            type="verandah",
            x=0,
            y=0,
            width=4,
            depth=2,
            edge_arcs={"S": 0.25},
        )
    ]
    _draw_edge_arcs(c, rooms, s=10.0, ox=5.0, oy=5.0)

    # 1. the straight chord (S edge: (0,0)->(4,0) in room coords) was hidden
    # with a single straight stroke...
    assert len(line_calls) == 1
    x1, y1, x2, y2 = line_calls[0]
    assert (x1, y1) == pytest.approx((5.0, 5.0))
    assert (x2, y2) == pytest.approx((45.0, 5.0))

    # 2. ...and the curve was then stroked as a polyline path with more than
    # 2 points, whose interior actually leaves the chord (a mutation that
    # ignored bulge and drew the straight line again would collapse this to
    # 2 collinear points and fail the interior-offset assertion below).
    assert len(path_calls) == 1
    pts = path_calls[0]
    assert len(pts) > 2
    assert pts[0] == pytest.approx((5.0, 5.0))
    assert pts[-1] == pytest.approx((45.0, 5.0))
    mid = pts[len(pts) // 2]
    assert mid[1] > 5.0 + 1e-6, "the curve's midpoint must have left the chord"
