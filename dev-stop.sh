#!/usr/bin/env bash
# Stop the PlanForge dev stack: kill backend + frontend, then stop PostgreSQL
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS_FILE="$ROOT/.dev.pids"

# Kill a process and all its descendants (depth-first so parents die last)
_kill_tree() {
  local pid=$1
  local child
  while read -r child; do
    _kill_tree "$child"
  done < <(pgrep -P "$pid" 2>/dev/null || true)
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
  fi
}

if [[ -f "$PIDS_FILE" ]]; then
  mapfile -t PIDS <"$PIDS_FILE"
  labels=("backend" "frontend")
  for i in "${!PIDS[@]}"; do
    pid="${PIDS[$i]}"
    label="${labels[$i]:-process $i}"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      printf "▶ Stopping %s (PID %s)...\n" "$label" "$pid"
      _kill_tree "$pid"
    else
      printf "  %s (PID %s) is not running.\n" "$label" "${pid:-?}"
    fi
  done
  rm -f "$PIDS_FILE"
  printf "  Processes stopped.\n\n"
else
  printf "  No .dev.pids found — processes may already be stopped.\n\n"
fi

printf "▶ Stopping PostgreSQL...\n"
docker compose -f "$ROOT/docker-compose.yml" stop db
printf "\n✓ Dev stack stopped.\n"
