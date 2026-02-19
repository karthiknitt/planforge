#!/usr/bin/env bash
# Start the PlanForge dev stack: PostgreSQL → backend → frontend
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS_FILE="$ROOT/.dev.pids"
LOGS_DIR="$ROOT/.dev-logs"

# Locate uv (check PATH first, then common install location)
UV="$(command -v uv 2>/dev/null || echo "$HOME/.local/bin/uv")"

if [[ -f "$PIDS_FILE" ]]; then
  echo "⚠ .dev.pids already exists — dev stack may already be running."
  echo "  Run ./dev-stop.sh first, then retry."
  exit 1
fi

mkdir -p "$LOGS_DIR"

# ── 1. PostgreSQL ─────────────────────────────────────────────────────────────
printf "▶ Starting PostgreSQL...\n"
docker compose -f "$ROOT/docker-compose.yml" up db -d --wait
printf "  ✓ DB ready\n\n"

# ── 2. Backend ────────────────────────────────────────────────────────────────
printf "▶ Starting backend  → http://localhost:8002\n"
# exec replaces the subshell so $! is the actual uvicorn PID
(cd "$ROOT/backend" && exec "$UV" run uvicorn app.main:app --reload --port 8002) \
  >"$LOGS_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
printf "  PID %-6s  tail -f .dev-logs/backend.log\n\n" "$BACKEND_PID"

# ── 3. Frontend ───────────────────────────────────────────────────────────────
printf "▶ Starting frontend → http://localhost:3001\n"
(cd "$ROOT/frontend" && exec npx next dev --port 3001) \
  >"$LOGS_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
printf "  PID %-6s  tail -f .dev-logs/frontend.log\n\n" "$FRONTEND_PID"

# ── 4. Persist PIDs ──────────────────────────────────────────────────────────
printf "%s\n%s\n" "$BACKEND_PID" "$FRONTEND_PID" >"$PIDS_FILE"

printf "✓ Dev stack started.\n"
printf "  Stop with: ./dev-stop.sh\n"
