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
from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas

from app.engine.geometry import arc_points, buildable_polygon
from app.engine.models import ComplianceResult, FloorPlan, Layout, PlotConfig, Room
from app.engine.pdf import _draw_edge_arcs, _edge_arc_bands, _is_external_edge
from app.engine.plan_geometry import (
    EWT,
    IWT,
    _plate_bounds,
    build_floor_drawing,
    opening_boxes,
    wall_polygons,
)


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


def test_edge_arcs_rejected_on_a_non_rect_template():
    """Important #5: a non-RECT bounding-box side is not guaranteed to sit
    on a real wall (an L/T-shape's bbox can extend past its footprint), so
    an arc there could slash across open space with no wall under it."""
    with pytest.raises(ValueError, match="edge_arcs"):
        Room(
            id="a",
            name="A",
            type="verandah",
            x=0,
            y=0,
            width=4,
            depth=3,
            template="L",
            shape_ratio=0.6,
            edge_arcs={"S": 0.2},
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
# _edge_arc_bands — the pure Shapely geometry behind the PDF overlay.
#
# These assert directly on the band SHAPES rather than reverse-engineering
# them from ReportLab canvas calls, per the reviewer's fix instructions:
# the reviewer could not verify the sliver (Critical #1) or the
# opening-refill (Critical #3) from the diff alone, so both are exercised
# here with a REAL `build_floor_drawing` (not a bare `Room`), on an edge
# that actually sits on the floor's exterior plate boundary and actually
# carries a real derived opening — the fixture the original review found
# missing.
# ─────────────────────────────────────────────────────────────────────────────


def _road_side_room(edge_arcs: dict[str, float], depth: float = 4.0) -> tuple:
    """A single room spanning the full buildable width, its S edge flush with
    the floor's exterior plate boundary (the road side) — the genuinely
    EXTERNAL case Critical #1/#3 are about, as opposed to `_plan()`'s
    verandah (S edge shared with `living`, i.e. INTERNAL)."""
    cfg = _cfg()
    buildable = buildable_polygon(cfg)
    bx1, by1, bx2, by2 = buildable.bounds
    room = Room(
        id="living",
        name="Living",
        type="living",
        x=bx1,
        y=by1,
        width=bx2 - bx1,
        depth=depth,
        edge_arcs=edge_arcs,
    )
    return cfg, buildable, room


def test_external_erase_band_matches_the_real_poche_band():
    """Critical #1: the erase band must actually cover the real wall poché
    along that edge, not just approximate it with a stroke width guessed to
    be wide enough. Mutation-provable: centring the band on the footprint
    edge instead of offsetting it outward (the original bug) would leave it
    overlapping only ~half of `real_ext`, well under the 0.95 threshold."""
    cfg, buildable, room = _road_side_room({"S": 0.05})
    fp = FloorPlan(floor=0, rooms=[room])
    drawing = build_floor_drawing(fp, cfg)
    plate = _plate_bounds(fp.rooms, buildable, EWT)

    straight_band, _curve = _edge_arc_bands(room, "S", 0.05, plate, EWT, IWT, [])
    real_ext = wall_polygons(drawing.walls, openings=[])["external"]

    covered = straight_band.intersection(real_ext).area
    assert straight_band.area > 0, "fixture must produce a real band"
    assert covered / straight_band.area > 0.95, (
        "erase band must lie almost entirely within the real external poché"
    )


def test_curve_band_is_cut_by_a_real_derived_opening():
    """Critical #3: subtracting `opening_polys` must actually remove area
    where a REAL derived opening sits — not just run without erroring. Uses
    a small bulge so the curve stays close to the wall centreline near the
    opening (a large bulge sweeps the curve's midpoint away from the
    opening entirely and would make this pass vacuously)."""
    cfg, buildable, room = _road_side_room({"S": 0.02})
    fp = FloorPlan(floor=0, rooms=[room])
    drawing = build_floor_drawing(fp, cfg)
    plate = _plate_bounds(fp.rooms, buildable, EWT)
    opening_polys = opening_boxes(drawing.openings)
    main_doors = [
        op for o, op in zip(drawing.openings, opening_polys, strict=True) if o.is_main
    ]
    assert main_doors, "fixture must derive a main entrance on the S edge"

    with_opening = _edge_arc_bands(room, "S", 0.02, plate, EWT, IWT, opening_polys)[1]
    without_opening = _edge_arc_bands(room, "S", 0.02, plate, EWT, IWT, [])[1]

    assert without_opening.area > with_opening.area, (
        "cutting against the main door's opening box must shrink the band"
    )
    reduction = without_opening.area - with_opening.area
    assert reduction == pytest.approx(main_doors[0].area, rel=0.05), (
        "the removed area should be ~ the opening's own box area, not a "
        "coincidental sliver"
    )


def test_internal_edge_uses_iwt_not_ewt():
    """Important #4: an edge shared between two rooms (not on the plate
    boundary) must use IWT, not the external EWT — reusing `_plan()`'s
    verandah/living fixture, whose shared S edge is internal by construction
    (see its own docstring)."""
    cfg = _cfg()
    plan = _plan({"S": 0.1})
    buildable = buildable_polygon(cfg)
    plate = _plate_bounds(plan.rooms, buildable, EWT)
    verandah = plan.rooms[1]

    assert not _is_external_edge(verandah, "S", plate), (
        "fixture must actually be internal for this test to mean anything"
    )
    straight_band, _curve = _edge_arc_bands(verandah, "S", 0.1, plate, EWT, IWT, [])
    width = straight_band.bounds[3] - straight_band.bounds[1]  # S is horizontal
    assert width == pytest.approx(IWT, abs=1e-6)


# side -> which bound must move, and in which direction, for a positive
# bulge to be a genuine outward bow (Critical #2's fix).
_OUTWARD_BOUND = {
    "S": (1, "decrease"),  # min-y moves down (more negative)
    "N": (3, "increase"),  # max-y moves up
    "W": (0, "decrease"),  # min-x moves left
    "E": (2, "increase"),  # max-x moves right
}


@pytest.mark.parametrize("side", ["S", "N", "W", "E"])
def test_positive_bulge_bows_outward_on_every_side(side):
    """Critical #2: the review found N/W bowing outward but S/E bowing
    INWARD for a positive bulge under the original chord ordering — and the
    original test's `mid[1] > 5.0` assertion blessed the bug on `S`, the
    side the motivating Kerala verandah case actually uses. Check all four
    sides explicitly so no side can silently regress back to inward."""
    room = Room(
        id="r",
        name="R",
        type="verandah",
        x=0.0,
        y=0.0,
        width=4.0,
        depth=3.0,
        edge_arcs={side: 0.2},
    )
    # Bulge of 0.2 with no plate to be "external" against -> everything is
    # internal (IWT-thick), which is irrelevant to direction; use plate
    # bounds equal to the room itself so the edge counts as external and
    # exercises the outward-offset code path too.
    plate = (room.x, room.y, room.x + room.width, room.y + room.depth)
    straight_band, curve_band = _edge_arc_bands(room, side, 0.2, plate, EWT, IWT, [])

    idx, direction = _OUTWARD_BOUND[side]
    if direction == "decrease":
        assert curve_band.bounds[idx] < straight_band.bounds[idx], (
            f"{side}: positive bulge must bow OUTWARD, away from the room"
        )
    else:
        assert curve_band.bounds[idx] > straight_band.bounds[idx], (
            f"{side}: positive bulge must bow OUTWARD, away from the room"
        )


# ─────────────────────────────────────────────────────────────────────────────
# _draw_edge_arcs — the ReportLab-drawing wrapper around _edge_arc_bands
# ─────────────────────────────────────────────────────────────────────────────


def test_no_op_when_no_room_has_edge_arcs():
    c = canvas.Canvas(BytesIO())
    calls: list[str] = []
    c.beginPath = lambda: calls.append("beginPath") or canvas.Canvas.beginPath(c)  # type: ignore[method-assign]
    cfg, _buildable, room = _road_side_room({})
    _draw_edge_arcs(c, [room], cfg, [], s=10.0, ox=0.0, oy=0.0)
    assert calls == []


def test_draws_a_white_fill_then_a_black_fill():
    """Both the colour AND the fill-vs-stroke mode carry the hide decision
    (Minor #7): a mutation flipping the erase fill to black, or skipping the
    `setFillColor`/`setStrokeColor` calls, must be caught here — not just
    the coordinates of what got drawn."""
    c = canvas.Canvas(BytesIO())
    fill_colors: list[str] = []
    orig_set_fill = c.setFillColor

    def spy_set_fill(color):
        fill_colors.append(color.hexval() if hasattr(color, "hexval") else str(color))
        return orig_set_fill(color)

    c.setFillColor = spy_set_fill  # type: ignore[method-assign]

    fill_calls: list[str] = []
    orig_draw_path = c.drawPath

    def spy_draw_path(path, **kw):
        fill_calls.append(fill_colors[-1])
        return orig_draw_path(path, **kw)

    c.drawPath = spy_draw_path  # type: ignore[method-assign]

    cfg, _buildable, room = _road_side_room({"S": 0.05})
    _draw_edge_arcs(c, [room], cfg, [], s=10.0, ox=0.0, oy=0.0)

    assert len(fill_calls) == 2, "expected exactly one erase fill + one curve fill"
    white_hex = white.hexval()
    black_hex = HexColor("#000000").hexval()
    assert fill_calls[0] == white_hex, "the erase band must be filled white first"
    assert fill_calls[1] == black_hex, "the curve band must be filled black second"


def test_edge_arcs_run_immediately_after_the_poche(monkeypatch):
    """Important #6: this function's call site has already moved twice on
    this branch for paint-order reasons (Task 11 moved `_draw_compound_wall`;
    Task 12 inserted `_draw_landscape`) — a docstring alone would not have
    caught a THIRD reorder. Spies on every named drawing pass in
    `_draw_floor_projected` and asserts `_draw_edge_arcs` is the first pass
    to run after the two poché `_shape_path` fills, and strictly before
    every other named pass."""
    from app.engine import pdf as pdf_mod

    order: list[str] = []

    def _tap(name):
        original = getattr(pdf_mod, name)

        def wrapper(*a, **kw):
            order.append(name)
            return original(*a, **kw)

        return wrapper

    # `_draw_landscape` legitimately runs BEFORE the poché (ground texture
    # under everything) — it belongs on the "before" side, not the "after"
    # side, of this ordering check.
    before_arcs = ["_draw_landscape"]
    after_arcs = [
        "_draw_compound_wall",
        "_draw_dim_chains",
        "_draw_voids",
        "_draw_labels",
        "_draw_stair_geometry",
        "_draw_opening_symbol",
        "_draw_setback_callouts",
    ]
    for name in ["_shape_path", "_draw_edge_arcs", *before_arcs, *after_arcs]:
        monkeypatch.setattr(pdf_mod, name, _tap(name))

    cfg, _buildable, room = _road_side_room({"S": 0.05})
    fp = FloorPlan(floor=0, rooms=[room])
    layout = Layout(
        id="A",
        name="A",
        ground_floor=fp,
        first_floor=FloorPlan(floor=1),
        compliance=ComplianceResult(passed=True),
    )
    c = canvas.Canvas(BytesIO())
    pdf_mod._draw_floor_projected(c, fp, layout, cfg, "T", 3, "GROUND")

    assert order.count("_draw_edge_arcs") == 1, "sanity: arcs must run exactly once"
    arcs_idx = order.index("_draw_edge_arcs")
    shape_path_positions = [i for i, name in enumerate(order) if name == "_shape_path"]
    assert len(shape_path_positions) >= 2, "sanity: fixture must draw the wall poché"
    # Arcs must be the very next entry after the LAST poché `_shape_path`
    # call (external, then internal) — not merely "somewhere after".
    last_poche_idx = shape_path_positions[1]
    assert arcs_idx == last_poche_idx + 1, (
        f"expected arcs immediately after the 2nd poché _shape_path call, "
        f"got order={order}"
    )
    for name in before_arcs:
        positions = [i for i, n in enumerate(order) if n == name]
        assert positions, f"sanity: {name} must actually run"
        assert all(i < arcs_idx for i in positions), (
            f"{name} must run before _draw_edge_arcs (ground texture under "
            f"the poché) — draw-order regression"
        )
    for name in after_arcs:
        positions = [i for i, n in enumerate(order) if n == name]
        assert positions, f"sanity: {name} must actually run"
        assert all(i > arcs_idx for i in positions), (
            f"{name} ran before _draw_edge_arcs — draw-order regression"
        )
