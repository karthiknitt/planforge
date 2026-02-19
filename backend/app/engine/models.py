from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RoomType = Literal["living", "bedroom", "kitchen", "toilet", "staircase", "parking", "utility"]


@dataclass
class Room:
    id: str
    name: str
    type: RoomType
    x: float    # left edge in plot coordinates (metres from plot left)
    y: float    # front edge in plot coordinates (metres from road/front)
    width: float  # metres (x direction)
    depth: float  # metres (y direction, away from road)

    @property
    def area(self) -> float:
        return round(self.width * self.depth, 2)


@dataclass
class Column:
    x: float
    y: float


@dataclass
class FloorPlan:
    floor: int  # 0 = ground, 1 = first
    rooms: list[Room] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)


@dataclass
class ComplianceResult:
    passed: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Layout:
    id: str          # "A", "B", "C"
    name: str
    ground_floor: FloorPlan
    first_floor: FloorPlan
    compliance: ComplianceResult


@dataclass
class PlotConfig:
    plot_length: float
    plot_width: float
    setback_front: float
    setback_rear: float
    setback_left: float
    setback_right: float
    bhk: int
    toilets: int
    parking: bool


@dataclass
class FloorPlate:
    """Usable internal floor plate after setbacks + external wall thickness."""
    ox: float    # left edge of internal space (in plot coordinates)
    oy: float    # front edge of internal space (in plot coordinates)
    width: float  # internal usable width
    depth: float  # internal usable depth
