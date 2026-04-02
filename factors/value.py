"""Value factors — mean-reversion and relative value indicators.

Since ETFs don't have direct PE/PB, we use price-based value proxies:
- Distance from moving average (mean reversion signal)
- Price percentile rank over lookback window
- Volume-weighted average price deviation
"""

from __future__ import annotations

import pandas as pd

from factors.base import check_nan_ratio, validate_ohlcv


def ma_deviation(close: pd.Series, window: int = 60) -> pd.Series:
    """Deviation from moving average as a percentage.

    (close - MA) / MA
    Negative = below MA (potentially undervalued / mean reversion opportunity).
    """
    ma = close.rolling(window=window, min_periods=window).mean()
    result = (close - ma) / ma
    return check_nan_ratio(result, name=f"ma_dev_{window}d")


def price_percentile(close: pd.Series, window: int = 120) -> pd.Series:
    """Rolling percentile rank of current price within lookback window.

    0 = at the lowest point in the window, 1 = at the highest.
    Low values = potentially cheap (value signal).
    """

    def _pct_rank(s: pd.Series) -> float:
        if s.isna().any() or len(s) < 2:
            return float("nan")
        return (s.iloc[-1:].values[0] > s.iloc[:-1]).sum() / (len(s) - 1)

    result = close.rolling(window=window, min_periods=window).apply(_pct_rank, raw=False)
    return check_nan_ratio(result, name=f"price_pctile_{window}d")


def vwap_deviation(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Deviation from Volume-Weighted Average Price (VWAP).

    VWAP = sum(price * volume) / sum(volume) over window.
    Deviation = (close - VWAP) / VWAP
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical_price * df["volume"]
    vwap = (
        pv.rolling(window=window, min_periods=window).sum()
        / df["volume"].rolling(window=window, min_periods=window).sum()
    )
    result = (df["close"] - vwap) / vwap
    return check_nan_ratio(result, name=f"vwap_dev_{window}d")


def turnover_ratio(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Average turnover ratio over window.

    Higher turnover can indicate more speculative activity.
    Uses the 'turnover' column if available, otherwise computes from volume/amount.
    """
    if "turnover" in df.columns:
        result = df["turnover"].rolling(window=window, min_periods=window).mean()
    else:
        result = df["volume"].rolling(window=window, min_periods=window).mean()
    return check_nan_ratio(result, name=f"turnover_{window}d")


def compute_value_factors(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all value factors for a single-symbol OHLCV DataFrame.

    Returns a new DataFrame with factor columns added.
    """
    if not validate_ohlcv(df, min_rows=120):
        return df

    close = df["close"]

    factors = pd.DataFrame(index=df.index)
    factors["ma_dev_20d"] = ma_deviation(close, 20)
    factors["ma_dev_60d"] = ma_deviation(close, 60)
    factors["price_pctile_120d"] = price_percentile(close, 120)
    factors["vwap_dev_20d"] = vwap_deviation(df, 20)
    factors["turnover_20d"] = turnover_ratio(df, 20)

    return pd.concat([df, factors], axis=1)
