"""Gated AI render endpoints — persisted per-geometry-hash render cache.

render_image is always monkeypatched: these tests never hit a live provider.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.api.routes import render as render_route
from app.config.settings import settings
from app.models.user import User
from app.services.render_providers import RenderProviderError, RenderResult

HDRS = {"X-Test-User-Id": "render-owner"}

PROJECT_BODY = {
    "name": "Render Endpoint Test",
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

FAKE_PNG = b"\x89PNG\r\n\x1a\nfake-render-bytes"


@pytest.fixture(autouse=True)
def _reset_render_settings():
    """Provider config is a global singleton — restore it after every test so
    tests don't leak render_provider/render_model/keys into each other."""
    orig = (
        settings.render_provider,
        settings.render_model,
        settings.gemini_api_key,
    )
    yield
    settings.render_provider, settings.render_model, settings.gemini_api_key = orig


async def _pro_user(sf, user_id="render-owner"):
    async with sf() as session:
        session.add(
            User(
                id=user_id,
                plan_tier="pro",
                plan_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
        )
        await session.commit()


async def _make_project_with_layout(client) -> tuple[str, str]:
    res = await client.post("/api/projects", json=PROJECT_BODY, headers=HDRS)
    assert res.status_code == 201, res.text
    project_id = res.json()["id"]

    gen = await client.get(f"/api/projects/{project_id}/generate", headers=HDRS)
    assert gen.status_code == 200, gen.text
    layout_id = gen.json()["layouts"][0]["id"]
    return project_id, layout_id


def _configure_provider(monkeypatch, mock_render_image=None):
    settings.render_provider = "gemini"
    settings.render_model = "test-model"
    settings.gemini_api_key = "test-key"
    if mock_render_image is not None:
        monkeypatch.setattr(render_route, "render_image", mock_render_image)


def _mock_render_image(model="test-model", provider="gemini"):
    return AsyncMock(
        return_value=RenderResult(
            image_png=FAKE_PNG, provider=provider, model=model, cost_usd=0.01
        )
    )


async def test_render_returns_402_below_tier(client_db):
    client, _ = client_db
    project_id, layout_id = await _make_project_with_layout(client)

    res = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render", headers=HDRS
    )
    assert res.status_code == 402


async def test_render_returns_503_when_unconfigured(client_db):
    client, sf = client_db
    await _pro_user(sf)
    project_id, layout_id = await _make_project_with_layout(client)

    settings.render_provider = ""
    res = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render", headers=HDRS
    )
    assert res.status_code == 503


async def test_render_502_on_provider_error(client_db, monkeypatch):
    client, sf = client_db
    await _pro_user(sf)
    project_id, layout_id = await _make_project_with_layout(client)

    _configure_provider(
        monkeypatch,
        AsyncMock(side_effect=RenderProviderError("gemini: HTTP 500")),
    )
    res = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render", headers=HDRS
    )
    assert res.status_code == 502


async def test_render_first_call_generates_and_stores(client_db, monkeypatch):
    client, sf = client_db
    await _pro_user(sf)
    project_id, layout_id = await _make_project_with_layout(client)

    mock = _mock_render_image()
    _configure_provider(monkeypatch, mock)

    res = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render", headers=HDRS
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {"cached": False, "provider": "gemini", "model": "test-model"}
    mock.assert_awaited_once()


async def test_render_second_call_is_cache_hit(client_db, monkeypatch):
    client, sf = client_db
    await _pro_user(sf)
    project_id, layout_id = await _make_project_with_layout(client)

    mock = _mock_render_image()
    _configure_provider(monkeypatch, mock)

    first = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render", headers=HDRS
    )
    assert first.status_code == 200
    assert first.json()["cached"] is False

    second = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render", headers=HDRS
    )
    assert second.status_code == 200
    assert second.json() == {
        "cached": True,
        "provider": "gemini",
        "model": "test-model",
    }

    # The provider must NOT be called again for an unchanged geometry hash.
    mock.assert_awaited_once()


async def test_render_cache_miss_after_geometry_edit(client_db, monkeypatch):
    client, sf = client_db
    await _pro_user(sf)
    project_id, layout_id = await _make_project_with_layout(client)

    mock = _mock_render_image()
    _configure_provider(monkeypatch, mock)

    first = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render", headers=HDRS
    )
    assert first.status_code == 200
    mock.assert_awaited_once()

    gen = (
        await client.get(f"/api/projects/{project_id}/generate", headers=HDRS)
    ).json()
    layout = next(lay for lay in gen["layouts"] if lay["id"] == layout_id)
    rooms = [
        {
            "id": r["id"],
            "type": r["type"],
            "name": r["name"],
            "x": r["x"],
            "y": r["y"],
            "width": r["width"],
            "height": r["depth"],
            "floor": "gf",
        }
        for r in layout["ground_floor"]["rooms"]
    ] + [
        {
            "id": r["id"],
            "type": r["type"],
            "name": r["name"],
            "x": r["x"],
            "y": r["y"],
            "width": r["width"],
            "height": r["depth"],
            "floor": "ff",
        }
        for r in layout["first_floor"]["rooms"]
    ]
    rooms[0]["x"] = round(rooms[0]["x"] + 0.1, 3)
    patch = await client.patch(
        f"/api/projects/{project_id}/layouts/{layout_id}",
        json={"rooms": rooms},
        headers=HDRS,
    )
    assert patch.status_code == 200, patch.text

    second = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render", headers=HDRS
    )
    assert second.status_code == 200
    assert second.json()["cached"] is False
    assert mock.await_count == 2


async def test_render_get_404_before_first_render(client_db):
    client, sf = client_db
    await _pro_user(sf)
    project_id, layout_id = await _make_project_with_layout(client)

    res = await client.get(
        f"/api/projects/{project_id}/layouts/{layout_id}/render", headers=HDRS
    )
    assert res.status_code == 404


async def test_render_get_returns_png_after_post(client_db, monkeypatch):
    client, sf = client_db
    await _pro_user(sf)
    project_id, layout_id = await _make_project_with_layout(client)

    mock = _mock_render_image()
    _configure_provider(monkeypatch, mock)
    post_res = await client.post(
        f"/api/projects/{project_id}/layouts/{layout_id}/render", headers=HDRS
    )
    assert post_res.status_code == 200

    get_res = await client.get(
        f"/api/projects/{project_id}/layouts/{layout_id}/render", headers=HDRS
    )
    assert get_res.status_code == 200
    assert get_res.headers["content-type"] == "image/png"
    assert get_res.content == FAKE_PNG
