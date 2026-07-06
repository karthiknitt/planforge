import inngest as inngest_lib
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.revisions import save_auto_revision
from app.db import get_db
from app.dependencies.auth import get_current_user_id
from app.schemas.job import JobOut
from app.services import jobs, layout_store
from app.services.access import get_accessible_project

router = APIRouter()


@router.get("/projects/{project_id}/jobs/{job_id}", response_model=JobOut)
async def read_job(
    project_id: str,
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    project = await get_accessible_project(project_id, user_id, db)
    job = await jobs.get_job(db, project.id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut.model_validate(job)


@router.post("/projects/{project_id}/generate-jobs", response_model=JobOut)
async def create_generate_job(
    project_id: str,
    response: Response,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    from app import inngest_app  # runtime import so tests can monkeypatch

    project = await get_accessible_project(project_id, user_id, db)

    existing = await layout_store.get_stored_layouts(project.id, db)
    if existing:
        # Fire-and-forget snapshot, mirroring generate?refresh=true
        try:
            await save_auto_revision(
                db, project, label_prefix="Auto-save before regeneration"
            )
        except Exception:
            pass

    job = await jobs.create_job(db, project_id=project.id, requested_by=user_id)

    if inngest_app.inngest_enabled():
        await inngest_app.inngest_client.send(
            inngest_lib.Event(
                name="layout/generate.requested",
                data={"job_id": job.id, "project_id": project.id},
            )
        )
        response.status_code = 202
        return JobOut.model_validate(job)

    # Inline fallback (dev/CI, or Inngest not yet provisioned): solve now,
    # reusing this request's own `db` session directly (run_layout_job's
    # own-session variant is for the Inngest callback, which has no
    # request-scoped session to reuse).
    try:
        await jobs.execute_layout_job(db, job)
    except Exception:
        pass  # job row already carries status=failed + error
    # mark()'s commits expire server-computed columns (created_at/updated_at);
    # refresh so the sync Pydantic validation below doesn't lazy-load them
    # outside the async context.
    await db.refresh(job)
    return JobOut.model_validate(job)
