"""Structural design of a generated layout via the StructAgent API.

POST /projects/{project_id}/structural  — extract the column grid from the
stored layout, call structapi's /v1/design/building, and return the
clause-referenced result (checks, member designs, quantities, optional PDF).
Deterministic: same layout + inputs => same design.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.engine.structural_grid import extract_grid
from app.services import (
    layout_store,
    structagent_client,
    structural_loop,
    structural_store,
)
from app.services.access import get_accessible_project

router = APIRouter()

#: IS 1893:2016 Annex E seismic zones for supported municipalities.
#: Default zone III is conservative for most of peninsular India.
CITY_SEISMIC_ZONE = {
    "chennai": "III",
    "bengaluru": "II",
    "bangalore": "II",
    "hyderabad": "II",
    "pune": "III",
    "mumbai": "III",
    "delhi": "IV",
}


class StructuralDesignRequest(BaseModel):
    layout_id: str = "A"
    sbc_kpa: float = Field(default=200.0, gt=0, description="safe bearing capacity")
    fck: float = Field(default=25.0, description="concrete grade MPa")
    fy: float = Field(default=500.0, description="steel grade MPa")
    include_pdf: bool = True
    # low-confidence grids (irregular layouts) design badly; the UI shows
    # the grid-review warning and re-submits with this flag once confirmed
    allow_unconfident_grid: bool = False


class ApproveRequest(BaseModel):
    layout_id: str = "A"


async def _get_layout_row(project_id: str, layout_id: str, user_id, db):
    project = await get_accessible_project(project_id, user_id, db)
    stored = await layout_store.get_or_generate_layouts(project, db)
    row = next((r for r in stored if r.layout_key == layout_id), None)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layout {layout_id!r} not found",
        )
    return project, row


@router.post("/projects/{project_id}/structural/approve")
async def approve_architectural_plan(
    project_id: str,
    body: ApproveRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Freeze the current layout geometry as an immutable approved revision.

    Until approval, all architectural outputs are preliminary ("for planning
    only"); structural design refuses to run without a revision matching the
    layout's CURRENT geometry. Idempotent: re-approving unchanged geometry
    returns the existing revision.
    """
    _, row = await _get_layout_row(project_id, body.layout_id, user_id, db)
    revision, created = await structural_store.approve_layout(
        project_id, body.layout_id, row.geometry, user_id, db
    )
    return {
        "revision_id": revision.id,
        "layout_id": body.layout_id,
        "geometry_hash": revision.geometry_hash,
        "approved_at": revision.approved_at.isoformat()
        if revision.approved_at
        else None,
        "status": "approved",
        "created": created,
    }


@router.get("/projects/{project_id}/structural/status")
async def structural_status(
    project_id: str,
    layout_id: str = "A",
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _, row = await _get_layout_row(project_id, layout_id, user_id, db)
    return await structural_store.layout_status(project_id, layout_id, row.geometry, db)


@router.get("/projects/{project_id}/structural/design")
async def get_structural_design(
    project_id: str,
    layout_id: str = "A",
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch the latest non-stale structural design for the layout's
    CURRENT approved revision (matching the layout's current geometry
    hash). Used by drawing/BOQ surfaces to read the structural set."""
    _, row = await _get_layout_row(project_id, layout_id, user_id, db)

    revision = await structural_store.find_revision_for_hash(
        project_id,
        layout_id,
        structural_store.geometry_hash(row.geometry),
        db,
    )
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_approved",
                "help": (
                    "Approve the architectural plan first: "
                    f"POST /api/projects/{project_id}/structural/approve "
                    f'{{"layout_id": "{layout_id}"}}'
                ),
            },
        )
    surface = await structural_store.design_surface(
        project_id, layout_id, row.geometry, db
    )
    if surface is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_designed",
                "help": (
                    "Run structural design first: "
                    f"POST /api/projects/{project_id}/structural "
                    f'{{"layout_id": "{layout_id}"}}'
                ),
            },
        )
    return surface


@router.post("/projects/{project_id}/structural")
async def structural_design(
    project_id: str,
    body: StructuralDesignRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not structagent_client.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Structural design service is not configured (STRUCTURAL_API_URL).",
        )
    project, row = await _get_layout_row(project_id, body.layout_id, user_id, db)

    # Approval gate: structural design only runs against an APPROVED
    # architectural revision that still matches the layout's current
    # geometry — any edit since approval drops it back to Draft.
    revision = await structural_store.find_revision_for_hash(
        project_id,
        body.layout_id,
        structural_store.geometry_hash(row.geometry),
        db,
    )
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "not_approved",
                "help": (
                    "Approve the architectural plan first: "
                    f"POST /api/projects/{project_id}/structural/approve "
                    f'{{"layout_id": "{body.layout_id}"}}'
                ),
            },
        )

    ground = (row.geometry or {}).get("ground_floor") or {}
    grid = extract_grid(ground.get("columns") or [])
    if not grid.x_spacings_m or not grid.y_spacings_m:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Could not extract a structural grid from this layout",
                "notes": grid.notes,
            },
        )
    if not grid.confident and not body.allow_unconfident_grid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "grid_needs_review",
                "notes": grid.notes,
                "help": (
                    "The extracted column grid is irregular. Review it, then "
                    "re-submit with allow_unconfident_grid=true to proceed."
                ),
            },
        )

    try:
        design, final_grid, result = await structural_loop.run_design_loop(
            project,
            revision,
            db,
            sbc_kpa=body.sbc_kpa,
            fck=body.fck,
            fy=body.fy,
            include_pdf=body.include_pdf,
            city_seismic_zone=CITY_SEISMIC_ZONE,
        )
    except structural_loop.GridNotExtractable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Could not extract a structural grid from this layout",
                "notes": exc.notes,
            },
        )
    except structagent_client.StructuralAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return {
        "ok": result.ok,
        "revision_id": revision.id,
        "design_id": design.id,
        "status": design.status,
        "iterations_used": design.iterations_used,
        "changelog": design.changelog or [],
        "layout_adjusted": design.final_geometry is not None,
        "grid": {
            "x_spacings_m": final_grid.x_spacings_m,
            "y_spacings_m": final_grid.y_spacings_m,
            "confident": final_grid.confident,
            "notes": final_grid.notes,
        },
        "checks": result.checks,
        "data": result.data,
        "artifacts": result.artifacts,
        "disclaimer": result.disclaimer,
    }
