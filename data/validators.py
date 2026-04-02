"""Data quality validation for ETF historical data.

Checks for common data issues:
- Missing trading dates (gaps)
- Price anomalies (extreme moves, zero/negative prices)
- Volume anomalies (zero volume on trading days)
- Sufficient history length
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)

# A-share market trading calendar approximation: weekdays excluding known holidays
# For precise checks, we'd need an actual holiday calendar; using bday as approximation.


@dataclass(frozen=True)
class QualityReport:
    """Data quality report for a single symbol."""

    symbol: str
    total_rows: int
    date_range: str
    trading_days: int
    gap_count: int
    gap_dates: tuple[str, ...]
    zero_volume_count: int
    price_anomaly_count: int
    nan_count: int
    quality_score: float  # 0-100

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "total_rows": self.total_rows,
            "date_range": self.date_range,
            "trading_days": self.trading_days,
            "gap_count": self.gap_count,
            "gap_dates": list(self.gap_dates[:10]),  # limit to 10
            "zero_volume_count": self.zero_volume_count,
            "price_anomaly_count": self.price_anomaly_count,
            "nan_count": self.nan_count,
            "quality_score": round(self.quality_score, 1),
        }


def check_date_gaps(df: pd.DataFrame) -> list[str]:
    """Find missing business days in the index."""
    if df.empty or len(df) < 2:
        return []

    full_range = pd.bdate_range(df.index.min(), df.index.max())
    missing = full_range.difference(df.index)

    # Filter: only count gaps > 3 consecutive business days as real gaps
    # (short gaps may be holidays)
    gap_dates: list[str] = []
    if len(missing) == 0:
        return gap_dates

    # Group consecutive missing dates
    groups: list[list[pd.Timestamp]] = []
    current_group: list[pd.Timestamp] = [missing[0]]

    for i in range(1, len(missing)):
        if (missing[i] - missing[i - 1]).days <= 5:
            current_group.append(missing[i])
        else:
            groups.append(current_group)
            current_group = [missing[i]]
    groups.append(current_group)

    # Only report groups > 7 business days as real gaps
    # (Chinese holidays like 国庆 and 春节 can be 5-7 bdays long)
    for group in groups:
        if len(group) > 7:
            gap_dates.append(f"{group[0].date()} ~ {group[-1].date()} ({len(group)} days)")

    return gap_dates


def check_price_anomalies(df: pd.DataFrame, max_daily_pct: float = 0.15) -> int:
    """Count days with unreasonable price movements.

    For A-share market: normal limit is ±10% for stocks, ±20% for some ETFs.
    We use 15% as threshold.
    """
    if "close" not in df.columns or len(df) < 2:
        return 0

    returns = df["close"].pct_change().abs()
    anomalies = returns > max_daily_pct
    count = int(anomalies.sum())

    if count > 0:
        logger.warning(
            "Found %d price anomalies (>%.0f%% daily move)",
            count,
            max_daily_pct * 100,
        )
    return count


def check_zero_volume(df: pd.DataFrame) -> int:
    """Count days with zero volume (suspicious for actively traded ETFs)."""
    if "volume" not in df.columns:
        return 0
    return int((df["volume"] == 0).sum())


def check_nan_values(df: pd.DataFrame) -> int:
    """Count total NaN values across OHLCV columns."""
    ohlcv = ["open", "high", "low", "close", "volume"]
    cols = [c for c in ohlcv if c in df.columns]
    return int(df[cols].isna().sum().sum())


def validate_symbol(df: pd.DataFrame, symbol: str = "") -> QualityReport:
    """Run all quality checks on a single symbol's data."""
    if df.empty:
        return QualityReport(
            symbol=symbol,
            total_rows=0,
            date_range="N/A",
            trading_days=0,
            gap_count=0,
            gap_dates=(),
            zero_volume_count=0,
            price_anomaly_count=0,
            nan_count=0,
            quality_score=0.0,
        )

    # Basic stats
    total_rows = len(df)
    start = str(df.index.min().date()) if hasattr(df.index.min(), "date") else str(df.index.min())
    end = str(df.index.max().date()) if hasattr(df.index.max(), "date") else str(df.index.max())
    date_range = f"{start} ~ {end}"
    trading_days = len(pd.bdate_range(df.index.min(), df.index.max()))

    # Quality checks
    gaps = check_date_gaps(df)
    price_anomalies = check_price_anomalies(df)
    zero_vol = check_zero_volume(df)
    nan_count = check_nan_values(df)

    # Quality score (100 = perfect)
    # A-share market has ~12 holidays/year → ~242 real trading days vs ~252 bdays
    # Adjust expected trading days by ~4% to account for this
    score = 100.0
    if trading_days > 0:
        expected_days = trading_days * 0.96  # Adjust for Chinese holidays
        coverage = total_rows / expected_days
        score *= min(coverage, 1.0)
    score -= len(gaps) * 5  # -5 per significant gap
    score -= price_anomalies * 2  # -2 per anomaly
    score -= zero_vol * 1  # -1 per zero volume day
    score -= nan_count * 0.5  # -0.5 per NaN
    score = max(0.0, min(100.0, score))

    return QualityReport(
        symbol=symbol,
        total_rows=total_rows,
        date_range=date_range,
        trading_days=trading_days,
        gap_count=len(gaps),
        gap_dates=tuple(gaps),
        zero_volume_count=zero_vol,
        price_anomaly_count=price_anomalies,
        nan_count=nan_count,
        quality_score=score,
    )
