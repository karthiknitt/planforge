"""Expensive endpoints must shed load before the instance does."""

import pytest

from app.middleware.rate_limit import TokenBucket


def test_bucket_allows_up_to_capacity():
    b = TokenBucket(capacity=3, refill_per_second=0.0)
    assert b.take(now=0.0)
    assert b.take(now=0.0)
    assert b.take(now=0.0)
    assert not b.take(now=0.0)


def test_bucket_refills_over_time():
    b = TokenBucket(capacity=2, refill_per_second=1.0)
    assert b.take(now=0.0)
    assert b.take(now=0.0)
    assert not b.take(now=0.0)
    assert b.take(now=1.0)  # one token back after 1s
    assert not b.take(now=1.0)


def test_bucket_never_exceeds_capacity():
    b = TokenBucket(capacity=2, refill_per_second=100.0)
    b.take(now=0.0)
    assert b.take(now=1000.0)
    assert b.take(now=1000.0)
    assert not b.take(now=1000.0)  # capped at capacity, not 100k tokens


@pytest.mark.asyncio
async def test_generate_endpoint_returns_429_when_exhausted(client):
    headers = {"X-Test-User-Id": "rl-user"}
    codes = [
        (
            await client.post("/projects/does-not-exist/layouts", headers=headers)
        ).status_code
        for _ in range(12)
    ]
    assert 429 in codes, f"expected a 429 among {codes}"
