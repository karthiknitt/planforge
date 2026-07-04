"""GET /projects/{id}/layouts/{layout_id}/quality returns the deterministic CCQS."""

HDRS = {"X-Test-User-Id": "quality-owner"}

PROJECT_BODY = {
    "name": "Quality Endpoint Test",
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


async def _make_project_with_layout(client) -> tuple[str, str]:
    res = await client.post("/api/projects", json=PROJECT_BODY, headers=HDRS)
    assert res.status_code == 201, res.text
    project_id = res.json()["id"]

    gen = await client.get(f"/api/projects/{project_id}/generate", headers=HDRS)
    assert gen.status_code == 200, gen.text
    layout_id = gen.json()["layouts"][0]["id"]
    return project_id, layout_id


async def test_quality_endpoint_scores_stored_layout(client):
    project_id, layout_id = await _make_project_with_layout(client)

    resp = await client.get(
        f"/api/projects/{project_id}/layouts/{layout_id}/quality", headers=HDRS
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["max"] == 80
    assert 0 <= body["total"] <= 80
    for key in (
        "monochrome",
        "dimension_density",
        "ft_in_labels",
        "layout_completeness",
    ):
        assert key in body


async def test_quality_endpoint_404_for_unknown_layout(client):
    project_id, _ = await _make_project_with_layout(client)

    resp = await client.get(
        f"/api/projects/{project_id}/layouts/nope/quality", headers=HDRS
    )
    assert resp.status_code == 404
