"""Structural Drawing Set export route (GET /projects/{id}/export/structural-drawing-set).

Tests the error-path gates: checks approval + design requirements before export.
Happy-path (complete export with PDF verification) deferred to Task 14 due to
external structapi HTTP call requirements.
"""

from app.models.layout import StoredLayout

HDRS = {"X-Test-User-Id": "export-owner"}

PROJECT_BODY = {
    "name": "Export Test",
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

GRID_COLUMNS = [{"x": x, "y": y} for x in (0.0, 4.0, 8.0) for y in (0.0, 4.5)]

GEO_V1 = {
    "id": "A",
    "name": "Layout A",
    "ground_floor": {
        "floor": 0,
        "rooms": [
            {
                "id": "r1",
                "name": "Living",
                "type": "living",
                "x": 0.0,
                "y": 0.0,
                "width": 4.0,
                "depth": 3.5,
                "area": 14.0,
            },
            {
                "id": "r2",
                "name": "Kitchen",
                "type": "kitchen",
                "x": 4.0,
                "y": 0.0,
                "width": 2.5,
                "depth": 2.0,
                "area": 5.0,
            },
        ],
        "columns": GRID_COLUMNS,
    },
    "first_floor": {
        "floor": 1,
        "rooms": [
            {
                "id": "r3",
                "name": "Bedroom 1",
                "type": "bedroom",
                "x": 0.0,
                "y": 0.0,
                "width": 4.0,
                "depth": 3.5,
                "area": 14.0,
            }
        ],
        "columns": [],
    },
}


async def _make_project(client) -> str:
    res = await client.post("/api/projects", json=PROJECT_BODY, headers=HDRS)
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def _seed_layout(SessionLocal, project_id: str, geometry: dict) -> str:
    async with SessionLocal() as s:
        row = StoredLayout(
            project_id=project_id,
            layout_key="A",
            source="solver",
            geometry=geometry,
        )
        s.add(row)
        await s.commit()
        return row.id


# ──────────────────────────────────── Error paths ────────────────────────────────────


async def test_export_structural_drawing_set_409_not_approved(client_db):
    """Layout with no approved revision -> 409 with code 'not_approved'."""
    client, SessionLocal = client_db
    project_id = await _make_project(client)
    await _seed_layout(SessionLocal, project_id, GEO_V1)

    res = await client.get(
        f"/api/projects/{project_id}/export/structural-drawing-set",
        headers=HDRS,
    )
    assert res.status_code == 409, res.text
    body = res.json()
    assert body["detail"]["code"] == "not_approved"
    assert "Approve the architectural plan first" in body["detail"]["help"]


async def test_export_structural_drawing_set_409_not_designed(client_db):
    """Layout with approval but no structural design -> 409 with code 'not_designed'."""
    client, SessionLocal = client_db
    project_id = await _make_project(client)
    await _seed_layout(SessionLocal, project_id, GEO_V1)

    # Approve the layout
    res = await client.post(
        f"/api/projects/{project_id}/structural/approve",
        json={"layout_id": "A"},
        headers=HDRS,
    )
    assert res.status_code == 200, res.text

    # Try to export without running structural design
    res = await client.get(
        f"/api/projects/{project_id}/export/structural-drawing-set",
        headers=HDRS,
    )
    assert res.status_code == 409, res.text
    body = res.json()
    assert body["detail"]["code"] == "not_designed"
    assert "Run structural design first" in body["detail"]["help"]


async def test_export_structural_drawing_set_404_missing_layout(client_db):
    """Layout ID not found -> 404."""
    client, SessionLocal = client_db
    project_id = await _make_project(client)
    await _seed_layout(SessionLocal, project_id, GEO_V1)

    res = await client.get(
        f"/api/projects/{project_id}/export/structural-drawing-set?layout_id=Z",
        headers=HDRS,
    )
    assert res.status_code == 404, res.text
    assert "Layout 'Z' not found" in res.json()["detail"]
