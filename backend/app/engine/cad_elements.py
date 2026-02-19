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
    """A wall segment defined by two endpoints and its thickness."""
    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float  # metres

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


@dataclass
class DoorSymbol:
    """Door defined by hinge point, width, wall side, and swing direction."""
    hinge_x: float
    hinge_y: float
    width: float      # metres (default 0.9 m)
    angle_start: float  # angle of door leaf at rest (degrees)
    swing_cw: bool = True  # clockwise swing


@dataclass
class WindowSymbol:
    """Window defined by centre point and width, on a given wall."""
    cx: float
    cy: float
    width: float     # metres (default 1.2 m)
    is_horizontal: bool = True  # True = window on horizontal wall (N/S), False = vertical (E/W)


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
    x1: float   # start of measured extent
    y1: float
    x2: float   # end of measured extent
    y2: float
    offset: float   # offset from the measured line (positive = away from building)
    text: str       # e.g. "3.05 m"
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

def build_walls_from_rooms(rooms, ewt: float, iwt: float,
                            buildable_x: float, buildable_y: float,
                            buildable_w: float, buildable_d: float) -> list[WallSegment]:
    """
    Derive wall segments from room geometry.
    External walls follow the buildable boundary; internal walls sit between rooms.
    """
    walls: list[WallSegment] = []

    # External boundary walls (4 sides of the building footprint)
    bx2 = buildable_x + buildable_w
    by2 = buildable_y + buildable_d
    walls.append(WallSegment(buildable_x, buildable_y, bx2, buildable_y, ewt))   # front
    walls.append(WallSegment(bx2, buildable_y, bx2, by2, ewt))                   # right
    walls.append(WallSegment(bx2, by2, buildable_x, by2, ewt))                   # rear
    walls.append(WallSegment(buildable_x, by2, buildable_x, buildable_y, ewt))   # left

    # Internal walls: collect unique vertical and horizontal room boundaries
    xs = sorted({r.x for r in rooms} | {r.x + r.width for r in rooms})
    ys = sorted({r.y for r in rooms} | {r.y + r.depth for r in rooms})

    for x in xs:
        if abs(x - buildable_x) < 0.01 or abs(x - (buildable_x + buildable_w)) < 0.01:
            continue  # skip external boundary
        walls.append(WallSegment(x, buildable_y, x, buildable_y + buildable_d, iwt))

    for y in ys:
        if abs(y - buildable_y) < 0.01 or abs(y - (buildable_y + buildable_d)) < 0.01:
            continue  # skip external boundary
        walls.append(WallSegment(buildable_x, y, buildable_x + buildable_w, y, iwt))

    return walls


def build_dimensions(plot_width: float, plot_length: float,
                     buildable_x: float, buildable_y: float,
                     buildable_w: float, buildable_d: float,
                     offset: float = 1.2) -> list[DimensionLine]:
    """Generate overall plot dimension lines."""
    dims: list[DimensionLine] = []

    # Overall width dimension (bottom)
    dims.append(DimensionLine(
        x1=0, y1=0, x2=plot_width, y2=0,
        offset=-offset,
        text=f"{plot_width:.2f} m",
        is_horizontal=True,
    ))
    # Overall depth dimension (left side)
    dims.append(DimensionLine(
        x1=0, y1=0, x2=0, y2=plot_length,
        offset=-offset,
        text=f"{plot_length:.2f} m",
        is_horizontal=False,
    ))
    # Buildable width dimension
    dims.append(DimensionLine(
        x1=buildable_x, y1=buildable_y + buildable_d,
        x2=buildable_x + buildable_w, y2=buildable_y + buildable_d,
        offset=offset * 0.7,
        text=f"{buildable_w:.2f} m",
        is_horizontal=True,
    ))

    return dims


def build_columns(rooms) -> list[ColumnMarker]:
    """Place 300×300 column markers at room intersections."""
    xs = sorted({r.x for r in rooms} | {r.x + r.width for r in rooms})
    ys = sorted({r.y for r in rooms} | {r.y + r.depth for r in rooms})
    return [ColumnMarker(cx=round(x, 3), cy=round(y, 3)) for x in xs for y in ys]


def build_windows(rooms, buildable_x: float, buildable_y: float,
                  buildable_w: float, buildable_d: float) -> list[WindowSymbol]:
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
        win_w = min(1.2, room.width * 0.6)

        # Check each face of the room against building exterior
        if abs(room.y - buildable_y) < 0.05:           # front wall
            windows.append(WindowSymbol(cx=cx, cy=buildable_y, width=win_w, is_horizontal=True))
        elif abs(room.y + room.depth - by2) < 0.05:    # rear wall
            windows.append(WindowSymbol(cx=cx, cy=by2, width=win_w, is_horizontal=True))
        if abs(room.x - buildable_x) < 0.05:           # left wall
            windows.append(WindowSymbol(cx=buildable_x, cy=cy, width=win_w, is_horizontal=False))
        elif abs(room.x + room.width - bx2) < 0.05:    # right wall
            windows.append(WindowSymbol(cx=bx2, cy=cy, width=win_w, is_horizontal=False))

    return windows
