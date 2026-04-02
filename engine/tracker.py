"""Signal accuracy tracker — records predictions and validates against reality.

Flow:
1. record_signals(): Save today's signals to disk (called daily after market close)
2. validate_signals(): Compare N-day-old signals against actual price moves
3. get_accuracy(): Return hit rate + per-factor performance stats
4. Auto-adjust factor weights based on historical accuracy

Storage: data_store/signal_history/{date}.json
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from config.settings import settings
from data.storage.parquet_store import load_hist
from engine.signals import TradingSignal

logger = logging.getLogger(__name__)

HISTORY_DIR = settings.data.data_dir / "signal_history"
ACCURACY_FILE = settings.data.data_dir / "signal_accuracy.json"
VALIDATE_AFTER_DAYS = 5  # Check signal accuracy after 5 trading days


def _ensure_dir() -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORY_DIR


def record_signals(signals: list[TradingSignal], record_date: date | None = None) -> Path:
    """Save today's signals to disk for later validation.

    Returns the path of the saved file.
    """
    _ensure_dir()
    d = record_date or date.today()
    file_path = HISTORY_DIR / f"{d.isoformat()}.json"

    records = []
    for s in signals:
        records.append(
            {
                "symbol": s.symbol,
                "direction": s.direction.value,
                "score": s.score,
                "strength": s.strength,
                "current_price": s.current_price,
                "entry_price": s.entry_price,
                "target_price": s.target_price,
                "stop_loss": s.stop_loss,
                "factors": {k: v for k, v in s.factors.items()},
            }
        )

    file_path.write_text(
        json.dumps(
            {
                "date": d.isoformat(),
                "count": len(records),
                "signals": records,
            },
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    logger.info("Recorded %d signals for %s → %s", len(records), d, file_path)
    return file_path


def _load_record(d: date) -> dict | None:
    """Load a signal record for a specific date."""
    file_path = HISTORY_DIR / f"{d.isoformat()}.json"
    if not file_path.exists():
        return None
    return json.loads(file_path.read_text(encoding="utf-8"))


def validate_signals(signal_date: date, check_after_days: int = VALIDATE_AFTER_DAYS) -> dict | None:
    """Compare a past signal record against actual price movement.

    Args:
        signal_date: The date the signals were generated.
        check_after_days: How many trading days later to check.

    Returns:
        Validation result dict or None if data unavailable.
    """
    record = _load_record(signal_date)
    if not record:
        return None

    results = []
    correct = 0
    total = 0

    for sig in record["signals"]:
        symbol = sig["symbol"]
        df = load_hist(symbol)
        if df.empty:
            continue

        # Find the signal date and N days later in the data
        signal_dt = pd.Timestamp(signal_date)
        if signal_dt not in df.index:
            # Find nearest trading date
            mask = df.index >= signal_dt
            if not mask.any():
                continue
            signal_dt = df.index[mask][0]

        signal_idx = df.index.get_loc(signal_dt)
        check_idx = signal_idx + check_after_days

        if check_idx >= len(df):
            continue

        price_at_signal = float(df.iloc[signal_idx]["close"])
        price_after = float(df.iloc[check_idx]["close"])
        actual_return = (price_after - price_at_signal) / price_at_signal

        # Was the signal correct?
        direction = sig["direction"]
        if direction in ("strong_buy", "buy"):
            hit = actual_return > 0
        elif direction in ("strong_sell", "sell"):
            hit = actual_return < 0
        else:
            hit = abs(actual_return) < 0.02  # Hold = price stayed flat

        total += 1
        if hit:
            correct += 1

        results.append(
            {
                "symbol": symbol,
                "direction": direction,
                "score": sig["score"],
                "price_at_signal": round(price_at_signal, 4),
                "price_after": round(price_after, 4),
                "actual_return": round(actual_return * 100, 2),
                "hit": hit,
            }
        )

    if total == 0:
        return None

    accuracy = correct / total

    return {
        "signal_date": signal_date.isoformat(),
        "check_after_days": check_after_days,
        "total_signals": total,
        "correct": correct,
        "accuracy": round(accuracy * 100, 1),
        "details": results,
    }


def get_overall_accuracy(lookback_days: int = 30) -> dict:
    """Calculate overall signal accuracy over recent history.

    Returns aggregate stats + per-direction breakdown.
    """
    _ensure_dir()
    today = date.today()
    all_validations: list[dict] = []

    for days_ago in range(VALIDATE_AFTER_DAYS + 1, lookback_days + 1):
        d = today - timedelta(days=days_ago)
        validation = validate_signals(d)
        if validation:
            all_validations.append(validation)

    if not all_validations:
        return {
            "period_days": lookback_days,
            "records_checked": 0,
            "overall_accuracy": 0,
            "by_direction": {},
            "message": "暂无足够历史记录进行准确率统计",
        }

    # Aggregate
    total_correct = sum(v["correct"] for v in all_validations)
    total_signals = sum(v["total_signals"] for v in all_validations)
    overall = total_correct / total_signals if total_signals > 0 else 0

    # Per-direction breakdown
    by_dir: dict[str, dict] = {}
    for v in all_validations:
        for d in v["details"]:
            direction = d["direction"]
            if direction not in by_dir:
                by_dir[direction] = {"total": 0, "correct": 0, "avg_return": 0}
            by_dir[direction]["total"] += 1
            if d["hit"]:
                by_dir[direction]["correct"] += 1
            by_dir[direction]["avg_return"] += d["actual_return"]

    for direction in by_dir:
        n = by_dir[direction]["total"]
        by_dir[direction]["accuracy"] = (
            round(by_dir[direction]["correct"] / n * 100, 1) if n > 0 else 0
        )
        by_dir[direction]["avg_return"] = (
            round(by_dir[direction]["avg_return"] / n, 2) if n > 0 else 0
        )

    return {
        "period_days": lookback_days,
        "records_checked": len(all_validations),
        "total_signals": total_signals,
        "overall_accuracy": round(overall * 100, 1),
        "by_direction": by_dir,
    }


def suggest_weight_adjustment() -> dict[str, float]:
    """Based on accuracy data, suggest new factor weights.

    If buy signals are inaccurate → reduce momentum weight.
    If hold signals are wrong → adjust value/volatility weights.
    """
    accuracy = get_overall_accuracy(60)

    # Default weights
    weights = {"momentum": 0.5, "value": 0.3, "volatility": 0.2}

    if accuracy["records_checked"] < 5:
        return {**weights, "_note": "样本不足，使用默认权重"}

    by_dir = accuracy.get("by_direction", {})

    # If buy accuracy > 60%, boost momentum (trend following works)
    buy_acc = by_dir.get("buy", {}).get("accuracy", 50)
    strong_buy_acc = by_dir.get("strong_buy", {}).get("accuracy", 50)
    avg_buy_acc = (buy_acc + strong_buy_acc) / 2

    if avg_buy_acc > 60:
        weights["momentum"] = min(0.7, weights["momentum"] + 0.1)
        weights["value"] = max(0.1, weights["value"] - 0.05)
        weights["volatility"] = max(0.1, weights["volatility"] - 0.05)
    elif avg_buy_acc < 40:
        # Momentum signals are bad → lean into value (mean reversion)
        weights["momentum"] = max(0.2, weights["momentum"] - 0.15)
        weights["value"] = min(0.5, weights["value"] + 0.1)
        weights["volatility"] = min(0.3, weights["volatility"] + 0.05)

    # Normalize to sum to 1
    total = sum(weights.values())
    weights = {k: round(v / total, 2) for k, v in weights.items()}

    return {**weights, "_accuracy_base": accuracy["overall_accuracy"]}
