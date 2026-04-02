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
    eval_horizon: int = 5,
) -> dict:
    """Backtest signal accuracy over recent history.

    V5.0: Evaluates signals over a configurable horizon (default 5 days)
    instead of only next-day. ETF rotation signals work on 5-20 day cycles,
    so T+1 evaluation understates true accuracy.

    Args:
        symbols: List of ETF symbols to test.
        lookback_days: How many days of history the signal engine needs.
        test_days: How many days to test over.
        eval_horizon: Days to hold after signal before checking return.
            Default 5 (one trading week). Also reports T+1 for comparison.

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
        if df.empty or len(df) < lookback_days + test_days + eval_horizon:
            continue

        factors = precompute_factors(df)

        total_rows = len(df)
        start_idx = max(total_rows - test_days - eval_horizon, lookback_days)

        for i in range(start_idx, total_rows - eval_horizon):
            current_price = float(df["close"].iloc[i])
            direction, score = score_at_index(factors, i, current_price, market_regime=regime)

            # T+1 return (for comparison)
            next_close = float(df["close"].iloc[i + 1])
            ret_1d = (next_close - current_price) / current_price

            # T+N return (primary evaluation)
            future_close = float(df["close"].iloc[i + eval_horizon])
            ret_nd = (future_close - current_price) / current_price

            is_buy = direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)
            is_sell = direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL)

            results_by_dir[direction.value].append(
                {
                    "symbol": symbol,
                    "score": score,
                    "ret_1d": ret_1d,
                    "ret_nd": ret_nd,
                    "correct_1d": (
                        (is_buy and ret_1d > 0)
                        or (is_sell and ret_1d < 0)
                        or (direction == SignalDirection.HOLD and abs(ret_1d) < 0.01)
                    ),
                    "correct_nd": (
                        (is_buy and ret_nd > 0)
                        or (is_sell and ret_nd < 0)
                        or (direction == SignalDirection.HOLD and abs(ret_nd) < 0.02)
                    ),
                }
            )

    # Aggregate results
    summary: dict[str, dict] = {}
    for direction, records in results_by_dir.items():
        if not records:
            summary[direction] = {
                "total": 0,
                "correct_1d": 0,
                "accuracy_1d": 0.0,
                "correct_nd": 0,
                "accuracy_nd": 0.0,
                "avg_return_1d": 0.0,
                "avg_return_nd": 0.0,
            }
            continue

        total = len(records)
        correct_1d = sum(1 for r in records if r["correct_1d"])
        correct_nd = sum(1 for r in records if r["correct_nd"])
        avg_ret_1d = np.mean([r["ret_1d"] for r in records])
        avg_ret_nd = np.mean([r["ret_nd"] for r in records])

        summary[direction] = {
            "total": total,
            "correct_1d": correct_1d,
            "accuracy_1d": round(correct_1d / total * 100, 1) if total > 0 else 0.0,
            "correct_nd": correct_nd,
            "accuracy_nd": round(correct_nd / total * 100, 1) if total > 0 else 0.0,
            "avg_return_1d": round(avg_ret_1d * 100, 2),
            "avg_return_nd": round(avg_ret_nd * 100, 2),
        }

    # Score bucket analysis for buy signals
    all_buys = results_by_dir["buy"] + results_by_dir["strong_buy"]
    score_buckets: list[dict] = []
    if all_buys:
        scores = np.array([r["score"] for r in all_buys])
        rets_1d = np.array([r["ret_1d"] for r in all_buys])
        rets_nd = np.array([r["ret_nd"] for r in all_buys])
        corrects_1d = np.array([r["correct_1d"] for r in all_buys])
        corrects_nd = np.array([r["correct_nd"] for r in all_buys])

        for lo, hi in [(10, 20), (20, 30), (30, 50), (50, 100)]:
            mask = (scores >= lo) & (scores < hi)
            if mask.sum() > 0:
                score_buckets.append(
                    {
                        "range": f"{lo}-{hi}",
                        "count": int(mask.sum()),
                        "accuracy_1d": round(corrects_1d[mask].mean() * 100, 1),
                        "accuracy_nd": round(corrects_nd[mask].mean() * 100, 1),
                        "avg_return_1d": round(rets_1d[mask].mean() * 100, 2),
                        "avg_return_nd": round(rets_nd[mask].mean() * 100, 2),
                    }
                )

    # Overall
    all_records = [r for recs in results_by_dir.values() for r in recs]
    total_all = len(all_records)
    correct_1d_all = sum(1 for r in all_records if r["correct_1d"])
    correct_nd_all = sum(1 for r in all_records if r["correct_nd"])

    buy_correct_1d = sum(1 for r in all_buys if r["correct_1d"]) if all_buys else 0
    buy_correct_nd = sum(1 for r in all_buys if r["correct_nd"]) if all_buys else 0

    return {
        "test_days": test_days,
        "eval_horizon": eval_horizon,
        "total_signals": total_all,
        "overall_accuracy_1d": round(correct_1d_all / total_all * 100, 1) if total_all > 0 else 0.0,
        "overall_accuracy_nd": round(correct_nd_all / total_all * 100, 1) if total_all > 0 else 0.0,
        "by_direction": summary,
        "buy_score_buckets": score_buckets,
        "buy_total": len(all_buys),
        "buy_accuracy_1d": round(buy_correct_1d / len(all_buys) * 100, 1) if all_buys else 0.0,
        "buy_accuracy_nd": round(buy_correct_nd / len(all_buys) * 100, 1) if all_buys else 0.0,
    }
