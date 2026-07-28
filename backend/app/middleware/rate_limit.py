"""In-process token-bucket rate limiting for expensive endpoints.

Deliberately in-memory: Memorystore/Redis is ~$35/mo always-on, which would
exceed the entire rest of this project's GCP bill. With max-instances=3 the
effective limit is up to 3x the configured value; that is fine for stopping
runaway clients, which is the actual threat.
"""

import time
from dataclasses import dataclass, field

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# (method, path-prefix) pairs that cost real CPU or real money.
LIMITED_PREFIXES: tuple[str, ...] = (
    "/layouts",
    "/export",
    "/render",
    "/generation-jobs",
    "/render-jobs",
)


@dataclass
class TokenBucket:
    capacity: int
    refill_per_second: float
    tokens: float = field(default=None)  # type: ignore[assignment]
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if self.tokens is None:
            self.tokens = float(self.capacity)

    def take(self, now: float) -> bool:
        elapsed = max(0.0, now - self.updated_at)
        self.tokens = min(
            float(self.capacity), self.tokens + elapsed * self.refill_per_second
        )
        self.updated_at = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, capacity: int = 10, refill_per_second: float = 0.2) -> None:
        super().__init__(app)
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._buckets: dict[str, TokenBucket] = {}

    def _key(self, request: Request) -> str:
        user = request.headers.get("X-Test-User-Id") or request.headers.get("X-User-Id")
        if user:
            return f"u:{user}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    async def dispatch(self, request: Request, call_next):
        if not any(p in request.url.path for p in LIMITED_PREFIXES):
            return await call_next(request)

        key = self._key(request)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self.capacity, self.refill_per_second)
            self._buckets[key] = bucket

        if not bucket.take(now=time.monotonic()):
            return JSONResponse(
                status_code=429,
                content={
                    "code": "rate_limited",
                    "detail": "Too many requests.",
                    "help": "Wait a few seconds and retry.",
                },
                headers={"Retry-After": "5"},
            )
        return await call_next(request)
