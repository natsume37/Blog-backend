#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/uv-run.sh dev
#   ./scripts/uv-run.sh prod
#
# You can override host/port:
#   HOST=0.0.0.0 PORT=8090 ./scripts/uv-run.sh prod

MODE="${1:-dev}"

if [[ "$MODE" == "prod" || "$MODE" == "production" ]]; then
  export ENVIRONMENT=production
  HOST="${HOST:-0.0.0.0}"
  PORT="${PORT:-8090}"
  exec uv run uvicorn app.main:app --host "$HOST" --port "$PORT"
fi

export ENVIRONMENT=development
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8090}"
exec uv run uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
