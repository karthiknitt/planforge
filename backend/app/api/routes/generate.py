from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.engine.generator import generate
from app.models.project import Project
from app.services.plot_config import plot_config_from_project
from app.schemas.layout import (
    ColumnOut,
    ComplianceOut,
    FloorPlanOut,
    GenerateResponse,
    LayoutOut,
    LayoutScoreOut,
    RoomOut,
)
from app.api.routes.revisions import save_auto_revision

router = APIRouter()


def _to_float(v) -> float:
    return float(v) if isinstance(v, Decimal) else v


def _floor_plan_out(fp) -> FloorPlanOut:
    return FloorPlanOut(
        floor=fp.floor,
        floor_type=getattr(fp, "floor_type", "ground"),
        needs_mech_ventilation=getattr(fp, "needs_mech_ventilation", False),
        rooms=[
            RoomOut(
                id=r.id,
                name=r.name,
                type=r.type,
                x=r.x,
                y=r.y,
                width=r.width,
                depth=r.depth,
                area=r.area,
            )
            for r in fp.rooms
        ],
        columns=[ColumnOut(x=c.x, y=c.y) for c in fp.columns],
    )


@router.get("/projects/{project_id}/generate", response_model=GenerateResponse)
async def generate_layouts(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    cfg = plot_config_from_project(project)

    layouts = generate(cfg)

    # Auto-snapshot the current state before delivering new results.
    # Fire-and-forget: failure must not block the response.
    try:
        await save_auto_revision(
            db, project, label_prefix="Auto-save before generation"
        )
    except Exception:
        pass

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
                second_floor=_floor_plan_out(lay.second_floor)
                if lay.second_floor
                else None,
                basement_floor=_floor_plan_out(lay.basement_floor)
                if lay.basement_floor
                else None,
                score=LayoutScoreOut(
                    total=lay.score.total,
                    natural_light=lay.score.natural_light,
                    adjacency=lay.score.adjacency,
                    aspect_ratio=lay.score.aspect_ratio,
                    circulation=lay.score.circulation,
                    vastu=lay.score.vastu,
                )
                if lay.score
                else None,
                space_notes=getattr(lay, "space_notes", []),
                auto_added_rooms=getattr(lay, "space_notes", []),
            )
            for lay in layouts
        ],
    )
