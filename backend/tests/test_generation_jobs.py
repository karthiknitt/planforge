"""Regression tests for the generation_jobs table, jobs service, and status
endpoint — the persistence layer Inngest (Task 4) drives to make layout
generation async instead of blocking inside a request/response cycle."""

from app.models.project import Project
from app.models.user import User

PROJECT_BODY = {
    "name": "Jobs Test",
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


async def _seed_user(session, user_id: str, plan_tier: str) -> None:
    session.add(User(id=user_id, plan_tier=plan_tier))
    await session.commit()


async def _seed_project(session, user_id: str) -> str:
    project = Project(user_id=user_id, **PROJECT_BODY)
    session.add(project)
    await session.commit()
    return project.id


async def test_job_lifecycle_service(client_db):
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1", "free")
        project_id = await _seed_project(session, "u1")

    from app.services import jobs

    async with SessionLocal() as db:
        job = await jobs.create_job(db, project_id=project_id, requested_by="u1")
        assert job.status == "queued" and job.stage == "queued" and job.kind == "layout"
        await jobs.mark(db, job, status="running", stage="solving")

    async with SessionLocal() as db:  # fresh session — proves persistence
        job2 = await jobs.get_job(db, project_id, job.id)
        assert job2.status == "running" and job2.stage == "solving"


async def test_job_status_endpoint(client_db):
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1", "free")
        project_id = await _seed_project(session, "u1")
    from app.services import jobs

    async with SessionLocal() as db:
        job = await jobs.create_job(db, project_id=project_id, requested_by="u1")

    resp = await client.get(
        f"/api/projects/{project_id}/jobs/{job.id}", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job.id and body["status"] == "queued"

    # cross-project probe → 404
    resp = await client.get(
        f"/api/projects/{project_id}/jobs/not-a-job", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 404


async def test_run_layout_job_stores_layouts_and_marks_done(client_db):
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1", "free")
        project_id = await _seed_project(
            session, "u1"
        )  # small rectangular plot → fast solve
    from app.services import jobs, layout_store

    async with SessionLocal() as db:
        job = await jobs.create_job(db, project_id=project_id, requested_by="u1")

    # session_factory override: run_layout_job otherwise opens app.db.SessionLocal,
    # which points at real Postgres — this test's data only exists in the
    # isolated in-memory engine `client_db` created for this test.
    await jobs.run_layout_job(job.id, session_factory=SessionLocal)

    async with SessionLocal() as db:
        done = await jobs.get_job(db, project_id, job.id)
        assert done.status == "done" and done.stage == "stored"
        stored = await layout_store.get_stored_layouts(project_id, db)
        assert len(stored) >= 1
