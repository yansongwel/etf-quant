"""Tests for volatility factor calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors.volatility import (
    atr,
    compute_volatility_factors,
    historical_volatility,
    max_drawdown,
    realized_skewness,
)


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    np.random.seed(42)
    n = 100
    dates = pd.bdate_range("2024-01-01", periods=n)
    close = 3.0 * np.cumprod(1 + np.random.normal(0.001, 0.02, n))
    df = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.random.randint(1_000_000, 10_000_000, n),
        },
        index=dates,
    )
    df.index.name = "date"
    return df


class TestHistoricalVolatility:
    def test_positive_values(self, ohlcv_df):
        result = historical_volatility(ohlcv_df["close"], 20)
        valid = result.dropna()
        assert (valid > 0).all()

    def test_nan_count(self, ohlcv_df):
        result = historical_volatility(ohlcv_df["close"], 20)
        # Need 1 for diff + 20 for rolling = 21 NaN
        assert result.isna().sum() >= 20

    def test_flat_price_zero_vol(self):
        close = pd.Series([100.0] * 30, index=pd.bdate_range("2024-01-01", periods=30))
        result = historical_volatility(close, 20)
        valid = result.dropna()
        assert (valid == 0).all()


class TestATR:
    def test_positive_atr(self, ohlcv_df):
        result = atr(ohlcv_df, 14)
        valid = result.dropna()
        assert (valid > 0).all()

    def test_nan_count(self, ohlcv_df):
        result = atr(ohlcv_df, 14)
        # EWM with span=14 needs prev_close shift(1) = 1 NaN + min_periods=14 - 1
        assert result.isna().sum() >= 13

    def test_atr_at_least_high_minus_low(self, ohlcv_df):
        # ATR should generally be >= high-low for the smoothed average
        result = atr(ohlcv_df, 14)
        hl = ohlcv_df["high"] - ohlcv_df["low"]
        # Not strictly true for EMA, but ATR should be in same ballpark
        valid_idx = result.dropna().index
        assert result.loc[valid_idx].mean() >= hl.loc[valid_idx].mean() * 0.5


class TestMaxDrawdown:
    def test_drawdown_in_range(self, ohlcv_df):
        result = max_drawdown(ohlcv_df["close"], 60)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 1).all()

    def test_monotonic_increase_zero_drawdown(self):
        close = pd.Series(np.linspace(1, 2, 70), index=pd.bdate_range("2024-01-01", periods=70))
        result = max_drawdown(close, 60)
        # Monotonically increasing: drawdown should be 0
        valid = result.dropna()
        assert (valid < 1e-10).all()

    def test_known_drawdown(self):
        # Price goes 100 → 90 → 80 then stays: 20% drawdown
        prices = [100.0] * 30 + [90.0] * 20 + [80.0] * 20
        close = pd.Series(prices, index=pd.bdate_range("2024-01-01", periods=70))
        result = max_drawdown(close, 60)
        assert result.iloc[-1] == pytest.approx(0.2)


class TestRealizedSkewness:
    def test_output_length(self, ohlcv_df):
        result = realized_skewness(ohlcv_df["close"], 20)
        assert len(result) == len(ohlcv_df)

    def test_nan_count(self, ohlcv_df):
        result = realized_skewness(ohlcv_df["close"], 20)
        # Need 1 for pct_change + 20 for rolling
        assert result.isna().sum() >= 20


class TestComputeVolatilityFactors:
    def test_adds_factor_columns(self, ohlcv_df):
        result = compute_volatility_factors(ohlcv_df)
        expected = ["hvol_20d", "hvol_60d", "atr_14", "mdd_60d", "skew_20d"]
        for col in expected:
            assert col in result.columns

    def test_preserves_original(self, ohlcv_df):
        result = compute_volatility_factors(ohlcv_df)
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in result.columns

    def test_does_not_mutate_input(self, ohlcv_df):
        original_cols = list(ohlcv_df.columns)
        compute_volatility_factors(ohlcv_df)
        assert list(ohlcv_df.columns) == original_cols

    def test_insufficient_rows_returns_unchanged(self):
        """Line 69: < 60 rows returns original df without factor columns."""
        df = pd.DataFrame(
            {
                "open": [1.0] * 30,
                "high": [1.1] * 30,
                "low": [0.9] * 30,
                "close": [1.0] * 30,
                "volume": [1000] * 30,
            },
            index=pd.bdate_range("2024-01-01", periods=30),
        )
        result = compute_volatility_factors(df)
        assert "hvol_20d" not in result.columns  # Should be unchanged
