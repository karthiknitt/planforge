import jwt
from fastapi import Header, HTTPException, status

from app.config.settings import settings


def _decode_internal_auth(x_internal_auth: str) -> dict:
    try:
        return jwt.decode(
            x_internal_auth,
            settings.internal_auth_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "user_id"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired internal auth token"
        ) from exc


def get_current_user_id(
    x_internal_auth: str = Header(..., alias="X-Internal-Auth"),
) -> str:
    payload = _decode_internal_auth(x_internal_auth)
    return payload["user_id"]


def get_current_user_email(
    x_internal_auth: str = Header(..., alias="X-Internal-Auth"),
) -> str | None:
    """Return the trusted `email` claim from the internal JWT, or None if absent.

    Never trust a client-supplied email in a request body for anything
    security-sensitive (e.g. claiming a team invite) — only this claim,
    which the frontend mints from the verified Better Auth session.
    """
    payload = _decode_internal_auth(x_internal_auth)
    return payload.get("email")
