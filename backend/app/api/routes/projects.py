import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.project import Project
from app.models.team import TeamMember
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter()


async def _get_user(user_id: str, db: AsyncSession) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _get_plan_tier(user_id: str, db: AsyncSession) -> str:
    u = await _get_user(user_id, db)
    return u.plan_tier if u else "free"


async def _get_user_team_ids(user_id: str, db: AsyncSession) -> list[int]:
    """Return all team IDs the user belongs to (any role)."""
    result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user_id)
    )
    return [row[0] for row in result.all()]


async def _can_access_project(project: Project, user_id: str, db: AsyncSession) -> bool:
    """Return True if user owns the project or is a member of the project's team."""
    if project.user_id == user_id:
        return True
    if project.team_id is not None:
        team_ids = await _get_user_team_ids(user_id, db)
        return project.team_id in team_ids
    return False


def get_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    """Extract authenticated user ID from request header set by the frontend."""
    return x_user_id


def _serialize_project_data(data: dict) -> dict:
    """Serialize list fields (custom_room_config, plot_corners) to JSON strings for DB storage."""
    crc = data.get("custom_room_config")
    if crc is not None and not isinstance(crc, str):
        if isinstance(crc, list):
            serialized = []
            for item in crc:
                serialized.append(item if isinstance(item, dict) else item.model_dump())
            data["custom_room_config"] = json.dumps(serialized)
        else:
            data["custom_room_config"] = None

    corners = data.get("plot_corners")
    if corners is not None and not isinstance(corners, str):
        data["plot_corners"] = json.dumps(corners) if isinstance(corners, list) else None

    return data


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Project:
    user = await _get_user(user_id, db)
    plan = user.plan_tier if user else "free"
    if plan == "free":
        count_result = await db.execute(
            select(func.count(Project.id)).where(Project.user_id == user_id)
        )
        project_count = count_result.scalar_one()
        credits = user.project_credits if user else 0
        if project_count >= 3 and credits <= 0:
            raise HTTPException(
                status_code=402,
                detail="Purchase credits or upgrade to Basic",
            )
        if project_count >= 3 and credits > 0:
            # Deduct one credit for this project
            user.project_credits = credits - 1

    data = _serialize_project_data(body.model_dump())

    # 4BHK minimum plot area guard
    num_bedrooms = data.get("num_bedrooms", 2)
    if num_bedrooms >= 4:
        plot_length = data.get("plot_length", 0) or 0
        plot_width = data.get("plot_width", 0) or 0
        if float(plot_length) * float(plot_width) < 200:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="4BHK requires minimum 200 sqm plot area",
            )

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
    if not await _can_access_project(project, user_id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    data = _serialize_project_data(body.model_dump(exclude_none=True))

    # 4BHK minimum plot area guard (check merged values: patch may update bedrooms or dimensions)
    merged_bedrooms = data.get("num_bedrooms", project.num_bedrooms)
    if merged_bedrooms >= 4:
        merged_length = float(data.get("plot_length") or project.plot_length or 0)
        merged_width = float(data.get("plot_width") or project.plot_width or 0)
        if merged_length * merged_width < 200:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="4BHK requires minimum 200 sqm plot area",
            )

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
    team_ids = await _get_user_team_ids(user_id, db)

    if team_ids:
        result = await db.execute(
            select(Project)
            .where(
                or_(
                    Project.user_id == user_id,
                    Project.team_id.in_(team_ids),
                )
            )
            .order_by(Project.created_at.desc())
        )
    else:
        result = await db.execute(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.created_at.desc())
        )
    return list(result.scalars().all())


# ── Annotation routes ─────────────────────────────────────────────────────────

class AnnotationItem(BaseModel):
    room_id: str
    room_name: str
    note: str
    x: float
    y: float


@router.get("/projects/{project_id}/annotations", response_model=dict[str, Any])
async def get_annotations(
    project_id: str,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not await _can_access_project(project, user_id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return project.annotations or {}


@router.put("/projects/{project_id}/annotations", response_model=dict[str, Any])
async def put_annotations(
    project_id: str,
    body: dict[str, Any],
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not await _can_access_project(project, user_id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    project.annotations = body
    await db.commit()
    await db.refresh(project)
    return project.annotations or {}
