"""Regression tests for the queued-job watchdog — Task 1.5.

Production layout/render generation is entirely Inngest-callback-driven
once INNGEST_EVENT_KEY/SIGNING_KEY are set (no inline fallback). If the
Inngest app isn't synced to the current deployment URL, the enqueued event
is never picked up and the job row stays `queued` forever while the
frontend polls every 2s for 5 minutes then gives up vaguely. This watchdog
runs on every GET poll: past `settings.job_queued_timeout_s`, a still-
`queued` job is flipped to `failed` with an actionable error instead of
hanging indefinitely.
"""

from datetime import datetime, timedelta, timezone

from app.models.job import GenerationJob
from app.models.project import Project
from app.models.user import User

PROJECT_BODY = {
    "name": "Watchdog Test",
    "plot_length": 15.0,
    "plot_width": 10.0,
    "setback_front": 1.5,
    "setback_rear": 1.0,
    "setback_left": 1.0,
    "setback_right": 1.0,
    "road_side": "S",
    "north_direction": "N",
    "num_bedrooms": 2,
    "toilets": 2,
    "parking": False,
}


async def _seed_user(session, user_id: str, plan_tier: str = "free") -> None:
    session.add(User(id=user_id, plan_tier=plan_tier))
    await session.commit()


async def _seed_project(session, user_id: str) -> str:
    project = Project(user_id=user_id, **PROJECT_BODY)
    session.add(project)
    await session.commit()
    return project.id


async def _seed_job(
    SessionLocal,
    *,
    project_id: str,
    user_id: str,
    age_seconds: float,
    status: str = "queued",
    stage: str = "queued",
    kind: str = "layout",
    layout_key: str | None = None,
) -> str:
    """Insert a GenerationJob row with a backdated created_at — no
    sleeps/timers needed to simulate an old queued job."""
    created = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    async with SessionLocal() as session:
        job = GenerationJob(
            project_id=project_id,
            requested_by=user_id,
            kind=kind,
            layout_key=layout_key,
            status=status,
            stage=stage,
            created_at=created,
            updated_at=created,
        )
        session.add(job)
        await session.commit()
        return job.id


async def test_stale_queued_job_fails_fast_on_poll(client_db):
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1")
        project_id = await _seed_project(session, "u1")

    job_id = await _seed_job(
        SessionLocal, project_id=project_id, user_id="u1", age_seconds=200
    )  # older than the 120s default timeout

    resp = await client.get(
        f"/api/projects/{project_id}/jobs/{job_id}", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["stage"] == "failed"
    assert "inngest" in body["error"].lower()
    assert "docs/deploy" in body["error"]

    # DB row persists as failed, not just the response body
    async with SessionLocal() as session:
        from app.services import jobs

        persisted = await jobs.get_job(session, project_id, job_id)
        assert persisted.status == "failed"
        assert persisted.stage == "failed"
        assert persisted.error is not None and "inngest" in persisted.error.lower()


async def test_fresh_queued_job_stays_queued(client_db):
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1")
        project_id = await _seed_project(session, "u1")

    job_id = await _seed_job(
        SessionLocal, project_id=project_id, user_id="u1", age_seconds=5
    )  # well under the 120s default timeout

    resp = await client.get(
        f"/api/projects/{project_id}/jobs/{job_id}", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["stage"] == "queued"
    assert body["error"] is None


async def test_running_job_never_touched_regardless_of_age(client_db):
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1")
        project_id = await _seed_project(session, "u1")

    job_id = await _seed_job(
        SessionLocal,
        project_id=project_id,
        user_id="u1",
        age_seconds=10_000,
        status="running",
        stage="solving",
    )

    resp = await client.get(
        f"/api/projects/{project_id}/jobs/{job_id}", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert body["stage"] == "solving"
    assert body["error"] is None


async def test_done_job_never_touched_regardless_of_age(client_db):
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1")
        project_id = await _seed_project(session, "u1")

    job_id = await _seed_job(
        SessionLocal,
        project_id=project_id,
        user_id="u1",
        age_seconds=10_000,
        status="done",
        stage="stored",
    )

    resp = await client.get(
        f"/api/projects/{project_id}/jobs/{job_id}", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["stage"] == "stored"


async def test_stale_queued_render_job_fails_fast_too(client_db):
    """The same GET /jobs/{job_id} poll handler serves render-kind jobs
    (kind='render') — the watchdog must apply equally, not just to
    layout-kind jobs."""
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1", plan_tier="pro")
        project_id = await _seed_project(session, "u1")

    job_id = await _seed_job(
        SessionLocal,
        project_id=project_id,
        user_id="u1",
        age_seconds=200,
        kind="render",
        layout_key="layout-a",
    )

    resp = await client.get(
        f"/api/projects/{project_id}/jobs/{job_id}", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "inngest" in body["error"].lower()


async def test_timeout_configurable_via_settings(client_db, monkeypatch):
    """settings.job_queued_timeout_s (env JOB_QUEUED_TIMEOUT_S) governs the
    threshold — lowering it fails a job that the 120s default would still
    consider fresh."""
    from app.config.settings import settings

    monkeypatch.setattr(settings, "job_queued_timeout_s", 5)

    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1")
        project_id = await _seed_project(session, "u1")

    job_id = await _seed_job(
        SessionLocal, project_id=project_id, user_id="u1", age_seconds=30
    )  # under the 120s default, but over the 5s override

    resp = await client.get(
        f"/api/projects/{project_id}/jobs/{job_id}", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"


def test_settings_reads_job_queued_timeout_s_from_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "test-secret-value-0123456789abcdefgh")
    monkeypatch.setenv("JOB_QUEUED_TIMEOUT_S", "45")
    from app.config.settings import Settings

    s = Settings(_env_file=None)
    assert s.job_queued_timeout_s == 45


def test_settings_defaults_job_queued_timeout_s_to_120(monkeypatch):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "test-secret-value-0123456789abcdefgh")
    monkeypatch.delenv("JOB_QUEUED_TIMEOUT_S", raising=False)
    from app.config.settings import Settings

    s = Settings(_env_file=None)
    assert s.job_queued_timeout_s == 120
