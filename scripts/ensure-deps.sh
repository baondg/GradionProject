#!/usr/bin/env bash
# Shared by start.sh and test.sh. Creates the venv and installs deps if missing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/backend/.venv"

if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install -q -U pip
"$VENV/bin/pip" install -q -e "$ROOT/backend[dev]"

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  npm install --prefix "$ROOT/frontend"
fi
