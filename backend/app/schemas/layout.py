from pydantic import BaseModel


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
    floor_type: str = "ground"
    rooms: list[RoomOut]
    columns: list[ColumnOut]
    needs_mech_ventilation: bool = False


class ComplianceOut(BaseModel):
    passed: bool
    violations: list[str]
    warnings: list[str]


class LayoutScoreOut(BaseModel):
    total: float
    natural_light: float
    adjacency: float
    aspect_ratio: float
    circulation: float
    vastu: float


class LayoutOut(BaseModel):
    id: str
    name: str
    compliance: ComplianceOut
    ground_floor: FloorPlanOut
    first_floor: FloorPlanOut
    second_floor: FloorPlanOut | None = None
    basement_floor: FloorPlanOut | None = None
    score: LayoutScoreOut | None = None
    space_notes: list[str] = []
    auto_added_rooms: list[str] = []


class GenerateResponse(BaseModel):
    project_id: str
    layouts: list[LayoutOut]


class BOQItemOut(BaseModel):
    item: str
    description: str
    quantity: float
    unit: str
    rate: float = 0.0
    amount: float = 0.0


class BOQOut(BaseModel):
    project_name: str
    layout_id: str
    city: str = "Generic"
    rates_note: str = "Generic rates (2026)"
    total_cost: float = 0.0
    generic_total_cost: float | None = None
    cost_difference: float | None = None
    items: list[BOQItemOut] = []
