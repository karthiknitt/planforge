from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class RevisionCreate(BaseModel):
    label: Optional[str] = None


class RevisionListItem(BaseModel):
    id: int
    project_id: str
    version: int
    label: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class RevisionDetail(BaseModel):
    id: int
    project_id: str
    version: int
    label: Optional[str]
    snapshot: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class RevisionCreateResponse(BaseModel):
    id: int
    version: int
    label: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
