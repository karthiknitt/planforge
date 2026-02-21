from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Direction = Literal["N", "S", "E", "W"]

CITIES = Literal["bangalore", "chennai", "delhi", "hyderabad", "pune", "other"]

FloorPreference = Literal["basement", "stilt", "gf", "ff", "sf", "either"]


class CustomRoomSpec(BaseModel):
    """User-defined room added via the advanced room config interface."""
    type: str
    name: str | None = None
    min_area_sqm: float | None = None
    floor_preference: FloorPreference = "either"
    mandatory: bool = True


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    plot_length: float = Field(ge=5.0, description="Plot length in metres (minimum 5 m)")
    plot_width: float = Field(ge=5.0, description="Plot width in metres (minimum 5 m)")
    setback_front: float = Field(ge=0)
    setback_rear: float = Field(ge=0)
    setback_left: float = Field(ge=0)
    setback_right: float = Field(ge=0)
    road_side: Direction
    north_direction: Direction
    num_bedrooms: int = Field(ge=1, le=6, description="Number of bedrooms (1–6)")
    toilets: int = Field(ge=1, le=6)
    parking: bool = False
    city: str = "other"
    vastu_enabled: bool = False
    road_width_m: float = Field(default=9.0, ge=3.0, le=60.0)
    has_pooja: bool = False
    has_study: bool = False
    has_balcony: bool = False
    plot_shape: str = "rectangular"
    plot_front_width: float | None = None
    plot_rear_width: float | None = None
    plot_side_offset: float | None = None
    # Multi-floor (Phase E)
    num_floors: int = Field(default=1, ge=1, le=3, description="Number of floors: 1=G, 2=G+1, 3=G+2")
    has_stilt: bool = False
    has_basement: bool = False
    # Arbitrary rooms (Phase C)
    custom_room_config: list[CustomRoomSpec] | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    plot_length: float | None = Field(default=None, ge=5.0)
    plot_width: float | None = Field(default=None, ge=5.0)
    setback_front: float | None = Field(default=None, ge=0)
    setback_rear: float | None = Field(default=None, ge=0)
    setback_left: float | None = Field(default=None, ge=0)
    setback_right: float | None = Field(default=None, ge=0)
    road_side: Direction | None = None
    north_direction: Direction | None = None
    num_bedrooms: int | None = Field(default=None, ge=1, le=6)
    toilets: int | None = Field(default=None, ge=1, le=6)
    parking: bool | None = None
    city: str | None = None
    vastu_enabled: bool | None = None
    road_width_m: float | None = Field(default=None, ge=3.0, le=60.0)
    has_pooja: bool | None = None
    has_study: bool | None = None
    has_balcony: bool | None = None
    plot_shape: str | None = None
    plot_front_width: float | None = None
    plot_rear_width: float | None = None
    plot_side_offset: float | None = None
    num_floors: int | None = Field(default=None, ge=1, le=3)
    has_stilt: bool | None = None
    has_basement: bool | None = None
    custom_room_config: list[CustomRoomSpec] | None = None


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
    plot_shape: str = "rectangular"
    plot_front_width: float | None = None
    plot_rear_width: float | None = None
    plot_side_offset: float | None = None
    num_floors: int = 1
    has_stilt: bool = False
    has_basement: bool = False
    custom_room_config: str | None = None   # raw JSON string from DB
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
