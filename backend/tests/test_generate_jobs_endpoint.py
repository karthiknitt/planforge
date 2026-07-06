"""Regression tests for POST /projects/{id}/generate-jobs — the async
entry point that replaces blocking inline generation. Covers both the
inline-fallback path (no Inngest keys configured, dev/CI default) and the
Inngest event-enqueue path."""

from app.models.project import Project
from app.models.user import User

PROJECT_BODY = {
    "name": "Generate Jobs Test",
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


async def test_generate_job_inline_fallback_completes(client_db):
    """No Inngest keys in the test env → the endpoint solves inline and
    returns a finished job."""
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1", "free")
        project_id = await _seed_project(session, "u1")

    resp = await client.post(
        f"/api/projects/{project_id}/generate-jobs", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done" and body["stage"] == "stored"

    layouts = await client.get(
        f"/api/projects/{project_id}/layouts", headers={"X-Test-User-Id": "u1"}
    )
    assert len(layouts.json()["layouts"]) >= 1


async def test_generate_job_event_path_enqueues(client_db, monkeypatch):
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1", "free")
        project_id = await _seed_project(session, "u1")

    sent: list = []

    from app import inngest_app

    async def fake_send(event):
        sent.append(event)
        return ["evt-1"]

    monkeypatch.setattr(inngest_app, "inngest_enabled", lambda: True)
    monkeypatch.setattr(inngest_app.inngest_client, "send", fake_send)

    resp = await client.post(
        f"/api/projects/{project_id}/generate-jobs", headers={"X-Test-User-Id": "u1"}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert len(sent) == 1
    assert sent[0].name == "layout/generate.requested"
    assert sent[0].data["job_id"] == body["id"]
