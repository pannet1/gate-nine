#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

uv python install 3.12
uv sync
uv run playwright install chromium

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add tenant credentials before browser runs."
else
  echo ".env already exists; leaving it unchanged."
fi

echo "Installation complete. Start Gate Nine with ./run.sh"
