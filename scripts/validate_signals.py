"""Validate historical signals against actual price movements.

Scans signal_history/ for records older than 5 trading days,
validates each against actual returns, and writes a summary report.

Usage:
    PYTHONPATH=. uv run python scripts/validate_signals.py [--days 30]
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta

from config.settings import settings
from engine.tracker import get_overall_accuracy, validate_signals

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

HISTORY_DIR = settings.data.data_dir / "signal_history"
REPORT_DIR = settings.data.data_dir / "signal_accuracy"


def validate_all(lookback_days: int = 30) -> dict:
    """Validate all historical signals and write per-date results."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    today = date.today()
    validated = 0
    skipped = 0

    for days_ago in range(6, lookback_days + 1):
        d = today - timedelta(days=days_ago)
        report_path = REPORT_DIR / f"{d.isoformat()}.json"

        # Skip if already validated
        if report_path.exists():
            skipped += 1
            continue

        result = validate_signals(d)
        if result is None:
            continue

        report_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        validated += 1
        logger.info(
            "Validated %s: %d/%d correct (%.1f%%)",
            d,
            result["correct"],
            result["total_signals"],
            result["accuracy"],
        )

    # Write aggregate report
    accuracy = get_overall_accuracy(lookback_days)
    summary_path = REPORT_DIR / "latest_summary.json"
    summary_path.write_text(
        json.dumps(
            {**accuracy, "generated_date": today.isoformat()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    logger.info("Validated: %d new, %d skipped (already done)", validated, skipped)
    logger.info(
        "Overall accuracy: %.1f%% (%d records)",
        accuracy["overall_accuracy"],
        accuracy["records_checked"],
    )

    # Print per-direction breakdown
    for direction, stats in accuracy.get("by_direction", {}).items():
        logger.info(
            "  %s: %.1f%% (%d signals, avg return %.2f%%)",
            direction,
            stats.get("accuracy", 0),
            stats.get("total", 0),
            stats.get("avg_return", 0),
        )

    return accuracy


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate signal accuracy")
    parser.add_argument("--days", type=int, default=60, help="Lookback days (default: 60)")
    args = parser.parse_args()

    validate_all(args.days)


if __name__ == "__main__":
    main()
