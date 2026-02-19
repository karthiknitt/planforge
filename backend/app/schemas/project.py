from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Direction = Literal["N", "S", "E", "W"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    plot_length: float = Field(gt=0)
    plot_width: float = Field(gt=0)
    setback_front: float = Field(ge=0)
    setback_rear: float = Field(ge=0)
    setback_left: float = Field(ge=0)
    setback_right: float = Field(ge=0)
    road_side: Direction
    north_direction: Direction
    bhk: Literal[2, 3]
    toilets: int = Field(ge=1, le=4)
    parking: bool = False


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
