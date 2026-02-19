from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Direction = Literal["N", "S", "E", "W"]


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
    bhk: Literal[2, 3]
    toilets: int = Field(ge=1, le=4)
    parking: bool = False


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
    bhk: Literal[2, 3] | None = None
    toilets: int | None = Field(default=None, ge=1, le=4)
    parking: bool | None = None


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
    bhk: int
    toilets: int
    parking: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
