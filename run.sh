#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  set -- --host 127.0.0.1 --port 8000
fi

exec uv run uvicorn app.main:app "$@"
