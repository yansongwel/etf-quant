"""Tests for value factor calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors.value import (
    compute_value_factors,
    ma_deviation,
    price_percentile,
    turnover_ratio,
    vwap_deviation,
)


@pytest.fixture
def close_series() -> pd.Series:
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=150)
    prices = 3.0 * np.cumprod(1 + np.random.normal(0.0, 0.02, 150))
    return pd.Series(prices, index=dates, name="close")


@pytest.fixture
def ohlcv_df(close_series) -> pd.DataFrame:
    n = len(close_series)
    df = pd.DataFrame(
        {
            "open": close_series * 0.999,
            "high": close_series * 1.01,
            "low": close_series * 0.99,
            "close": close_series,
            "volume": np.random.randint(1_000_000, 10_000_000, n),
        },
        index=close_series.index,
    )
    df.index.name = "date"
    return df


class TestMADeviation:
    def test_at_ma_returns_zero(self):
        # Flat price = always at MA
        close = pd.Series([100.0] * 30, index=pd.bdate_range("2024-01-01", periods=30))
        result = ma_deviation(close, 20)
        valid = result.dropna()
        assert (valid.abs() < 1e-10).all()

    def test_above_ma_positive(self):
        # Trending up: last price above MA → positive deviation
        close = pd.Series(np.linspace(1, 2, 30), index=pd.bdate_range("2024-01-01", periods=30))
        result = ma_deviation(close, 20)
        assert result.iloc[-1] > 0

    def test_nan_count(self, close_series):
        result = ma_deviation(close_series, 60)
        assert result.isna().sum() == 59  # rolling needs 60 periods


class TestPricePercentile:
    def test_monotonic_increase_near_one(self):
        close = pd.Series(np.linspace(1, 2, 130), index=pd.bdate_range("2024-01-01", periods=130))
        result = price_percentile(close, 120)
        # Last price is highest in window → percentile near 1
        assert result.iloc[-1] > 0.95

    def test_monotonic_decrease_near_zero(self):
        close = pd.Series(np.linspace(2, 1, 130), index=pd.bdate_range("2024-01-01", periods=130))
        result = price_percentile(close, 120)
        assert result.iloc[-1] < 0.05

    def test_range_zero_to_one(self, close_series):
        result = price_percentile(close_series, 120)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 1).all()

    def test_nan_in_window_returns_nan(self):
        """Line 36: series with NaN within rolling window."""
        close = pd.Series(
            [float("nan")] * 5 + list(range(1, 126)),
            index=pd.bdate_range("2024-01-01", periods=130),
        )
        result = price_percentile(close, 120)
        # First valid window contains NaN → should produce NaN
        assert result.isna().any()


class TestVWAPDeviation:
    def test_output_length(self, ohlcv_df):
        result = vwap_deviation(ohlcv_df, 20)
        assert len(result) == len(ohlcv_df)

    def test_nan_count(self, ohlcv_df):
        result = vwap_deviation(ohlcv_df, 20)
        assert result.isna().sum() >= 19


class TestTurnoverRatio:
    def test_with_volume(self, ohlcv_df):
        result = turnover_ratio(ohlcv_df, 20)
        valid = result.dropna()
        assert (valid > 0).all()

    def test_with_turnover_column(self, ohlcv_df):
        df = ohlcv_df.assign(turnover=np.random.uniform(0.5, 5.0, len(ohlcv_df)))
        result = turnover_ratio(df, 20)
        valid = result.dropna()
        assert (valid > 0).all()


class TestComputeValueFactors:
    def test_adds_factor_columns(self, ohlcv_df):
        result = compute_value_factors(ohlcv_df)
        expected = ["ma_dev_20d", "ma_dev_60d", "price_pctile_120d", "vwap_dev_20d", "turnover_20d"]
        for col in expected:
            assert col in result.columns

    def test_preserves_original(self, ohlcv_df):
        result = compute_value_factors(ohlcv_df)
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in result.columns

    def test_insufficient_data_returns_unchanged(self):
        df = pd.DataFrame(
            {
                "open": [1] * 10,
                "high": [2] * 10,
                "low": [0.5] * 10,
                "close": [1.5] * 10,
                "volume": [100] * 10,
            },
            index=pd.bdate_range("2024-01-01", periods=10),
        )
        result = compute_value_factors(df)
        assert "ma_dev_20d" not in result.columns
