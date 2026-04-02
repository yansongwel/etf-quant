"""Daily data collection script with resume support.

Usage:
    uv run python scripts/collect_daily.py                  # Collect all defaults
    uv run python scripts/collect_daily.py --symbols 510300 510500
    uv run python scripts/collect_daily.py --days 30        # Last 30 days
    uv run python scripts/collect_daily.py --resume          # Skip up-to-date symbols
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from config.constants import DEFAULT_ETF_LIST
from data.collectors.etf_hist import collect_etf_hist
from data.collectors.etf_spot import collect_etf_spot
from data.storage.parquet_store import load_hist, save_hist, save_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETF daily data collection")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="ETF symbols to collect (default: all in watchlist)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365 * 5,
        help="Number of days to look back (default: 5 years)",
    )
    parser.add_argument(
        "--skip-spot",
        action="store_true",
        help="Skip real-time spot snapshot",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip symbols that already have data within last 3 days",
    )
    return parser.parse_args()


def _beijing_today() -> date:
    """Get today's date in Beijing time (UTC+8), which is what A-share market uses."""
    return datetime.now(timezone(timedelta(hours=8))).date()


def _last_trading_day(ref_date: date | None = None) -> date:
    """Get the most recent A-share trading day (skip weekends)."""
    d = ref_date or _beijing_today()
    # If today is weekend, go back to Friday
    while d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        d -= timedelta(days=1)
    return d


def _is_up_to_date(symbol: str, max_age_days: int = 1) -> bool:
    """Check if a symbol's data includes the last trading day.

    Uses Beijing time since A-share market operates in CST (UTC+8).
    """
    df = load_hist(symbol)
    if df.empty:
        return False
    last_date = df.index.max()
    if hasattr(last_date, "date"):
        last_date = last_date.date()
    last_td = _last_trading_day()
    return last_date >= last_td


def main() -> None:
    args = parse_args()

    symbols = args.symbols or [etf["symbol"] for etf in DEFAULT_ETF_LIST]
    end_date = _beijing_today()
    start_date = end_date - timedelta(days=args.days)

    logger.info("Collecting %d ETFs from %s to %s", len(symbols), start_date, end_date)

    # ── Resume: filter out up-to-date symbols ────────────
    if args.resume:
        to_skip = []
        to_collect = []
        for sym in symbols:
            if _is_up_to_date(sym):
                to_skip.append(sym)
            else:
                to_collect.append(sym)
        if to_skip:
            logger.info(
                "Resume: skipping %d up-to-date symbols: %s", len(to_skip), ", ".join(to_skip)
            )
        symbols = to_collect
        if not symbols:
            logger.info("All symbols up to date, nothing to collect")
            return

    # ── Historical OHLCV ──────────────────────────────────
    start_time = time.monotonic()
    succeeded: list[str] = []
    failed: list[str] = []
    total_rows = 0

    for i, symbol in enumerate(symbols, 1):
        logger.info("[%d/%d] Collecting %s...", i, len(symbols), symbol)
        df = collect_etf_hist(symbol, start_date, end_date)
        if df.empty:
            failed.append(symbol)
            continue
        save_hist(df)
        succeeded.append(symbol)
        total_rows += len(df)

    # ── Fallback: Tencent kline + realtime for failed symbols ─
    if failed:
        logger.info("Trying Tencent APIs for %d failed symbols...", len(failed))
        from data.collectors.realtime import fetch_hist_from_tencent, fetch_realtime_quotes

        tencent_ok = []
        for sym in failed:
            existing = load_hist(sym)
            if existing.empty:
                continue

            # Step 1: Backfill missing days via Tencent kline API
            last_date = existing.index.max().date()
            kline_start = last_date + timedelta(days=1)
            if kline_start < end_date:
                kline_df = fetch_hist_from_tencent(sym, kline_start, count=10)
                if not kline_df.empty:
                    # Only keep rows not already in existing
                    new_dates = kline_df.index.difference(existing.index)
                    if len(new_dates) > 0:
                        new_rows = kline_df.loc[new_dates].assign(symbol=sym)
                        existing = pd.concat([existing, new_rows]).sort_index()
                        save_hist(existing)
                        total_rows += len(new_dates)
                        logger.info(
                            "Backfilled %d days for %s via Tencent kline", len(new_dates), sym
                        )

            # Step 2: If still missing today, use realtime quote
            existing = load_hist(sym)  # Reload after potential kline update
            if existing.index.max().date() < _last_trading_day():
                rt_df = fetch_realtime_quotes([sym])
                if not rt_df.empty:
                    r = rt_df.iloc[0]
                    trade_date = pd.Timestamp(r["date"])
                    if trade_date > existing.index.max():
                        new_row = pd.DataFrame(
                            [
                                {
                                    "open": r["open"],
                                    "close": r["close"],
                                    "high": r["high"],
                                    "low": r["low"],
                                    "volume": r["volume"],
                                    "amount": r["amount"],
                                    "pct_change": r["pct_change"],
                                    "turnover": r["turnover"],
                                    "symbol": sym,
                                }
                            ],
                            index=pd.DatetimeIndex([trade_date], name="date"),
                        )
                        updated = pd.concat([existing, new_row]).sort_index()
                        save_hist(updated)
                        total_rows += 1

            tencent_ok.append(sym)

        if tencent_ok:
            logger.info(
                "Tencent fallback succeeded for %d: %s", len(tencent_ok), ", ".join(tencent_ok)
            )
            succeeded.extend(tencent_ok)
            failed = [s for s in failed if s not in tencent_ok]

    # ── Spot snapshot ─────────────────────────────────────
    if not args.skip_spot:
        all_symbols = args.symbols or [etf["symbol"] for etf in DEFAULT_ETF_LIST]
        spot_df = collect_etf_spot(all_symbols)
        if not spot_df.empty:
            save_snapshot(spot_df)

    # ── Summary report ────────────────────────────────────
    elapsed = time.monotonic() - start_time
    logger.info("=" * 60)
    logger.info("Collection complete in %.1fs", elapsed)
    logger.info("  Succeeded: %d (%s)", len(succeeded), ", ".join(succeeded) if succeeded else "-")
    logger.info("  Failed:    %d (%s)", len(failed), ", ".join(failed) if failed else "-")
    logger.info("  Total rows: %d", total_rows)
    logger.info("=" * 60)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
