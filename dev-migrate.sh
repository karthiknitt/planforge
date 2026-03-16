#!/usr/bin/env bash
# dev-migrate.sh — sync both Drizzle and SQLAlchemy schemas to the DB
# Usage: ./dev-migrate.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DB_URL="postgresql://planforge:planforge@localhost:5432/planforge"

# ── 1. Drizzle push (frontend schema → DB) ──────────────────────────────────
echo "▶ Drizzle: pushing frontend schema…"
cd "$ROOT/frontend"
DATABASE_URL="$DB_URL" bunx drizzle-kit push
echo "  ✓ Drizzle schema applied"

# ── 2. Backend auto-migration (SQLAlchemy models → DB) ───────────────────────
# The backend lifespan runs auto_migrate_missing_columns() on startup.
# We trigger it here by calling the script directly (no server needed).
echo ""
echo "▶ Backend: applying SQLAlchemy model columns…"
cd "$ROOT/backend"
DATABASE_URL="${DB_URL/postgresql/postgresql+asyncpg}" \
  /home/karthik/.local/bin/uv run python - <<'PYEOF'
import asyncio, os, sys
sys.path.insert(0, ".")
from app.db import engine
from app.db.auto_migrate import auto_migrate_missing_columns
import app.models.project, app.models.revision, app.models.team, app.models.user  # noqa
asyncio.run(auto_migrate_missing_columns(engine))
print("  ✓ Backend schema applied")
PYEOF

# ── 3. Drift report ───────────────────────────────────────────────────────────
echo ""
echo "▶ Running drift check…"
cd "$ROOT/backend"
DATABASE_URL="$DB_URL" \
  /home/karthik/.local/bin/uv run python "$ROOT/scripts/check_schema.py"
