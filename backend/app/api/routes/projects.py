import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter()


def get_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    """Extract authenticated user ID from request header set by the frontend."""
    return x_user_id


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        user_id=user_id,
        **body.model_dump(),
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

    for field, value in body.model_dump(exclude_none=True).items():
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
