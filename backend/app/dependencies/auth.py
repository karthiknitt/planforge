import jwt
from fastapi import Header, HTTPException, status

from app.config.settings import settings


def get_current_user_id(x_internal_auth: str = Header(..., alias="X-Internal-Auth")) -> str:
    try:
        payload = jwt.decode(
            x_internal_auth,
            settings.internal_auth_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "user_id"]},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired internal auth token"
        ) from exc
    return payload["user_id"]
