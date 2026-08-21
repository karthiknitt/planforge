"""BOQ route (Stage 2.6): structural line items are replaced with IS-code
designed quantities when a persisted StructuralDesign exists for the
layout's current approved revision, and left as rule-of-thumb estimates
(with basis="estimated" + preliminary=true) otherwise.

Mirrors test_structural_revisions.py's client_db + seeded StoredLayout
pattern -- never runs the solver or calls structapi in these tests.
"""

from app.models.layout import StoredLayout
from app.services import structural_store

HDRS = {"X-Test-User-Id": "boq-owner"}

PROJECT_BODY = {
    "name": "BOQ Design Test",
    "plot_y_extent": 15.0,
    "plot_x_extent": 10.0,
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

GRID_COLUMNS = [{"x": x, "y": y} for x in (0.0, 4.0, 8.0) for y in (0.0, 4.5)]

GEOMETRY = {
    "id": "A",
    "name": "Layout A",
    "ground_floor": {"floor": 0, "rooms": [], "columns": GRID_COLUMNS},
    "first_floor": {"floor": 1, "rooms": [], "columns": []},
}

QUANTITIES = {
    "concrete_m3": {
        "slabs": 12.5,
        "beams": 4.2,
        "columns": 3.1,
        "footings": 5.6,
        "total": 25.4,
    },
    "steel_kg": {
        "slabs": 800.0,
        "beams": 300.0,
        "columns": 200.0,
        "footings": 150.0,
        "total": 1450.0,
    },
    "grade": "M25 / Fe500",
}


async def _make_project(client) -> str:
    res = await client.post("/api/projects", json=PROJECT_BODY, headers=HDRS)
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def _seed_layout(SessionLocal, project_id: str, geometry: dict) -> None:
    async with SessionLocal() as s:
        s.add(
            StoredLayout(
                project_id=project_id,
                layout_key="A",
                source="solver",
                geometry=geometry,
            )
        )
        await s.commit()


async def test_boq_no_design_is_preliminary(client_db):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEOMETRY)

    res = await client.get(
        f"/api/projects/{pid}/boq", params={"layout_id": "A"}, headers=HDRS
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["preliminary"] is True
    assert body["basis_summary"]["designed_items"] == 0
    assert all(item["basis"] == "estimated" for item in body["items"])


async def test_boq_with_persisted_design_uses_designed_quantities(client_db):
    client, SessionLocal = client_db
    pid = await _make_project(client)
    await _seed_layout(SessionLocal, pid, GEOMETRY)

    async with SessionLocal() as s:
        revision, _ = await structural_store.approve_layout(
            pid, "A", GEOMETRY, "boq-owner", s
        )
        await structural_store.persist_design(
            revision,
            s,
            status="designed",
            structapi_response={
                "ok": True,
                "checks": [],
                "data": {"quantities": QUANTITIES},
                "disclaimer": "verify against official BIS copies",
            },
            changelog=[],
        )

    res = await client.get(
        f"/api/projects/{pid}/boq", params={"layout_id": "A"}, headers=HDRS
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["preliminary"] is False
    designed = {
        item["item"]: item for item in body["items"] if item["basis"] == "designed"
    }
    assert designed["3"]["quantity"] == 12.5
    assert designed["5"]["quantity"] == 1450.0
