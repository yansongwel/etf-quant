"""Per-ETF signal quality scoring — identifies which ETFs the signal engine works well on.

Runs a rolling 90-day backtest per ETF to compute historical buy/sell accuracy.
ETFs with buy accuracy < 50% are flagged as "low_confidence".
This data is used to:
1. Weight down signals for unreliable ETFs
2. Show confidence badges on the frontend
3. Exclude worst ETFs from the buy recommendation list
"""

from __future__ import annotations

import logging
import time

from data.storage.parquet_store import load_hist
from engine.signals import (
    _detect_market_regime,
    precompute_factors,
    score_at_index,
)

logger = logging.getLogger(__name__)

_quality_cache: tuple[float, dict[str, dict]] | None = None
_QUALITY_CACHE_TTL = 3600  # 1 hour — expensive to compute


def compute_signal_quality(lookback_days: int = 90) -> dict[str, dict]:
    """Compute per-ETF signal accuracy over recent history.

    Returns: {symbol: {buy_accuracy, buy_count, sell_accuracy, sell_count, confidence}}
    """
    global _quality_cache
    now = time.monotonic()
    if _quality_cache is not None and now - _quality_cache[0] < _QUALITY_CACHE_TTL:
        return _quality_cache[1]

    from config.constants import DEFAULT_ETF_LIST

    regime = _detect_market_regime()
    results: dict[str, dict] = {}

    for etf in DEFAULT_ETF_LIST:
        sym = etf["symbol"]
        df = load_hist(sym)
        if df.empty or len(df) < lookback_days + 60:
            continue

        factors = precompute_factors(df)
        total = len(df)
        buy_ok = buy_n = sell_ok = sell_n = 0

        start_idx = max(total - lookback_days, 60)
        for i in range(start_idx, total - 5):
            price = float(df["close"].iloc[i])
            direction, _, _ = score_at_index(factors, i, price, market_regime=regime)
            fwd_ret = (float(df["close"].iloc[i + 5]) - price) / price

            if direction.value in ("buy", "strong_buy"):
                buy_n += 1
                if fwd_ret > 0:
                    buy_ok += 1
            elif direction.value in ("sell", "strong_sell"):
                sell_n += 1
                if fwd_ret < 0:
                    sell_ok += 1

        buy_acc = (buy_ok / buy_n * 100) if buy_n > 0 else 50.0
        sell_acc = (sell_ok / sell_n * 100) if sell_n > 0 else 50.0

        if buy_acc >= 65:
            confidence = "high"
        elif buy_acc >= 50:
            confidence = "medium"
        else:
            confidence = "low"

        results[sym] = {
            "name": etf["name"],
            "buy_accuracy": round(buy_acc, 1),
            "buy_count": buy_n,
            "sell_accuracy": round(sell_acc, 1),
            "sell_count": sell_n,
            "confidence": confidence,
        }

    _quality_cache = (now, results)
    logger.info(
        "Signal quality: %d high, %d medium, %d low confidence ETFs",
        sum(1 for v in results.values() if v["confidence"] == "high"),
        sum(1 for v in results.values() if v["confidence"] == "medium"),
        sum(1 for v in results.values() if v["confidence"] == "low"),
    )
    return results
