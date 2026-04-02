"""Flow factors — volume and money flow indicators.

Captures institutional activity through volume anomalies, money flow,
and volume-price divergence patterns. These complement momentum/value/volatility
factors by adding a "who's behind the move" dimension.

All functions operate on a single-symbol OHLCV DataFrame with a DatetimeIndex.
No look-ahead: each row only uses data from that row and earlier.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from factors.base import check_nan_ratio, validate_ohlcv


def volume_ratio(volume: pd.Series, window: int = 20) -> pd.Series:
    """Volume relative to N-day moving average.

    Values > 2.0 indicate abnormal volume (potential institutional activity).
    Values < 0.5 indicate low interest / dead volume.
    """
    ma = volume.rolling(window=window, min_periods=window).mean()
    result = volume / ma
    return check_nan_ratio(result, name=f"vol_ratio_{window}d")


def amount_ratio(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Turnover amount relative to N-day average.

    More reliable than volume ratio for ETFs because it accounts for
    price changes (volume * price = amount).
    """
    if "amount" in df.columns:
        amt = df["amount"].copy()
        # Fill NaN amounts (e.g. from realtime quotes) with close * volume
        missing = amt.isna()
        if missing.any():
            amt[missing] = df["close"][missing] * df["volume"][missing]
    else:
        amt = df["close"] * df["volume"]

    ma = amt.rolling(window=window, min_periods=window).mean()
    result = amt / ma
    return check_nan_ratio(result, name=f"amt_ratio_{window}d")


def money_flow_index(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Money Flow Index (MFI) — RSI weighted by volume.

    MFI combines price and volume to measure buying/selling pressure.
    Range: 0-100. Above 80 = overbought, below 20 = oversold.
    More reliable than RSI alone for ETFs with varying liquidity.
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    money_flow = typical_price * df["volume"]

    delta = typical_price.diff()
    positive_flow = pd.Series(0.0, index=df.index)
    negative_flow = pd.Series(0.0, index=df.index)

    positive_flow[delta > 0] = money_flow[delta > 0]
    negative_flow[delta < 0] = money_flow[delta < 0]

    pos_sum = positive_flow.rolling(window=period, min_periods=period).sum()
    neg_sum = negative_flow.rolling(window=period, min_periods=period).sum()

    mfr = pos_sum / neg_sum.replace(0, np.nan)
    result = 100 - (100 / (1 + mfr))
    # Handle edge case: all positive flow → MFI = 100
    result[neg_sum == 0] = 100.0
    result[:period] = float("nan")

    return check_nan_ratio(result, name=f"mfi_{period}")


def on_balance_volume_trend(close: pd.Series, volume: pd.Series, window: int = 20) -> pd.Series:
    """OBV (On-Balance Volume) trend direction.

    OBV accumulates volume on up days, subtracts on down days.
    The slope of OBV's moving average indicates institutional accumulation/distribution.
    Positive = accumulation, negative = distribution.
    """
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv = (direction * volume).cumsum()
    obv_ma = obv.rolling(window=window, min_periods=window).mean()
    # Normalize as percentage change of OBV MA
    result = obv_ma.pct_change(periods=5)
    return check_nan_ratio(result, name=f"obv_trend_{window}d")


def volume_price_divergence(close: pd.Series, volume: pd.Series, window: int = 10) -> pd.Series:
    """Volume-price divergence score.

    Measures disagreement between price trend and volume trend.
    - Price up + volume down = bearish divergence (negative score)
    - Price down + volume up = potential accumulation (positive score)
    - Price and volume aligned = confirmation (near zero)

    Returns: normalized divergence score [-1, 1].
    """
    price_change = close.pct_change(periods=window)
    vol_change = volume.rolling(window=window, min_periods=window).mean().pct_change(periods=window)

    # Normalize both to [-1, 1] range using tanh
    price_norm = np.tanh(price_change * 10)
    vol_norm = np.tanh(vol_change * 5)

    # Divergence: when signs differ, score is large
    # vol_up + price_down = positive (accumulation signal)
    result = vol_norm - price_norm
    return check_nan_ratio(result, name=f"vol_price_div_{window}d")


def smart_money_flow(close: pd.Series, volume: pd.Series, window: int = 20) -> pd.Series:
    """Smart money flow — directional volume accumulation normalized by total.

    Splits volume into "up volume" (close > prev close) and "down volume",
    then computes the ratio: (up_vol - down_vol) / total_vol over a window.

    Range: [-1, 1]. Positive = net buying pressure (smart accumulation).
    Negative = net selling pressure (smart distribution).

    This is a cleaner version of OBV that normalizes by total volume,
    making it comparable across different activity levels.
    """
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    signed_vol = direction * volume

    net_flow = signed_vol.rolling(window=window, min_periods=window).sum()
    total_vol = volume.rolling(window=window, min_periods=window).sum()

    result = net_flow / total_vol.replace(0, np.nan)
    return check_nan_ratio(result, name=f"smart_flow_{window}d")


def volume_acceleration(volume: pd.Series, short: int = 5, long: int = 20) -> pd.Series:
    """Volume acceleration — rate of change in volume momentum.

    Positive = volume trend strengthening (more institutional interest).
    Negative = volume trend fading.
    """
    vol_short = volume.rolling(window=short, min_periods=short).mean()
    vol_long = volume.rolling(window=long, min_periods=long).mean()
    vol_ratio_series = vol_short / vol_long
    result = vol_ratio_series.pct_change(periods=short)
    return check_nan_ratio(result, name="vol_accel")


def compute_flow_factors(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all flow/volume factors for a single-symbol OHLCV DataFrame.

    Returns a new DataFrame with factor columns added (original data preserved).
    """
    if not validate_ohlcv(df, min_rows=60):
        return df

    close = df["close"]
    vol = df["volume"]

    factors = pd.DataFrame(index=df.index)
    factors["vol_ratio_20d"] = volume_ratio(vol, 20)
    factors["amt_ratio_20d"] = amount_ratio(df, 20)
    factors["mfi_14"] = money_flow_index(df, 14)
    factors["obv_trend_20d"] = on_balance_volume_trend(close, vol, 20)
    factors["vol_price_div_10d"] = volume_price_divergence(close, vol, 10)
    factors["vol_accel"] = volume_acceleration(vol, 5, 20)
    factors["smart_flow_20d"] = smart_money_flow(close, vol, 20)

    return pd.concat([df, factors], axis=1)
