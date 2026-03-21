"""Tests for DXF document-level setup: metric headers, LWDISPLAY, DEFPOINTS."""
import io
import pytest
import ezdxf

from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.api.routes.export import _render_dxf


@pytest.fixture(scope="module")
def sample_cfg():
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
        road_side="S",
        num_floors=2,
    )


@pytest.fixture(scope="module")
def dxf_doc(sample_cfg):
    layouts = generate(sample_cfg)
    dxf_bytes = _render_dxf("Test", layouts[0], sample_cfg)
    return ezdxf.read(io.StringIO(dxf_bytes.decode("utf-8")))


def test_dxf_has_lwdisplay(dxf_doc):
    assert dxf_doc.header.get("$LWDISPLAY") == 1


def test_dxf_has_measurement_metric(dxf_doc):
    assert dxf_doc.header.get("$MEASUREMENT") == 1


def test_dxf_has_defpoints_layer(dxf_doc):
    # ezdxf creates "Defpoints" (mixed case) when setup=True; check case-insensitively
    layer_names = [lyr.dxf.name.upper() for lyr in dxf_doc.layers]
    assert "DEFPOINTS" in layer_names
