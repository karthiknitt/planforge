"""
Auto-migration: adds any column defined in SQLAlchemy models
but missing from the actual Postgres database.

Runs at backend startup (lifespan) — safe to call every boot.
ALTER TABLE ... ADD COLUMN IF NOT EXISTS is idempotent.
"""
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


def _pg_type(col: Any) -> str:
    from sqlalchemy import Boolean, Float, Integer, Numeric, String, Text
    from sqlalchemy.types import JSON, DateTime

    t = col.type
    if isinstance(t, (String, Text)):
        return "TEXT"
    if isinstance(t, Integer):
        return "INTEGER"
    if isinstance(t, Boolean):
        return "BOOLEAN"
    if isinstance(t, Float):
        return "DOUBLE PRECISION"
    if isinstance(t, Numeric):
        if t.precision is not None:
            return f"NUMERIC({t.precision}, {t.scale or 0})"
        return "NUMERIC"
    if isinstance(t, JSON):
        return "JSONB"
    if isinstance(t, DateTime):
        return "TIMESTAMP WITH TIME ZONE"
    return "TEXT"


def _server_default_sql(col: Any) -> str:
    if col.server_default is None:
        return ""
    arg = col.server_default.arg
    if hasattr(arg, "text"):
        return f"DEFAULT {arg.text}"
    raw = str(arg).strip("'")
    if raw.lower() in ("now()", "true", "false") or raw.replace(".", "").lstrip("-").isdigit():
        return f"DEFAULT {raw}"
    return f"DEFAULT '{raw}'"


async def auto_migrate_missing_columns(engine: AsyncEngine) -> None:
    from app.db import Base

    async with engine.begin() as conn:
        for table_name, table in Base.metadata.tables.items():
            result = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :tbl"
                ),
                {"tbl": table_name},
            )
            db_cols = {row[0] for row in result}

            for col in table.columns:
                if col.name in db_cols:
                    continue

                pg_type = _pg_type(col)
                default = _server_default_sql(col)
                # If NOT NULL but no default, add as nullable to avoid breaking existing rows
                if not col.nullable and not default:
                    logger.warning(
                        "Schema drift: %s.%s is NOT NULL but has no server_default — "
                        "adding as NULLABLE to avoid data errors. Fix the model.",
                        table_name, col.name,
                    )
                    null_clause = ""
                else:
                    null_clause = "" if col.nullable else "NOT NULL"

                parts = [
                    f'ALTER TABLE "{table_name}"',
                    f'ADD COLUMN IF NOT EXISTS "{col.name}"',
                    pg_type,
                ]
                if default:
                    parts.append(default)
                if null_clause:
                    parts.append(null_clause)

                await conn.execute(text(" ".join(parts)))
                logger.warning(
                    "Auto-migrated: added %s.%s (%s)", table_name, col.name, pg_type
                )
