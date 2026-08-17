"""Unit tests for the shared compound-wall geometry (app.engine.geometry) and
its DXF/PDF consumers.

NOTE ON GATE WIDTH: task-11-brief.md's sample code hardcodes a 3.0 m gate.
The shipping DXF renderer (cad_advanced.draw_compound_wall, pre-existing —
not written for this task) has used a 3.6 m gate since before this module
existed; see GATE_WIDTH_M in app/engine/geometry.py. Per the task's own
instruction ("the existing renderer is shipping behavior; the brief's sample
is illustrative"), these tests assert the real 3.6 m figure, not the spec
sample's 3.0 m.

NOTE ON IMPORT PATH: the brief's sample test imports
`from app.engine.pdf import compound_wall_segments`. The real home is
`app.engine.geometry` (the existing plot/setback geometry module — see its
module docstring), imported by both `cad_advanced.py` (DXF) and `pdf.py`.
Importing a DXF module from a ReportLab module (or vice versa) would be a bad
dependency direction, so the test imports from the real home instead of
relying on a re-export.
"""

from __future__ import annotations

import types
from io import BytesIO

import ezdxf
import pytest
from reportlab.pdfgen import canvas

from app.engine.cad_advanced import draw_compound_wall
from app.engine.geometry import (
    GATE_WIDTH_M,
    compound_wall_gate_posts,
    compound_wall_segments,
)
from app.engine.models import (
    ComplianceResult,
    FloorPlan,
    Layout,
    PlotConfig,
    Room,
)
from app.engine.pdf import _draw_compound_wall, _ground_floor_main_door_x
from app.engine.plan_geometry import build_floor_drawing


def _cfg(road_side: str = "S") -> PlotConfig:
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


# ─────────────────────────────────────────────────────────────────────────────
# compound_wall_segments — pure geometry
# ─────────────────────────────────────────────────────────────────────────────


def test_compound_wall_has_a_gate_gap_on_the_road_side():
    segs = compound_wall_segments(_cfg("S"))
    front = [s for s in segs if abs(s[1] - 0.0) < 1e-6 and abs(s[3] - 0.0) < 1e-6]
    assert len(front) == 2, "front run must be split into two by the gate gap"
    covered = sum(abs(s[2] - s[0]) for s in front)
    assert abs((9.0 - covered) - GATE_WIDTH_M) < 1e-6, (
        f"gate gap must be {GATE_WIDTH_M} m (shipping DXF value)"
    )


def test_gate_moves_with_road_side():
    segs = compound_wall_segments(_cfg("W"))
    left = [s for s in segs if abs(s[0] - 0.0) < 1e-6 and abs(s[2] - 0.0) < 1e-6]
    assert len(left) == 2, "gate must be on the W run when road_side='W'"
    covered = sum(abs(s[3] - s[1]) for s in left)
    assert abs((15.0 - covered) - GATE_WIDTH_M) < 1e-6


def test_all_four_runs_present():
    segs = compound_wall_segments(_cfg("S"))
    assert len(segs) == 5, "3 solid runs + 2 gate-split front pieces"
    solid = [s for s in segs if not (abs(s[1]) < 1e-6 and abs(s[3]) < 1e-6)]
    assert len(solid) == 3


def test_gate_centred_by_default_on_south_edge():
    segs = compound_wall_segments(_cfg("S"))
    front = sorted(
        (s for s in segs if abs(s[1]) < 1e-6 and abs(s[3]) < 1e-6), key=lambda s: s[0]
    )
    assert len(front) == 2
    gap_start, gap_end = front[0][2], front[1][0]
    assert gap_start < gap_end, "gate gap endpoints must be in order"
    mid = (gap_start + gap_end) / 2
    assert abs(mid - 4.5) < 1e-6, "gate must be centred on a 9.0 m road-side edge"


