"""Tests for DXF wall hatch convention: solid fill (not ANSI31/37 pattern)."""
import io
import pytest
import ezdxf

from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.api.routes.export import _render_dxf


@pytest.fixture(scope="module")
def dxf_doc():
    cfg = PlotConfig(
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
        road_side="S",
        num_floors=2,
    )
    layouts = generate(cfg)
    dxf_bytes = _render_dxf("Test", layouts[0], cfg)
    return ezdxf.read(io.StringIO(dxf_bytes.decode("utf-8")))


def test_wall_hatches_exist_and_are_solid(dxf_doc):
    """
    Wall hatches must exist (previously silently failed due to elevation dxfattrib bug)
    and must use solid fill (not ANSI31/37 diagonal pattern).
    """
    hatches = [e for e in dxf_doc.modelspace() if e.dxftype() == "HATCH"]
    # wall-brick and wall-int hatches come from draw_wall_with_breaks
    wall_hatches = [
        h for h in hatches
        if any(k in h.dxf.layer.upper() for k in ("WALL-BRICK", "WALL-INT"))
    ]
    assert len(wall_hatches) > 0, (
        "Expected wall hatch entities on A-WALL-BRICK or A-WALL-INT layers. "
        "Previously these were silently dropped due to 'elevation' dxfattrib bug."
    )
    for h in wall_hatches:
        assert h.dxf.solid_fill == 1, (
            f"Wall hatch on {h.dxf.layer!r} should be solid fill, not pattern"
        )
