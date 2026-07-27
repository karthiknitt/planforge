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
    from sqlalchemy import Boolean, Float, Integer, LargeBinary, Numeric, String, Text
    from sqlalchemy.types import JSON, DateTime

    t = col.type
    if isinstance(t, LargeBinary):
        return "BYTEA"
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
    if (
        raw.lower() in ("now()", "true", "false")
        or raw.replace(".", "").lstrip("-").isdigit()
    ):
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
                        table_name,
                        col.name,
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


# Columns whose nullability was relaxed after initial deploy. The column
# already exists in production, so `auto_migrate_missing_columns` (which only
# adds missing columns) never touches it — the old NOT NULL constraint sticks
# around until something explicitly drops it. Add an entry here only for a
# real, reviewed nullability change; this is deliberately not a blanket
# "sync every column to the model" sweep (too wide a blast radius on a
# database that carries some intentional drift).
NULLABLE_RECONCILIATIONS = (
    # image_png moved to R2; rows written after R2 is configured store the
    # bytes under image_key instead and leave this column NULL.
    ("layout_renders", "image_png"),
)


async def reconcile_nullable_columns(engine: AsyncEngine) -> None:
    """Drop NOT NULL on columns in `NULLABLE_RECONCILIATIONS` if the live
    database still has it set. Safe to call every boot — idempotent, and a
    no-op once the constraint has been dropped."""
    from app.db import Base

    async with engine.begin() as conn:
        for table_name, col_name in NULLABLE_RECONCILIATIONS:
            table = Base.metadata.tables.get(table_name)
            if table is None or col_name not in table.columns:
                continue
            if not table.columns[col_name].nullable:
                # Model itself still requires NOT NULL — nothing to relax.
                continue

            result = await conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :tbl "
                    "AND column_name = :col"
                ),
                {"tbl": table_name, "col": col_name},
            )
            row = result.first()
            if row is None or row[0] == "YES":
                continue

            await conn.execute(
                text(
                    f'ALTER TABLE "{table_name}" '
                    f'ALTER COLUMN "{col_name}" DROP NOT NULL'
                )
            )
            logger.warning(
                "Auto-migrated: dropped NOT NULL on %s.%s", table_name, col_name
            )
