"""Regression tests: geometry input validation at the API boundary (C3)
and share-endpoint hardening (C2).

Degenerate inputs previously produced silently wrong geometry (negative
buildable areas, NaN through Shapely, cutouts larger than the plot).
"""

import json
import math

BASE = {
    "name": "Validation Test",
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

HDRS = {"X-Test-User-Id": "validator-user"}


async def _post(client, **overrides):
    return await client.post("/api/projects", json={**BASE, **overrides}, headers=HDRS)


class TestProjectGeometryValidation:
    async def test_valid_project_created(self, client):
        res = await _post(client)
        assert res.status_code == 201, res.text

    async def test_setbacks_consuming_width_rejected(self, client):
        res = await _post(client, setback_left=5.0, setback_right=5.0)
        assert res.status_code == 422

    async def test_setbacks_consuming_length_rejected(self, client):
        res = await _post(client, setback_front=8.0, setback_rear=7.0)
        assert res.status_code == 422

    async def test_nan_dimension_rejected(self, client):
        # httpx's json= refuses NaN, but json.dumps emits the bare NaN literal
        # (and Python's json parser accepts it) — that raw-body path is the
        # actual attack surface.
        body = json.dumps({**BASE, "plot_y_extent": math.nan})
        res = await client.post(
            "/api/projects",
            content=body,
            headers={**HDRS, "Content-Type": "application/json"},
        )
        assert res.status_code == 422

    async def test_absurd_dimension_rejected(self, client):
        res = await _post(client, plot_y_extent=10_000.0)
        assert res.status_code == 422

    async def test_invalid_plot_shape_rejected(self, client):
        res = await _post(client, plot_shape="hexagonal")
        assert res.status_code == 422

    async def test_l_shape_cutout_larger_than_plot_rejected(self, client):
        res = await _post(
            client, plot_shape="l_shaped", cutout_width=12.0, cutout_height=4.0
        )
        assert res.status_code == 422

    async def test_l_shape_zero_cutout_rejected(self, client):
        res = await _post(
            client, plot_shape="l_shaped", cutout_width=0.0, cutout_height=0.0
        )
        assert res.status_code == 422

    async def test_l_shape_valid_cutout_accepted(self, client):
        res = await _post(
            client,
            plot_shape="l_shaped",
            cutout_corner="NE",
            cutout_width=3.0,
            cutout_height=4.0,
        )
        assert res.status_code == 201, res.text

    async def test_invalid_cutout_corner_rejected(self, client):
        res = await _post(
            client,
            plot_shape="l_shaped",
            cutout_corner="XX",
            cutout_width=3.0,
            cutout_height=4.0,
        )
        assert res.status_code == 422

    async def test_quad_with_three_corners_rejected(self, client):
        res = await _post(
            client,
            plot_shape="quadrilateral",
            plot_corners=[[0, 0], [10, 0], [10, 15]],
        )
        assert res.status_code == 422

    async def test_degenerate_quad_rejected(self, client):
        # All four corners collinear — zero area
        res = await _post(
            client,
            plot_shape="quadrilateral",
            plot_corners=[[0, 0], [5, 0], [10, 0], [15, 0]],
        )
        assert res.status_code == 422

    async def test_valid_quad_accepted(self, client):
        res = await _post(
            client,
            plot_shape="quadrilateral",
            plot_corners=[[0, 0], [10, 0], [9.5, 15], [0, 14]],
        )
        assert res.status_code == 201, res.text

    async def test_trapezoid_without_widths_rejected(self, client):
        res = await _post(client, plot_shape="trapezoid")
        assert res.status_code == 422


class TestShareHardening:
    async def _project_and_token(self, client) -> tuple[str, str]:
        pid = (await _post(client)).json()["id"]
        token = (await client.post(f"/api/projects/{pid}/share", headers=HDRS)).json()[
            "token"
        ]
        return pid, token

    async def test_oversized_note_rejected(self, client):
        _, token = await self._project_and_token(client)
        res = await client.post(
            f"/api/share/{token}/request-changes", json={"note": "x" * 100_000}
        )
        assert res.status_code == 422

    async def test_reasonable_note_accepted(self, client):
        _, token = await self._project_and_token(client)
        res = await client.post(
            f"/api/share/{token}/request-changes", json={"note": "Make kitchen bigger"}
        )
        assert res.status_code == 200

    async def test_too_many_selected_layouts_rejected(self, client):
        _, token = await self._project_and_token(client)
        res = await client.post(
            f"/api/share/{token}/approve",
            json={"selected_layout_ids": [f"layout-{i}" for i in range(100)]},
        )
        assert res.status_code == 422

    async def test_owner_can_revoke_share_link(self, client):
        pid, token = await self._project_and_token(client)
        res = await client.delete(f"/api/projects/{pid}/share", headers=HDRS)
        assert res.status_code == 200
        # Old token no longer resolves
        res = await client.get(f"/api/share/{token}")
        assert res.status_code == 404

    async def test_outsider_cannot_revoke_share_link(self, client):
        pid, _ = await self._project_and_token(client)
        res = await client.delete(
            f"/api/projects/{pid}/share", headers={"X-Test-User-Id": "someone-else"}
        )
        assert res.status_code == 404
