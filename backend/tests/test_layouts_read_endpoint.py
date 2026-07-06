"""Regression tests for the read-only layouts endpoint.

Project page loads must never trigger the CP-SAT solver — that used to
happen on a store miss inside GET /projects/{id}/generate, inside
fetchBackend's 15s timeout. Generation is now an explicit action; reads
only ever return what's already stored.
"""

from app.services import layout_store

HDRS = {"X-Test-User-Id": "layouts-read-owner"}

PROJECT_BODY = {
    "name": "Layouts Read Test",
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


async def _make_project(client) -> str:
    res = await client.post("/api/projects", json=PROJECT_BODY, headers=HDRS)
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def test_read_layouts_returns_empty_list_without_solving(client_db, monkeypatch):
    client, _ = client_db
    project_id = await _make_project(client)

    def _boom(*a, **k):
        raise AssertionError("read endpoint must never solve")

    monkeypatch.setattr(layout_store, "regenerate_and_store", _boom)
    monkeypatch.setattr(layout_store, "get_or_generate_layouts", _boom)

    res = await client.get(f"/api/projects/{project_id}/layouts", headers=HDRS)
    assert res.status_code == 200
    assert res.json() == {"project_id": project_id, "layouts": []}


async def test_read_layouts_returns_stored_geometry(client_db):
    client, _ = client_db
    project_id = await _make_project(client)
    # The one call in this test allowed to solve — seeds the store exactly
    # like a real "Generate" action would.
    generated = await client.get(f"/api/projects/{project_id}/generate", headers=HDRS)
    assert generated.status_code == 200, generated.text

    res = await client.get(f"/api/projects/{project_id}/layouts", headers=HDRS)
    assert res.status_code == 200
    body = res.json()
    assert len(body["layouts"]) >= 1
    assert body == generated.json()
