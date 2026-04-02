"""Signal backtest — validate signal accuracy against historical data.

Replays the signal engine over historical data to compute:
- Buy accuracy: % of buy signals where next-day return > 0
- Average return per signal direction
- Precision by score bucket

V2: Uses precomputed factors for ~30x speedup over per-day generation.
"""

from __future__ import annotations

import logging

import numpy as np

from data.storage.parquet_store import load_hist
from engine.signals import (
    SignalDirection,
    _detect_market_regime,
    precompute_factors,
    score_at_index,
)

logger = logging.getLogger(__name__)


def backtest_signals(
    symbols: list[str],
    lookback_days: int = 60,
    test_days: int = 30,
) -> dict:
    """Backtest signal accuracy over recent history.

    For each of the last `test_days` trading days, scores signals using
    precomputed factors and checks if the next-day return matches direction.

    Args:
        symbols: List of ETF symbols to test.
        lookback_days: How many days of history the signal engine needs.
        test_days: How many days to test over.

    Returns:
        Dict with accuracy metrics by direction and score bucket.
    """
    results_by_dir: dict[str, list[dict]] = {
        "strong_buy": [],
        "buy": [],
        "hold": [],
        "sell": [],
        "strong_sell": [],
    }

    regime = _detect_market_regime()

    for symbol in symbols:
        df = load_hist(symbol)
        if df.empty or len(df) < lookback_days + test_days + 1:
            continue

        # Precompute all factors once for the full history
        factors = precompute_factors(df)

        total_rows = len(df)
        start_idx = max(total_rows - test_days - 1, lookback_days)

        for i in range(start_idx, total_rows - 1):
            current_price = float(df["close"].iloc[i])
            direction, score = score_at_index(factors, i, current_price, market_regime=regime)

            # Next day return
            next_close = float(df["close"].iloc[i + 1])
            next_ret = (next_close - current_price) / current_price

            results_by_dir[direction.value].append(
                {
                    "symbol": symbol,
                    "score": score,
                    "next_return": next_ret,
                    "correct": (
                        (
                            direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)
                            and next_ret > 0
                        )
                        or (
                            direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL)
                            and next_ret < 0
                        )
                        or (direction == SignalDirection.HOLD and abs(next_ret) < 0.01)
                    ),
                }
            )

    # Aggregate results
    summary: dict[str, dict] = {}
    for direction, records in results_by_dir.items():
        if not records:
            summary[direction] = {
                "total": 0,
                "correct": 0,
                "accuracy": 0.0,
                "avg_return": 0.0,
            }
            continue

        total = len(records)
        correct = sum(1 for r in records if r["correct"])
        avg_ret = np.mean([r["next_return"] for r in records])

        summary[direction] = {
            "total": total,
            "correct": correct,
            "accuracy": round(correct / total * 100, 1) if total > 0 else 0.0,
            "avg_return": round(avg_ret * 100, 2),
        }

    # Score bucket analysis for buy signals
    all_buys = results_by_dir["buy"] + results_by_dir["strong_buy"]
    score_buckets: list[dict] = []
    if all_buys:
        scores = np.array([r["score"] for r in all_buys])
        rets = np.array([r["next_return"] for r in all_buys])
        corrects = np.array([r["correct"] for r in all_buys])

        for lo, hi in [(10, 20), (20, 30), (30, 50), (50, 100)]:
            mask = (scores >= lo) & (scores < hi)
            if mask.sum() > 0:
                score_buckets.append(
                    {
                        "range": f"{lo}-{hi}",
                        "count": int(mask.sum()),
                        "accuracy": round(corrects[mask].mean() * 100, 1),
                        "avg_return": round(rets[mask].mean() * 100, 2),
                    }
                )

    # Overall
    all_records = [r for recs in results_by_dir.values() for r in recs]
    total_all = len(all_records)
    correct_all = sum(1 for r in all_records if r["correct"])

    return {
        "test_days": test_days,
        "total_signals": total_all,
        "overall_accuracy": round(correct_all / total_all * 100, 1) if total_all > 0 else 0.0,
        "by_direction": summary,
        "buy_score_buckets": score_buckets,
        "buy_total": len(all_buys),
        "buy_accuracy": round(sum(1 for r in all_buys if r["correct"]) / len(all_buys) * 100, 1)
        if all_buys
        else 0.0,
    }
