"""ETF historical OHLCV data collector via AkShare."""

from __future__ import annotations

import logging
from datetime import date

import akshare as ak
import pandas as pd

from config.constants import AKSHARE_DATE_FORMAT, ETF_HIST_COLUMNS
from data.collectors.base import fetch_with_retry, normalize_columns

logger = logging.getLogger(__name__)


def collect_etf_hist(
    symbol: str,
    start_date: date,
    end_date: date,
    period: str = "daily",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """Fetch historical OHLCV for a single ETF.

    Args:
        symbol: 6-digit ETF code, e.g. "510300".
        start_date: Start date (inclusive).
        end_date: End date (inclusive).
        period: "daily", "weekly", or "monthly".
        adjust: "qfq" (forward), "hfq" (backward), or "" (no adjust).

    Returns:
        DataFrame with standardized English columns and a datetime index.
        Empty DataFrame if the fetch fails.
    """
    raw = fetch_with_retry(
        ak.fund_etf_hist_em,
        symbol=symbol,
        period=period,
        start_date=start_date.strftime(AKSHARE_DATE_FORMAT),
        end_date=end_date.strftime(AKSHARE_DATE_FORMAT),
        adjust=adjust,
    )

    if raw.empty:
        return raw

    df = normalize_columns(raw, ETF_HIST_COLUMNS)
    df = df.assign(
        date=pd.to_datetime(df["date"]),
        symbol=symbol,
    )
    df = df.set_index("date").sort_index()

    logger.info("Collected %d rows for %s (%s ~ %s)", len(df), symbol, start_date, end_date)
    return df


def collect_etf_hist_batch(
    symbols: list[str],
    start_date: date,
    end_date: date,
    period: str = "daily",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """Fetch historical data for multiple ETFs and concatenate.

    Returns a single DataFrame with a 'symbol' column to distinguish ETFs.
    Skips symbols that fail silently (logged as warnings).
    """
    frames: list[pd.DataFrame] = []

    for symbol in symbols:
        df = collect_etf_hist(symbol, start_date, end_date, period, adjust)
        if not df.empty:
            frames.append(df)

    if not frames:
        logger.warning("No data collected for any of %d symbols", len(symbols))
        return pd.DataFrame()

    return pd.concat(frames)
