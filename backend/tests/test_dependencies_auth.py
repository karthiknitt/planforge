import time

import jwt
import pytest
from fastapi import HTTPException

from app.dependencies.auth import get_current_user_id

SECRET = "test-secret-value"


def _token(user_id: str, exp_offset_seconds: int = 60, secret: str = SECRET) -> str:
    payload = {"user_id": user_id, "exp": time.time() + exp_offset_seconds}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_valid_token_returns_user_id(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.auth.settings.internal_auth_secret", SECRET
    )
    token = _token("user-123")
    assert get_current_user_id(x_internal_auth=token) == "user-123"


def test_expired_token_raises_401(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.auth.settings.internal_auth_secret", SECRET
    )
    token = _token("user-123", exp_offset_seconds=-10)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(x_internal_auth=token)
    assert exc_info.value.status_code == 401


def test_tampered_signature_raises_401(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.auth.settings.internal_auth_secret", SECRET
    )
    token = _token("user-123", secret="wrong-secret")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(x_internal_auth=token)
    assert exc_info.value.status_code == 401


def test_malformed_token_raises_401(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.auth.settings.internal_auth_secret", SECRET
    )
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(x_internal_auth="not-a-jwt")
    assert exc_info.value.status_code == 401
