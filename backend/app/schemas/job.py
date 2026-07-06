from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    kind: str
    layout_key: str | None = None
    status: str
    stage: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime
