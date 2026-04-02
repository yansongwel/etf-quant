"""Volatility factors — risk and dispersion indicators.

All functions operate on single-symbol OHLCV DataFrames with DatetimeIndex.
No look-ahead bias.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from factors.base import check_nan_ratio, validate_ohlcv


def historical_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    """Annualized historical volatility (rolling std of log returns).

    vol = std(log_returns, window) * sqrt(252)
    252 = approximate trading days per year for A-share market.
    """
    log_ret = np.log(close / close.shift(1))
    result = log_ret.rolling(window=window, min_periods=window).std() * np.sqrt(252)
    return check_nan_ratio(result, name=f"hvol_{window}d")


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (ATR).

    TR = max(high-low, |high-prev_close|, |low-prev_close|)
    ATR = EMA(TR, period)
    """
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    result = true_range.ewm(span=period, min_periods=period, adjust=False).mean()
    return check_nan_ratio(result, name=f"atr_{period}")


def max_drawdown(close: pd.Series, window: int = 60) -> pd.Series:
    """Rolling maximum drawdown over a lookback window.

    MDD = (cummax - current) / cummax  (positive value = bigger drawdown)
    """
    rolling_max = close.rolling(window=window, min_periods=1).max()
    drawdown = (rolling_max - close) / rolling_max
    result = drawdown.rolling(window=window, min_periods=window).max()
    return check_nan_ratio(result, name=f"mdd_{window}d")


def realized_skewness(close: pd.Series, window: int = 20) -> pd.Series:
    """Rolling skewness of daily returns.

    Negative skew = heavier left tail (more crash risk).
    """
    daily_ret = close.pct_change()
    result = daily_ret.rolling(window=window, min_periods=window).skew()
    return check_nan_ratio(result, name=f"skew_{window}d")


def volatility_regime(close: pd.Series, short: int = 20, long: int = 60) -> pd.Series:
    """Volatility regime indicator: short-term vol / long-term vol.

    Values > 1.5 indicate volatility expansion (crisis/opportunity).
    Values < 0.7 indicate volatility compression (calm, breakout pending).

    This is useful for position sizing:
    - High regime → reduce position size (risk management)
    - Low regime → normal or increased size (trend is stable)
    """
    vol_short = historical_volatility(close, short)
    vol_long = historical_volatility(close, long)
    result = vol_short / vol_long.replace(0, np.nan)
    return check_nan_ratio(result, name=f"vol_regime_{short}_{long}")


def compute_volatility_factors(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all volatility factors for a single-symbol OHLCV DataFrame.

    Returns a new DataFrame with factor columns added.
    """
    if not validate_ohlcv(df, min_rows=60):
        return df

    factors = pd.DataFrame(index=df.index)
    factors["hvol_20d"] = historical_volatility(df["close"], 20)
    factors["hvol_60d"] = historical_volatility(df["close"], 60)
    factors["atr_14"] = atr(df, 14)
    factors["mdd_60d"] = max_drawdown(df["close"], 60)
    factors["skew_20d"] = realized_skewness(df["close"], 20)
    factors["vol_regime"] = volatility_regime(df["close"], 20, 60)

    return pd.concat([df, factors], axis=1)
