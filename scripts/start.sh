#!/usr/bin/env bash
# Production-style single process: builds the web app if needed, then serves
# API + WebSocket + UI from FastAPI on $QVERIS_PORT (default 8000).
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f web/dist/index.html ]; then
  (cd web && ([ -d node_modules ] || npm ci) && npm run build)
fi
export PYTHONPATH=src
exec python -m server "$@"
