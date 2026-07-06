"""Regression tests for async render jobs — the render/requested pipeline
(Task 6), reusing the generation_jobs table and Inngest wiring from Task 3/4."""

import pytest

from app.models.project import Project
from app.models.user import User
from app.services import render_runner
from app.services.render_providers import RenderResult

PROJECT_BODY = {
    "name": "Render Jobs Test",
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


async def _seed_project_with_layout(sf, user_id: str) -> tuple[str, str]:
    from app.services import layout_store

    async with sf() as session:
        project = Project(user_id=user_id, **PROJECT_BODY)
        session.add(project)
        await session.commit()
        stored = await layout_store.regenerate_and_store(project, session)
        return project.id, stored[0].layout_key


@pytest.fixture
def fake_render(monkeypatch):
    async def _fake(
        prompt, reference_png, provider, *, api_key, model=None, timeout=120.0
    ):
        return RenderResult(
            image_png=b"\x89PNG-fake",
            provider=provider,
            model=model or "m",
            cost_usd=None,
        )

    # patch where it is USED (render_runner imports it)
    monkeypatch.setattr(render_runner, "render_image", _fake)
    return _fake


async def test_render_job_inline_completes(client_db, fake_render, monkeypatch):
    from app.config.settings import settings

    monkeypatch.setattr(settings, "render_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1", "pro")
    project_id, layout_id = await _seed_project_with_layout(SessionLocal, "u1")

    resp = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render-jobs",
        headers={"X-Test-User-Id": "u1"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"

    # image now served by the existing GET render endpoint
    img = await client.get(
        f"/api/projects/{project_id}/layouts/{layout_id}/render",
        headers={"X-Test-User-Id": "u1"},
    )
    assert img.status_code == 200


async def test_render_job_free_tier_402(client_db):
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u2", "free")
    project_id, layout_id = await _seed_project_with_layout(SessionLocal, "u2")

    resp = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render-jobs",
        headers={"X-Test-User-Id": "u2"},
    )
    assert resp.status_code == 402
