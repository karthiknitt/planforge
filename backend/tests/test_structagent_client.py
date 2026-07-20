"""Tests for structagent_client.calc_beam."""

import httpx
import pytest

from app.services import structagent_client


@pytest.mark.asyncio
async def test_calc_beam_posts_to_calc_beam_endpoint(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "ok": True,
                "checks": [{"name": "flexure", "ok": True}],
                "data": {"design": {"n_bars": 3, "bar_dia": 12}},
                "artifacts": [],
                "disclaimer": "verify against official BIS copies",
            },
        )

    monkeypatch.setattr(
        structagent_client.settings, "structural_api_url", "http://fake"
    )
    monkeypatch.setattr(
        structagent_client, "_transport_for_tests", httpx.MockTransport(handler)
    )

    result = await structagent_client.calc_beam(
        {
            "span_m": 3.5,
            "w_dl_kn_m": 12.65,
            "w_il_kn_m": 0.0,
            "b": 230,
            "D": 300,
            "fck": 20,
            "fy": 500,
        }
    )

    assert result.ok is True
    assert "v1/calc/beam" in seen["url"]
    assert result.data["design"]["n_bars"] == 3
