"""Reusable DXF block definitions for openings (drafted-class symbols).

Blocks are defined once per document at their standard size (Task 13 config);
inserts place them by base point + rotation. Base point = the opening's start
point along the wall (hinge for doors, sill start for windows/ventilators),
symbol drawn along +X.
"""

from app.engine.standards import get_opening_standards

DOOR_BLOCK = "PF_DOOR"
WINDOW_BLOCK = "PF_WINDOW"
VENT_BLOCK = "PF_VENT"


def define_opening_blocks(doc) -> None:
    std = get_opening_standards()

    if DOOR_BLOCK not in doc.blocks:
        blk = doc.blocks.new(name=DOOR_BLOCK)
        w = std.door_width_m
        # door leaf, opened 90°: from hinge (0,0) up to (0, w)
        blk.add_line((0.0, 0.0), (0.0, w))
        # swing arc from the leaf tip to the closed position (w, 0)
        blk.add_arc(center=(0.0, 0.0), radius=w, start_angle=0.0, end_angle=90.0)

    if WINDOW_BLOCK not in doc.blocks:
        blk = doc.blocks.new(name=WINDOW_BLOCK)
        w = std.window_width_m
        t = 0.23  # external wall thickness — window symbol spans the wall
        for frac in (0.0, 0.5, 1.0):  # 3 parallel lines: faces + glazing line
            y = -t / 2 + t * frac
            blk.add_line((0.0, y), (w, y))
        blk.add_line((0.0, -t / 2), (0.0, t / 2))
        blk.add_line((w, -t / 2), (w, t / 2))

    if VENT_BLOCK not in doc.blocks:
        blk = doc.blocks.new(name=VENT_BLOCK)
        w = std.ventilator_width_m
        t = 0.23
        blk.add_line((0.0, -t / 2), (w, -t / 2))
        blk.add_line((0.0, t / 2), (w, t / 2))
        blk.add_line((0.0, 0.0), (w, 0.0))


def _insert(
    msp,
    name: str,
    layer: str,
    x: float,
    y: float,
    rotation_deg: float,
    z: float,
    mirror: bool = False,
) -> None:
    dxfattribs = {"layer": layer, "rotation": rotation_deg}
    if mirror:
        dxfattribs["yscale"] = -1.0
    msp.add_blockref(name, insert=(x, y, z), dxfattribs=dxfattribs)


def insert_door(
    msp, x: float, y: float, rotation_deg: float, z: float = 0.0, mirror: bool = False
) -> None:
    """Insert PF_DOOR at its hinge point.

    The block swings CCW from local +X (closed) to local +Y (open). Mirror
    about local X (``yscale=-1``) to render a clockwise swing — pass
    ``mirror=opening.swing_cw`` from the canonical FloorDrawing opening.
    """
    _insert(msp, DOOR_BLOCK, "A-DOOR", x, y, rotation_deg, z, mirror=mirror)


def insert_window(msp, x: float, y: float, rotation_deg: float, z: float = 0.0) -> None:
    _insert(msp, WINDOW_BLOCK, "A-WINDOW", x, y, rotation_deg, z)


def insert_ventilator(
    msp, x: float, y: float, rotation_deg: float, z: float = 0.0
) -> None:
    _insert(msp, VENT_BLOCK, "A-VENTILATOR", x, y, rotation_deg, z)
