"""
End-to-end API workflow tests.

Covers the complete user journey against an in-memory SQLite database:
  create project → list projects → generate layouts → export PDF
  plus auth isolation and error-path assertions.
"""

USER_ID = "user-e2e-001"
HEADERS = {"X-User-Id": USER_ID}

# A valid 9 m × 12 m residential plot
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
    "num_bedrooms": 2,
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
    assert data["num_bedrooms"] == 2
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
    # Should get A, B, C at minimum for a valid plot
    assert len(gen["layouts"]) >= 3
    layout_ids = {lay["id"] for lay in gen["layouts"]}
    assert {"A", "B", "C"}.issubset(layout_ids)

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
        assert len(r.content) > 5_000, f"PDF for layout {layout_id} is suspiciously small ({len(r.content)} bytes)"


async def test_full_workflow(client):
    """Single test that exercises every step in order."""
    # 1. Create
    project_id = await _create_project(client)

    # 2. Generate
    r = await client.get(f"/api/projects/{project_id}/generate", headers=HEADERS)
    assert r.status_code == 200
    layouts = r.json()["layouts"]
    assert len(layouts) >= 3

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
    bad = {**BASE_PAYLOAD, "num_bedrooms": 5}  # num_bedrooms must be 1–4
    r = await client.post("/api/projects", json=bad, headers=HEADERS)
    assert r.status_code == 422


# ── Fix regression tests ──────────────────────────────────────────────────────

async def test_plot_below_minimum_rejected(client):
    """Schema rejects plots smaller than 5 m on either dimension."""
    bad = {**BASE_PAYLOAD, "plot_length": 4.9}
    r = await client.post("/api/projects", json=bad, headers=HEADERS)
    assert r.status_code == 422


async def test_non_compliant_plot_returns_no_layouts(client):
    """Generate returns empty list when all archetypes fail compliance.

    A 5 m × 5 m plot with zero setbacks has 100% floor coverage (> 70% limit),
    so every archetype fails and no layouts are returned.
    """
    tiny_payload = {
        **BASE_PAYLOAD,
        "name": "Non-Compliant Plot",
        "plot_length": 5.0,
        "plot_width": 5.0,
        "setback_front": 0.0,
        "setback_rear": 0.0,
        "setback_left": 0.0,
        "setback_right": 0.0,
    }
    project_id = await _create_project(client, tiny_payload)
    r = await client.get(f"/api/projects/{project_id}/generate", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["layouts"] == []


async def test_rooms_respect_wall_thickness(client):
    """Room coordinates are offset from setback lines by EWT from JSON.

    EWT from compliance_rules.json is 230 mm = 0.23 m.
    With setback_left = 1.0 m the leftmost room x must be >= 1.23 m.
    """
    project_id = await _create_project(client)
    r = await client.get(f"/api/projects/{project_id}/generate", headers=HEADERS)
    assert r.status_code == 200
    layouts = r.json()["layouts"]
    assert len(layouts) > 0

    ewt = 0.23
    expected_min_x = BASE_PAYLOAD["setback_left"] + ewt
    expected_min_y = BASE_PAYLOAD["setback_front"] + ewt

    for lay in layouts:
        all_rooms = lay["ground_floor"]["rooms"] + lay["first_floor"]["rooms"]
        for room in all_rooms:
            assert room["x"] >= expected_min_x - 0.01, (
                f"Layout {lay['id']} room '{room['name']}': "
                f"x={room['x']:.3f} < expected min {expected_min_x:.3f}"
            )
            assert room["y"] >= expected_min_y - 0.01, (
                f"Layout {lay['id']} room '{room['name']}': "
                f"y={room['y']:.3f} < expected min {expected_min_y:.3f}"
            )


# ── BHK variants ─────────────────────────────────────────────────────────────

async def test_1bhk_project(client):
    payload = {**BASE_PAYLOAD, "name": "1BHK Plot", "num_bedrooms": 1, "toilets": 1}
    project_id = await _create_project(client, payload)
    r = await client.get(f"/api/projects/{project_id}/generate", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()["layouts"]) >= 1


async def test_3bhk_project(client):
    payload = {**BASE_PAYLOAD, "name": "3BHK Plot", "num_bedrooms": 3,
               "toilets": 3, "parking": True}
    project_id = await _create_project(client, payload)

    r = await client.get(f"/api/projects/{project_id}/generate", headers=HEADERS)
    assert r.status_code == 200

    for lay in r.json()["layouts"]:
        ground_types = {rm["type"] for rm in lay["ground_floor"]["rooms"]}
        first_types  = {rm["type"] for rm in lay["first_floor"]["rooms"]}
        all_types    = ground_types | first_types
        assert "bedroom" in first_types
        assert "kitchen" in ground_types
        assert "living" in all_types

    r = await client.get(f"/api/projects/{project_id}/export/pdf", headers=HEADERS)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


async def test_4bhk_project(client):
    payload = {**BASE_PAYLOAD, "name": "4BHK Plot", "num_bedrooms": 4, "toilets": 4}
    project_id = await _create_project(client, payload)
    r = await client.get(f"/api/projects/{project_id}/generate", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()["layouts"]) >= 1


async def test_optional_rooms(client):
    payload = {
        **BASE_PAYLOAD,
        "name": "Pooja+Study",
        "num_bedrooms": 3,
        "has_pooja": True,
        "has_study": True,
        "has_balcony": True,
    }
    project_id = await _create_project(client, payload)
    r = await client.get(f"/api/projects/{project_id}/generate", headers=HEADERS)
    assert r.status_code == 200


async def test_city_selector(client):
    payload = {**BASE_PAYLOAD, "name": "Bangalore Plot", "city": "bangalore"}
    project_id = await _create_project(client, payload)
    r = await client.get(f"/api/projects/{project_id}/generate", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    # May have FAR warning but should still generate layouts
    for lay in data["layouts"]:
        assert lay["compliance"]["passed"] is True
