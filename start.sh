#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/ensure-deps.sh
source "$ROOT/scripts/ensure-deps.sh"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

backend_pid=""
frontend_pid=""

cleanup() {
  if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill "$backend_pid" 2>/dev/null || true
  fi
  if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" 2>/dev/null; then
    kill "$frontend_pid" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}

trap cleanup EXIT INT TERM

cd "$ROOT/backend"
"$VENV/bin/uvicorn" app.main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  --workers 1 &
backend_pid=$!

cd "$ROOT/frontend"
npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" &
frontend_pid=$!

echo
echo "Book Illustration Studio"
echo "  Frontend  http://127.0.0.1:${FRONTEND_PORT}"
echo "  Backend   http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "  Health    http://${BACKEND_HOST}:${BACKEND_PORT}/api/health"
echo
echo "Ctrl+C stops both processes."
echo

wait
