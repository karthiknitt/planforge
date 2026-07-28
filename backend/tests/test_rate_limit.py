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


@pytest.mark.asyncio
async def test_429_response_carries_cors_headers(client):
    """CORS must wrap the rate limiter, not the other way round: the limiter
    middleware is registered before CORSMiddleware in main.py so CORS is the
    outermost layer and its headers land on 429 responses too. Otherwise a
    cross-origin browser rejects the header-less 429 as a CORS failure before
    the frontend ever sees the "rate limited" status."""
    origin = "http://localhost:3001"
    headers = {"X-Test-User-Id": "rl-cors-user", "Origin": origin}

    responses = [
        await client.post("/projects/does-not-exist/layouts", headers=headers)
        for _ in range(12)
    ]

    rate_limited = [r for r in responses if r.status_code == 429]
    assert rate_limited, f"expected a 429 among {[r.status_code for r in responses]}"
    assert rate_limited[0].headers.get("access-control-allow-origin") == origin
