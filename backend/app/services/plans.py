"""Effective plan tier — the single place plan gating consults.

plan_expires_at was previously written at payment time but never read,
so an expired subscription kept paid features forever.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_effective_plan_tier(user_id: str, db: AsyncSession) -> str:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return "free"
    tier = user.plan_tier or "free"
    if tier == "free":
        return "free"
    exp = user.plan_expires_at
    if exp is not None:
        # SQLite (tests) returns naive datetimes; Postgres returns aware
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return "free"
    return tier
