#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8792}"
RELOAD="${RELOAD:-0}"
BUILD_WEB="${BUILD_WEB:-1}"
KILL_OLD="${KILL_OLD:-1}"
PID_FILE="${PID_FILE:-$ROOT_DIR/.run.pid}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Please install uv first." >&2
  exit 1
fi

kill_pid() {
  local pid="$1"
  if [[ -z "$pid" || "$pid" == "$$" ]]; then
    return
  fi
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    return
  fi
  echo "Stopping old process: $pid"
  kill "$pid" >/dev/null 2>&1 || true
  for _ in {1..20}; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return
    fi
    sleep 0.2
  done
  echo "Force stopping old process: $pid"
  kill -9 "$pid" >/dev/null 2>&1 || true
}

kill_old_processes() {
  if [[ -f "$PID_FILE" ]]; then
    kill_pid "$(tr -d '[:space:]' < "$PID_FILE")"
    rm -f "$PID_FILE"
  fi

  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti TCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n tcp "$PORT" 2>/dev/null || true)"
  fi
  for pid in $pids; do
    kill_pid "$pid"
  done
}

if [[ "$BUILD_WEB" == "1" || ( "$BUILD_WEB" == "auto" && ! -f "$ROOT_DIR/web/dist/index.html" ) ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required to build the frontend." >&2
    exit 1
  fi
  (cd "$ROOT_DIR/web" && npm install && npm run build)
fi

if [[ "$KILL_OLD" == "1" ]]; then
  kill_old_processes
fi

args=(python -m uvicorn py.main:app --host "$HOST" --port "$PORT")
if [[ "$RELOAD" == "1" ]]; then
  args+=(--reload)
fi

echo "Starting GPT-Web-CF-Make on http://${HOST}:${PORT}"
exec uv run "${args[@]}"
