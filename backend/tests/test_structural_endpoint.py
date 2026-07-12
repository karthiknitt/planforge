"""Structural-design endpoint + grid extraction (StructAgent integration).

The external structapi call is faked with httpx.MockTransport via the
service's test seam — no network, deterministic.
"""

import json

import httpx

from app.config.settings import settings
from app.engine.structural_grid import extract_grid
from app.services import layout_store, structagent_client

HDRS = {"X-Test-User-Id": "structural-owner"}

PROJECT_BODY = {
    "name": "Structural Test",
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

#: a regular 3x2-intersection grid (2 bays x 1 bay), spacings 4.0 / 4.5 m
GRID_COLUMNS = [{"x": x, "y": y} for x in (0.0, 4.0, 8.0) for y in (0.0, 4.5)]


class _FakeRow:
    layout_key = "A"
    geometry = {"ground_floor": {"columns": GRID_COLUMNS}}


ENVELOPE = {
    "api_version": "1",
    "ok": True,
    "checks": [
        {"name": "columns/interior: biaxial interaction <= 1.0 (cl 39.6)", "ok": True}
    ],
    "data": {
        "quantities": {"steel_kg": {"total": 1234.5}, "concrete_m3": {"total": 21.0}}
    },
    "artifacts": [
        {
            "name": "building_report.pdf",
            "content_type": "application/pdf",
            "encoding": "base64",
            "content": "JVBERi0=",
        }
    ],
    "disclaimer": "verify against official BIS copies",
}


async def _make_project(client) -> str:
    res = await client.post("/api/projects", json=PROJECT_BODY, headers=HDRS)
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ---------------------------- grid extraction -----------------------------


def test_extract_grid_regular():
    g = extract_grid(GRID_COLUMNS)
    assert g.x_spacings_m == [4.0, 4.0]
    assert g.y_spacings_m == [4.5]
    assert g.confident


def test_extract_grid_too_few_columns():
    g = extract_grid([{"x": 0, "y": 0}, {"x": 4, "y": 0}])
    assert not g.x_spacings_m and not g.confident


def test_extract_grid_flags_implausible_spacing():
    cols = [{"x": x, "y": y} for x in (0.0, 0.9) for y in (0.0, 4.0)]
    g = extract_grid(cols)
    assert not g.confident
    assert any("outside" in n for n in g.notes)


# ------------------------------- endpoint ---------------------------------


async def test_structural_503_when_unconfigured(client_db, monkeypatch):
    client, _ = client_db
    project_id = await _make_project(client)
    monkeypatch.setattr(settings, "structural_api_url", "")
    res = await client.post(
        f"/api/projects/{project_id}/structural", json={}, headers=HDRS
    )
    assert res.status_code == 503


async def test_structural_404_missing_layout(client_db, monkeypatch):
    client, _ = client_db
    project_id = await _make_project(client)
    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")

    async def _none(project, db):
        return []

    monkeypatch.setattr(layout_store, "get_or_generate_layouts", _none)
    res = await client.post(
        f"/api/projects/{project_id}/structural", json={"layout_id": "A"}, headers=HDRS
    )
    assert res.status_code == 404


async def test_structural_happy_path(client_db, monkeypatch):
    client, _ = client_db
    project_id = await _make_project(client)
    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")
    monkeypatch.setattr(settings, "structural_api_key", "k1")

    async def _stored(project, db):
        return [_FakeRow()]

    monkeypatch.setattr(layout_store, "get_or_generate_layouts", _stored)

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ENVELOPE)

    monkeypatch.setattr(
        structagent_client, "_transport_for_tests", httpx.MockTransport(handler)
    )

    res = await client.post(
        f"/api/projects/{project_id}/structural",
        json={"layout_id": "A", "sbc_kpa": 180},
        headers=HDRS,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["grid"]["x_spacings_m"] == [4.0, 4.0]
    assert body["grid"]["confident"] is True
    assert body["data"]["quantities"]["steel_kg"]["total"] == 1234.5
    assert body["artifacts"][0]["name"] == "building_report.pdf"
    assert "BIS" in body["disclaimer"]
    # request that reached structapi
    assert seen["url"].endswith("/v1/design/building")
    assert seen["key"] == "k1"
    assert seen["body"]["grid"]["x_spacings_m"] == [4.0, 4.0]
    assert seen["body"]["sbc_kpa"] == 180


async def test_structural_502_on_upstream_error(client_db, monkeypatch):
    client, _ = client_db
    project_id = await _make_project(client)
    monkeypatch.setattr(settings, "structural_api_url", "http://sapi.test")

    async def _stored(project, db):
        return [_FakeRow()]

    monkeypatch.setattr(layout_store, "get_or_generate_layouts", _stored)
    monkeypatch.setattr(
        structagent_client,
        "_transport_for_tests",
        httpx.MockTransport(lambda r: httpx.Response(500, text="boom")),
    )

    res = await client.post(
        f"/api/projects/{project_id}/structural", json={}, headers=HDRS
    )
    assert res.status_code == 502
