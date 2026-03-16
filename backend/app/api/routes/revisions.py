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

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.engine.generator import generate
from app.engine.models import PlotConfig
from app.models.project import Project
from app.models.revision import ProjectRevision
from app.schemas.layout import (
    ColumnOut,
    ComplianceOut,
    FloorPlanOut,
    GenerateResponse,
    LayoutOut,
    LayoutScoreOut,
    RoomOut,
)
from app.schemas.revision import (
    RevisionCreate,
    RevisionCreateResponse,
    RevisionDetail,
    RevisionListItem,
)

router = APIRouter()


def _get_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    return x_user_id


async def _require_project(
    project_id: str, user_id: str, db: AsyncSession
) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


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


def _floor_plan_out(fp: Any) -> FloorPlanOut:
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


def _build_snapshot(project_id: str, layouts: list[Any]) -> dict[str, Any]:
    """Build the GenerateResponse-shaped dict to store as snapshot JSON."""
    layout_dicts = []
    for lay in layouts:
        lo = LayoutOut(
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
        layout_dicts.append(lo.model_dump())
    return GenerateResponse(project_id=project_id, layouts=layout_dicts).model_dump()  # type: ignore[arg-type]


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
    import json

    try:
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
            cutout_corner=getattr(project, "cutout_corner", None),
            cutout_width=_to_float(getattr(project, "cutout_width_m", 0.0) or 0.0),
            cutout_height=_to_float(getattr(project, "cutout_height_m", 0.0) or 0.0),
            num_floors=getattr(project, "num_floors", 1) or 1,
            has_stilt=getattr(project, "has_stilt", False) or False,
            has_basement=getattr(project, "has_basement", False) or False,
            custom_room_config=custom_room_config,
        )

        layouts = generate(cfg)
        snapshot = _build_snapshot(project.id, layouts)
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
    user_id: str = Depends(_get_user_id),
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
    user_id: str = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectRevision:
    project = await _require_project(project_id, user_id, db)

    import json

    try:
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
            cutout_corner=getattr(project, "cutout_corner", None),
            cutout_width=_to_float(getattr(project, "cutout_width_m", 0.0) or 0.0),
            cutout_height=_to_float(getattr(project, "cutout_height_m", 0.0) or 0.0),
            num_floors=getattr(project, "num_floors", 1) or 1,
            has_stilt=getattr(project, "has_stilt", False) or False,
            has_basement=getattr(project, "has_basement", False) or False,
            custom_room_config=custom_room_config,
        )
        layouts = generate(cfg)
        snapshot = _build_snapshot(project_id, layouts)
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
    user_id: str = Depends(_get_user_id),
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
    user_id: str = Depends(_get_user_id),
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
