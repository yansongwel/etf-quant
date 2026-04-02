#!/usr/bin/env bash
# First-time project setup with uv
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR=$(pwd)

echo "==> ETF Quant Platform Setup"
echo "    Project: ${PROJECT_DIR}"
echo ""

# 1. Check uv
if ! command -v uv &>/dev/null; then
    echo "==> Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "==> uv $(uv --version)"

# 2. Create venv and install deps
echo "==> Creating virtual environment and installing dependencies..."
uv sync --dev
echo "==> Installed $(uv pip list 2>/dev/null | wc -l) packages"

# 3. Create logs directory
mkdir -p logs

# 4. Copy .env if missing
if [ ! -f .env ]; then
    cp config/.env.example .env
    echo "==> Created .env from template — edit it with your credentials"
else
    echo "==> .env already exists, skipping"
fi

# 5. Check pm2
if ! command -v pm2 &>/dev/null; then
    echo "==> pm2 not found. Install with: npm install -g pm2"
else
    echo "==> pm2 $(pm2 --version 2>/dev/null | tail -1)"
fi

echo ""
echo "==> Setup complete!"
echo "    Dev mode:  bash scripts/dev.sh"
echo "    Prod mode: pm2 start ecosystem.config.cjs"
echo "    Tests:     uv run pytest"
echo "    Lint:      uv run ruff check ."
