#!/usr/bin/env bash
# Development: backend with auto-reload on :8000 and the Vite dev server on :5173
# (Vite proxies /api and /ws to the backend). Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src QVERIS_ENV=development
[ -d web/node_modules ] || (cd web && npm ci)
python -m server --reload &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
cd web && npm run dev
