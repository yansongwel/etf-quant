"""Tests for data quality validators."""

from __future__ import annotations

import numpy as np
import pandas as pd

from data.validators import (
    check_date_gaps,
    check_nan_values,
    check_price_anomalies,
    check_zero_volume,
    validate_symbol,
)


def _make_clean_df(days: int = 60) -> pd.DataFrame:
    """Create clean OHLCV data with no issues."""
    dates = pd.bdate_range("2024-01-01", periods=days)
    close = 3.5 + np.random.normal(0, 0.05, days).cumsum() * 0.01
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": np.random.randint(1_000_000, 10_000_000, days),
        },
        index=dates,
    )


class TestDateGaps:
    def test_no_gaps(self):
        df = _make_clean_df()
        gaps = check_date_gaps(df)
        # Should be minimal/no significant gaps (holidays may show up)
        assert len(gaps) <= 1

    def test_detects_large_gap(self):
        dates = pd.bdate_range("2024-01-01", periods=40).tolist()
        # Remove 10 consecutive business days (a real gap, larger than holiday)
        dates = dates[:10] + dates[20:]
        df = pd.DataFrame(
            {"close": range(len(dates)), "volume": [100] * len(dates)},
            index=pd.DatetimeIndex(dates),
        )
        gaps = check_date_gaps(df)
        assert len(gaps) >= 1

    def test_empty_df(self):
        df = pd.DataFrame()
        assert check_date_gaps(df) == []


class TestPriceAnomalies:
    def test_no_anomalies(self):
        df = _make_clean_df()
        count = check_price_anomalies(df)
        assert count == 0

    def test_detects_large_jump(self):
        np.random.seed(42)
        dates = pd.bdate_range("2024-01-01", periods=10)
        prices = [3.5, 3.5, 3.5, 3.5, 4.5, 3.5, 3.5, 3.5, 3.5, 3.5]  # ~28% jump
        df = pd.DataFrame({"close": prices}, index=dates)
        count = check_price_anomalies(df, max_daily_pct=0.15)
        assert count >= 1  # At least the jump and recovery


class TestZeroVolume:
    def test_no_zeros(self):
        df = _make_clean_df()
        assert check_zero_volume(df) == 0

    def test_detects_zeros(self):
        dates = pd.bdate_range("2024-01-01", periods=5)
        df = pd.DataFrame(
            {"close": [1, 2, 3, 4, 5], "volume": [100, 0, 100, 0, 100]},
            index=dates,
        )
        assert check_zero_volume(df) == 2


class TestNanValues:
    def test_no_nans(self):
        df = _make_clean_df()
        assert check_nan_values(df) == 0

    def test_detects_nans(self):
        dates = pd.bdate_range("2024-01-01", periods=3)
        df = pd.DataFrame(
            {"close": [1.0, float("nan"), 3.0], "volume": [100, 100, 100]},
            index=dates,
        )
        assert check_nan_values(df) == 1


class TestValidateSymbol:
    def test_clean_data_high_score(self):
        df = _make_clean_df(days=100)
        report = validate_symbol(df, "510300")
        assert report.quality_score > 80
        assert report.total_rows == 100
        assert report.symbol == "510300"

    def test_empty_data_zero_score(self):
        report = validate_symbol(pd.DataFrame(), "999999")
        assert report.quality_score == 0
        assert report.total_rows == 0

    def test_to_dict(self):
        df = _make_clean_df()
        report = validate_symbol(df, "510300")
        d = report.to_dict()
        assert "symbol" in d
        assert "quality_score" in d
        assert isinstance(d["quality_score"], float)
