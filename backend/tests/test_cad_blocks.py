"""Unit tests for cad_blocks.py — PF_* opening block definitions/inserts."""

import ezdxf

from app.engine.cad_blocks import (
    DOOR_BLOCK,
    define_opening_blocks,
    insert_door,
)


def _doc_with_door(mirror: bool):
    doc = ezdxf.new("R2010", setup=True)
    define_opening_blocks(doc)
    msp = doc.modelspace()
    insert_door(msp, 1.0, 2.0, 30.0, z=0.5, mirror=mirror)
    return next(e for e in msp.query("INSERT") if e.dxf.name == DOOR_BLOCK)


def test_insert_door_default_is_not_mirrored():
    ins = _doc_with_door(mirror=False)
    assert ins.dxf.rotation == 30.0
    assert ins.dxf.yscale == 1.0


def test_insert_door_mirror_flips_yscale():
    ins = _doc_with_door(mirror=True)
    assert ins.dxf.rotation == 30.0
    assert ins.dxf.yscale == -1.0


def test_insert_door_uses_hinge_point_and_layer():
    ins = _doc_with_door(mirror=False)
    assert ins.dxf.insert == (1.0, 2.0, 0.5)
    assert ins.dxf.layer == "A-DOOR"
