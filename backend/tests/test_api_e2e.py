"""
End-to-end API workflow tests.

Covers the complete user journey against an in-memory SQLite database:
  create project → list projects → generate layouts → export PDF (all 3 layouts)
  plus auth isolation and error-path assertions.
"""

USER_ID = "user-e2e-001"
HEADERS = {"X-User-Id": USER_ID}

# A valid 9 m × 12 m residential plot — same as the engine test suite
BASE_PAYLOAD = {
    "name": "E2E Test Plot",
    "plot_length": 12.0,
    "plot_width": 9.0,
    "setback_front": 1.5,
    "setback_rear": 1.5,
    "setback_left": 1.0,
    "setback_right": 1.0,
    "road_side": "S",
    "north_direction": "N",
    "bhk": 2,
    "toilets": 2,
    "parking": False,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_project(client, payload=None):
    r = await client.post(
        "/api/projects", json=payload or BASE_PAYLOAD, headers=HEADERS
    )
    assert r.status_code == 201
    return r.json()["id"]


# ── Main workflow ─────────────────────────────────────────────────────────────

async def test_health_check(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_create_and_list_project(client):
    r = await client.post("/api/projects", json=BASE_PAYLOAD, headers=HEADERS)
    assert r.status_code == 201
    data = r.json()
    assert data["user_id"] == USER_ID
    assert data["name"] == "E2E Test Plot"
    assert data["bhk"] == 2
    project_id = data["id"]

    r = await client.get("/api/projects", headers=HEADERS)
    assert r.status_code == 200
    assert any(p["id"] == project_id for p in r.json())


async def test_generate_layouts(client):
    project_id = await _create_project(client)

    r = await client.get(f"/api/projects/{project_id}/generate", headers=HEADERS)
    assert r.status_code == 200

    gen = r.json()
    assert gen["project_id"] == project_id
    assert len(gen["layouts"]) == 3
    assert {lay["id"] for lay in gen["layouts"]} == {"A", "B", "C"}

    for lay in gen["layouts"]:
        assert len(lay["ground_floor"]["rooms"]) > 0, f"Layout {lay['id']} has no ground floor rooms"
        assert len(lay["first_floor"]["rooms"]) > 0, f"Layout {lay['id']} has no first floor rooms"
        assert len(lay["ground_floor"]["columns"]) > 0, f"Layout {lay['id']} has no columns"


async def test_export_pdf_all_layouts(client):
    project_id = await _create_project(client)

    for layout_id in ["A", "B", "C"]:
        r = await client.get(
            f"/api/projects/{project_id}/export/pdf?layout_id={layout_id}",
            headers=HEADERS,
        )
        assert r.status_code == 200, f"Expected 200 for layout {layout_id}, got {r.status_code}"
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF", f"Layout {layout_id} response is not a valid PDF"
        assert (
            r.headers["content-disposition"]
            == f'attachment; filename="planforge-{project_id}-layout-{layout_id}.pdf"'
        )
        # A proper 2-page PDF should be at least 5 KB
        assert len(r.content) > 5_000, f"PDF for layout {layout_id} is suspiciously small ({len(r.content)} bytes)"


async def test_full_workflow(client):
    """Single test that exercises every step in order."""
    # 1. Create
    project_id = await _create_project(client)

    # 2. Generate
    r = await client.get(f"/api/projects/{project_id}/generate", headers=HEADERS)
    assert r.status_code == 200
    layouts = r.json()["layouts"]
    assert len(layouts) == 3

    # 3. Export default layout (A)
    r = await client.get(f"/api/projects/{project_id}/export/pdf", headers=HEADERS)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"

    # 4. Auth isolation
    other = {"X-User-Id": "someone-else"}
    assert (await client.get(f"/api/projects/{project_id}/generate", headers=other)).status_code == 404
    assert (await client.get(f"/api/projects/{project_id}/export/pdf", headers=other)).status_code == 404

    # 5. Non-existent project
    assert (await client.get("/api/projects/no-such-id/export/pdf", headers=HEADERS)).status_code == 404
    assert (await client.get("/api/projects/no-such-id/generate", headers=HEADERS)).status_code == 404


# ── Error paths ───────────────────────────────────────────────────────────────

async def test_missing_user_id_returns_422(client):
    r = await client.get("/api/projects")
    assert r.status_code == 422


async def test_invalid_layout_id_returns_404(client):
    project_id = await _create_project(client)
    r = await client.get(
        f"/api/projects/{project_id}/export/pdf?layout_id=Z", headers=HEADERS
    )
    assert r.status_code == 404


async def test_validation_rejects_bad_payload(client):
    bad = {**BASE_PAYLOAD, "bhk": 4}  # bhk must be 2 or 3
    r = await client.post("/api/projects", json=bad, headers=HEADERS)
    assert r.status_code == 422


# ── BHK variants ─────────────────────────────────────────────────────────────

async def test_3bhk_project(client):
    payload = {**BASE_PAYLOAD, "name": "3BHK Plot", "bhk": 3, "toilets": 3, "parking": True}
    project_id = await _create_project(client, payload)

    r = await client.get(f"/api/projects/{project_id}/generate", headers=HEADERS)
    assert r.status_code == 200

    for lay in r.json()["layouts"]:
        ground_types = {rm["type"] for rm in lay["ground_floor"]["rooms"]}
        first_types = {rm["type"] for rm in lay["first_floor"]["rooms"]}
        all_types = ground_types | first_types
        # Bedrooms land on the first floor; kitchen + living on the ground floor
        assert "bedroom" in first_types
        assert "kitchen" in ground_types
        assert "living" in all_types

    # PDF export still works for 3BHK
    r = await client.get(f"/api/projects/{project_id}/export/pdf", headers=HEADERS)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
