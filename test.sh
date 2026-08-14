#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/ensure-deps.sh
source "$ROOT/scripts/ensure-deps.sh"

echo "==> backend (pytest)"
cd "$ROOT/backend"
"$VENV/bin/pytest"

echo "==> frontend (vitest)"
cd "$ROOT/frontend"
npm test