def test_gate_shifts_toward_gate_cx():
    # gate_cx must stay in [GATE_WIDTH_M/2, plot_width - GATE_WIDTH_M/2] = [1.8, 7.2]
    # to land unclamped; 6.0 is off-centre from the 4.5 default so movement is
    # observable without hitting the wall edge.
    centred = compound_wall_segments(_cfg("S"))
    offset = compound_wall_segments(_cfg("S"), gate_cx=6.0)
    assert centred != offset, "gate_cx must actually move the gate"
    front_offset = sorted(
        (s for s in offset if abs(s[1]) < 1e-6 and abs(s[3]) < 1e-6),
        key=lambda s: s[0],
    )
    assert len(front_offset) == 2
    gap_start, gap_end = front_offset[0][2], front_offset[1][0]
    mid = (gap_start + gap_end) / 2
    assert abs(mid - 6.0) < 1e-6, "gate must centre on gate_cx when it fits on the wall"


def test_gate_posts_bracket_the_gap():
    posts = compound_wall_gate_posts(_cfg("S"))
    assert posts is not None
    (x1, y1), (x2, y2) = posts
    assert x1 < x2
    assert abs(x2 - x1 - GATE_WIDTH_M) < 1e-6
    assert abs(y1) < 1e-6
    assert abs(y2) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# DXF path — behaviour-preservation after the refactor to consume the shared
# helper (draw_compound_wall previously computed this geometry inline)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def msp():
    doc = ezdxf.new("R2010")
    doc.layers.new("A-COMPOUND-WALL")
    return doc.modelspace()


def _polys_on_layer(msp, layer: str) -> list:
    return [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == layer]


def test_dxf_compound_wall_still_produces_five_walls_plus_two_posts(msp):
    """Regression pin for the extraction: with the S-road fixture the old
    inline implementation drew 3 solid-side polys + 2 gate-split polys + 2
    gate-post squares = 7 LWPOLYLINEs. The shared-helper version must match."""
    draw_compound_wall(msp, _cfg("S"), "A-COMPOUND-WALL", 0.0)
    polys = _polys_on_layer(msp, "A-COMPOUND-WALL")
    assert len(polys) == 7


def _drawn_post_centres(
    msp, layer: str = "A-COMPOUND-WALL"
) -> set[tuple[float, float]]:
    """Centres of the gate-post squares actually emitted into ``msp``.

    Posts are the only near-square polylines on the layer — wall segments are
    long buffered rectangles — so a small bounding box identifies them.
    """

    def _is_post(e) -> bool:
        pts = list(e.get_points("xy"))
        if len(pts) != 4:
            return False
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (max(xs) - min(xs)) < 0.35 and (max(ys) - min(ys)) < 0.35

    centres = set()
    for e in _polys_on_layer(msp, layer):
        if _is_post(e):
            pts = list(e.get_points("xy"))
            centres.add(
                (
                    round(sum(p[0] for p in pts) / 4, 2),
                    round(sum(p[1] for p in pts) / 4, 2),
                )
            )
    return centres


def test_dxf_gate_posts_sit_at_the_shared_gate_positions(msp):
    cfg = _cfg("S")
    draw_compound_wall(msp, cfg, "A-COMPOUND-WALL", 0.0)
    expected_posts = compound_wall_gate_posts(cfg)
    assert expected_posts is not None

    post_centres = _drawn_post_centres(msp)
    assert len(post_centres) == 2, "expected exactly 2 gate-post squares"
    assert post_centres == {(round(p[0], 2), round(p[1], 2)) for p in expected_posts}
    # Independent of the shared helper: the pre-refactor inline code placed the
    # posts at the gate-gap edges of a centred 3.6 m gate on a 9.0 m frontage,
    # i.e. (9.0 ± 3.6) / 2 = 2.7 and 6.3, both on the y=0 road edge.
    assert post_centres == {(2.7, 0.0), (6.3, 0.0)}


def test_dxf_gate_still_tracks_gate_cx(msp):
    """Behaviour preserved: passing gate_cx still shifts the DRAWN gate.

    Asserts against the entities `draw_compound_wall` emitted, not against the
    shared helper — otherwise this passes even if the DXF renderer ignored
    `gate_cx`, which is live shipping behaviour (`export.py` passes it on every
    export).
    """
    draw_compound_wall(msp, _cfg("S"), "A-COMPOUND-WALL", 0.0, gate_cx=6.0)

    drawn = _drawn_post_centres(msp)
    assert len(drawn) == 2, f"expected 2 drawn gate posts, got {drawn}"
    mid_x = sum(cx for cx, _ in drawn) / 2
    assert abs(mid_x - 6.0) < 1e-6, f"drawn gate centred at {mid_x}, expected 6.0"
    # Guards the fixture: a gate at 4.5 is where the default already sits, so
    # 6.0 must actually differ from the centred case for this to prove anything.
    assert drawn != {(2.7, 0.0), (6.3, 0.0)}


