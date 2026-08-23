from __future__ import annotations

from dataclasses import MISSING, dataclass, field
from typing import Literal

from app.engine.shapes import Rect, ShapeTemplate, parts_for, validate_shape

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
    # When set, this room is carved out of the interior of the room with this
    # id: its area is subtracted from the parent's usable area and its edges
    # become interior partitions. 22% of the reverse_engr corpus needs this
    # (an ensuite toilet sitting in a corner of a bedroom's rectangle).
    # Defaults to None, so every existing layout is unaffected.
    parent_id: str | None = None
    # Shape template: the room's footprint is the union of 1-3 axis-aligned
    # rectangles derived from its bounding box (x, y, width, depth) and this
    # template. "RECT" — the default — yields exactly one rectangle equal to
    # that bounding box, so every existing caller is unaffected.
    template: ShapeTemplate = "RECT"
    shape_ratio: float = 0.6
    # id of a room on the floor below that this room opens onto. A void has no
    # slab, no ceiling, and no carpet area — it is a hole, not a room (a
    # double-height living area or courtyard). Defaults to None, so every
    # existing layout is unaffected.
    void_over: str | None = None
    # Side letter -> bulge (sagitta as a fraction of the edge length; POSITIVE
    # bulge always bows AWAY from the room, outward across that side — never
    # into the room, regardless of which side letter). Purely a drawing
    # annotation: walls, adjacency, area and every solver constraint use the
    # straight chord. Kerala-style curved verandah fronts are the use case.
    # RECT-only (see __post_init__): a bounding-box side is only guaranteed
    # to sit on a real wall for the "RECT" template.
    edge_arcs: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_shape(self.template, self.shape_ratio)
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
        if self.edge_arcs and self.template != "RECT":
            raise ValueError(
                f"edge_arcs is only supported on template='RECT' rooms "
                f"(got template={self.template!r}); a non-RECT bounding-box "
                "side is not guaranteed to sit on a real wall, so drawing an "
                "arc there could slash across open space"
            )
        bad_arc_sides = set(self.edge_arcs) - _VALID_SIDES
        if bad_arc_sides:
            raise ValueError(
                f"edge_arcs contains unknown side(s) {sorted(bad_arc_sides)}; "
                f"expected a subset of {sorted(_VALID_SIDES)}"
            )
        arc_open_sides = set(self.edge_arcs) & set(self.open_sides)
        if arc_open_sides:
            raise ValueError(
                f"edge_arcs cannot target open side(s) {sorted(arc_open_sides)}; "
                "an arc requires a wall edge, and open_sides has no wall there"
            )
        for side, bulge in self.edge_arcs.items():
            if not -1.0 <= bulge <= 1.0:
                raise ValueError(
                    f"edge_arcs[{side!r}] = {bulge} is out of range; bulge is a "
                    "sagitta fraction of the edge length and must be in [-1, 1]"
                )

    @property
    def is_open(self) -> bool:
        return bool(self.open_sides)

    @property
    def is_void(self) -> bool:
        return self.void_over is not None

    @property
    def rects(self) -> tuple[Rect, ...]:
        """The room's occupied rectangles.

        A 1-tuple equal to the room's own rectangle for "RECT", so every
        caller that assumed one rectangle per room keeps working unchanged.
        """
        return parts_for(
            self.x, self.y, self.width, self.depth, self.template, self.shape_ratio
        )

    @property
    def area(self) -> float:
        """Occupied area — the union of the shape-template parts.

        Identical to `width * depth` for "RECT" rooms.
        """
        return round(sum(p.area for p in self.rects), 2)

    def net_area(self, children: list["Room"]) -> float:
        """Area minus any rooms carved out of this one.

        Both terms use `.area` (not `width * depth`) so a non-RECT parent or
        carve is measured by its part union rather than its bounding box — an
        L/T/U carve would otherwise over-subtract by up to half its bbox.
        """
        carved = sum(c.area for c in children if c.parent_id == self.id)
        return round(self.area - carved, 2)


@dataclass
class Column:
    x: float
    y: float


@dataclass
class OpeningOverride:
    """A user/AI delta against ONE derived opening, keyed by its deterministic
    `Opening.id` (Phase 7 Task 29).

    Overrides live on FloorPlan and are applied as a post-pass inside
    build_floor_drawing(), so derivation stays pure: same rooms + same
    overrides = same drawing. Any field left None keeps the derived value.
    An override whose id no longer exists (the room changed) degrades to a
    no-op recorded in FloorDrawing.diagnostics — never an exception.
    """

    opening_id: str
    along: float | None = None  # offset (m) from the host wall's low end
    width: float | None = None  # metres
    suppressed: bool = False  # remove the opening entirely


@dataclass
class AddedOpening:
    """A user/AI request for a NEW opening (Phase 7 Task 30).

    Overrides delta existing derived openings; they cannot create one. An
    AddedOpening names a wall by the two rooms it separates (or a room and
    the outside) and is resolved inside build_floor_drawing() BEFORE
    assign_opening_ids()/assign_opening_marks(), so it receives identity and
    a schedule mark through the same deterministic passes as derived
    openings — and an OpeningOverride may target it. A spec whose rooms no
    longer share a wall degrades to a diagnostic no-op, never an exception.
    """

    kind: str  # "door" | "window"
    room_a: str
    room_b: str  # second room id, or the literal "outside"
    along: float | None = (
        None  # offset (m) from the shared span's low end; None = centred
    )
    width: float | None = None  # metres; None: 0.9 for doors, 1.2 for windows
    side: str | None = None  # "N"|"S"|"E"|"W" — only meaningful for room_b=="outside"


