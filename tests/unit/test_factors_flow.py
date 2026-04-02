"""Tests for flow factors — volume and money flow indicators."""

from __future__ import annotations

import numpy as np
import pandas as pd

from factors.flow import (
    amount_ratio,
    compute_flow_factors,
    money_flow_index,
    on_balance_volume_trend,
    volume_acceleration,
    volume_price_divergence,
    volume_ratio,
)


def _make_ohlcv(days: int = 100, trend: float = 0.001) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=days)
    close = 4.0 * np.cumprod(1 + np.random.normal(trend, 0.02, days))
    volume = np.random.randint(1_000_000, 10_000_000, days).astype(float)
    high = close * (1 + np.random.uniform(0, 0.02, days))
    low = close * (1 - np.random.uniform(0, 0.02, days))
    return pd.DataFrame(
        {
            "open": close * (1 + np.random.normal(0, 0.005, days)),
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "amount": close * volume,
        },
        index=dates,
    )


class TestVolumeRatio:
    def test_basic(self) -> None:
        df = _make_ohlcv()
        result = volume_ratio(df["volume"], 20)
        assert not result.empty
        assert result.iloc[-1] > 0
        # First 19 values should be NaN (window=20)
        assert result.iloc[:19].isna().all()

    def test_spike_detection(self) -> None:
        df = _make_ohlcv()
        # Create a volume spike
        df.iloc[-1, df.columns.get_loc("volume")] = df["volume"].mean() * 5
        result = volume_ratio(df["volume"], 20)
        assert result.iloc[-1] > 2.0  # Should detect spike


class TestAmountRatio:
    def test_with_amount_column(self) -> None:
        df = _make_ohlcv()
        result = amount_ratio(df, 20)
        assert not result.empty
        assert not np.isnan(result.iloc[-1])

    def test_without_amount_column(self) -> None:
        df = _make_ohlcv().drop(columns=["amount"])
        result = amount_ratio(df, 20)
        assert not result.empty
        assert not np.isnan(result.iloc[-1])

    def test_nan_amount_filled(self) -> None:
        df = _make_ohlcv()
        df.iloc[-1, df.columns.get_loc("amount")] = np.nan
        result = amount_ratio(df, 20)
        # Should fill NaN with close*volume, not propagate NaN
        assert not np.isnan(result.iloc[-1])


class TestMoneyFlowIndex:
    def test_range(self) -> None:
        df = _make_ohlcv()
        result = money_flow_index(df, 14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_initial_nan(self) -> None:
        df = _make_ohlcv()
        result = money_flow_index(df, 14)
        assert result.iloc[:14].isna().all()


class TestOBVTrend:
    def test_basic(self) -> None:
        df = _make_ohlcv(trend=0.01)  # Uptrend
        result = on_balance_volume_trend(df["close"], df["volume"], 20)
        assert not result.dropna().empty

    def test_uptrend_positive(self) -> None:
        df = _make_ohlcv(days=200, trend=0.01)
        result = on_balance_volume_trend(df["close"], df["volume"], 20)
        # In strong uptrend, OBV trend should generally be positive
        last_10 = result.iloc[-10:].dropna()
        assert last_10.mean() > -0.1  # Not strongly negative


class TestVolPriceDivergence:
    def test_range(self) -> None:
        df = _make_ohlcv()
        result = volume_price_divergence(df["close"], df["volume"], 10)
        valid = result.dropna()
        # tanh-based, should be roughly in [-2, 2]
        assert (valid.abs() < 3).all()


class TestVolumeAcceleration:
    def test_basic(self) -> None:
        df = _make_ohlcv()
        result = volume_acceleration(df["volume"], 5, 20)
        assert not result.dropna().empty


class TestComputeFlowFactors:
    def test_adds_columns(self) -> None:
        df = _make_ohlcv()
        result = compute_flow_factors(df)
        expected_cols = [
            "vol_ratio_20d",
            "amt_ratio_20d",
            "mfi_14",
            "obv_trend_20d",
            "vol_price_div_10d",
            "vol_accel",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_preserves_original(self) -> None:
        df = _make_ohlcv()
        result = compute_flow_factors(df)
        for col in df.columns:
            assert col in result.columns

    def test_insufficient_data(self) -> None:
        df = _make_ohlcv(days=10)
        result = compute_flow_factors(df)
        # Should return original df unchanged (min_rows=60)
        assert len(result.columns) == len(df.columns)

    def test_no_nan_in_last_row(self) -> None:
        df = _make_ohlcv(days=200)
        result = compute_flow_factors(df)
        factor_cols = ["vol_ratio_20d", "mfi_14", "obv_trend_20d", "vol_price_div_10d", "vol_accel"]
        for col in factor_cols:
            assert not np.isnan(result[col].iloc[-1]), f"NaN in {col} last row"
