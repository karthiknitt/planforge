"""
CAD element geometry classes for PlanForge.

These are pure data containers used by both the PDF renderer and DXF exporter.
All coordinates are in metres (plot coordinate system).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class WallSegment:
    """A wall segment defined by two endpoints and its thickness.

    In `plan_geometry`-derived drawings the coordinates are the wall
    CENTRELINE; legacy renderers still construct these at room-edge
    coordinates (5 positional args, kind defaulting to "internal").
    """

    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float  # metres
    kind: str = "internal"  # "external" | "internal"

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


@dataclass
class WallJunction:
    """Point where two or more non-collinear wall centrelines meet."""

    x: float
    y: float
    degree: int  # distinct incident arm directions (2=corner, 3=T, 4=cross)


@dataclass
class Opening:
    """A door/window/ventilator cut into a wall, centred at (cx, cy).

    (cx, cy) sits ON the wall centreline; `width` runs along the wall.
    Door fields describe the hinge end and which room the leaf swings into.
    """

    kind: str  # "door" | "window" | "ventilator"
    cx: float
    cy: float
    width: float
    is_horizontal: bool  # True = on a horizontal wall (width runs along x)
    wall_thickness: float
    hinge_x: float = 0.0
    hinge_y: float = 0.0
    swing_into_room_id: str = ""
    swing_cw: bool = True
    is_main: bool = False  # main entrance door (MD) on the road-facing wall


@dataclass
class LabelBox:
    """Room label with pre-fitted text lines (never truncated — a label that
    cannot fit inside its room moves outside with a leader)."""

    room_id: str
    cx: float
    cy: float
    lines: list[str]
    font_pt: float
    leader: tuple[float, float] | None = None  # target point when outside
    rotated: bool = False  # render at 90 deg (slim vertical rooms)


@dataclass
class DimChainEntry:
    start: float  # along-axis position (m)
    end: float
    text: str  # formatted ft-in


@dataclass
class DimChain:
    side: str  # "bottom" | "top" | "left" | "right"
    level: int  # 0=room chain, 1=overall, 2=plot/setback chain
    coord: float  # cross-axis lane position (m, plot coords)
    entries: list[DimChainEntry] = field(default_factory=list)


@dataclass
class StairGeometry:
    room_id: str
    treads: list[tuple[float, float, float, float]]
    break_line: tuple[float, float, float, float]
    arrow: tuple[float, float, float, float]  # tail -> head
    up_label_xy: tuple[float, float]
    tread_count: int


def _rounded(node):
    if isinstance(node, float):
        return round(node, 4)
    if isinstance(node, (list, tuple)):
        return [_rounded(v) for v in node]
    if isinstance(node, dict):
        return {k: _rounded(v) for k, v in node.items()}
    return node


@dataclass
class FloorDrawing:
    """Complete canonical drawing for one floor — the single source every
    renderer (PDF/DXF/SVG) projects."""

    floor: int
    walls: list[WallSegment]
    openings: list[Opening]
    columns: list[ColumnMarker]
    junctions: list[WallJunction]
    dim_chains: list[DimChain]
    labels: list[LabelBox]
    stair: StairGeometry | None
    bounds: tuple[float, float, float, float]  # buildable bbox
    diagnostics: list[str] = field(default_factory=list)  # placement problems
    entrance_not_on_ground_floor: bool = False

    def to_dict(self) -> dict:
        from dataclasses import asdict

        payload = _rounded(asdict(self))
        payload["version"] = 1
        return payload


@dataclass
class ColumnMarker:
    """300×300 mm structural column."""

    cx: float
    cy: float
    size: float = 0.3  # metres
