#!/usr/bin/env bash
# Development mode — start API with hot reload only
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"

echo "==> Starting ETF Quant API (dev mode)..."
uv run uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
