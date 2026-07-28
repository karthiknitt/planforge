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


class _FakeStorage:
    """In-memory stand-in for R2 — no boto3, no network."""

    def __init__(self, *, fail_upload=False):
        self.fail_upload = fail_upload
        self.objects: dict[str, bytes] = {}

    async def put_bytes(self, key, data, content_type):
        if self.fail_upload:
            raise RuntimeError("simulated R2 outage")
        self.objects[key] = data

    async def get_bytes(self, key):
        return self.objects.get(key)

    def signed_url(self, key, ttl_seconds=900):
        return f"https://signed.example/{key}"


def _use_storage(monkeypatch, storage, mode):
    monkeypatch.setattr(export_routes, "get_storage", lambda: storage)
    monkeypatch.setattr(export_routes.settings, "export_delivery_mode", mode)


@pytest.mark.asyncio
async def test_redirect_mode_falls_back_to_inline_when_upload_fails(monkeypatch):
    # Redirecting to a key we failed to write would hand the user R2's
    # NoSuchKey XML instead of their PDF.
    _use_storage(monkeypatch, _FakeStorage(fail_upload=True), "redirect")

    resp = await export_routes._deliver(
        b"%PDF-1.4", "application/pdf", "x.pdf", "exports/p/A/deadbeef.pdf"
    )

    assert resp.status_code == 200
    assert resp.body == b"%PDF-1.4"
    assert "attachment" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_redirect_mode_307s_when_upload_succeeds(monkeypatch):
    storage = _FakeStorage()
    _use_storage(monkeypatch, storage, "redirect")
    key = "exports/p/A/deadbeef.pdf"

    resp = await export_routes._deliver(b"%PDF-1.4", "application/pdf", "x.pdf", key)

    assert resp.status_code == 307
    assert resp.headers["location"] == f"https://signed.example/{key}"
    assert storage.objects[key] == b"%PDF-1.4"


@pytest.mark.asyncio
async def test_inline_mode_never_redirects_even_on_a_healthy_upload(monkeypatch):
    storage = _FakeStorage()
    _use_storage(monkeypatch, storage, "inline")
    key = "exports/p/A/deadbeef.pdf"

    resp = await export_routes._deliver(b"%PDF-1.4", "application/pdf", "x.pdf", key)

    assert resp.status_code == 200
    assert resp.body == b"%PDF-1.4"
    assert storage.objects[key] == b"%PDF-1.4"


def test_artifact_key_is_stable_and_content_addressed():
    k1 = export_routes._artifact_key("proj1", "A", "pdf", b"same-bytes")
    k2 = export_routes._artifact_key("proj1", "A", "pdf", b"same-bytes")
    k3 = export_routes._artifact_key("proj1", "A", "pdf", b"other-bytes")
    assert k1 == k2
    assert k1 != k3
    assert k1.startswith("exports/proj1/A/") and k1.endswith(".pdf")
