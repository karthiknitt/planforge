import base64
import json

import httpx
import pytest

from app.services.render_providers import (
    RenderProviderError,
    RenderResult,
    render_image,
)

FAKE_PNG = b"\x89PNG\r\n\x1a\nfakepixels"
FAKE_B64 = base64.b64encode(FAKE_PNG).decode()


def _transport(handler):
    return httpx.MockTransport(handler)


async def test_gemini_happy_path(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "generativelanguage.googleapis.com" in str(request.url)
        assert request.headers["x-goog-api-key"] == "k"
        body = json.loads(request.content)
        parts = body["contents"][0]["parts"]
        assert any("inline_data" in p for p in parts)
        assert any("text" in p for p in parts)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inline_data": {
                                        "mime_type": "image/png",
                                        "data": FAKE_B64,
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        )

    import app.services.render_providers as rp

    monkeypatch.setattr(rp, "_transport_for_tests", _transport(handler))
    result = await render_image("prompt", FAKE_PNG, "gemini", api_key="k")
    assert isinstance(result, RenderResult)
    assert result.image_png == FAKE_PNG
    assert result.provider == "gemini"


async def test_openai_happy_path(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "api.openai.com" in str(request.url)
        assert request.headers["Authorization"] == "Bearer k"
        # Multipart field name is `image[]` (bracketed array), per current
        # OpenAI docs — not the bare `image` singular field.
        assert b'name="image[]"' in request.content
        assert b'name="prompt"' in request.content
        # gpt-image-2 high-fidelity defaults: explicit size + quality.
        assert b'name="model"\r\n\r\ngpt-image-2' in request.content
        assert b'name="size"\r\n\r\n1280x800' in request.content
        assert b'name="quality"\r\n\r\nhigh' in request.content
        return httpx.Response(
            200,
            json={"data": [{"b64_json": FAKE_B64}]},
        )

    import app.services.render_providers as rp

    monkeypatch.setattr(rp, "_transport_for_tests", _transport(handler))
    result = await render_image("prompt", FAKE_PNG, "openai", api_key="k")
    assert result.image_png == FAKE_PNG
    assert result.provider == "openai"


async def test_openrouter_happy_path(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "openrouter.ai" in str(request.url)
        assert request.headers["Authorization"] == "Bearer k"
        body = json.loads(request.content)
        assert body["prompt"] == "prompt"
        ref = body["input_references"][0]
        assert ref["type"] == "image_url"
        assert ref["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            json={
                "created": 123,
                "data": [{"b64_json": FAKE_B64}],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 10,
                    "total_tokens": 10,
                    "cost": 0.041,
                },
            },
        )

    import app.services.render_providers as rp

    monkeypatch.setattr(rp, "_transport_for_tests", _transport(handler))
    result = await render_image("prompt", FAKE_PNG, "openrouter", api_key="k")
    assert result.image_png == FAKE_PNG
    assert result.cost_usd == 0.041


async def test_provider_error_raises_readable_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}})

    import app.services.render_providers as rp

    monkeypatch.setattr(rp, "_transport_for_tests", _transport(handler))
    with pytest.raises(RenderProviderError, match="gemini"):
        await render_image("prompt", FAKE_PNG, "gemini", api_key="k")


async def test_unknown_provider_raises():
    with pytest.raises(RenderProviderError, match="unknown provider"):
        await render_image("prompt", FAKE_PNG, "dalle", api_key="k")


async def test_missing_key_raises():
    with pytest.raises(RenderProviderError, match="api_key"):
        await render_image("prompt", FAKE_PNG, "gemini", api_key="")
