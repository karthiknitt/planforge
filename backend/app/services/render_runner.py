"""Render execution — the shared core for the synchronous POST render
endpoint and the async Inngest render-job pipeline (Task 6)."""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.config.settings import settings
from app.engine.pdf import render_pdf
from app.engine.render_prompt import build_render_prompt
from app.models.job import GenerationJob
from app.models.project import Project
from app.models.render import LayoutRender
from app.quality.pdf_image import pdf_page_png
from app.services import jobs, layout_store
from app.services.plot_config import plot_config_from_project
from app.services.storage import NullStorage, get_storage
from app.services.render_providers import (
    GEMINI_MODEL,
    OPENAI_MODEL,
    OPENROUTER_MODEL,
    RenderProviderError,
    render_image,
)

logger = logging.getLogger(__name__)

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


RENDER_FLOORS = ("ground_floor", "first_floor", "second_floor", "basement_floor")


def _geometry_hash(geometry: dict) -> str:
    return hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()


async def _daily_render_count(user_id: str, db) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    result = await db.execute(
        select(func.count())
        .select_from(LayoutRender)
        .join(Project, Project.id == LayoutRender.project_id)
        .where(Project.user_id == user_id, LayoutRender.created_at >= since)
    )
    return int(result.scalar_one())


async def check_render_quota(user_id: str, db, limit: int | None = None) -> None:
    """Raise 429 if the user has burned their 24h AI-render allowance."""
    from app.config.settings import settings

    cap = settings.render_daily_quota if limit is None else limit
    used = await _daily_render_count(user_id, db)
    if used >= cap:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "render_quota_exceeded",
                "detail": f"Daily AI render limit reached ({cap}).",
                "help": "Renders reset 24h after each generation.",
            },
        )


def validate_render_floor(floor: str) -> str:
    if floor not in RENDER_FLOORS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"floor must be one of {', '.join(RENDER_FLOORS)}",
        )
    return floor


async def find_render(
    layout_pk: str,
    db: AsyncSession,
    *,
    layout_hash: str | None = None,
    floor: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    with_image: bool = False,
) -> LayoutRender | None:
    stmt = select(LayoutRender).where(LayoutRender.layout_id == layout_pk)
    if layout_hash is not None:
        stmt = stmt.where(LayoutRender.layout_hash == layout_hash)
    if floor is not None:
        stmt = stmt.where(LayoutRender.floor == floor)
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


def ensure_provider_configured() -> None:
    if not settings.render_provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Render provider not configured.",
        )


async def perform_render(
    project_id: str,
    layout_id: str,
    db: AsyncSession,
    *,
    reference_png: bytes | None = None,
    reference_kind: str = "cad",
    floor: str = "ground_floor",
) -> LayoutRender:
    """Render (or return the cached render for) one floor of a layout.

    Sets a transient `was_cached` attribute on the returned row — not a
    mapped column, just a same-request signal so callers (the sync POST
    endpoint) can report `cached: bool` without a second return type.

    `reference_png` is the conditioning image: when the frontend supplies an
    R3F 3D snapshot it is used directly (exact geometry, best fidelity);
    otherwise we fall back to a rasterised 2D PDF plan.
    """
    ensure_provider_configured()
    provider = settings.render_provider
    requested_model = settings.render_model or None
    effective_model = requested_model or _DEFAULT_MODELS.get(provider, "")
    api_key_fn = _PROVIDER_KEYS.get(provider)
    api_key = api_key_fn() if api_key_fn else ""

    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    stored = await layout_store.get_stored_layout(project_id, layout_id, db)
    if stored is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Layout {layout_id!r} not found"
        )

    validate_render_floor(floor)
    if stored.geometry.get(floor) is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Floor {floor!r} not present in layout {layout_id!r}",
        )

    layout_hash = _geometry_hash(stored.geometry)
    cached = await find_render(
        stored.id,
        db,
        layout_hash=layout_hash,
        floor=floor,
        provider=provider,
        model=effective_model,
    )
    if cached is not None:
        cached.was_cached = True
        return cached

    await check_render_quota(project.user_id, db)

    cfg = plot_config_from_project(project)
    layout = layout_store.engine_layout_from_geometry(stored.geometry)
    if reference_png is None:
        pdf_bytes = render_pdf(project.name, layout, cfg, project.num_bedrooms)
        # Standard PDF page order: GF architectural = 0, FF architectural = 1.
        # Conditioning the FF render on the GF page made the model draw the
        # wrong rooms — pick the page that matches the requested floor.
        page_idx = {"ground_floor": 0, "first_floor": 1}.get(floor, 0)
        reference_png = pdf_page_png(pdf_bytes, page_idx=page_idx)
        reference_kind = "cad"
    prompt = build_render_prompt(
        stored.geometry,
        plot_length_m=cfg.plot_length,
        plot_width_m=cfg.plot_width,
        north_direction=project.north_direction,
        floor=floor,
        reference_kind=reference_kind,
    )

    try:
        result = await render_image(
            prompt, reference_png, provider, api_key=api_key, model=requested_model
        )
    except RenderProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    storage = get_storage()
    image_key = f"renders/{project_id}/{layout_hash}/{floor}.png"
    stored_remotely = False
    try:
        await storage.put_bytes(image_key, result.image_png, "image/png")
        stored_remotely = not isinstance(storage, NullStorage)
    except Exception:
        logger.warning(
            "R2 render upload failed — falling back to DB blob", exc_info=True
        )

    row = LayoutRender(
        project_id=project_id,
        layout_id=stored.id,
        layout_hash=layout_hash,
        floor=floor,
        provider=result.provider,
        model=result.model,
        image_png=None if stored_remotely else result.image_png,
        image_key=image_key if stored_remotely else None,
    )
    db.add(row)
    await db.commit()
    row.was_cached = False
    return row


async def render_bytes(row: LayoutRender) -> bytes | None:
    if row.image_key:
        data = await get_storage().get_bytes(row.image_key)
        if data is not None:
            return data
    return row.image_png


async def execute_render_job(db: AsyncSession, job: GenerationJob) -> None:
    """Render and store for `job` using the given session.

    Shared core for `run_render_job` (own session, for the Inngest callback
    which has no request-scoped session to reuse) and the render-jobs
    endpoint's inline fallback (reuses the request's own session directly).
    """
    if job.status == "done" or job.layout_key is None:
        return
    try:
        await jobs.mark(db, job, status="running", stage="rendering")
        await perform_render(
            job.project_id,
            job.layout_key,
            db,
            reference_png=job.reference_png,
            reference_kind="r3f" if job.reference_png else "cad",
            floor=job.render_floor or "ground_floor",
        )
        await jobs.mark(db, job, status="done", stage="stored")
    except Exception as exc:
        logger.exception("render job %s failed", job.id)
        await jobs.mark(db, job, status="failed", stage="failed", error=str(exc))
        raise


async def run_render_job(job_id: str, session_factory=None) -> None:
    """Execute a render job in its own DB session.

    Called from the Inngest function (durable path), which only has a
    job_id and no request-scoped session to reuse.

    `session_factory` defaults to the app's real SessionLocal; tests pass
    the isolated in-memory `client_db` factory instead so this never opens
    a connection to the real (Postgres) database.
    """
    if session_factory is None:
        from app.db import SessionLocal as session_factory

    async with session_factory() as db:
        job = await db.get(GenerationJob, job_id)
        if job is None:
            return
        await execute_render_job(db, job)
