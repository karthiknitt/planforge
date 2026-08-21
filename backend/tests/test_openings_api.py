"""Opening-level API endpoints (Phase 7 / Task 30 backend half).

The agent tools move/resize/remove existing openings and add new ones via
`OpeningOverride` / `AddedOpening` deltas stored on the persisted layout —
derivation stays pure and undo snapshots ride the same state dict as room
edits. Infeasible requests are rejected with a machine-readable reason and,
where one exists, a feasible alternative; never silently applied.
"""

from urllib.parse import quote

from app.engine.models import (
    ComplianceResult,
    FloorPlan,
    Layout,
)
from app.models.layout import StoredLayout
from app.models.project import Project
from app.models.user import User
from app.services.layout_store import layout_out_from_engine

from tests.test_plan_geometry import _room

PROJECT_BODY = {
    "name": "Openings API Test",
    "plot_length": 15.0,
    "plot_width": 9.0,
    "setback_front": 1.5,
    "setback_rear": 1.0,
    "setback_left": 1.0,
    "setback_right": 1.0,
    "road_side": "S",
    "north_direction": "N",
    "num_bedrooms": 2,
    "toilets": 1,
    "parking": False,
}

USER = "u-openings"


async def _seed(client_db):
    """Seed a pro user + project + a stored layout. The persisted geometry is
    rooms-only; every endpoint derives the drawing from the project's own
    PlotConfig, so listing/edit ids stay self-consistent per request.

    Returns (client, project_id).
    """
    client, SessionLocal = client_db
    async with SessionLocal() as s:
        s.add(User(id=USER, plan_tier="pro"))
        project = Project(user_id=USER, **PROJECT_BODY)
        s.add(project)
        await s.commit()
        project_id = project.id
        lay = Layout(
            id="A",
            name="Seeded",
            ground_floor=FloorPlan(
                floor=0,
                floor_type="ground",
                rooms=[
                    _room("a", 1.23, 7.73, 3.155, 6.04),
                    _room("b", 4.5, 7.73, 3.27, 6.04),
                    _room("c", 1.23, 1.73, 3.155, 5.885),
                    _room("d", 4.5, 1.73, 3.27, 5.885),
                ],
            ),
            first_floor=FloorPlan(floor=1, floor_type="first", rooms=[]),
            compliance=ComplianceResult(passed=True),
        )
        s.add(
            StoredLayout(
                project_id=project_id,
                layout_key="A",
                source="solver",
                geometry=layout_out_from_engine(lay).model_dump(mode="json"),
            )
        )
        await s.commit()
    return client, project_id


def _hdrs() -> dict[str, str]:
    return {"X-Test-User-Id": USER}


