#!/usr/bin/env python3
"""
Schema drift detector for PlanForge.

Compares:
  1. SQLAlchemy models  →  actual DB  (backend drift)
  2. Drizzle schema.ts  →  actual DB  (frontend drift)

Usage:
    cd /path/to/PlanForge
    DATABASE_URL=postgresql://planforge:planforge@localhost:5432/planforge \
        uv run --project backend python scripts/check_schema.py

Exit code 0 = no drift. Exit code 1 = drift found.
"""
import os
import re
import sys
from collections import defaultdict

import asyncpg


# ── 1. Fetch actual DB columns ─────────────────────────────────────────────

async def get_db_columns(dsn: str) -> dict[str, set[str]]:
    conn = await asyncpg.connect(dsn)
    rows = await conn.fetch(
        "SELECT table_name, column_name "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' "
        "ORDER BY table_name, ordinal_position"
    )
    await conn.close()
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        result[row["table_name"]].add(row["column_name"])
    return dict(result)


# ── 2. Extract SQLAlchemy model columns ───────────────────────────────────

def get_sqlalchemy_columns() -> dict[str, set[str]]:
    """Import backend models and read metadata without starting FastAPI."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    # Ensure the URL uses the asyncpg driver so SQLAlchemy doesn't reach for psycopg2
    raw_url = os.environ.get("DATABASE_URL", "postgresql://planforge:planforge@localhost:5432/planforge")
    asyncpg_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    os.environ["DATABASE_URL"] = asyncpg_url

    # Import models so they register with Base.metadata
    import app.models.project  # noqa: F401
    import app.models.revision  # noqa: F401
    import app.models.team  # noqa: F401
    import app.models.user  # noqa: F401
    from app.db import Base

    result: dict[str, set[str]] = {}
    for table_name, table in Base.metadata.tables.items():
        result[table_name] = {col.name for col in table.columns}
    return result


# ── 3. Extract Drizzle schema columns (simple regex parse) ─────────────────

DRIZZLE_TABLE_RE = re.compile(
    r'export const (\w+)\s*=\s*pgTable\(\s*["\'](\w+)["\']',
    re.MULTILINE,
)
DRIZZLE_COL_RE = re.compile(
    r'^\s{2,4}(\w+)\s*:',
    re.MULTILINE,
)
DRIZZLE_SKIP_KEYS = {
    "relations", "primaryKey", "index", "uniqueIndex",
    "foreignKey", "check", "unique",
}


def get_drizzle_columns(schema_path: str) -> dict[str, set[str]]:
    with open(schema_path) as f:
        src = f.read()

    # Find pgTable blocks and their declared field names
    # Strategy: find each pgTable(..., { ... }) block and scan for field keys
    result: dict[str, set[str]] = {}

    # Match: export const foo = pgTable("bar", { ... })
    # We grab everything between the outer braces of the column definition object
    table_pattern = re.compile(
        r'pgTable\s*\(\s*["\'](\w+)["\']\s*,\s*\{',
        re.MULTILINE,
    )
    for m in table_pattern.finditer(src):
        table_name = m.group(1)
        start = m.end()  # position after opening {
        depth = 1
        i = start
        while i < len(src) and depth > 0:
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
            i += 1
        block = src[start : i - 1]

        # Extract top-level keys (field names → DB columns via camelCase→snake_case)
        cols: set[str] = set()
        for line in block.splitlines():
            stripped = line.strip()
            key_match = re.match(r"^(\w+)\s*:", stripped)
            if key_match:
                key = key_match.group(1)
                if key not in DRIZZLE_SKIP_KEYS:
                    cols.add(_camel_to_snake(key))
        result[table_name] = cols

    return result


def _camel_to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


# ── 4. Report ──────────────────────────────────────────────────────────────

def report_drift(
    label: str,
    model_cols: dict[str, set[str]],
    db_cols: dict[str, set[str]],
) -> int:
    """Return number of drifted columns found."""
    drift_count = 0
    for table, cols in model_cols.items():
        if table not in db_cols:
            print(f"  [{label}] Table '{table}' missing from DB entirely!")
            drift_count += len(cols)
            continue
        missing = sorted(cols - db_cols[table])
        extra = sorted(db_cols[table] - cols)
        if missing:
            print(f"  [{label}] {table}: in model but NOT in DB → {missing}")
            drift_count += len(missing)
        if extra:
            print(f"  [{label}] {table}: in DB but NOT in model → {extra}")
            # Don't count extras as errors — they may be Better Auth managed
    return drift_count


async def main() -> None:
    import asyncio

    dsn = os.environ.get(
        "DATABASE_URL",
        "postgresql://planforge:planforge@localhost:5432/planforge",
    ).replace("postgresql+asyncpg://", "postgresql://")

    print("Fetching DB columns…")
    db_cols = await get_db_columns(dsn)

    print("Reading SQLAlchemy models…")
    sa_cols = get_sqlalchemy_columns()

    schema_path = os.path.join(
        os.path.dirname(__file__), "..", "frontend", "src", "db", "schema.ts"
    )
    print("Reading Drizzle schema.ts…")
    drizzle_cols = get_drizzle_columns(schema_path)

    print()
    print("=" * 60)
    print("SCHEMA DRIFT REPORT")
    print("=" * 60)

    total = 0

    print("\n── Backend (SQLAlchemy → DB) ──")
    total += report_drift("backend", sa_cols, db_cols)

    print("\n── Frontend (Drizzle → DB) ──")
    total += report_drift("frontend", drizzle_cols, db_cols)

    print()
    if total == 0:
        print("✓ No drift detected. Schemas are in sync.")
    else:
        print(f"✗ {total} column(s) out of sync.")
        print("  Run ./dev-migrate.sh or restart the backend to auto-fix.")

    sys.exit(0 if total == 0 else 1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
