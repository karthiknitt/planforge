"""The agent-chat path must never invoke the CP-SAT solver.

`_load_layout_state` used to solve-and-persist on a store miss, so a single
agent tool call on a project with no stored layouts ran up to 3 CP-SAT solves
(~15s). Combined with a Cloud Run cold start (~23s measured), that blew past
the frontend fetch budget and surfaced as a "connection error". The agent path
is now read-only: a store miss returns 409 {code: no_layouts} instead of
generating, and generation stays an explicit action.
"""

import pytest

from app.models.project import Project
from app.models.user import User
from app.services import layout_store

PROJECT_BODY = {
    "name": "Agent No-Solve Test",
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


async def _seed_user(sf, user_id: str, plan_tier: str = "pro") -> None:
    async with sf() as session:
        session.add(User(id=user_id, plan_tier=plan_tier))
        await session.commit()


async def _seed_project(sf, user_id: str, with_layout: bool) -> str:
    async with sf() as session:
        project = Project(user_id=user_id, **PROJECT_BODY)
        session.add(project)
        await session.commit()
        if with_layout:
            await layout_store.regenerate_and_store(project, session)
        return project.id


async def test_agent_endpoint_returns_409_when_no_layouts(client_db):
    """GET /rooms on a project with no stored layouts returns a structured
    409 the frontend can distinguish, not a solver run."""
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u-nolayout")
    project_id = await _seed_project(SessionLocal, "u-nolayout", with_layout=False)

    res = await client.get(
        f"/api/projects/{project_id}/rooms", headers={"X-Test-User-Id": "u-nolayout"}
    )

    assert res.status_code == 409, res.text
    assert res.json() == {
        "detail": {"code": "no_layouts", "help": "Generate layouts first"}
    }


async def test_agent_endpoint_does_not_invoke_solver(client_db, monkeypatch):
    """The agent path must not call the solver on a miss — monkeypatch both
    generate entrypoints to explode if touched."""
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u-nosolve")
    project_id = await _seed_project(SessionLocal, "u-nosolve", with_layout=False)

    def _boom(*a, **k):
        raise AssertionError("solver invoked from the agent path")

    monkeypatch.setattr(layout_store, "regenerate_and_store", _boom)
    monkeypatch.setattr(layout_store, "get_or_generate_layouts", _boom)

    res = await client.get(
        f"/api/projects/{project_id}/rooms", headers={"X-Test-User-Id": "u-nosolve"}
    )
    assert res.status_code == 409, res.text


@pytest.mark.parametrize(
    "path",
    [
        "rooms",
        "rooms/layout-state",
        "compliance",
        "available-space",
    ],
)
async def test_agent_read_endpoints_409_without_layouts(client_db, path):
    """Every read-only agent endpoint that loads layout state returns 409,
    not 422/500, when nothing has been generated yet."""
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u-multi")
    project_id = await _seed_project(SessionLocal, "u-multi", with_layout=False)

    res = await client.get(
        f"/api/projects/{project_id}/{path}", headers={"X-Test-User-Id": "u-multi"}
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["code"] == "no_layouts"


async def test_agent_endpoint_works_when_layouts_exist(client_db):
    """With layouts stored, the agent path behaves exactly as before —
    listing rooms returns the persisted geometry."""
    client, SessionLocal = client_db
    await _seed_user(SessionLocal, "u-haslayout")
    project_id = await _seed_project(SessionLocal, "u-haslayout", with_layout=True)

    res = await client.get(
        f"/api/projects/{project_id}/rooms", headers={"X-Test-User-Id": "u-haslayout"}
    )
    assert res.status_code == 200, res.text
    rooms = res.json()
    assert isinstance(rooms, list)
    assert len(rooms) >= 1
    assert "id" in rooms[0]