# ─────────────────────────────────────────────────────────────────────────────
# PDF path — the new consumer added by this task
# ─────────────────────────────────────────────────────────────────────────────


def test_pdf_compound_wall_draws_a_stroke_per_segment():
    buf = BytesIO()
    c = canvas.Canvas(buf)
    cfg = _cfg("S")
    calls: list[tuple[float, float, float, float]] = []
    c.line = lambda x1, y1, x2, y2: calls.append((x1, y1, x2, y2))  # type: ignore[method-assign]

    _draw_compound_wall(c, cfg, ox=10.0, oy=20.0, s=2.0)

    expected = compound_wall_segments(cfg)
    assert len(calls) == len(expected) == 5
    for (x1, y1, x2, y2), (ex1, ey1, ex2, ey2) in zip(calls, expected, strict=True):
        assert abs(x1 - (10.0 + ex1 * 2.0)) < 1e-6
        assert abs(y1 - (20.0 + ey1 * 2.0)) < 1e-6
        assert abs(x2 - (10.0 + ex2 * 2.0)) < 1e-6
        assert abs(y2 - (20.0 + ey2 * 2.0)) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# PDF/DXF gate agreement
#
# The property worth pinning is not that either renderer accepts a gate_cx —
# it is that both derive the SAME gate position from the SAME layout. Before
# this was wired, PDF always centred the gate while DXF aligned it to the main
# entrance, so the two exports of one building disagreed about where the gate
# physically is.
# ─────────────────────────────────────────────────────────────────────────────


def _layout_with_main_door_at(cx: float) -> Layout:
    """A ground floor whose derived main entrance sits near plot-x ``cx``.

    The main-entrance pass picks the road-facing wall of the entry room, so the
    room is placed to straddle ``cx`` on the south (road) edge.

    Rooms stay inside the buildable envelope for ``_cfg()`` — x [1.2, 7.8],
    y [3.0, 13.5] — so the geometry pass does not warn about out-of-bounds
    rooms and the derivation runs on a realistic plan.
    """
    return Layout(
        id="gate-test",
        name="Gate Test",
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
                Room(
                    id="bed-1",
                    name="Bedroom 1",
                    type="bedroom",
                    x=1.2,
                    y=6.5,
                    width=3.0,
                    depth=3.0,
                ),
            ],
        ),
        first_floor=FloorPlan(floor=1, floor_type="first", rooms=[]),
        compliance=ComplianceResult(passed=True),
    )


def _front_gate_midpoint(segs, cfg: PlotConfig) -> float:
    """Centre of the gate gap on the south (y=0) run.

    The run is split into two pieces; the gap lies between their inner ends,
    which are the only front x-coordinates that are neither plot edge.
    """
    front = [s for s in segs if abs(s[1]) < 1e-6 and abs(s[3]) < 1e-6]
    assert len(front) == 2, f"expected a split front run, got {len(front)} piece(s)"
    inner = sorted(
        x
        for s in front
        for x in (s[0], s[2])
        if abs(x) > 1e-6 and abs(x - cfg.plot_width) > 1e-6
    )
    assert len(inner) == 2, f"expected two inner gate edges, got {inner}"
    return (inner[0] + inner[1]) / 2.0


def test_pdf_and_dxf_derive_the_same_gate_x_from_the_same_layout():
    """The two renderers must agree on where the gate is, not merely accept a value."""
    cfg, layout = _cfg("S"), _layout_with_main_door_at(6.5)

    pdf_gate_x = _ground_floor_main_door_x(layout, cfg)

    # The DXF derivation, reproduced exactly as api/routes/export.py performs it.
    drawing = build_floor_drawing(layout.ground_floor, cfg)
    dxf_gate_x = next((o.cx for o in drawing.openings if o.is_main), None)

    assert pdf_gate_x is not None, (
        "fixture must derive a main entrance, else this test proves nothing"
    )
    assert pdf_gate_x == dxf_gate_x


