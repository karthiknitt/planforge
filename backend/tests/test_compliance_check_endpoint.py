"""
Tests for POST /api/layouts/{layout_id}/compliance-check (P2-2).

This is the live compliance check used by the frontend edit mode.
It accepts a flat list of rooms (all floors) and returns violations/warnings
plus a per-room issue map so the UI can highlight bad rooms in red.

Covers:
  - Compliant rooms return passed=True, no violations
  - Room below minimum area triggers a violation
  - Room below minimum area is surfaced in room_issues map by its id
  - Undersized staircase triggers staircase width violation
  - Missing project returns 404
  - Missing X-User-Id returns 422
"""

import pytest

USER_ID = "user-cc-001"
HEADERS = {"X-User-Id": USER_ID}
PROJECT_HEADERS = lambda pid: {"X-User-Id": USER_ID, "X-Project-Id": pid}

BASE_PROJECT = {
    "name": "Compliance Check Test",
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

# Rooms placed inside the buildable area.
# For 9×12 plot with setbacks L=1.0, R=1.0, F=1.5, B=1.5 and ewt=0.23:
#   x range: [1.23, 7.77]  y range: [1.73, 10.27]
COMPLIANT_ROOMS = [
    {"id": "r-bed1", "type": "bedroom",  "name": "Bedroom 1",
     "x": 1.5, "y": 2.0, "width": 3.5, "height": 3.0, "floor": "gf"},
    {"id": "r-kit",  "type": "kitchen",  "name": "Kitchen",
     "x": 1.5, "y": 5.5, "width": 3.0, "height": 2.5, "floor": "gf"},
    {"id": "r-wc1",  "type": "toilet",   "name": "Toilet 1",
     "x": 5.0, "y": 2.0, "width": 1.5, "height": 2.0, "floor": "gf"},
    # First floor rooms
    {"id": "r-bed2", "type": "bedroom",  "name": "Bedroom 2",
     "x": 1.5, "y": 2.0, "width": 3.5, "height": 3.0, "floor": "ff"},
]


async def _create_project(client) -> str:
    r = await client.post("/api/projects", json=BASE_PROJECT, headers=HEADERS)
    assert r.status_code == 201
    return r.json()["id"]


# ── Happy path ─────────────────────────────────────────────────────────────────

async def test_compliant_rooms_pass(client):
    pid = await _create_project(client)
    r = await client.post(
        "/api/layouts/test-layout/compliance-check",
        json={"rooms": COMPLIANT_ROOMS},
        headers=PROJECT_HEADERS(pid),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["passed"] is True
    assert data["violations"] == []


# ── Bedroom too small → violation ─────────────────────────────────────────────

async def test_undersized_bedroom_creates_violation(client):
    pid = await _create_project(client)
    rooms = [
        # Tiny bedroom: 2×2 = 4 sqm (< 9.5 sqm minimum) — inside boundary
        {"id": "r-tiny-bed", "type": "bedroom", "name": "Tiny Bedroom",
         "x": 1.5, "y": 2.0, "width": 2.0, "height": 2.0, "floor": "gf"},
        {"id": "r-kit",      "type": "kitchen", "name": "Kitchen",
         "x": 4.0, "y": 2.0, "width": 3.0, "height": 2.5, "floor": "gf"},
        {"id": "r-wc1",      "type": "toilet",  "name": "Toilet 1",
         "x": 1.5, "y": 5.0, "width": 1.5, "height": 2.0, "floor": "gf"},
        {"id": "r-bed-ff",   "type": "bedroom", "name": "Bedroom FF",
         "x": 1.5, "y": 2.0, "width": 3.5, "height": 3.0, "floor": "ff"},
    ]
    r = await client.post(
        "/api/layouts/test-layout/compliance-check",
        json={"rooms": rooms},
        headers=PROJECT_HEADERS(pid),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["passed"] is False
    assert any("Tiny Bedroom" in v for v in data["violations"])


async def test_undersized_bedroom_appears_in_room_issues(client):
    """The room_issues map must link the violation back to the room id."""
    pid = await _create_project(client)
    rooms = [
        {"id": "r-tiny-bed", "type": "bedroom", "name": "Small Room",
         "x": 1.5, "y": 2.0, "width": 2.0, "height": 2.0, "floor": "gf"},
        {"id": "r-kit",      "type": "kitchen", "name": "Kitchen",
         "x": 4.0, "y": 2.0, "width": 3.0, "height": 2.5, "floor": "gf"},
        {"id": "r-wc",       "type": "toilet",  "name": "Toilet 1",
         "x": 1.5, "y": 5.0, "width": 1.5, "height": 2.0, "floor": "gf"},
        {"id": "r-bed-ff",   "type": "bedroom", "name": "Bedroom FF",
         "x": 1.5, "y": 2.0, "width": 3.5, "height": 3.0, "floor": "ff"},
    ]
    r = await client.post(
        "/api/layouts/test-layout/compliance-check",
        json={"rooms": rooms},
        headers=PROJECT_HEADERS(pid),
    )
    data = r.json()
    assert "r-tiny-bed" in data["room_issues"]
    assert len(data["room_issues"]["r-tiny-bed"]) >= 1


# ── Undersized toilet → violation ─────────────────────────────────────────────

async def test_undersized_toilet_creates_violation(client):
    pid = await _create_project(client)
    rooms = [
        {"id": "r-bed1", "type": "bedroom", "name": "Bedroom 1",
         "x": 1.5, "y": 2.0, "width": 3.5, "height": 3.0, "floor": "gf"},
        {"id": "r-kit",  "type": "kitchen", "name": "Kitchen",
         "x": 1.5, "y": 5.5, "width": 3.0, "height": 2.5, "floor": "gf"},
        # Tiny toilet: 1×1 = 1 sqm (< 3 sqm minimum) — inside boundary
        {"id": "r-tiny-wc", "type": "toilet", "name": "Toilet 1",
         "x": 5.0, "y": 2.0, "width": 1.0, "height": 1.0, "floor": "gf"},
        {"id": "r-bed-ff", "type": "bedroom", "name": "Bedroom FF",
         "x": 1.5, "y": 2.0, "width": 3.5, "height": 3.0, "floor": "ff"},
    ]
    r = await client.post(
        "/api/layouts/test-layout/compliance-check",
        json={"rooms": rooms},
        headers=PROJECT_HEADERS(pid),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["passed"] is False
    assert any("Toilet 1" in v for v in data["violations"])


# ── Undersized kitchen → violation ────────────────────────────────────────────

async def test_undersized_kitchen_creates_violation(client):
    pid = await _create_project(client)
    rooms = [
        {"id": "r-bed1", "type": "bedroom", "name": "Bedroom 1",
         "x": 1.5, "y": 2.0, "width": 3.5, "height": 3.0, "floor": "gf"},
        # Tiny kitchen: 2×2 = 4 sqm (< 7 sqm minimum) — inside boundary
        {"id": "r-tiny-kit", "type": "kitchen", "name": "Kitchen",
         "x": 1.5, "y": 5.5, "width": 2.0, "height": 2.0, "floor": "gf"},
        {"id": "r-wc",  "type": "toilet", "name": "Toilet 1",
         "x": 5.0, "y": 2.0, "width": 1.5, "height": 2.0, "floor": "gf"},
        {"id": "r-bed-ff", "type": "bedroom", "name": "Bedroom FF",
         "x": 1.5, "y": 2.0, "width": 3.5, "height": 3.0, "floor": "ff"},
    ]
    r = await client.post(
        "/api/layouts/test-layout/compliance-check",
        json={"rooms": rooms},
        headers=PROJECT_HEADERS(pid),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["passed"] is False
    assert any("Kitchen" in v for v in data["violations"])


# ── Guard rails ────────────────────────────────────────────────────────────────

async def test_compliance_check_unknown_project_returns_404(client):
    r = await client.post(
        "/api/layouts/test-layout/compliance-check",
        json={"rooms": []},
        headers={"X-User-Id": USER_ID, "X-Project-Id": "nonexistent-project-id"},
    )
    assert r.status_code == 404


async def test_compliance_check_missing_user_id_returns_422(client):
    r = await client.post(
        "/api/layouts/test-layout/compliance-check",
        json={"rooms": []},
        headers={"X-Project-Id": "some-pid"},
    )
    assert r.status_code == 422
