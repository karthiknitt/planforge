"""Image-render provider adapters — Gemini, OpenAI, OpenRouter.

One interface: render_image(prompt, reference_png, provider, api_key=...).
Provider choice is config (RENDER_PROVIDER env) — locked decision: bake-off
picks the default before this is user-facing.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

# Test seam: tests monkeypatch this with httpx.MockTransport.
_transport_for_tests: httpx.AsyncBaseTransport | None = None

GEMINI_MODEL = "gemini-2.5-flash-image"
OPENAI_MODEL = "gpt-image-1"
OPENROUTER_MODEL = "google/gemini-2.5-flash-image"

# Indicative per-image cost (USD) — refined at bake-off from real usage data.
# OpenRouter reports actual cost per call (usage.cost); this is only the
# fallback when the response omits it.
_COSTS = {"gemini": 0.039, "openai": 0.07, "openrouter": 0.04}


@dataclass
class RenderResult:
    image_png: bytes
    provider: str
    model: str
    cost_usd: float | None


class RenderProviderError(Exception):
    pass


def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=_transport_for_tests)


async def render_image(
    prompt: str,
    reference_png: bytes,
    provider: str,
    *,
    api_key: str,
    model: str | None = None,
    timeout: float = 120.0,
) -> RenderResult:
    if not api_key:
        raise RenderProviderError(f"{provider}: api_key is empty")
    if provider == "gemini":
        return await _render_gemini(prompt, reference_png, api_key, model, timeout)
    if provider == "openai":
        return await _render_openai(prompt, reference_png, api_key, model, timeout)
    if provider == "openrouter":
        return await _render_openrouter(prompt, reference_png, api_key, model, timeout)
    raise RenderProviderError(f"unknown provider {provider!r}")


async def _render_gemini(
    prompt: str, reference_png: bytes, api_key: str, model: str | None, timeout: float
) -> RenderResult:
    model = model or GEMINI_MODEL
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": base64.b64encode(reference_png).decode(),
                        }
                    },
                    {"text": prompt},
                ]
            }
        ]
    }
    async with _client(timeout) as client:
        resp = await client.post(url, json=payload, headers={"x-goog-api-key": api_key})
    if resp.status_code != 200:
        raise RenderProviderError(f"gemini: HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        parts = resp.json()["candidates"][0]["content"]["parts"]
        data = next(p["inline_data"]["data"] for p in parts if "inline_data" in p)
    except (KeyError, IndexError, StopIteration) as e:
        raise RenderProviderError(f"gemini: no image in response ({e})") from e
    return RenderResult(base64.b64decode(data), "gemini", model, _COSTS["gemini"])


async def _render_openai(
    prompt: str, reference_png: bytes, api_key: str, model: str | None, timeout: float
) -> RenderResult:
    model = model or OPENAI_MODEL
    async with _client(timeout) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": model, "prompt": prompt},
            # Field name is `image[]` (bracketed array) per current OpenAI
            # docs, even for a single reference image.
            files=[("image[]", ("reference.png", reference_png, "image/png"))],
        )
    if resp.status_code != 200:
        raise RenderProviderError(f"openai: HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        b64 = resp.json()["data"][0]["b64_json"]
    except (KeyError, IndexError) as e:
        raise RenderProviderError(f"openai: no image in response ({e})") from e
    return RenderResult(base64.b64decode(b64), "openai", model, _COSTS["openai"])


async def _render_openrouter(
    prompt: str, reference_png: bytes, api_key: str, model: str | None, timeout: float
) -> RenderResult:
    model = model or OPENROUTER_MODEL
    payload = {
        "model": model,
        "prompt": prompt,
        "input_references": [
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,"
                    + base64.b64encode(reference_png).decode()
                },
            }
        ],
    }
    async with _client(timeout) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/images",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    if resp.status_code != 200:
        raise RenderProviderError(
            f"openrouter: HTTP {resp.status_code}: {resp.text[:300]}"
        )
    body = resp.json()
    try:
        b64 = body["data"][0]["b64_json"]
    except (KeyError, IndexError) as e:
        raise RenderProviderError(f"openrouter: no image in response ({e})") from e
    cost = body.get("usage", {}).get("cost", _COSTS["openrouter"])
    return RenderResult(base64.b64decode(b64), "openrouter", model, cost)
