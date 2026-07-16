"""Persistence layer for generated/edited layouts — the single source of truth.

Also owns the engine-Layout -> LayoutOut serialization that was previously
copy-pasted in generate.py, share.py and revisions.py.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.engine.generator import generate
from app.engine.models import (
    Column,
    ComplianceResult,
    FloorPlan,
    Layout,
    LayoutScore,
    Room,
)
from app.engine.plan_geometry import build_floor_drawing
from app.models.layout import StoredLayout
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
from app.services.plot_config import plot_config_from_project


def floor_plan_out(fp: Any) -> FloorPlanOut:
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


def layout_out_from_engine(lay: Any) -> LayoutOut:
    return LayoutOut(
        id=lay.id,
        name=lay.name,
        compliance=ComplianceOut(
            passed=lay.compliance.passed,
            violations=lay.compliance.violations,
            warnings=lay.compliance.warnings,
        ),
        ground_floor=floor_plan_out(lay.ground_floor),
        first_floor=floor_plan_out(lay.first_floor),
        second_floor=floor_plan_out(lay.second_floor) if lay.second_floor else None,
        basement_floor=floor_plan_out(lay.basement_floor)
        if lay.basement_floor
        else None,
        score=LayoutScoreOut(
            total=lay.score.total,
            natural_light=lay.score.natural_light,
            adjacency=lay.score.adjacency,
            aspect_ratio=lay.score.aspect_ratio,
            circulation=lay.score.circulation,
            vastu=lay.score.vastu,
            grid_regularity=lay.score.grid_regularity,
        )
        if lay.score
        else None,
        space_notes=getattr(lay, "space_notes", []),
        auto_added_rooms=getattr(lay, "space_notes", []),
    )


async def get_stored_layouts(project_id: str, db: AsyncSession) -> list[StoredLayout]:
    result = await db.execute(
        select(StoredLayout)
        .where(StoredLayout.project_id == project_id)
        .order_by(StoredLayout.created_at, StoredLayout.layout_key)
    )
    return list(result.scalars().all())


async def get_stored_layout(
    project_id: str, layout_key: str, db: AsyncSession
) -> StoredLayout | None:
    result = await db.execute(
        select(StoredLayout).where(
            StoredLayout.project_id == project_id,
            StoredLayout.layout_key == layout_key,
        )
    )
    return result.scalar_one_or_none()


async def regenerate_and_store(
    project: Project, db: AsyncSession
) -> list[StoredLayout]:
    """Run the solver and replace the project's stored layouts.

    Destructive for edited layouts by design — callers snapshot a revision
    first (generate.py does).
    """
    cfg = plot_config_from_project(project)
    layouts = generate(cfg)

    await db.execute(delete(StoredLayout).where(StoredLayout.project_id == project.id))
    stored: list[StoredLayout] = []
    for lay in layouts:
        row = StoredLayout(
            project_id=project.id,
            layout_key=lay.id,
            source="solver",
            geometry=layout_out_from_engine(lay).model_dump(),
        )
        db.add(row)
        stored.append(row)
    await db.commit()
    return stored


async def get_or_generate_layouts(
    project: Project, db: AsyncSession
) -> list[StoredLayout]:
    stored = await get_stored_layouts(project.id, db)
    if stored:
        return stored
    return await regenerate_and_store(project, db)


async def save_edited_geometry(
    stored: StoredLayout, geometry: dict, db: AsyncSession
) -> StoredLayout:
    stored.geometry = geometry
    # Callers often mutate the same dict instance in place — SQLAlchemy's
    # change tracking misses that, so force the column dirty.
    flag_modified(stored, "geometry")
    stored.source = "edited"
    await db.commit()
    await db.refresh(stored)
    return stored


def to_generate_response(
    project: Project, stored: list[StoredLayout]
) -> GenerateResponse:
    """Build the API response, attaching each floor's canonical drawing.

    `drawing` is recomputed here (not read from the stored geometry) so an
    edited layout's drawing always matches its current room positions —
    the same engine_layout_from_geometry() reconstruction render.py/export.py
    already use, never a stale snapshot from generation time.
    """
    cfg = plot_config_from_project(project)
    layouts = []
    for row in stored:
        layout_out = LayoutOut(**row.geometry)
        engine_layout = engine_layout_from_geometry(row.geometry)
        for floor_out, engine_fp in (
            (layout_out.ground_floor, engine_layout.ground_floor),
            (layout_out.first_floor, engine_layout.first_floor),
            (layout_out.second_floor, engine_layout.second_floor),
            (layout_out.basement_floor, engine_layout.basement_floor),
        ):
            if floor_out is not None and engine_fp is not None and engine_fp.rooms:
                floor_out.drawing = build_floor_drawing(engine_fp, cfg).to_dict()
        layouts.append(layout_out)
    return GenerateResponse(project_id=project.id, layouts=layouts)


def _floor_from_dict(
    fp: dict | None, default_floor: int, ftype: str
) -> FloorPlan | None:
    if not fp:
        return None
    return FloorPlan(
        floor=fp.get("floor", default_floor),
        floor_type=fp.get("floor_type", ftype),
        rooms=[
            Room(
                id=r["id"],
                name=r["name"],
                type=r["type"],
                x=r["x"],
                y=r["y"],
                width=r["width"],
                depth=r["depth"],
            )
            for r in fp.get("rooms", [])
        ],
        columns=[Column(x=c["x"], y=c["y"]) for c in fp.get("columns", [])],
        needs_mech_ventilation=fp.get("needs_mech_ventilation", False),
    )


def engine_layout_from_geometry(g: dict) -> Layout:
    """Rebuild the engine dataclasses from a stored geometry dict so the
    PDF/DXF/BOQ pipelines can consume persisted (possibly edited) layouts."""
    comp = g.get("compliance") or {}
    score = g.get("score")
    return Layout(
        id=g["id"],
        name=g.get("name", g["id"]),
        ground_floor=_floor_from_dict(g.get("ground_floor"), 0, "ground"),
        first_floor=_floor_from_dict(g.get("first_floor"), 1, "first"),
        second_floor=_floor_from_dict(g.get("second_floor"), 2, "second"),
        basement_floor=_floor_from_dict(g.get("basement_floor"), -1, "basement"),
        compliance=ComplianceResult(
            passed=comp.get("passed", True),
            violations=comp.get("violations", []),
            warnings=comp.get("warnings", []),
        ),
        score=LayoutScore(
            total=score["total"],
            natural_light=score["natural_light"],
            adjacency=score["adjacency"],
            aspect_ratio=score["aspect_ratio"],
            circulation=score["circulation"],
            vastu=score["vastu"],
            grid_regularity=score.get("grid_regularity", 100.0),
        )
        if score
        else None,
        space_notes=g.get("space_notes", []),
    )
