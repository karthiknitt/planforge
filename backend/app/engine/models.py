from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RoomType = Literal[
    "living",
    "bedroom",
    "master_bedroom",
    "kitchen",
    "toilet",  # combined WC + wash basin + shower
    "wc_only",  # WC + wash basin only (no shower/bath)
    "bathroom_master",  # master en-suite: WC + basin + shower (+ optional tub)
    "staircase",
    "parking",  # generic — prefer parking_4w / parking_2w for new layouts
    "parking_4w",  # car parking (min 2.5 m × 5.0 m per NBC)
    "parking_2w",  # 2-wheeler bay (1.0 m × 2.5 m per bike)
    "utility",
    "pooja",
    "study",
    "balcony",
    "dining",
    "servant_quarter",
    "gym",
    "home_office",
    "store_room",
    "garage",
    "passage",
    # hand-authored / editor data only — the solver never generates these three
    "foyer",  # entry vestibule
    "courtyard",  # interior open-to-sky court (light-well)
    "wardrobe",  # walk-in closet
    # open / semi-open programme, evidenced by the reverse_engr corpus
    "terrace",  # open or semi-covered roof terrace
    "garden",  # landscaped ground area inside the plot
    "verandah",  # covered open-sided edge space (osari / otla / attole)
    "seating",  # outdoor seating pocket / conversation pit
    "open_to_sky",  # skylight void / open-to-sky cut-out
    "duct",  # service shaft
    "washbasin_nook",  # wash-basin alcove outside a toilet
]

_VALID_SIDES = frozenset({"N", "S", "E", "W"})


@dataclass
class Room:
    id: str
    name: str
    type: RoomType
    x: float  # left edge in plot coordinates (metres from plot left)
    y: float  # front edge in plot coordinates (metres from road/front)
    width: float  # metres (x direction)
    depth: float  # metres (y direction, away from road)
    # Plot-relative edges carrying no wall. "S" = y edge nearest the road,
    # "N" = far y edge, "W" = low x edge, "E" = high x edge. Empty means a
    # normal fully-enclosed room — the default, so existing layouts are
    # unaffected.
    open_sides: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        bad = set(self.open_sides) - _VALID_SIDES
        if bad:
            raise ValueError(
                f"open_sides contains unknown side(s) {sorted(bad)}; "
                f"expected a subset of {sorted(_VALID_SIDES)}"
            )
        if len(self.open_sides) == 4:
            raise ValueError(
                "open_sides cannot contain all four sides — a room with no "
                "walls has no derivable footprint; use a plot-level feature"
            )

    @property
    def is_open(self) -> bool:
        return bool(self.open_sides)

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
    floor_type: str = "ground"  # "basement"|"stilt"|"ground"|"first"|"second"
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
    id: str  # "A", "B", "C", "D", "E", "F" or solver-generated
    name: str
    ground_floor: FloorPlan
    first_floor: FloorPlan
    compliance: ComplianceResult
    second_floor: FloorPlan | None = None
    basement_floor: FloorPlan | None = None
    score: LayoutScore | None = None
    space_notes: list[str] = field(default_factory=list)  # auto-fill notes for user


@dataclass
class PlotConfig:
    plot_length: float  # y-extent (front/road -> rear), metres. NOT the longer axis.
    plot_width: float  # x-extent (left -> right, road frontage), metres.
    setback_front: float
    setback_rear: float
    setback_left: float
    setback_right: float
    num_bedrooms: int  # 1–4
    toilets: int
    parking: bool
    city: str = "other"
    vastu_enabled: bool = False
    road_width_m: float = 9.0
    road_side: str = "S"
    has_pooja: bool = False
    has_study: bool = False
    has_balcony: bool = False
    attached_toilets: bool = False
    plot_shape: str = (
        "rectangular"  # "rectangular" | "trapezoid" | "quadrilateral" | "l_shaped"
    )
    plot_front_width: float = 0.0  # front edge width (m), trapezoid only
    plot_rear_width: float = 0.0  # rear edge width (m), trapezoid only
    plot_side_offset: float = 0.0  # rear offset from front left (m)
    plot_corners: list[tuple[float, float]] | None = (
        None  # 4 pts CCW: FL, FR, RR, RL (metres)
    )
    # L-shaped plot cutout (rectangular corner removed)
    cutout_corner: str = "NE"  # "NE" | "NW" | "SE" | "SW"
    cutout_width: float = 0.0  # metres — width of cutout
    cutout_height: float = 0.0  # metres — height of cutout
    # Multi-floor
    num_floors: int = 1  # 1=G, 2=G+1, 3=G+2
    has_stilt: bool = False  # floor 0 is stilt (parking only)
    has_basement: bool = False  # add basement floor (-1)
    # Municipality / building authority (e.g. "Chennai (CMDA)") — for per-city rule loading
    municipality: str | None = None
    # Custom room config (arbitrary rooms, Phase C)
    custom_room_config: list | None = None  # list of dicts from CustomRoomSpec
    # En-suite toilets: one attached bath per bedroom, additive to `toilets`
    # (which then counts COMMON toilets only)
    attached_toilets: bool = False

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
    floor_preference: str  # "basement"|"stilt"|"gf"|"ff"|"sf"|"either"|"all"
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
    # defaults keep pre-existing stored layouts (no key) rehydrating cleanly
    grid_regularity: float = 100.0
    toilet_placement: float = 100.0


@dataclass
class FloorPlate:
    """Usable internal floor plate after setbacks + external wall thickness."""

    ox: float  # left edge of internal space (in plot coordinates)
    oy: float  # front edge of internal space (in plot coordinates)
    width: float  # internal usable width
    depth: float  # internal usable depth
