"""Cached AI floor-plan renders — persisted per layout geometry-hash so an
unchanged layout never re-hits the paid render provider."""

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.config.settings import settings
from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.engine.pdf import render_pdf
from app.engine.render_prompt import build_render_prompt
from app.models.render import LayoutRender
from app.quality.pdf_image import pdf_page_png
from app.services import layout_store
from app.services.access import get_accessible_project
from app.services.plans import get_effective_plan_tier, tier_at_least
from app.services.plot_config import plot_config_from_project
from app.services.render_providers import (
    GEMINI_MODEL,
    OPENAI_MODEL,
    OPENROUTER_MODEL,
    RenderProviderError,
    render_image,
)

router = APIRouter()

_PROVIDER_KEYS = {
    "gemini": lambda: settings.gemini_api_key,
    "openai": lambda: settings.openai_api_key,
    "openrouter": lambda: settings.openrouter_api_key,
}

_DEFAULT_MODELS = {
    "gemini": GEMINI_MODEL,
    "openai": OPENAI_MODEL,
    "openrouter": OPENROUTER_MODEL,
}


def _geometry_hash(geometry: dict) -> str:
    return hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()


async def _find_render(
    layout_pk: str,
    db: AsyncSession,
    *,
    layout_hash: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    with_image: bool = False,
) -> LayoutRender | None:
    stmt = select(LayoutRender).where(LayoutRender.layout_id == layout_pk)
    if layout_hash is not None:
        stmt = stmt.where(LayoutRender.layout_hash == layout_hash)
    if provider is not None:
        stmt = stmt.where(LayoutRender.provider == provider)
    if model is not None:
        stmt = stmt.where(LayoutRender.model == model)
    if with_image:
        # image_png is `deferred()` (kept off list/cache-check queries) — an
        # async session can't lazy-load it on attribute access afterwards, so
        # callers that need the bytes must undefer it up front.
        stmt = stmt.options(undefer(LayoutRender.image_png))
    stmt = stmt.order_by(LayoutRender.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().first()


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

    provider = settings.render_provider
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Render provider not configured.",
        )
    requested_model = settings.render_model or None
    effective_model = requested_model or _DEFAULT_MODELS.get(provider, "")
    api_key_fn = _PROVIDER_KEYS.get(provider)
    api_key = api_key_fn() if api_key_fn else ""

    project = await get_accessible_project(project_id, user_id, db)
    stored = await layout_store.get_stored_layout(project_id, layout_id, db)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layout {layout_id!r} not found",
        )

    layout_hash = _geometry_hash(stored.geometry)
    cached = await _find_render(
        stored.id,
        db,
        layout_hash=layout_hash,
        provider=provider,
        model=effective_model,
    )
    if cached is not None:
        return {"cached": True, "provider": cached.provider, "model": cached.model}

    cfg = plot_config_from_project(project)
    layout = layout_store.engine_layout_from_geometry(stored.geometry)
    pdf_bytes = render_pdf(project.name, layout, cfg, project.num_bedrooms)
    reference_png = pdf_page_png(pdf_bytes)
    prompt = build_render_prompt(
        stored.geometry,
        plot_length_m=cfg.plot_length,
        plot_width_m=cfg.plot_width,
        north_direction=project.north_direction,
    )

    try:
        result = await render_image(
            prompt,
            reference_png,
            provider,
            api_key=api_key,
            model=requested_model,
        )
    except RenderProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    row = LayoutRender(
        project_id=project_id,
        layout_id=stored.id,
        layout_hash=layout_hash,
        provider=result.provider,
        model=result.model,
        image_png=result.image_png,
    )
    db.add(row)
    await db.commit()

    return {"cached": False, "provider": result.provider, "model": result.model}


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

    row = await _find_render(stored.id, db, with_image=True)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No render available")

    return Response(content=row.image_png, media_type="image/png")
