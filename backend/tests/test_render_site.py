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
from app.engine.models import PlotConfig
from app.engine.pdf import _draw_compound_wall


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


def test_dxf_gate_posts_sit_at_the_shared_gate_positions(msp):
    cfg = _cfg("S")
    draw_compound_wall(msp, cfg, "A-COMPOUND-WALL", 0.0)
    expected_posts = compound_wall_gate_posts(cfg)
    assert expected_posts is not None

    def _is_post(e) -> bool:
        pts = list(e.get_points("xy"))
        if len(pts) != 4:
            return False
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (max(xs) - min(xs)) < 0.35 and (max(ys) - min(ys)) < 0.35

    post_centres = set()
    for e in _polys_on_layer(msp, "A-COMPOUND-WALL"):
        if _is_post(e):
            pts = list(e.get_points("xy"))
            cx = round(sum(p[0] for p in pts) / 4, 2)
            cy = round(sum(p[1] for p in pts) / 4, 2)
            post_centres.add((cx, cy))
    assert len(post_centres) == 2, "expected exactly 2 gate-post squares"
    expected = {(round(p[0], 2), round(p[1], 2)) for p in expected_posts}
    assert post_centres == expected


def test_dxf_gate_still_tracks_gate_cx(msp):
    """Behaviour preserved: passing gate_cx still shifts the gate on a
    horizontal road-side run (main-entrance-aligned gate)."""
    draw_compound_wall(msp, _cfg("S"), "A-COMPOUND-WALL", 0.0, gate_cx=6.0)
    posts = compound_wall_gate_posts(_cfg("S"), gate_cx=6.0)
    assert posts is not None
    mid_x = (posts[0][0] + posts[1][0]) / 2
    assert abs(mid_x - 6.0) < 1e-6


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
