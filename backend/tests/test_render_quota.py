"""AI renders cost real money per call — cap them per user per day."""

import pytest
from fastapi import HTTPException

from app.services import render_runner


@pytest.mark.asyncio
async def test_quota_allows_under_limit(client, monkeypatch):
    monkeypatch.setattr(render_runner, "_daily_render_count", _fake_count(3))
    await render_runner.check_render_quota("u1", db=None, limit=10)


@pytest.mark.asyncio
async def test_quota_blocks_at_limit(client, monkeypatch):
    monkeypatch.setattr(render_runner, "_daily_render_count", _fake_count(10))
    with pytest.raises(HTTPException) as exc:
        await render_runner.check_render_quota("u1", db=None, limit=10)
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "render_quota_exceeded"


def _fake_count(n: int):
    async def _count(user_id, db):
        return n

    return _count
