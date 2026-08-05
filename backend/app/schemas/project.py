from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


Direction = Literal["N", "S", "E", "W"]

CITIES = Literal["bangalore", "chennai", "delhi", "hyderabad", "pune", "other"]

FloorPreference = Literal["basement", "stilt", "gf", "ff", "sf", "either"]

PlotShape = Literal["rectangular", "trapezoid", "quadrilateral", "l_shaped"]

CutoutCorner = Literal["NE", "NW", "SE", "SW"]


def _shoelace_area(pts: list[tuple[float, float]]) -> float:
    n = len(pts)
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


class CustomRoomSpec(BaseModel):
    """User-defined room added via the advanced room config interface."""

    type: str
    name: str | None = None
    min_area_sqm: float | None = None
    floor_preference: FloorPreference = "either"
    mandatory: bool = True


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    plot_length: float = Field(
        ge=5.0,
        le=100.0,
        allow_inf_nan=False,
        description="Plot length in metres (5–100 m, residential)",
    )
    plot_width: float = Field(
        ge=5.0, le=100.0, allow_inf_nan=False, description="Plot width in metres"
    )
    setback_front: float = Field(ge=0, le=20.0, allow_inf_nan=False)
    setback_rear: float = Field(ge=0, le=20.0, allow_inf_nan=False)
    setback_left: float = Field(ge=0, le=20.0, allow_inf_nan=False)
    setback_right: float = Field(ge=0, le=20.0, allow_inf_nan=False)
    road_side: Direction
    north_direction: Direction
    num_bedrooms: int = Field(ge=1, le=6, description="Number of bedrooms (1–6)")
    toilets: int = Field(ge=1, le=6)
    parking: bool = False
    city: str = "other"
    vastu_enabled: bool = False
    road_width_m: float = Field(default=9.0, ge=3.0, le=60.0, allow_inf_nan=False)
    has_pooja: bool = False
    has_study: bool = False
    has_balcony: bool = False
    attached_toilets: bool = Field(
        default=False,
        description=(
            "Attach an en-suite toilet to every bedroom automatically; "
            "the `toilets` field then means COMMON toilets only"
        ),
    )
    plot_shape: PlotShape = "rectangular"
    plot_front_width: float | None = Field(
        default=None, gt=0, le=100.0, allow_inf_nan=False
    )
    plot_rear_width: float | None = Field(
        default=None, gt=0, le=100.0, allow_inf_nan=False
    )
    plot_side_offset: float | None = Field(
        default=None, ge=0, le=100.0, allow_inf_nan=False
    )
    plot_corners: list[tuple[float, float]] | None = None  # quadrilateral 4-corner list
    # L-shaped plot cutout
    cutout_corner: CutoutCorner = "NE"
    cutout_width: float = Field(default=0.0, ge=0, le=100.0, allow_inf_nan=False)
    cutout_height: float = Field(default=0.0, ge=0, le=100.0, allow_inf_nan=False)
    # Multi-floor (Phase E)
    num_floors: int = Field(
        default=1, ge=1, le=3, description="Number of floors: 1=G, 2=G+1, 3=G+2"
    )
    has_stilt: bool = False
    has_basement: bool = False
    # Municipality / building authority selector
    municipality: str | None = Field(default=None, max_length=100)
    # Arbitrary rooms (Phase C)
    custom_room_config: list[CustomRoomSpec] | None = Field(default=None, max_length=20)
    # Team assignment (optional — assign project to team)
    team_id: int | None = None

    @model_validator(mode="after")
    def _geometry_consistency(self) -> "ProjectCreate":
        if self.setback_left + self.setback_right >= self.plot_width:
            raise ValueError("Left + right setbacks consume the entire plot width")
        if self.setback_front + self.setback_rear >= self.plot_length:
            raise ValueError("Front + rear setbacks consume the entire plot length")
        if self.plot_shape == "l_shaped":
            if not (0 < self.cutout_width < self.plot_width) or not (
                0 < self.cutout_height < self.plot_length
            ):
                raise ValueError(
                    "L-shaped plot needs a cutout larger than 0 and smaller than the plot"
                )
        if self.plot_shape == "trapezoid":
            if not self.plot_front_width or not self.plot_rear_width:
                raise ValueError(
                    "Trapezoid plot requires positive plot_front_width and plot_rear_width"
                )
        if self.plot_shape == "quadrilateral":
            pts = self.plot_corners
            if not pts or len(pts) != 4:
                raise ValueError("Quadrilateral plot requires exactly 4 corners")
            if _shoelace_area(pts) < 25.0:  # matches the 5 m x 5 m rectangular minimum
                raise ValueError("Quadrilateral corners are degenerate or too small")
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    plot_length: float | None = Field(
        default=None, ge=5.0, le=100.0, allow_inf_nan=False
    )
    plot_width: float | None = Field(
        default=None, ge=5.0, le=100.0, allow_inf_nan=False
    )
    setback_front: float | None = Field(
        default=None, ge=0, le=20.0, allow_inf_nan=False
    )
    setback_rear: float | None = Field(default=None, ge=0, le=20.0, allow_inf_nan=False)
    setback_left: float | None = Field(default=None, ge=0, le=20.0, allow_inf_nan=False)
    setback_right: float | None = Field(
        default=None, ge=0, le=20.0, allow_inf_nan=False
    )
    road_side: Direction | None = None
    north_direction: Direction | None = None
    num_bedrooms: int | None = Field(default=None, ge=1, le=6)
    toilets: int | None = Field(default=None, ge=1, le=6)
    parking: bool | None = None
    city: str | None = None
    vastu_enabled: bool | None = None
    road_width_m: float | None = Field(
        default=None, ge=3.0, le=60.0, allow_inf_nan=False
    )
    has_pooja: bool | None = None
    has_study: bool | None = None
    has_balcony: bool | None = None
    attached_toilets: bool | None = None
    plot_shape: PlotShape | None = None
    plot_front_width: float | None = Field(
        default=None, gt=0, le=100.0, allow_inf_nan=False
    )
    plot_rear_width: float | None = Field(
        default=None, gt=0, le=100.0, allow_inf_nan=False
    )
    plot_side_offset: float | None = Field(
        default=None, ge=0, le=100.0, allow_inf_nan=False
    )
    plot_corners: list[tuple[float, float]] | None = None
    cutout_corner: CutoutCorner | None = None
    cutout_width: float | None = Field(
        default=None, ge=0, le=100.0, allow_inf_nan=False
    )
    cutout_height: float | None = Field(
        default=None, ge=0, le=100.0, allow_inf_nan=False
    )
    num_floors: int | None = Field(default=None, ge=1, le=3)
    has_stilt: bool | None = None
    has_basement: bool | None = None
    municipality: str | None = None
    custom_room_config: list[CustomRoomSpec] | None = None
    team_id: int | None = None


