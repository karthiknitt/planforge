"""Task 18B — every north arrow must point at true north on the sheet.

Three drawers drew north arrows with a fixed "up" triangle (both PDF drawers)
or a filled spike picked by `road_side` treated as a compass direction (DXF).
All three now rotate their glyph so the arrow points at true north per
`vastu.resolve_north_angle(cfg)` — the clockwise angle from the plot's +y axis
to true north. Sheet bearings (degrees, CCW from +x, so +y = 90°) are asserted
as literals:

  road_side="S" → up    (90°)
  road_side="E" → right (0°)
  road_side="N" → down  (270°)
  road_side="W" → left  (180°)

and a surveyed `north_angle_deg` (e.g. 37.5°) must rotate the arrow to sheet
bearing ``90 - north_angle_deg`` (52.5°) — overriding the road side entirely.
"""

import dataclasses
import io
import math

import ezdxf
import pytest

from app.api.routes.export import _render_dxf
from app.engine.approval_pdf import _draw_large_north_arrow
from app.engine.cad_primitives import draw_north_arrow
from app.engine.models import PlotConfig
from app.engine.pdf import _draw_north_arrow
from app.engine.vastu import resolve_north_angle

from tests.helpers.golden import golden_config, golden_layout

#: Sheet bearing (CCW from +x) of true north for each cardinal road side.
CARDINAL_BEARINGS: dict[str, float] = {"S": 90.0, "E": 0.0, "N": 270.0, "W": 180.0}

SURVEYED_ANGLE = 37.5  # non-cardinal — proves the surveyed angle, not the road side
SURVEYED_BEARING = 90.0 - SURVEYED_ANGLE  # 52.5°


def _cfg(road_side: str = "S", north_angle_deg: float | None = None) -> PlotConfig:
    return PlotConfig(
        plot_length=11.0,
        plot_width=12.0,
        setback_front=1.5,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=2,
        toilets=2,
        parking=True,
        city="trichy",
        road_side=road_side,
        north_angle_deg=north_angle_deg,
    )


def _bearing(px: float, py: float, cx: float, cy: float) -> float:
    """Sheet bearing (degrees, CCW from +x, 0..360) of (px,py) seen from (cx,cy)."""
    return math.degrees(math.atan2(py - cy, px - cx)) % 360.0


def _spike_tip_bearing(pts: list[tuple[float, float]], cx: float, cy: float) -> float:
    """Bearing of the triangle tip (vertex farthest from the arrow centre)."""
    tip = max(pts, key=lambda p: math.hypot(p[0] - cx, p[1] - cy))
    return _bearing(tip[0], tip[1], cx, cy)


def _dxf_filled_spike_bearing(hatch) -> float:
    """Bearing of the filled N spike's tip from the hatch's centre vertex.

    `draw_north_arrow` adds the spike path as [left, tip, right, centre], so
    the last vertex is the arrow centre and the farthest of the rest is the tip.
    """
    pts = list(hatch.paths[0].vertices)
    centre = pts[-1]
    tip = max(
        pts[:-1],
        key=lambda v: math.hypot(v[0] - centre[0], v[1] - centre[1]),
    )
    return _bearing(tip[0], tip[1], centre[0], centre[1])


class _StubPath:
    def __init__(self) -> None:
        self.points: list[tuple[float, float]] = []

    def moveTo(self, x: float, y: float) -> None:
        self.points.append((x, y))

    def lineTo(self, x: float, y: float) -> None:
        self.points.append((x, y))

    def close(self) -> None:
        pass


class _StubCanvas:
    """Records every filled path so a test can measure the drawn spike.

    The north-arrow drawers draw the circle and text via their own methods; the
    filled triangle is the only `beginPath`/`drawPath` pair, so `paths[0]` is
    the spike.
    """

    def __init__(self) -> None:
        self.paths: list[list[tuple[float, float]]] = []

    def beginPath(self) -> _StubPath:
        self._current = _StubPath()
        return self._current

    def drawPath(self, p: _StubPath, fill: int = 0, stroke: int = 0) -> None:
        self.paths.append(p.points)

    def circle(self, *args, **kwargs) -> None:
        pass

    def setFillColor(self, *args, **kwargs) -> None:
        pass

    def setStrokeColor(self, *args, **kwargs) -> None:
        pass

    def setLineWidth(self, *args, **kwargs) -> None:
        pass

    def setFont(self, *args, **kwargs) -> None:
        pass

    def drawCentredString(self, *args, **kwargs) -> None:
        pass


