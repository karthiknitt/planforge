"""Regression tests for persisted agent undo stacks — the DB-backed replacement
for rooms.py's in-memory _undo_stacks dict, which loses state across Cloud Run
scale-to-zero and isn't shared between instances."""

import pytest

from app.models.project import Project
from app.models.undo import UndoStack
from app.models.user import User
from app.services import layout_store

PROJECT_BODY = {
    "name": "Undo Persistence Test",
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


async def _seed_project_with_layout(sf, user_id: str) -> str:
    async with sf() as session:
        project = Project(user_id=user_id, **PROJECT_BODY)
        session.add(project)
        await session.commit()
        await layout_store.regenerate_and_store(project, session)
        return project.id


async def test_undo_survives_a_fresh_session(client_db):
    """Move a room, then undo through a DIFFERENT session — proves the stack
    is in the DB, not process memory (Cloud Run multi-instance safety)."""
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u1", "pro")
    project_id = await _seed_project_with_layout(SessionLocal, "u1")

    rooms = (
        await client.get(
            f"/api/projects/{project_id}/rooms", headers={"X-Test-User-Id": "u1"}
        )
    ).json()
    first = rooms[0]

    # Small shift within the inter-room gap (rooms are separated by a 0.115m
    # iwt gap in generated layouts — a larger delta collides with a neighbor).
    moved = await client.post(
        f"/api/projects/{project_id}/rooms/{first['id']}/move",
        json={"x": first["x"] + 0.05, "y": first["y"]},
        headers={"X-Test-User-Id": "u1"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["success"] is True

    # Fresh session, not the one the request used — proves the row is in the DB.
    async with SessionLocal() as session:
        row = await session.get(UndoStack, (project_id, "u1"))
        assert row is not None
        assert len(row.stack) == 1

    undone = await client.post(
        f"/api/projects/{project_id}/rooms/undo", headers={"X-Test-User-Id": "u1"}
    )
    assert undone.status_code == 200
    assert undone.json()["success"] is True

    after = (
        await client.get(
            f"/api/projects/{project_id}/rooms", headers={"X-Test-User-Id": "u1"}
        )
    ).json()
    match = next(r for r in after if r["id"] == first["id"])
    assert match["x"] == pytest.approx(first["x"])


async def test_undo_with_nothing_to_undo_returns_false(client_db):
    client, SessionLocal = client_db
    async with SessionLocal() as session:
        await _seed_user(session, "u2", "pro")
    project_id = await _seed_project_with_layout(SessionLocal, "u2")

    resp = await client.post(
        f"/api/projects/{project_id}/rooms/undo", headers={"X-Test-User-Id": "u2"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"success": False, "error": "Nothing to undo"}