def test_pdf_gate_actually_moves_with_the_derived_door():
    """Guards against the helper being computed and then not passed through."""
    cfg = _cfg("S")
    # Deliberately off-centre: a door at plot-x 4.5 would sit exactly where the
    # centred gate already is (plot_width 9.0 / 2), and the test would pass
    # against an implementation that ignored the door entirely.
    gate_x = _ground_floor_main_door_x(_layout_with_main_door_at(6.5), cfg)
    assert gate_x is not None

    aligned = compound_wall_segments(cfg, gate_cx=gate_x)
    centred = compound_wall_segments(cfg, gate_cx=None)
    assert aligned != centred, (
        f"derived gate x {gate_x} coincides with the centred gate, so this "
        "fixture cannot detect a gate that ignores the door"
    )

    assert abs(_front_gate_midpoint(aligned, cfg) - gate_x) < 1e-6


def test_missing_main_entrance_falls_back_to_a_centred_gate():
    """A ground floor with no derivable main entrance must still get a gate.

    The fixture is a degenerate empty floor, not the `l_shaped_3bhk` GCS case —
    that case is the reason this path is known to be reachable rather than
    defensive, but it is not what is exercised here.
    """
    cfg = _cfg("S")
    doorless = Layout(
        id="doorless",
        name="Doorless",
        ground_floor=FloorPlan(floor=0, floor_type="ground", rooms=[]),
        first_floor=FloorPlan(floor=1, floor_type="first", rooms=[]),
        compliance=ComplianceResult(passed=True),
    )
    assert _ground_floor_main_door_x(doorless, cfg) is None
    # And that None yields a gate centred on the 9.0 m frontage — asserting the
    # position, not that an explicit None equals the parameter's own default.
    mid = _front_gate_midpoint(compound_wall_segments(cfg, gate_cx=None), cfg)
    assert abs(mid - 4.5) < 1e-6


def test_render_pdf_threads_the_derived_gate_x_to_every_floor_page(monkeypatch):
    """The exact regression this fix closes: derived, then not passed through.

    Pins the whole chain — render_pdf derives once, _draw_floor_projected
    forwards, _draw_compound_wall receives it — and that every page gets the
    SAME value, since the compound wall is one site-level structure.
    """
    from app.engine import pdf as pdf_mod

    seen: list[float | None] = []

    def _spy(*args, gf_main_door_x=None, **kwargs):
        seen.append(gf_main_door_x)

    # Only the architectural-page loop is under test; stubbing the page
    # renderer keeps this off the section/elevation path, which needs a far
    # richer plan than the gate derivation does.
    monkeypatch.setattr(pdf_mod, "_draw_floor_projected", _spy)
    # The later page groups need a far richer plan than the gate derivation
    # does, so they are stubbed out rather than exercised — this lets
    # render_pdf run to completion instead of the test swallowing its error.
    _stub = types.SimpleNamespace(title="stub")
    monkeypatch.setattr(pdf_mod, "_draw_structural_floor", lambda *a, **k: None)
    monkeypatch.setattr(pdf_mod, "derive_section", lambda *a, **k: _stub)
    monkeypatch.setattr(pdf_mod, "derive_elevation", lambda *a, **k: _stub)
    monkeypatch.setattr(pdf_mod, "render_section_view", lambda *a, **k: 50)
    monkeypatch.setattr(pdf_mod, "render_elevation_view", lambda *a, **k: 50)
    monkeypatch.setattr(pdf_mod, "_draw_title_block", lambda *a, **k: None)

    cfg = _cfg("S")
    layout = _layout_with_main_door_at(6.5)
    expected = _ground_floor_main_door_x(layout, cfg)
    assert expected is not None

    pdf_mod.render_pdf("T", layout, cfg, 3)

    # Both floors of the fixture must render — set equality alone collapses
    # duplicates, so it would pass if a page group were dropped entirely.
    assert len(seen) == 2, f"expected 2 architectural pages, got {len(seen)}"
    assert set(seen) == {expected}, (
        f"every page must use the ground floor's gate x {expected}, got {seen}"
    )
