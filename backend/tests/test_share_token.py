"""
Tests for share token endpoint (P1-2).

Covers:
  - Authenticated engineer generates a share token for their project
  - GET /api/share/{token} returns project info + layouts (public, no auth)
  - Invalid / unknown token returns 404
  - Another user cannot generate a token for someone else's project (403)
  - Idempotency: repeated POST returns the same token
  - Approve and request-changes via public endpoints
  - Authenticated approval status poll
"""

import pytest

USER_ID = "user-share-001"
OTHER_USER = "user-share-002"
HEADERS = {"X-User-Id": USER_ID}

BASE_PAYLOAD = {
    "name": "Share Test Plot",
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


# ── Token generation ───────────────────────────────────────────────────────────

async def test_create_share_token_returns_token(client):
    pid = await _create_project(client)
    r = await client.post(f"/api/projects/{pid}/share", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert len(data["token"]) == 36          # UUID format
    assert data["share_url"] == f"/share/{data['token']}"


async def test_create_share_token_idempotent(client):
    """Second POST returns the same token as the first."""
    pid = await _create_project(client)
    r1 = await client.post(f"/api/projects/{pid}/share", headers=HEADERS)
    r2 = await client.post(f"/api/projects/{pid}/share", headers=HEADERS)
    assert r1.json()["token"] == r2.json()["token"]


async def test_create_share_token_wrong_user_returns_403(client):
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/share", headers={"X-User-Id": OTHER_USER}
    )
    assert r.status_code == 403


async def test_create_share_token_unknown_project_returns_404(client):
    r = await client.post(
        "/api/projects/nonexistent-id/share", headers=HEADERS
    )
    assert r.status_code == 404


# ── Public read via token ──────────────────────────────────────────────────────

async def test_get_shared_project_returns_layouts(client):
    pid = await _create_project(client)
    token_resp = await client.post(f"/api/projects/{pid}/share", headers=HEADERS)
    token = token_resp.json()["token"]

    # No auth headers — public endpoint
    r = await client.get(f"/api/share/{token}")
    assert r.status_code == 200
    data = r.json()
    assert data["project"]["id"] == pid
    assert data["project"]["num_bedrooms"] == 2
    assert len(data["generate"]["layouts"]) >= 1
    # Initial approval status is null
    assert data["approval_status"] is None


async def test_get_shared_project_unknown_token_returns_404(client):
    r = await client.get("/api/share/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ── Client approval flow ───────────────────────────────────────────────────────

async def test_approve_shared_project(client):
    pid = await _create_project(client)
    token = (await client.post(f"/api/projects/{pid}/share", headers=HEADERS)).json()["token"]

    r = await client.post(
        f"/api/share/{token}/approve",
        json={"selected_layout_ids": ["A"]},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    # Verify via public GET
    shared = (await client.get(f"/api/share/{token}")).json()
    assert shared["approval_status"] == "approved"
    assert shared["approval_selected_layouts"] == ["A"]


async def test_request_changes_shared_project(client):
    pid = await _create_project(client)
    token = (await client.post(f"/api/projects/{pid}/share", headers=HEADERS)).json()["token"]

    r = await client.post(
        f"/api/share/{token}/request-changes",
        json={"note": "Please widen the master bedroom."},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "changes_requested"

    shared = (await client.get(f"/api/share/{token}")).json()
    assert shared["approval_status"] == "changes_requested"
    assert "master bedroom" in shared["approval_note"]


async def test_approve_unknown_token_returns_404(client):
    r = await client.post(
        "/api/share/00000000-0000-0000-0000-000000000000/approve",
        json={},
    )
    assert r.status_code == 404


# ── Engineer polls approval status ────────────────────────────────────────────

async def test_approval_status_endpoint(client):
    pid = await _create_project(client)
    token = (await client.post(f"/api/projects/{pid}/share", headers=HEADERS)).json()["token"]

    # Before any client action
    r = await client.get(f"/api/projects/{pid}/approval-status", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["approval_status"] is None

    # After client approves
    await client.post(f"/api/share/{token}/approve", json={"selected_layout_ids": ["B"]})
    r = await client.get(f"/api/projects/{pid}/approval-status", headers=HEADERS)
    data = r.json()
    assert data["approval_status"] == "approved"
    assert data["approval_selected_layouts"] == ["B"]


async def test_approval_status_wrong_user_returns_403(client):
    pid = await _create_project(client)
    r = await client.get(
        f"/api/projects/{pid}/approval-status",
        headers={"X-User-Id": OTHER_USER},
    )
    assert r.status_code == 403
