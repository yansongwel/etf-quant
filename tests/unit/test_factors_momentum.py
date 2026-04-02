"""Tests for momentum factor calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors.momentum import (
    compute_momentum_factors,
    momentum,
    moving_average_ratio,
    rate_of_change,
    returns,
    rsi,
)


@pytest.fixture
def close_series() -> pd.Series:
    """100 days of synthetic close prices with a known uptrend."""
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=100)
    # Uptrend: start at 3.0, drift up ~0.1% per day + noise
    prices = 3.0 * np.cumprod(1 + np.random.normal(0.001, 0.02, 100))
    return pd.Series(prices, index=dates, name="close")


@pytest.fixture
def ohlcv_df(close_series) -> pd.DataFrame:
    """Full OHLCV DataFrame built from close_series."""
    df = pd.DataFrame(
        {
            "open": close_series * 0.999,
            "high": close_series * 1.01,
            "low": close_series * 0.99,
            "close": close_series,
            "volume": np.random.randint(1_000_000, 10_000_000, len(close_series)),
        },
        index=close_series.index,
    )
    df.index.name = "date"
    return df


class TestReturns:
    def test_1d_returns(self, close_series):
        result = returns(close_series, 1)
        assert len(result) == len(close_series)
        assert result.isna().sum() == 1  # first value is NaN

    def test_5d_returns(self, close_series):
        result = returns(close_series, 5)
        assert result.isna().sum() == 5

    def test_manual_check(self):
        close = pd.Series([100.0, 110.0, 105.0], index=pd.bdate_range("2024-01-01", periods=3))
        result = returns(close, 1)
        assert result.iloc[1] == pytest.approx(0.1)
        assert result.iloc[2] == pytest.approx(-5 / 110)


class TestMomentum:
    def test_lookback_nan_count(self, close_series):
        result = momentum(close_series, 20)
        assert result.isna().sum() == 20

    def test_positive_return_when_uptrend(self):
        close = pd.Series(
            [1.0, 1.1, 1.2, 1.3, 1.4],
            index=pd.bdate_range("2024-01-01", periods=5),
        )
        result = momentum(close, 2)
        # At index 2: 1.2/1.0 - 1 = 0.2
        assert result.iloc[2] == pytest.approx(0.2)


class TestRSI:
    def test_rsi_range(self, close_series):
        result = rsi(close_series, 14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_all_gains(self):
        # Monotonically increasing → RSI near 100 (need enough data)
        close = pd.Series(range(1, 51), index=pd.bdate_range("2024-01-01", periods=50), dtype=float)
        result = rsi(close, 14)
        assert result.iloc[-1] > 95

    def test_rsi_all_losses(self):
        close = pd.Series(
            range(50, 0, -1), index=pd.bdate_range("2024-01-01", periods=50), dtype=float
        )
        result = rsi(close, 14)
        assert result.iloc[-1] < 5


class TestRateOfChange:
    def test_basic(self):
        close = pd.Series(
            [100.0, 110.0, 120.0],
            index=pd.bdate_range("2024-01-01", periods=3),
        )
        result = rate_of_change(close, 1)
        assert result.iloc[1] == pytest.approx(10.0)

    def test_nan_count(self, close_series):
        result = rate_of_change(close_series, 10)
        assert result.isna().sum() == 10


class TestMovingAverageRatio:
    def test_uptrend_ratio_above_one(self):
        # Steady uptrend: short MA should be above long MA
        close = pd.Series(np.linspace(1, 2, 30), index=pd.bdate_range("2024-01-01", periods=30))
        result = moving_average_ratio(close, short=5, long=20)
        assert result.iloc[-1] > 1.0

    def test_nan_count(self, close_series):
        result = moving_average_ratio(close_series, 5, 20)
        assert result.isna().sum() >= 19  # Need at least `long` periods


class TestComputeMomentumFactors:
    def test_adds_factor_columns(self, ohlcv_df):
        result = compute_momentum_factors(ohlcv_df)
        expected_cols = [
            "ret_5d",
            "ret_10d",
            "ret_20d",
            "ret_60d",
            "momentum_20d",
            "rsi_14",
            "roc_10",
            "ma_ratio_5_20",
        ]
        for col in expected_cols:
            assert col in result.columns

    def test_preserves_original_columns(self, ohlcv_df):
        result = compute_momentum_factors(ohlcv_df)
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in result.columns

    def test_does_not_mutate_input(self, ohlcv_df):
        original_cols = list(ohlcv_df.columns)
        compute_momentum_factors(ohlcv_df)
        assert list(ohlcv_df.columns) == original_cols

    def test_insufficient_data_returns_unchanged(self):
        df = pd.DataFrame(
            {"open": [1], "high": [2], "low": [0.5], "close": [1.5], "volume": [100]},
            index=pd.bdate_range("2024-01-01", periods=1),
        )
        result = compute_momentum_factors(df)
        assert "ret_5d" not in result.columns