class ProjectRead(BaseModel):
    id: str
    user_id: str
    name: str
    plot_length: float
    plot_width: float
    setback_front: float
    setback_rear: float
    setback_left: float
    setback_right: float
    road_side: str
    north_direction: str
    num_bedrooms: int
    toilets: int
    parking: bool
    city: str
    vastu_enabled: bool
    road_width_m: float
    has_pooja: bool
    has_study: bool
    has_balcony: bool
    attached_toilets: bool = False
    plot_shape: str = "rectangular"
    plot_front_width: float | None = None
    plot_rear_width: float | None = None
    plot_side_offset: float | None = None
    plot_corners: str | None = None  # raw JSON string from DB: [[x,y], ...]
    cutout_corner: str = "NE"
    cutout_width: float = 0.0
    cutout_height: float = 0.0
    num_floors: int = 1
    has_stilt: bool = False
    has_basement: bool = False
    municipality: str | None = None
    custom_room_config: str | None = None  # raw JSON string from DB
    team_id: int | None = None
    created_at: datetime
    updated_at: datetime
    # Computed by list_projects — True if at least one row exists for this
    # project in the `layouts` table (i.e. generation has actually run and
    # produced a stored layout, regardless of the sync or async job path).
    # Not a mapped column, so it's only populated where the route sets it.
    has_layouts: bool = False

    model_config = {"from_attributes": True}
