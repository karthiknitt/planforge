"""
Revision history routes for project versioning.

Snapshot format (stored in snapshot column):
    {
      "project_id": "...",
      "layouts": [ <LayoutOut JSON> ... ]
    }
This is the full GenerateResponse payload, making each revision self-contained
for restore without re-running the solver.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.models.project import Project
from app.models.revision import ProjectRevision
from app.services import layout_store
from app.services.access import get_accessible_project
from app.schemas.revision import (
    RevisionCreate,
    RevisionCreateResponse,
    RevisionDetail,
    RevisionListItem,
)

router = APIRouter()


async def _require_project(project_id: str, user_id: str, db: AsyncSession) -> Project:
    return await get_accessible_project(project_id, user_id, db)


async def _next_version(project_id: str, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.max(ProjectRevision.version)).where(
            ProjectRevision.project_id == project_id
        )
    )
    current_max = result.scalar_one_or_none()
    return (current_max or 0) + 1


def _to_float(v: Any) -> float:
    return float(v) if isinstance(v, Decimal) else v


async def save_auto_revision(
    db: AsyncSession,
    project: Project,
    label_prefix: str = "Auto-save",
) -> ProjectRevision | None:
    """
    Generate layouts for `project` and persist a revision snapshot.
    Returns the saved revision, or None if generation fails.
    Called internally before destructive operations (e.g. re-generate).
    """
    try:
        stored = await layout_store.get_or_generate_layouts(project, db)
        snapshot = layout_store.to_generate_response(project.id, stored).model_dump()
    except Exception:
        return None

    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M")
    next_ver = await _next_version(project.id, db)
    revision = ProjectRevision(
        project_id=project.id,
        version=next_ver,
        label=f"{label_prefix} #{ts}",
        snapshot=snapshot,
    )
    db.add(revision)
    await db.commit()
    await db.refresh(revision)
    return revision


# ── GET /api/projects/{id}/revisions ────────────────────────────────────────


@router.get(
    "/projects/{project_id}/revisions",
    response_model=list[RevisionListItem],
)
async def list_revisions(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectRevision]:
    await _require_project(project_id, user_id, db)

    result = await db.execute(
        select(ProjectRevision)
        .where(ProjectRevision.project_id == project_id)
        .order_by(ProjectRevision.version.desc())
        .limit(10)
    )
    return list(result.scalars().all())


# ── POST /api/projects/{id}/revisions ───────────────────────────────────────


@router.post(
    "/projects/{project_id}/revisions",
    response_model=RevisionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_revision(
    project_id: str,
    body: RevisionCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectRevision:
    project = await _require_project(project_id, user_id, db)

    try:
        stored = await layout_store.get_or_generate_layouts(project, db)
        snapshot = layout_store.to_generate_response(project_id, stored).model_dump()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate snapshot: {exc}",
        ) from exc

    next_ver = await _next_version(project_id, db)
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M")
    label = body.label or f"Snapshot #{ts}"

    revision = ProjectRevision(
        project_id=project_id,
        version=next_ver,
        label=label,
        snapshot=snapshot,
    )
    db.add(revision)
    await db.commit()
    await db.refresh(revision)
    return revision


# ── GET /api/projects/{id}/revisions/{version} ──────────────────────────────


@router.get(
    "/projects/{project_id}/revisions/{version}",
    response_model=RevisionDetail,
)
async def get_revision(
    project_id: str,
    version: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectRevision:
    await _require_project(project_id, user_id, db)

    result = await db.execute(
        select(ProjectRevision).where(
            ProjectRevision.project_id == project_id,
            ProjectRevision.version == version,
        )
    )
    revision = result.scalar_one_or_none()
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revision v{version} not found for this project",
        )
    return revision


# ── DELETE /api/projects/{id}/revisions/{version} ───────────────────────────


@router.delete(
    "/projects/{project_id}/revisions/{version}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_revision(
    project_id: str,
    version: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _require_project(project_id, user_id, db)

    result = await db.execute(
        select(ProjectRevision).where(
            ProjectRevision.project_id == project_id,
            ProjectRevision.version == version,
        )
    )
    revision = result.scalar_one_or_none()
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revision v{version} not found for this project",
        )
    await db.delete(revision)
    await db.commit()
