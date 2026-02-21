from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RoomType = Literal[
    "living", "bedroom", "master_bedroom", "kitchen", "toilet", "staircase",
    "parking", "utility", "pooja", "study", "balcony", "dining",
    "servant_quarter", "gym", "home_office", "store_room", "garage", "passage",
]


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
    floor: int  # -1=basement, 0=stilt/ground, 1=first, 2=second
    floor_type: str = "ground"   # "basement"|"stilt"|"ground"|"first"|"second"
    rooms: list[Room] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    needs_mech_ventilation: bool = False


@dataclass
class ComplianceResult:
    passed: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Layout:
    id: str          # "A", "B", "C", "D", "E", "F" or solver-generated
    name: str
    ground_floor: FloorPlan
    first_floor: FloorPlan
    compliance: ComplianceResult
    second_floor: FloorPlan | None = None
    basement_floor: FloorPlan | None = None
    score: LayoutScore | None = None


@dataclass
class PlotConfig:
    plot_length: float
    plot_width: float
    setback_front: float
    setback_rear: float
    setback_left: float
    setback_right: float
    num_bedrooms: int   # 1–4
    toilets: int
    parking: bool
    city: str = "other"
    vastu_enabled: bool = False
    road_width_m: float = 9.0
    road_side: str = "S"
    has_pooja: bool = False
    has_study: bool = False
    has_balcony: bool = False
    plot_shape: str = "rectangular"       # "rectangular" | "trapezoid"
    plot_front_width: float = 0.0         # front edge width (m), trapezoid only
    plot_rear_width: float = 0.0          # rear edge width (m), trapezoid only
    plot_side_offset: float = 0.0         # rear offset from front left (m)
    # Multi-floor
    num_floors: int = 1                   # 1=G, 2=G+1, 3=G+2
    has_stilt: bool = False               # floor 0 is stilt (parking only)
    has_basement: bool = False            # add basement floor (-1)
    # Custom room config (arbitrary rooms, Phase C)
    custom_room_config: list | None = None  # list of dicts from CustomRoomSpec

    @property
    def bhk(self) -> int:
        """Backward-compat alias."""
        return self.num_bedrooms


@dataclass
class RoomSpec:
    """Specification for a single room used by the CP-SAT solver."""
    id: str
    name: str
    type: str
    min_area_sqm: float
    max_area_sqm: float
    min_width_m: float
    max_width_m: float
    floor_preference: str   # "basement"|"stilt"|"gf"|"ff"|"sf"|"either"|"all"
    mandatory: bool
    fixed_position: tuple[float, float] | None = None


@dataclass
class LayoutScore:
    """Scoring breakdown for a generated layout (0–100)."""
    total: float
    natural_light: float
    adjacency: float
    aspect_ratio: float
    circulation: float
    vastu: float


@dataclass
class FloorPlate:
    """Usable internal floor plate after setbacks + external wall thickness."""
    ox: float    # left edge of internal space (in plot coordinates)
    oy: float    # front edge of internal space (in plot coordinates)
    width: float  # internal usable width
    depth: float  # internal usable depth
