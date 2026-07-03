"""Share-link routes.

POST /api/projects/{project_id}/share       — authenticated, generates a UUID token
GET  /api/share/{token}                     — public, no auth required
POST /api/share/{token}/approve             — public (client action)
POST /api/share/{token}/request-changes     — public (client action)
GET  /api/projects/{project_id}/approval-status — authenticated, engineer polls
"""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.models.project import Project
from app.schemas.layout import GenerateResponse
from app.services import layout_store
from app.services.access import get_accessible_project

router = APIRouter()


def _to_float(v) -> float:
    return float(v) if isinstance(v, Decimal) else v


async def _build_generate_response(
    project: Project, db: AsyncSession
) -> GenerateResponse:
    stored = await layout_store.get_or_generate_layouts(project, db)
    return layout_store.to_generate_response(project.id, stored)


# ── Public response schema ─────────────────────────────────────────────────────


class ShareProjectInfo(BaseModel):
    id: str
    name: str
    plot_length: float
    plot_width: float
    road_side: str
    north_direction: str
    num_bedrooms: int
    toilets: int
    parking: bool
    plot_shape: str


class ShareResponse(BaseModel):
    project: ShareProjectInfo
    generate: GenerateResponse
    approval_status: str | None = None
    approval_note: str | None = None
    approval_selected_layouts: list[str] | None = None
    approval_updated_at: datetime | None = None


class ShareTokenResponse(BaseModel):
    share_url: str
    token: str


class ApproveBody(BaseModel):
    selected_layout_ids: list[str] = Field(default_factory=list, max_length=10)


class RequestChangesBody(BaseModel):
    note: str = Field(default="", max_length=2000)


class ApprovalStatusResponse(BaseModel):
    project_id: str
    approval_status: str | None
    approval_note: str | None
    approval_selected_layouts: list[str] | None
    approval_updated_at: datetime | None


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/share",
    response_model=ShareTokenResponse,
    status_code=status.HTTP_200_OK,
)
async def create_share_link(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ShareTokenResponse:
    project = await get_accessible_project(project_id, user_id, db)

    if not project.share_token:
        project.share_token = str(uuid.uuid4())
        await db.commit()
        await db.refresh(project)

    return ShareTokenResponse(
        share_url=f"/share/{project.share_token}",
        token=project.share_token,
    )


@router.delete("/projects/{project_id}/share", status_code=status.HTTP_200_OK)
async def revoke_share_link(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke the share link — the old token stops resolving immediately.

    A new POST /share afterwards mints a fresh token.
    """
    project = await get_accessible_project(project_id, user_id, db)
    project.share_token = None
    await db.commit()
    return {"status": "revoked"}


@router.get("/share/{token}", response_model=ShareResponse)
async def get_shared_project(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> ShareResponse:
    result = await db.execute(select(Project).where(Project.share_token == token))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found"
        )

    project_info = ShareProjectInfo(
        id=project.id,
        name=project.name,
        plot_length=_to_float(project.plot_length),
        plot_width=_to_float(project.plot_width),
        road_side=project.road_side,
        north_direction=project.north_direction,
        num_bedrooms=project.num_bedrooms,
        toilets=project.toilets,
        parking=project.parking,
        plot_shape=getattr(project, "plot_shape", "rectangular") or "rectangular",
    )

    generate_resp = await _build_generate_response(project, db)

    raw_sel = getattr(project, "approval_selected_layouts", None)
    selected = json.loads(raw_sel) if raw_sel else None

    return ShareResponse(
        project=project_info,
        generate=generate_resp,
        approval_status=getattr(project, "approval_status", None),
        approval_note=getattr(project, "approval_note", None),
        approval_selected_layouts=selected,
        approval_updated_at=getattr(project, "approval_updated_at", None),
    )


@router.post("/share/{token}/approve", status_code=status.HTTP_200_OK)
async def approve_shared_project(
    token: str,
    body: ApproveBody,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(Project).where(Project.share_token == token))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found"
        )

    project.approval_status = "approved"
    project.approval_note = None
    project.approval_selected_layouts = (
        json.dumps(body.selected_layout_ids) if body.selected_layout_ids else None
    )
    project.approval_updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "approved"}


@router.post("/share/{token}/request-changes", status_code=status.HTTP_200_OK)
async def request_changes_shared_project(
    token: str,
    body: RequestChangesBody,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(Project).where(Project.share_token == token))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found"
        )

    project.approval_status = "changes_requested"
    project.approval_note = body.note or None
    project.approval_updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "changes_requested"}


@router.get(
    "/projects/{project_id}/approval-status",
    response_model=ApprovalStatusResponse,
)
async def get_approval_status(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ApprovalStatusResponse:
    project = await get_accessible_project(project_id, user_id, db)

    raw_sel = getattr(project, "approval_selected_layouts", None)
    return ApprovalStatusResponse(
        project_id=project_id,
        approval_status=getattr(project, "approval_status", None),
        approval_note=getattr(project, "approval_note", None),
        approval_selected_layouts=json.loads(raw_sel) if raw_sel else None,
        approval_updated_at=getattr(project, "approval_updated_at", None),
    )
