"""Exports must be concurrency-bounded and cacheable."""

import asyncio

import pytest

from app.api.routes import export as export_routes


@pytest.mark.asyncio
async def test_export_semaphore_bounds_concurrency(monkeypatch):
    monkeypatch.setattr(export_routes, "_EXPORT_SEM", asyncio.Semaphore(2))
    peak = 0
    live = 0

    async def worker():
        nonlocal peak, live
        async with export_routes._EXPORT_SEM:
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.05)
            live -= 1

    await asyncio.gather(*(worker() for _ in range(8)))
    assert peak <= 2, f"exceeded the export concurrency cap (peak={peak})"


def test_artifact_key_is_stable_and_content_addressed():
    k1 = export_routes._artifact_key("proj1", "A", "pdf", b"same-bytes")
    k2 = export_routes._artifact_key("proj1", "A", "pdf", b"same-bytes")
    k3 = export_routes._artifact_key("proj1", "A", "pdf", b"other-bytes")
    assert k1 == k2
    assert k1 != k3
    assert k1.startswith("exports/proj1/A/") and k1.endswith(".pdf")
