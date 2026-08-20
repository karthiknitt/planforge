"""Tests for DXF door/window/ventilator openings as reusable BLOCK inserts."""

import io

import ezdxf
import pytest

from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.api.routes.export import _render_dxf


@pytest.fixture(scope="module")
def dxf_doc():
    cfg = PlotConfig(
        plot_y_extent=11.0,
        plot_x_extent=12.0,
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


def test_opening_blocks_are_defined_and_inserted(dxf_doc):
    assert "PF_DOOR" in dxf_doc.blocks
    assert "PF_WINDOW" in dxf_doc.blocks
    msp = dxf_doc.modelspace()
    door_inserts = [e for e in msp.query("INSERT") if e.dxf.name == "PF_DOOR"]
    window_inserts = [e for e in msp.query("INSERT") if e.dxf.name == "PF_WINDOW"]
    assert len(door_inserts) >= 1
    assert len(window_inserts) >= 1
    assert all(e.dxf.layer == "A-DOOR" for e in door_inserts)
    assert all(e.dxf.layer == "A-WINDOW" for e in window_inserts)


def test_no_loose_door_arcs_left_on_a_door_layer(dxf_doc):
    """Doors are now symbols: raw ARC entities on A-DOOR in modelspace mean the
    old free-floating drawing path is still active somewhere."""
    msp = dxf_doc.modelspace()
    assert not [e for e in msp.query("ARC") if e.dxf.layer == "A-DOOR"]
