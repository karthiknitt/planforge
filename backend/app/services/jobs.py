import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import GenerationJob
from app.models.project import Project
from app.services import layout_store

logger = logging.getLogger(__name__)


async def create_job(
    db: AsyncSession,
    *,
    project_id: str,
    requested_by: str,
    kind: str = "layout",
    layout_key: str | None = None,
) -> GenerationJob:
    job = GenerationJob(
        project_id=project_id,
        requested_by=requested_by,
        kind=kind,
        layout_key=layout_key,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job(
    db: AsyncSession, project_id: str, job_id: str
) -> GenerationJob | None:
    job = await db.get(GenerationJob, job_id)
    if job is None or job.project_id != project_id:
        return None
    return job


async def mark(
    db: AsyncSession,
    job: GenerationJob,
    *,
    status: str | None = None,
    stage: str | None = None,
    error: str | None = None,
) -> None:
    if status is not None:
        job.status = status
    if stage is not None:
        job.stage = stage
    if error is not None:
        job.error = error[:2000]
    await db.commit()


async def run_layout_job(job_id: str, session_factory=None) -> None:
    """Execute a layout-generation job in its own DB session.

    Called from the Inngest function (durable path) and from the inline
    fallback when Inngest is not configured. Marks the job failed and
    re-raises so Inngest's retry machinery sees the failure.

    `session_factory` defaults to the app's real SessionLocal; tests pass
    the isolated in-memory `client_db` factory instead so this never opens
    a connection to the real (Postgres) database.
    """
    if session_factory is None:
        from app.db import SessionLocal as session_factory

    async with session_factory() as db:
        job = await db.get(GenerationJob, job_id)
        if job is None or job.status == "done":
            return
        project = await db.get(Project, job.project_id)
        if project is None:
            await mark(
                db, job, status="failed", stage="failed", error="project missing"
            )
            return
        try:
            await mark(db, job, status="running", stage="solving")
            await layout_store.regenerate_and_store(project, db)
            await mark(db, job, status="done", stage="stored")
        except Exception as exc:
            logger.exception("layout job %s failed", job_id)
            await mark(db, job, status="failed", stage="failed", error=str(exc))
            raise