@pytest.mark.parametrize("road_side,bearing", sorted(CARDINAL_BEARINGS.items()))
def test_draw_north_arrow_tip_points_at_true_north(
    road_side: str, bearing: float
) -> None:
    angle = resolve_north_angle(_cfg(road_side=road_side))
    stub = _StubCanvas()
    _draw_north_arrow(stub, 100.0, 100.0, 20.0, angle)
    assert _spike_tip_bearing(stub.paths[0], 100.0, 100.0) == pytest.approx(
        bearing, abs=1e-6
    )


@pytest.mark.parametrize("road_side,bearing", sorted(CARDINAL_BEARINGS.items()))
def test_draw_large_north_arrow_tip_points_at_true_north(
    road_side: str, bearing: float
) -> None:
    angle = resolve_north_angle(_cfg(road_side=road_side))
    stub = _StubCanvas()
    _draw_large_north_arrow(stub, 100.0, 100.0, 20.0, angle)
    assert _spike_tip_bearing(stub.paths[0], 100.0, 100.0) == pytest.approx(
        bearing, abs=1e-6
    )


@pytest.mark.parametrize("road_side,bearing", sorted(CARDINAL_BEARINGS.items()))
def test_dxf_filled_n_spike_points_at_true_north(
    road_side: str, bearing: float
) -> None:
    angle = resolve_north_angle(_cfg(road_side=road_side))
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    draw_north_arrow(msp, 0.0, 0.0, angle, 1.0, "TEXT")
    hatches = list(msp.query("HATCH"))
    assert len(hatches) == 1
    assert _dxf_filled_spike_bearing(hatches[0]) == pytest.approx(bearing, abs=1e-6)


def test_pdf_north_arrow_honours_surveyed_north_angle_over_road_side() -> None:
    cfg = _cfg(road_side="S", north_angle_deg=SURVEYED_ANGLE)
    assert resolve_north_angle(cfg) == pytest.approx(SURVEYED_ANGLE)
    stub = _StubCanvas()
    _draw_north_arrow(stub, 100.0, 100.0, 20.0, resolve_north_angle(cfg))
    assert _spike_tip_bearing(stub.paths[0], 100.0, 100.0) == pytest.approx(
        SURVEYED_BEARING, abs=1e-6
    )


def test_dxf_north_arrow_honours_surveyed_north_angle_over_road_side() -> None:
    cfg = _cfg(road_side="S", north_angle_deg=SURVEYED_ANGLE)
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    draw_north_arrow(msp, 0.0, 0.0, resolve_north_angle(cfg), 1.0, "TEXT")
    hatch = next(iter(msp.query("HATCH")))
    assert _dxf_filled_spike_bearing(hatch) == pytest.approx(SURVEYED_BEARING, abs=1e-6)


def test_dxf_export_honours_surveyed_north_angle_over_road_side() -> None:
    """`export._render_dxf` must feed the RESOLVED angle, not `cfg.road_side`.

    A non-cardinal surveyed angle (37.5°) cannot be produced from any road-side
    string, so a passing assert proves the export path uses `resolve_north_angle`.
    """
    cfg = dataclasses.replace(golden_config(), north_angle_deg=SURVEYED_ANGLE)
    dxf_bytes = _render_dxf("Test", golden_layout(), cfg)
    doc = ezdxf.read(io.StringIO(dxf_bytes.decode("utf-8")))
    msp = doc.modelspace()
    north_hatches = [h for h in msp.query("HATCH") if h.dxf.layer == "TEXT"]
    assert len(north_hatches) == 1
    assert _dxf_filled_spike_bearing(north_hatches[0]) == pytest.approx(
        SURVEYED_BEARING, abs=1e-6
    )
