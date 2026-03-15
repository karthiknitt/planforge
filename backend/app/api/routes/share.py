"""Share-link routes.

POST /api/projects/{project_id}/share  — authenticated, generates a UUID token
GET  /api/share/{token}                — public, no auth required
"""

import json
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.models.project import Project
from app.schemas.layout import (
    ColumnOut,
    ComplianceOut,
    FloorPlanOut,
    GenerateResponse,
    LayoutOut,
    LayoutScoreOut,
    RoomOut,
)

router = APIRouter()


def _get_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    return x_user_id


def _to_float(v) -> float:
    return float(v) if isinstance(v, Decimal) else v


def _floor_plan_out(fp) -> FloorPlanOut:
    return FloorPlanOut(
        floor=fp.floor,
        floor_type=getattr(fp, "floor_type", "ground"),
        needs_mech_ventilation=getattr(fp, "needs_mech_ventilation", False),
        rooms=[
            RoomOut(
                id=r.id, name=r.name, type=r.type,
                x=r.x, y=r.y, width=r.width, depth=r.depth, area=r.area,
            )
            for r in fp.rooms
        ],
        columns=[ColumnOut(x=c.x, y=c.y) for c in fp.columns],
    )


def _build_generate_response(project_id: str, project: Project) -> GenerateResponse:
    custom_room_config = None
    raw_crc = getattr(project, "custom_room_config", None)
    if raw_crc:
        try:
            custom_room_config = json.loads(raw_crc)
        except Exception:
            custom_room_config = None

    plot_corners = None
    raw_corners = getattr(project, "plot_corners", None)
    if raw_corners:
        try:
            plot_corners = [tuple(pt) for pt in json.loads(raw_corners)]
        except Exception:
            plot_corners = None

    cfg = PlotConfig(
        plot_length=_to_float(project.plot_length),
        plot_width=_to_float(project.plot_width),
        setback_front=_to_float(project.setback_front),
        setback_rear=_to_float(project.setback_rear),
        setback_left=_to_float(project.setback_left),
        setback_right=_to_float(project.setback_right),
        num_bedrooms=project.num_bedrooms,
        toilets=project.toilets,
        parking=project.parking,
        city=getattr(project, "city", "other") or "other",
        vastu_enabled=getattr(project, "vastu_enabled", False) or False,
        road_width_m=_to_float(getattr(project, "road_width_m", 9.0) or 9.0),
        road_side=getattr(project, "road_side", "S") or "S",
        has_pooja=getattr(project, "has_pooja", False) or False,
        has_study=getattr(project, "has_study", False) or False,
        has_balcony=getattr(project, "has_balcony", False) or False,
        plot_shape=getattr(project, "plot_shape", "rectangular") or "rectangular",
        plot_front_width=_to_float(getattr(project, "plot_front_width", 0.0) or 0.0),
        plot_rear_width=_to_float(getattr(project, "plot_rear_width", 0.0) or 0.0),
        plot_side_offset=_to_float(getattr(project, "plot_side_offset", 0.0) or 0.0),
        plot_corners=plot_corners,
        num_floors=getattr(project, "num_floors", 1) or 1,
        has_stilt=getattr(project, "has_stilt", False) or False,
        has_basement=getattr(project, "has_basement", False) or False,
        custom_room_config=custom_room_config,
    )

    layouts = generate(cfg)

    return GenerateResponse(
        project_id=project_id,
        layouts=[
            LayoutOut(
                id=lay.id,
                name=lay.name,
                compliance=ComplianceOut(
                    passed=lay.compliance.passed,
                    violations=lay.compliance.violations,
                    warnings=lay.compliance.warnings,
                ),
                ground_floor=_floor_plan_out(lay.ground_floor),
                first_floor=_floor_plan_out(lay.first_floor),
                second_floor=_floor_plan_out(lay.second_floor) if lay.second_floor else None,
                basement_floor=_floor_plan_out(lay.basement_floor) if lay.basement_floor else None,
                score=LayoutScoreOut(
                    total=lay.score.total,
                    natural_light=lay.score.natural_light,
                    adjacency=lay.score.adjacency,
                    aspect_ratio=lay.score.aspect_ratio,
                    circulation=lay.score.circulation,
                    vastu=lay.score.vastu,
                ) if lay.score else None,
                space_notes=getattr(lay, "space_notes", []),
                auto_added_rooms=getattr(lay, "space_notes", []),
            )
            for lay in layouts
        ],
    )


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


class ShareTokenResponse(BaseModel):
    share_url: str
    token: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post(
    "/projects/{project_id}/share",
    response_model=ShareTokenResponse,
    status_code=status.HTTP_200_OK,
)
async def create_share_link(
    project_id: str,
    user_id: str = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
) -> ShareTokenResponse:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not project.share_token:
        project.share_token = str(uuid.uuid4())
        await db.commit()
        await db.refresh(project)

    return ShareTokenResponse(
        share_url=f"/share/{project.share_token}",
        token=project.share_token,
    )


@router.get("/share/{token}", response_model=ShareResponse)
async def get_shared_project(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> ShareResponse:
    result = await db.execute(select(Project).where(Project.share_token == token))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")

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

    generate_resp = _build_generate_response(project.id, project)

    return ShareResponse(project=project_info, generate=generate_resp)
