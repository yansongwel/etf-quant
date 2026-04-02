"""Tests for factor IC evaluation utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.factor_ic import calc_ic_series, compute_all_factors


class TestCalcIcSeries:
    def test_perfect_positive_correlation(self) -> None:
        factor = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0] * 7)  # 35 elements > 30
        returns = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05] * 7)
        ic = calc_ic_series(factor, returns)
        assert ic == pytest.approx(1.0, abs=0.01)

    def test_perfect_negative_correlation(self) -> None:
        factor = pd.Series([5.0, 4.0, 3.0, 2.0, 1.0] * 7)
        returns = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05] * 7)
        ic = calc_ic_series(factor, returns)
        assert ic == pytest.approx(-1.0, abs=0.01)

    def test_no_correlation_near_zero(self) -> None:
        np.random.seed(42)
        factor = pd.Series(np.random.randn(200))
        returns = pd.Series(np.random.randn(200))
        ic = calc_ic_series(factor, returns)
        assert abs(ic) < 0.15  # Should be near zero for random data

    def test_nan_handling(self) -> None:
        # Need enough valid pairs after NaN removal (>= 30)
        factor = pd.Series([1.0, np.nan, 3.0, 4.0, 5.0] * 10)
        returns = pd.Series([0.01, 0.02, np.nan, 0.04, 0.05] * 10)
        ic = calc_ic_series(factor, returns)
        assert not np.isnan(ic)  # Should still compute with valid pairs

    def test_insufficient_data_returns_nan(self) -> None:
        factor = pd.Series([1.0, 2.0, 3.0])
        returns = pd.Series([0.01, 0.02, 0.03])
        ic = calc_ic_series(factor, returns)
        assert np.isnan(ic)  # < 30 observations

    def test_all_nan_returns_nan(self) -> None:
        factor = pd.Series([np.nan] * 50)
        returns = pd.Series([np.nan] * 50)
        ic = calc_ic_series(factor, returns)
        assert np.isnan(ic)


class TestComputeAllFactors:
    @pytest.fixture()
    def sample_ohlcv(self) -> pd.DataFrame:
        dates = pd.bdate_range("2023-01-01", periods=200)
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(200) * 0.5)
        return pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.random.randint(100000, 1000000, 200),
            },
            index=dates,
        )

    def test_adds_factor_columns(self, sample_ohlcv: pd.DataFrame) -> None:
        result = compute_all_factors(sample_ohlcv)
        assert len(result.columns) > len(sample_ohlcv.columns)

    def test_includes_momentum_factors(self, sample_ohlcv: pd.DataFrame) -> None:
        result = compute_all_factors(sample_ohlcv)
        assert "ret_5d" in result.columns
        assert "rsi_14" in result.columns
        assert "momentum_20d" in result.columns

    def test_includes_value_factors(self, sample_ohlcv: pd.DataFrame) -> None:
        result = compute_all_factors(sample_ohlcv)
        assert "ma_dev_20d" in result.columns
        assert "vwap_dev_20d" in result.columns

    def test_includes_volatility_factors(self, sample_ohlcv: pd.DataFrame) -> None:
        result = compute_all_factors(sample_ohlcv)
        assert "hvol_20d" in result.columns
        assert "atr_14" in result.columns

    def test_includes_flow_factors(self, sample_ohlcv: pd.DataFrame) -> None:
        result = compute_all_factors(sample_ohlcv)
        assert "vol_ratio_20d" in result.columns
        assert "mfi_14" in result.columns

    def test_preserves_original_data(self, sample_ohlcv: pd.DataFrame) -> None:
        result = compute_all_factors(sample_ohlcv)
        pd.testing.assert_series_equal(result["close"], sample_ohlcv["close"])

    def test_same_row_count(self, sample_ohlcv: pd.DataFrame) -> None:
        result = compute_all_factors(sample_ohlcv)
        assert len(result) == len(sample_ohlcv)
