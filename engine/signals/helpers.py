"""Helper utilities for signal computation."""

from __future__ import annotations

import pandas as pd

from factors.momentum import momentum


def _safe_last(series: pd.Series) -> float | None:
    """Get last non-NaN value from a series."""
    if series.empty:
        return None
    val = series.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def _volume_ratio(volume: pd.Series) -> float | None:
    """Compute current volume / 20-day moving average."""
    if len(volume) < 21:
        return None
    current = float(volume.iloc[-1])
    ma20 = float(volume.iloc[-21:-1].mean())
    return current / ma20 if ma20 > 0 else None


def _momentum_acceleration(close: pd.Series) -> float | None:
    """5-day momentum minus 20-day momentum. Positive = accelerating up."""
    if len(close) < 21:
        return None
    m5 = _safe_last(momentum(close, 5))
    m20 = _safe_last(momentum(close, 20))
    if m5 is None or m20 is None:
        return None
    return m5 - m20


def _safe_at(series: pd.Series, idx: int) -> float | None:
    """Get value at index, returning None if NaN or out of bounds."""
    if idx < 0 or idx >= len(series):
        return None
    val = series.iloc[idx]
    if pd.isna(val):
        return None
    return float(val)
