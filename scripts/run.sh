#!/usr/bin/env bash
# Run the API server (dev, auto-reload).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export DATABASE_URL="${DATABASE_URL:-postgresql://localhost:55432/playclass}"
# DEV-ONLY: a local /reports access code so the page works out of the box on a laptop. The app itself has no
# default (REPORTS_KEY unset = /api/reports/* answers 503). Never use this value on a shared or public server.
export REPORTS_KEY="${REPORTS_KEY:-reports123}"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
exec "$PY" -m uvicorn app.main:app --reload --port "${PORT:-8000}" "$@"
