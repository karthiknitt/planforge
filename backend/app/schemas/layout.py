from pydantic import BaseModel, computed_field


class RoomOut(BaseModel):
    id: str
    name: str
    type: str
    x: float
    y: float
    width: float
    depth: float
    area: float


class ColumnOut(BaseModel):
    x: float
    y: float


class FloorPlanOut(BaseModel):
    floor: int
    rooms: list[RoomOut]
    columns: list[ColumnOut]


class ComplianceOut(BaseModel):
    passed: bool
    violations: list[str]
    warnings: list[str]


class LayoutOut(BaseModel):
    id: str
    name: str
    compliance: ComplianceOut
    ground_floor: FloorPlanOut
    first_floor: FloorPlanOut


class GenerateResponse(BaseModel):
    project_id: str
    layouts: list[LayoutOut]
