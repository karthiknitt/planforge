"""
CAD element geometry classes for PlanForge.

These are pure data containers used by both the PDF renderer and DXF exporter.
All coordinates are in metres (plot coordinate system).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.engine.standards import get_opening_standards


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

    def to_dict(self) -> dict:
        from dataclasses import asdict

        payload = _rounded(asdict(self))
        payload["version"] = 1
        return payload


@dataclass
class DoorSymbol:
    """Door defined by hinge point, width, wall side, and swing direction."""

    hinge_x: float
    hinge_y: float
    width: float  # metres (default 0.9 m)
    angle_start: float  # angle of door leaf at rest (degrees)
    swing_cw: bool = True  # clockwise swing


@dataclass
class WindowSymbol:
    """Window defined by centre point and width, on a given wall."""

    cx: float
    cy: float
    width: float  # metres (default 1.2 m)
    is_horizontal: bool = (
        True  # True = window on horizontal wall (N/S), False = vertical (E/W)
    )


@dataclass
class ColumnMarker:
    """300×300 mm structural column."""

    cx: float
    cy: float
    size: float = 0.3  # metres


@dataclass
class GridLine:
    """Structural grid line."""

    x1: float
    y1: float
    x2: float
    y2: float
    label: str


@dataclass
class DimensionLine:
    """IS-compliant linear dimension."""

    x1: float  # start of measured extent
    y1: float
    x2: float  # end of measured extent
    y2: float
    offset: float  # offset from the measured line (positive = away from building)
    text: str  # e.g. "3.05 m"
    is_horizontal: bool = True


@dataclass
class CADDrawing:
    """Collection of all CAD elements for one floor."""

    walls: list[WallSegment] = field(default_factory=list)
    doors: list[DoorSymbol] = field(default_factory=list)
    windows: list[WindowSymbol] = field(default_factory=list)
    columns: list[ColumnMarker] = field(default_factory=list)
    grid_lines: list[GridLine] = field(default_factory=list)
    dimensions: list[DimensionLine] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def build_dimensions(
    plot_width: float,
    plot_length: float,
    buildable_x: float,
    buildable_y: float,
    buildable_w: float,
    buildable_d: float,
    offset: float = 1.2,
) -> list[DimensionLine]:
    """Generate overall plot dimension lines."""
    dims: list[DimensionLine] = []

    # Overall width dimension (bottom)
    dims.append(
        DimensionLine(
            x1=0,
            y1=0,
            x2=plot_width,
            y2=0,
            offset=-offset,
            text=f"{plot_width:.2f} m",
            is_horizontal=True,
        )
    )
    # Overall depth dimension (left side)
    dims.append(
        DimensionLine(
            x1=0,
            y1=0,
            x2=0,
            y2=plot_length,
            offset=-offset,
            text=f"{plot_length:.2f} m",
            is_horizontal=False,
        )
    )
    # Buildable width dimension
    dims.append(
        DimensionLine(
            x1=buildable_x,
            y1=buildable_y + buildable_d,
            x2=buildable_x + buildable_w,
            y2=buildable_y + buildable_d,
            offset=offset * 0.7,
            text=f"{buildable_w:.2f} m",
            is_horizontal=True,
        )
    )

    return dims


def build_columns(rooms) -> list[ColumnMarker]:
    """Place 300×300 column markers at room intersections."""
    xs = sorted({r.x for r in rooms} | {r.x + r.width for r in rooms})
    ys = sorted({r.y for r in rooms} | {r.y + r.depth for r in rooms})
    return [ColumnMarker(cx=round(x, 3), cy=round(y, 3)) for x in xs for y in ys]


def build_windows(
    rooms,
    buildable_x: float,
    buildable_y: float,
    buildable_w: float,
    buildable_d: float,
) -> list[WindowSymbol]:
    """Add windows on exterior-facing room walls for habitable rooms."""
    windows: list[WindowSymbol] = []
    habitable = {"living", "bedroom", "kitchen", "study", "dining"}
    bx2 = buildable_x + buildable_w
    by2 = buildable_y + buildable_d

    for room in rooms:
        if room.type not in habitable:
            continue
        cx = room.x + room.width / 2
        cy = room.y + room.depth / 2
        _std = get_opening_standards()
        win_w = min(_std.window_width_m, room.width * _std.window_max_room_fraction)

        # Check each face of the room against building exterior
        if abs(room.y - buildable_y) < 0.05:  # front wall
            windows.append(
                WindowSymbol(cx=cx, cy=buildable_y, width=win_w, is_horizontal=True)
            )
        elif abs(room.y + room.depth - by2) < 0.05:  # rear wall
            windows.append(WindowSymbol(cx=cx, cy=by2, width=win_w, is_horizontal=True))
        if abs(room.x - buildable_x) < 0.05:  # left wall
            windows.append(
                WindowSymbol(cx=buildable_x, cy=cy, width=win_w, is_horizontal=False)
            )
        elif abs(room.x + room.width - bx2) < 0.05:  # right wall
            windows.append(
                WindowSymbol(cx=bx2, cy=cy, width=win_w, is_horizontal=False)
            )

    return windows
