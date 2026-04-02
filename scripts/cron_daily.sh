#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Daily cron job — runs after market close (16:00 CST)
#
# 1. Update ETF data (incremental)
# 2. Record today's signals for accuracy tracking
# 3. Flush stale Redis cache
#
# Crontab entry:
#   0 16 * * 1-5 /home/devops/etf-quant/scripts/cron_daily.sh >> /home/devops/etf-quant/logs/cron.log 2>&1
# ─────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT_DIR="/home/devops/etf-quant"
cd "$PROJECT_DIR"

export PYTHONPATH="$PROJECT_DIR"
UV="/home/devops/.local/bin/uv"

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_PREFIX === Daily cron start ==="

# 1. Update data
echo "$LOG_PREFIX Step 1: Collecting latest ETF data..."
$UV run python scripts/collect_daily.py --resume 2>&1 | tail -3

# 2. Record signals
echo "$LOG_PREFIX Step 2: Recording signals..."
curl -s -X POST http://127.0.0.1:8000/api/signals/record | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Recorded {d[\"recorded\"]} signals')" 2>/dev/null || echo "API not available, skipping signal record"

# 3. Flush cache so next request gets fresh data
echo "$LOG_PREFIX Step 3: Flushing cache..."
$UV run python -c "
from data.cache.redis_cache import cache_flush_pattern
n = cache_flush_pattern('hist:*') + cache_flush_pattern('factors:*')
print(f'Flushed {n} cache keys')
" 2>/dev/null || echo "Redis not available"

echo "$LOG_PREFIX === Daily cron complete ==="
