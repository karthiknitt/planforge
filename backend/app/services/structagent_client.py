"""Client for the StructAgent structural-design API (structapi).

structapi is a deterministic IS-code RCC design service (IS 456/875/1893/
13920 LSM): a column grid + storeys + location go in; clause-referenced
checks, member designs, BOQ-shaped quantities, and a PDF report come out.
Contract: structapi repo, docs/PLANFORGE-INTEGRATION.md (v1 envelope).

Follows the render_providers.py service pattern: module-level test
transport seam, dedicated exception, httpx.AsyncClient per call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.config.settings import settings

# Test seam: tests inject httpx.MockTransport here (see render_providers.py).
_transport_for_tests: httpx.AsyncBaseTransport | None = None


class StructuralAPIError(Exception):
    pass


@dataclass
class StructuralResult:
    ok: bool
    checks: list = field(default_factory=list)
    data: dict = field(default_factory=dict)
    artifacts: list = field(default_factory=list)
    disclaimer: str = ""


def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=_transport_for_tests)


def is_configured() -> bool:
    return bool(settings.structural_api_url)


async def design_building(
    payload: dict, *, correlation_id: str = "", timeout: float = 120.0
) -> StructuralResult:
    """POST /v1/design/building on structapi and return the parsed envelope."""
    if not settings.structural_api_url:
        raise StructuralAPIError("STRUCTURAL_API_URL is not configured")
    url = settings.structural_api_url.rstrip("/") + "/v1/design/building"
    headers = {"Content-Type": "application/json"}
    if settings.structural_api_key:
        headers["x-api-key"] = settings.structural_api_key
    if correlation_id:
        headers["x-correlation-id"] = correlation_id
    async with _client(timeout) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise StructuralAPIError(f"structapi unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise StructuralAPIError(
            f"structapi HTTP {resp.status_code}: {resp.text[:300]}"
        )
    body = resp.json()
    return StructuralResult(
        ok=bool(body.get("ok")),
        checks=body.get("checks", []),
        data=body.get("data", {}),
        artifacts=body.get("artifacts", []),
        disclaimer=body.get("disclaimer", ""),
    )


async def calc_beam(
    payload: dict, *, correlation_id: str = "", timeout: float = 30.0
) -> StructuralResult:
    """POST /v1/calc/beam on structapi — generic single-member beam design
    (arbitrary UDL in), used for plinth beams (wall load, not slab-driven).
    """
    if not settings.structural_api_url:
        raise StructuralAPIError("STRUCTURAL_API_URL is not configured")
    url = settings.structural_api_url.rstrip("/") + "/v1/calc/beam"
    headers = {"Content-Type": "application/json"}
    if settings.structural_api_key:
        headers["x-api-key"] = settings.structural_api_key
    if correlation_id:
        headers["x-correlation-id"] = correlation_id
    async with _client(timeout) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise StructuralAPIError(f"structapi unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise StructuralAPIError(
            f"structapi HTTP {resp.status_code}: {resp.text[:300]}"
        )
    body = resp.json()
    return StructuralResult(
        ok=bool(body.get("ok")),
        checks=body.get("checks", []),
        data=body.get("data", {}),
        artifacts=body.get("artifacts", []),
        disclaimer=body.get("disclaimer", ""),
    )
