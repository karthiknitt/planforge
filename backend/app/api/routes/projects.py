import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter()


async def _get_plan_tier(user_id: str, db: AsyncSession) -> str:
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    return u.plan_tier if u else "free"


def get_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    """Extract authenticated user ID from request header set by the frontend."""
    return x_user_id


def _serialize_project_data(data: dict) -> dict:
    """Serialize list fields (custom_room_config) to JSON strings for DB storage."""
    crc = data.get("custom_room_config")
    if crc is not None and not isinstance(crc, str):
        # Pydantic v2 model instances → dicts → JSON string
        if isinstance(crc, list):
            serialized = []
            for item in crc:
                serialized.append(item if isinstance(item, dict) else item.model_dump())
            data["custom_room_config"] = json.dumps(serialized)
        else:
            data["custom_room_config"] = None
    return data


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Project:
    plan = await _get_plan_tier(user_id, db)
    if plan == "free":
        count_result = await db.execute(
            select(func.count(Project.id)).where(Project.user_id == user_id)
        )
        if count_result.scalar_one() >= 3:
            raise HTTPException(
                status_code=402,
                detail="Free plan limited to 3 projects. Upgrade to Basic or Pro.",
            )

    data = _serialize_project_data(body.model_dump())
    project = Project(
        id=str(uuid.uuid4()),
        user_id=user_id,
        **data,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    data = _serialize_project_data(body.model_dump(exclude_none=True))
    for field, value in data.items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[Project]:
    result = await db.execute(
        select(Project)
        .where(Project.user_id == user_id)
        .order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())
