"""Integration tests proving get_current_user_id is actually wired into a real
route via FastAPI's Header(...) extraction over a live HTTP request — every
other test in this suite goes through the client fixture's dependency
override, which bypasses this entirely and would not catch a route missing
its Depends(get_current_user_id), a typo'd header alias, etc."""

import time

import jwt

SECRET = "test-secret-for-ci"  # matches conftest.py's INTERNAL_AUTH_SECRET default


def _token(user_id: str, exp_offset_seconds: int = 60, secret: str = SECRET) -> str:
    payload = {"user_id": user_id, "exp": time.time() + exp_offset_seconds}
    return jwt.encode(payload, secret, algorithm="HS256")


async def test_valid_internal_auth_token_reaches_the_route(client_real_auth):
    response = await client_real_auth.get(
        "/api/projects", headers={"X-Internal-Auth": _token("user-real-1")}
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_missing_internal_auth_header_returns_422(client_real_auth):
    response = await client_real_auth.get("/api/projects")
    assert response.status_code == 422


async def test_expired_internal_auth_token_returns_401(client_real_auth):
    token = _token("user-real-1", exp_offset_seconds=-10)
    response = await client_real_auth.get(
        "/api/projects", headers={"X-Internal-Auth": token}
    )
    assert response.status_code == 401


async def test_tampered_internal_auth_token_returns_401(client_real_auth):
    token = _token("user-real-1", secret="wrong-secret")
    response = await client_real_auth.get(
        "/api/projects", headers={"X-Internal-Auth": token}
    )
    assert response.status_code == 401


async def test_a_plain_client_supplied_user_id_header_is_no_longer_trusted(
    client_real_auth,
):
    """Regression guard for the original vulnerability this whole PR fixes:
    the old X-User-Id header must have zero effect now."""
    response = await client_real_auth.get(
        "/api/projects", headers={"X-User-Id": "attacker-controlled-value"}
    )
    assert response.status_code == 422