@dataclass
class FloorPlan:
    floor: int  # -1=basement, 0=stilt/ground, 1=first, 2=second
    floor_type: str = "ground"  # "basement"|"stilt"|"ground"|"first"|"second"
    rooms: list[Room] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    needs_mech_ventilation: bool = False
    # Optional with a default, per the Global Constraints: every persisted
    # FloorPlan deserialises unchanged when this is absent.
    opening_overrides: list[OpeningOverride] = field(default_factory=list)
    added_openings: list[AddedOpening] = field(default_factory=list)


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
    # Graded 0–100 Vastu compliance (vastu.vastu_layout_score) over the final
    # post-fill geometry of every floor, or None when cfg.vastu_enabled is False.
    # Ranking already consumes this through scorer._score_vastu; it is stored so
    # the API/UI can show the number that drove the ranking.
    vastu_score: float | None = None
    space_notes: list[str] = field(default_factory=list)  # auto-fill notes for user


@dataclass(init=False)
class PlotConfig:
    plot_x_extent: float  # x-extent (left -> right, road frontage), metres.
    plot_y_extent: float  # y-extent (front/road -> rear), metres. NOT the longer axis.
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
    # Clockwise degrees from the plot's +y axis to true north. `None` means the
    # orientation was never surveyed, so Vastu falls back to deriving it from
    # `road_side` — which is what every plot did before this field existed. An
    # explicit 0.0 is NOT the same thing: it asserts that +y *is* true north and
    # overrides `road_side`. Set it for the 24% of plots whose north arrow is not
    # axis-aligned; those must not be snapped to the nearest cardinal direction.
    north_angle_deg: float | None = None
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
    # Opt-in: let the solver give eligible rooms a non-RECT shape template, so
    # two rooms can interlock (an L's notch filled by its neighbour). Off by
    # default — every room then comes out `template="RECT"` and the CP-SAT
    # model is exactly the one that existed before shape templates.
    allow_shape_templates: bool = False
    # Rectilinear PLOT envelope — INDEPENDENT of `allow_shape_templates` above,
    # which is about ROOM shape. "RECT" (the default) is today's plain
    # rectangular site and changes nothing at all: the solver's notch pass
    # returns immediately and the CP-SAT model is byte-identical. "L"/"T"/"U"
    # cut a `notch_width` x `notch_depth` rectangle out of the plot's
    # REAR-RIGHT corner; that land is off-plot, so the solver forbids room
    # parts from entering it (it used to place rooms there and delete them
    # afterwards, silently losing programme).
    plot_template: ShapeTemplate = "RECT"
    notch_width: float = 0.0  # metres, x-extent of the cutout
    notch_depth: float = 0.0  # metres, y-extent of the cutout
    # Programme flags from the wizard (Task 25): one room per type is appended
    # to the solved programme. Empty by default, so every existing caller is
    # unaffected. Types must exist in room_specs.json (courtyard, verandah,
    # terrace fall back to the utility spec otherwise).
    required_types: frozenset[str] = frozenset()
    # When True the parking room's road-facing edge ("S" in plot coordinates,
    # regardless of the true-north angle) carries no wall.
    open_parking: bool = False

    def __init__(
        self,
        *,
        plot_x_extent: float | None = None,
        plot_y_extent: float | None = None,
        plot_width: float | None = None,
        plot_length: float | None = None,
        **kwargs,
    ) -> None:
        """Construct with the new primary names, accepting the legacy
        `plot_width`/`plot_length` aliases for one release so persisted configs
        and in-flight API payloads keep working."""
        if plot_width is not None:
            if plot_x_extent is not None and plot_x_extent != plot_width:
                raise ValueError("plot_x_extent and plot_width disagree")
            plot_x_extent = plot_width
        if plot_length is not None:
            if plot_y_extent is not None and plot_y_extent != plot_length:
                raise ValueError("plot_y_extent and plot_length disagree")
            plot_y_extent = plot_length
        if plot_x_extent is None or plot_y_extent is None:
            raise TypeError("plot_x_extent and plot_y_extent are required")
        kwargs["plot_x_extent"] = plot_x_extent
        kwargs["plot_y_extent"] = plot_y_extent
        fields = type(self).__dataclass_fields__
        unknown = set(kwargs) - set(fields)
        if unknown:
            raise TypeError(
                "PlotConfig got unexpected keyword argument(s): "
                + ", ".join(sorted(unknown))
            )
        for name, f in fields.items():
            if name in kwargs:
                value = kwargs[name]
            else:
                value = f.default if f.default is not MISSING else None
            object.__setattr__(self, name, value)

    @property
    def plot_width(self) -> float:
        """Deprecated alias for plot_x_extent."""
        return self.plot_x_extent

    @plot_width.setter
    def plot_width(self, v: float) -> None:
        self.plot_x_extent = v

    @property
    def plot_length(self) -> float:
        """Deprecated alias for plot_y_extent — NOT the longer axis."""
        return self.plot_y_extent

    @plot_length.setter
    def plot_length(self, v: float) -> None:
        self.plot_y_extent = v

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