async def test_list_openings_returns_ids_kinds_and_positions(client_db):
    client, project_id = await _seed(client_db)
    res = await client.get(
        f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["floor"] == "gf"
    # exact count is a function of the seeded project's derived rules; the
    # invariants that matter are door+window presence and well-formed ids
    kinds = {o["kind"] for o in data["openings"]}
    assert "door" in kinds and "window" in kinds
    assert len(data["openings"]) >= 8
    win = next(o for o in data["openings"] if o["kind"] == "window")
    assert win["id"].startswith("w:")
    assert win["mark"].startswith("W")
    assert win["cx"] > 0 and win["cy"] > 0
    assert win["width"] > 0
    assert win["along"] >= 0
    assert win["wall_length"] > win["along"]
    assert data["openings"][0]["rooms"]


async def test_move_window_persists_and_reports_coordinates(client_db):
    client, project_id = await _seed(client_db)
    listed = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    win = next(o for o in listed if o["kind"] == "window" and not o["is_horizontal"])

    res = await client.post(
        f"/api/projects/{project_id}/openings/{quote(win['id'], safe='')}/move",
        json={"floor": "gf", "along": 5.0},
        headers=_hdrs(),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["operation"] == "move_window"
    assert body["changes"]["along"] == 5.0
    wall_lo = win["cy"] - win["along"]
    assert abs(body["changes"]["cy"] - (wall_lo + 5.0)) < 1e-6
    assert win["id"] in body["affected_entities"]
    assert body["validation"]["status"] == "passed"

    relisted = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    win2 = next(o for o in relisted if o["id"] == win["id"])
    assert win2["along"] == 5.0


async def test_move_off_span_is_rejected_with_alternative(client_db):
    client, project_id = await _seed(client_db)
    listed = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    win = next(o for o in listed if o["kind"] == "window")

    res = await client.post(
        f"/api/projects/{project_id}/openings/{quote(win['id'], safe='')}/move",
        json={"floor": "gf", "along": win["wall_length"] + 5.0},
        headers=_hdrs(),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is False
    assert body["operation"] == "move_window"
    assert "outside its host wall" in body["reason"]
    assert body["alternative"]["min_along"] == win["width"] / 2
    assert body["alternative"]["max_along"] == win["wall_length"] - win["width"] / 2

    # nothing was written
    relisted = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    assert [o["id"] for o in relisted] == [o["id"] for o in listed]


async def test_resize_window_persists_new_width(client_db):
    client, project_id = await _seed(client_db)
    listed = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    win = next(o for o in listed if o["kind"] == "window")

    res = await client.post(
        f"/api/projects/{project_id}/openings/{quote(win['id'], safe='')}/resize",
        json={"floor": "gf", "width": 0.75},
        headers=_hdrs(),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["operation"] == "resize_window"
    assert body["changes"]["width"] == 0.75
    assert body["changes"]["cx"] == win["cx"]
    assert body["changes"]["cy"] == win["cy"]

    relisted = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    assert next(o for o in relisted if o["id"] == win["id"])["width"] == 0.75


async def test_unknown_opening_id_is_a_structured_error_not_a_500(client_db):
    client, project_id = await _seed(client_db)
    ghost = quote("w:v:i:a>b@4.44:7.67-13.88#9.999", safe="")
    for method, suffix, kwargs in (
        ("post", "/move", {"json": {"floor": "gf", "along": 1.0}}),
        ("post", "/resize", {"json": {"floor": "gf", "width": 0.8}}),
        ("delete", "", {"params": {"floor": "gf"}}),
    ):
        res = await getattr(client, method)(
            f"/api/projects/{project_id}/openings/{ghost}{suffix}",
            headers=_hdrs(),
            **kwargs,
        )
        assert res.status_code == 404, res.text
        assert res.json()["detail"]["code"] == "opening_not_found"


async def test_remove_only_door_disconnecting_a_room_is_rejected(client_db):
    client, project_id = await _seed(client_db)
    listed = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    # room c has exactly one door (to a): removing it disconnects c
    door_ca = next(o for o in listed if o["id"].startswith("w:h:i:c>a@"))

    res = await client.delete(
        f"/api/projects/{project_id}/openings/{quote(door_ca['id'], safe='')}",
        params={"floor": "gf"},
        headers=_hdrs(),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is False
    assert body["operation"] == "remove_opening"
    assert "c (bedroom) is not reachable" in body["reason"]
    # c and d share an unused wall, and d is reachable via the main entrance:
    # the rejection must come with a feasible alternative.
    alt = body["alternative"]
    assert alt is not None
    assert alt["operation"] == "add_door"
    assert alt["room_id"] == "c"
    assert alt["to_room_id"] == "d"
    assert alt["along"] > 0

    relisted = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    assert any(o["id"] == door_ca["id"] for o in relisted)


async def test_add_door_then_remove_original_round_trips(client_db):
    client, project_id = await _seed(client_db)
    n_before = len(
        (
            await client.get(
                f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
            )
        ).json()["openings"]
    )

    add = await client.post(
        f"/api/projects/{project_id}/openings/doors",
        json={"floor": "gf", "room_id": "c", "to_room_id": "d"},
        headers=_hdrs(),
    )
    assert add.status_code == 200, add.text
    added = add.json()
    assert added["success"] is True
    assert added["operation"] == "add_door"
    new_id = added["changes"]["opening_id"]
    assert new_id.startswith("w:v:i:c>d@")
    assert added["validation"]["status"] == "passed"

    listed = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    assert len(listed) == n_before + 1
    new_door = next(o for o in listed if o["id"] == new_id)
    assert new_door["kind"] == "door"
    assert sorted(new_door["rooms"]) == ["c", "d"]

    # c now has two doors, so the original c>a door can be removed
    door_ca = next(o for o in listed if o["id"].startswith("w:h:i:c>a@"))
    rem = await client.delete(
        f"/api/projects/{project_id}/openings/{quote(door_ca['id'], safe='')}",
        params={"floor": "gf"},
        headers=_hdrs(),
    )
    assert rem.status_code == 200, rem.text
    body = rem.json()
    assert body["success"] is True
    assert body["validation"]["status"] == "passed"

    relisted = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    assert not any(o["id"] == door_ca["id"] for o in relisted)
    assert any(o["id"] == new_id for o in relisted)


async def test_add_door_validation_failure_is_structured(client_db):
    client, project_id = await _seed(client_db)
    res = await client.post(
        f"/api/projects/{project_id}/openings/doors",
        json={"floor": "gf", "room_id": "a", "to_room_id": "d"},
        headers=_hdrs(),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is False
    assert "share no wall" in body["reason"]


async def test_opening_edits_are_undoable(client_db):
    client, project_id = await _seed(client_db)
    listed = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    win = next(o for o in listed if o["kind"] == "window" and not o["is_horizontal"])
    old_cy = win["cy"]

    move = await client.post(
        f"/api/projects/{project_id}/openings/{quote(win['id'], safe='')}/move",
        json={"floor": "gf", "along": 5.0},
        headers=_hdrs(),
    )
    assert move.json()["success"] is True

    undo = await client.post(f"/api/projects/{project_id}/rooms/undo", headers=_hdrs())
    assert undo.status_code == 200, undo.text

    relisted = (
        await client.get(
            f"/api/projects/{project_id}/openings?floor=gf", headers=_hdrs()
        )
    ).json()["openings"]
    assert next(o for o in relisted if o["id"] == win["id"])["cy"] == old_cy


async def test_free_tier_is_rejected(client_db):
    client, SessionLocal = client_db
    async with SessionLocal() as s:
        s.add(User(id="u-free", plan_tier="free"))
        project = Project(user_id="u-free", **PROJECT_BODY)
        s.add(project)
        await s.commit()
        pid = project.id
    res = await client.get(
        f"/api/projects/{pid}/openings?floor=gf",
        headers={"X-Test-User-Id": "u-free"},
    )
    assert res.status_code == 403
