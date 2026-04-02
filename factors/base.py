"""Base factor utilities — common helpers for all factor calculations.

All factor functions are pure: same input → same output, no side effects.
Only use data available up to and including the current row (no look-ahead).
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Maximum allowed NaN ratio before warning
NAN_WARN_THRESHOLD = 0.05


def validate_ohlcv(df: pd.DataFrame, min_rows: int = 2) -> bool:
    """Check that a DataFrame has required OHLCV columns and sufficient rows."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        logger.error("Missing OHLCV columns: %s", missing)
        return False
    if len(df) < min_rows:
        logger.error("Insufficient data: %d rows (need >= %d)", len(df), min_rows)
        return False
    return True


def check_nan_ratio(series: pd.Series, name: str = "") -> pd.Series:
    """Log warning if NaN ratio exceeds threshold, return the series unchanged."""
    if series.empty:
        return series
    ratio = series.isna().sum() / len(series)
    if ratio > NAN_WARN_THRESHOLD:
        logger.warning(
            "Factor '%s' has %.1f%% NaN values (%d/%d)",
            name or series.name or "unnamed",
            ratio * 100,
            series.isna().sum(),
            len(series),
        )
    return series


def rank_cross_section(df: pd.DataFrame, column: str) -> pd.Series:
    """Rank values cross-sectionally (across symbols at each date).

    Returns percentile rank [0, 1] where 1 = highest.
    Requires a MultiIndex (date, symbol) or a 'date' column.
    """
    if isinstance(df.index, pd.MultiIndex):
        return df.groupby(level=0)[column].rank(pct=True)
    return df.groupby("date")[column].rank(pct=True)
