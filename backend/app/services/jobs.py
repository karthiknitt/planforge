import logging
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.job import GenerationJob
from app.models.project import Project
from app.services import layout_store

logger = logging.getLogger(__name__)

QUEUED_TIMEOUT_ERROR = (
    "Job has been queued for over {timeout}s without starting. "
    "Inngest app may not be synced to this deployment — see "
    "docs/guides/solver-service-split.md, "
    "then retry generation."
)


async def create_job(
    db: AsyncSession,
    *,
    project_id: str,
    requested_by: str,
    kind: str = "layout",
    layout_key: str | None = None,
    reference_png: bytes | None = None,
    render_floor: str | None = None,
) -> GenerationJob:
    job = GenerationJob(
        project_id=project_id,
        requested_by=requested_by,
        kind=kind,
        layout_key=layout_key,
        reference_png=reference_png,
        render_floor=render_floor,
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
    return await apply_queued_timeout(db, job)


def _job_age_seconds(job: GenerationJob) -> float:
    created = job.created_at
    # SQLite (tests) returns naive datetimes; Postgres returns aware.
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).total_seconds()


async def apply_queued_timeout(db: AsyncSession, job: GenerationJob) -> GenerationJob:
    """Watchdog: fail a job stuck in `queued` past `job_queued_timeout_s`.

    Production generation is entirely Inngest-callback-driven once
    INNGEST_EVENT_KEY/SIGNING_KEY are set (no inline fallback) — if the
    Inngest app isn't synced to the current deployment URL, the enqueued
    event is sent but never picked up, and the row would stay `queued`
    forever while the frontend polls. Runs on every GET poll (`get_job`
    above); past the timeout it flips the status to `failed` with an
    actionable error. This is purely a status flip — it never re-runs
    generation, and never touches `running`/`done`/`failed` jobs.

    Uses an optimistic guard (`WHERE status = 'queued'`) so a job that
    transitions off `queued` between the staleness check and this write
    (e.g. the real Inngest callback finishes at the same moment) is never
    clobbered — the update simply affects 0 rows and the fresh row (as
    updated by the other writer) is returned instead.
    """
    if job.status != "queued":
        return job
    if _job_age_seconds(job) < settings.job_queued_timeout_s:
        return job

    error = QUEUED_TIMEOUT_ERROR.format(timeout=settings.job_queued_timeout_s)
    await db.execute(
        update(GenerationJob)
        .where(GenerationJob.id == job.id, GenerationJob.status == "queued")
        .values(status="failed", stage="failed", error=error[:2000])
    )
    await db.commit()
    # `update()` is Core-level and doesn't sync the ORM instance; `refresh()`
    # (unlike `db.get()`) always issues a real SELECT rather than returning
    # the identity-mapped copy, so it reflects our write if it won, or the
    # concurrent writer's if we lost the optimistic-guard race.
    await db.refresh(job)
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


async def execute_layout_job(db: AsyncSession, job: GenerationJob) -> None:
    """Solve and store layouts for `job` using the given session.

    Shared core for both entry points below: `run_layout_job` (own session,
    for the Inngest callback which has no request-scoped session to reuse)
    and the generate-jobs endpoint's inline fallback (reuses the request's
    own session directly instead of opening a second one).
    """
    if job.status == "done":
        return
    project = await db.get(Project, job.project_id)
    if project is None:
        await mark(db, job, status="failed", stage="failed", error="project missing")
        return
    try:
        await mark(db, job, status="running", stage="solving")
        await layout_store.regenerate_and_store(project, db)
        await mark(db, job, status="done", stage="stored")
    except Exception as exc:
        logger.exception("layout job %s failed", job.id)
        await mark(db, job, status="failed", stage="failed", error=str(exc))
        raise


async def run_layout_job(job_id: str, session_factory=None) -> None:
    """Execute a layout-generation job in its own DB session.

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
        await execute_layout_job(db, job)
