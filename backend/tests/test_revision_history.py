"""
Tests for revision history / versioning (P2-4).

Covers:
  - Create a revision snapshot for a project
  - List revisions returns them newest-first, capped at 10
  - Get a specific revision by version number
  - Delete a revision
  - 403 / 404 guard rails
"""

import pytest

USER_ID = "user-rev-001"
OTHER_USER = "user-rev-002"
HEADERS = {"X-User-Id": USER_ID}

BASE_PAYLOAD = {
    "name": "Revision Test Plot",
    "plot_length": 12.0,
    "plot_width": 9.0,
    "setback_front": 1.5,
    "setback_rear": 1.5,
    "setback_left": 1.0,
    "setback_right": 1.0,
    "road_side": "S",
    "north_direction": "N",
    "num_bedrooms": 2,
    "toilets": 2,
    "parking": False,
}


async def _create_project(client) -> str:
    r = await client.post("/api/projects", json=BASE_PAYLOAD, headers=HEADERS)
    assert r.status_code == 201
    return r.json()["id"]


# ── Create revision ────────────────────────────────────────────────────────────

async def test_create_revision_returns_201(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/revisions",
        json={"label": "Snapshot before demo"},
        headers=HEADERS,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["version"] == 1
    assert data["label"] == "Snapshot before demo"
    assert "id" in data  # RevisionCreateResponse includes id, not project_id


async def test_create_revision_auto_label(client):
    """Empty label falls back to auto timestamp label."""
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/revisions",
        json={},
        headers=HEADERS,
    )
    assert r.status_code == 201
    assert "Snapshot" in r.json()["label"]


async def test_create_revision_increments_version(client):
    pid = await _create_project(client)
    r1 = await client.post(f"/api/projects/{pid}/revisions", json={}, headers=HEADERS)
    r2 = await client.post(f"/api/projects/{pid}/revisions", json={}, headers=HEADERS)
    assert r1.json()["version"] == 1
    assert r2.json()["version"] == 2


async def test_create_revision_wrong_user_returns_404(client):
    """Accessing another user's project returns 404 (not 403, by design)."""
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/revisions",
        json={},
        headers={"X-User-Id": OTHER_USER},
    )
    assert r.status_code == 404


# ── List revisions ─────────────────────────────────────────────────────────────

async def test_list_revisions_empty(client):
    pid = await _create_project(client)
    r = await client.get(f"/api/projects/{pid}/revisions", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []


async def test_list_revisions_newest_first(client):
    pid = await _create_project(client)
    for i in range(3):
        await client.post(
            f"/api/projects/{pid}/revisions",
            json={"label": f"Rev {i+1}"},
            headers=HEADERS,
        )
    r = await client.get(f"/api/projects/{pid}/revisions", headers=HEADERS)
    versions = [item["version"] for item in r.json()]
    assert versions == sorted(versions, reverse=True)


async def test_list_revisions_capped_at_10(client):
    pid = await _create_project(client)
    for _ in range(12):
        await client.post(f"/api/projects/{pid}/revisions", json={}, headers=HEADERS)
    r = await client.get(f"/api/projects/{pid}/revisions", headers=HEADERS)
    assert len(r.json()) <= 10


# ── Get revision ───────────────────────────────────────────────────────────────

async def test_get_revision_by_version(client):
    pid = await _create_project(client)
    await client.post(
        f"/api/projects/{pid}/revisions",
        json={"label": "v1 snapshot"},
        headers=HEADERS,
    )
    r = await client.get(f"/api/projects/{pid}/revisions/1", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == 1
    assert data["label"] == "v1 snapshot"
    # Snapshot must be non-empty
    assert data["snapshot"] is not None
    assert "layouts" in data["snapshot"]


async def test_get_revision_not_found_returns_404(client):
    pid = await _create_project(client)
    r = await client.get(f"/api/projects/{pid}/revisions/99", headers=HEADERS)
    assert r.status_code == 404


# ── Delete revision ────────────────────────────────────────────────────────────

async def test_delete_revision(client):
    pid = await _create_project(client)
    await client.post(f"/api/projects/{pid}/revisions", json={}, headers=HEADERS)

    r = await client.delete(f"/api/projects/{pid}/revisions/1", headers=HEADERS)
    assert r.status_code == 204

    # Gone after deletion
    r2 = await client.get(f"/api/projects/{pid}/revisions/1", headers=HEADERS)
    assert r2.status_code == 404


async def test_delete_nonexistent_revision_returns_404(client):
    pid = await _create_project(client)
    r = await client.delete(f"/api/projects/{pid}/revisions/42", headers=HEADERS)
    assert r.status_code == 404
