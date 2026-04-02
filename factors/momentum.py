"""Momentum factors — price-based trend and strength indicators.

All functions operate on a single-symbol OHLCV DataFrame with a DatetimeIndex.
No look-ahead: each row only uses data from that row and earlier.
"""

from __future__ import annotations

import pandas as pd

from factors.base import check_nan_ratio, validate_ohlcv


def returns(close: pd.Series, period: int = 1) -> pd.Series:
    """Simple return over N periods: (close[t] - close[t-N]) / close[t-N].

    Args:
        close: Close price series with DatetimeIndex.
        period: Lookback period in trading days.

    Returns:
        Series of returns, first `period` values are NaN.
    """
    result = close.pct_change(periods=period)
    return check_nan_ratio(result, name=f"returns_{period}d")


def momentum(close: pd.Series, lookback: int = 20) -> pd.Series:
    """Cumulative return over lookback window (same as returns but named for clarity).

    Classic momentum factor: (price_today / price_N_days_ago) - 1
    """
    result = close / close.shift(lookback) - 1
    return check_nan_ratio(result, name=f"momentum_{lookback}d")


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (RSI).

    RSI = 100 - (100 / (1 + RS))
    RS = avg_gain / avg_loss over `period` days (exponential moving average).

    Returns values in [0, 100]. Higher = more overbought.
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    # When avg_loss is 0 (all gains), RSI = 100
    # When avg_gain is 0 (all losses), RSI = 0
    rs = avg_gain / avg_loss
    result = pd.Series(100.0, index=close.index, dtype=float)
    valid = avg_loss > 0
    result[valid] = 100 - (100 / (1 + rs[valid]))
    # Where avg_loss == 0 but avg_gain > 0 → RSI = 100 (already set)
    # Where both are 0 → RSI = 50 (neutral)
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    result[both_zero] = 50.0
    # Keep NaN for initial periods
    result[:period] = float("nan")
    return check_nan_ratio(result, name=f"rsi_{period}")


def rate_of_change(close: pd.Series, period: int = 10) -> pd.Series:
    """Rate of Change (ROC): percentage change over N periods.

    ROC = (close[t] / close[t-N] - 1) * 100
    """
    result = (close / close.shift(period) - 1) * 100
    return check_nan_ratio(result, name=f"roc_{period}")


def moving_average_ratio(close: pd.Series, short: int = 5, long: int = 20) -> pd.Series:
    """Ratio of short-term MA to long-term MA.

    Values > 1 indicate uptrend (short MA above long MA).
    Values < 1 indicate downtrend.
    """
    ma_short = close.rolling(window=short, min_periods=short).mean()
    ma_long = close.rolling(window=long, min_periods=long).mean()
    result = ma_short / ma_long
    return check_nan_ratio(result, name=f"ma_ratio_{short}_{long}")


def compute_momentum_factors(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all momentum factors for a single-symbol OHLCV DataFrame.

    Returns a new DataFrame with factor columns added (original data preserved).
    """
    if not validate_ohlcv(df, min_rows=60):
        return df

    close = df["close"]

    factors = pd.DataFrame(index=df.index)
    factors["ret_5d"] = returns(close, 5)
    factors["ret_10d"] = returns(close, 10)
    factors["ret_20d"] = returns(close, 20)
    factors["ret_60d"] = returns(close, 60)
    factors["momentum_20d"] = momentum(close, 20)
    factors["rsi_14"] = rsi(close, 14)
    factors["roc_10"] = rate_of_change(close, 10)
    factors["ma_ratio_5_20"] = moving_average_ratio(close, 5, 20)

    return pd.concat([df, factors], axis=1)
