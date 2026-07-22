#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
  echo "Missing .venv. Create it and install requirements-fastapi.txt first." >&2
  exit 1
fi

exec .venv/bin/python -m uvicorn test7.api_server:app \
  --app-dir "$ROOT/.." \
  --host "${ALLOY_API_HOST:-127.0.0.1}" \
  --port "${ALLOY_API_PORT:-8000}" \
  --reload
