"""Tests for DXF ARCH_MM dimstyle: exists at doc level, uses architectural tick arrow."""
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


def test_arch_mm_dimstyle_exists(dxf_doc):
    assert "ARCH_MM" in dxf_doc.dimstyles


def test_arch_mm_uses_archtick(dxf_doc):
    """ARCH_MM dimstyle must have architectural tick as the arrow block (dimblk)."""
    ds = dxf_doc.dimstyles.get("ARCH_MM")
    # ezdxf stores set_arrows(blk=ARCHTICK) in the 'dimblk' attribute
    dimblk = ds.dxf.dimblk.upper()
    assert "ARCHTICK" in dimblk, (
        f"Expected ARCHTICK in dimblk, got {dimblk!r}"
    )
