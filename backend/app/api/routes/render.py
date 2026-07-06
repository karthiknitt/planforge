"""Cached AI floor-plan renders — persisted per layout geometry-hash so an
unchanged layout never re-hits the paid render provider."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.services import layout_store, render_runner
from app.services.access import get_accessible_project
from app.services.plans import get_effective_plan_tier, tier_at_least

router = APIRouter()


@router.post("/projects/{project_id}/layouts/{layout_id}/render")
async def render_layout(
    project_id: str,
    layout_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    plan = await get_effective_plan_tier(user_id, db)
    if not tier_at_least(plan, "pro"):
        raise HTTPException(
            status_code=402, detail="AI render requires Pro plan or above."
        )
    render_runner.ensure_provider_configured()
    await get_accessible_project(project_id, user_id, db)

    row = await render_runner.perform_render(project_id, layout_id, db)
    return {
        "cached": bool(getattr(row, "was_cached", False)),
        "provider": row.provider,
        "model": row.model,
    }


@router.get("/projects/{project_id}/layouts/{layout_id}/render")
async def get_layout_render(
    project_id: str,
    layout_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await get_accessible_project(project_id, user_id, db)
    stored = await layout_store.get_stored_layout(project_id, layout_id, db)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Layout not found")

    row = await render_runner.find_render(stored.id, db, with_image=True)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No render available")

    return Response(content=row.image_png, media_type="image/png")
