"""Tests for volatility regime factor."""

from __future__ import annotations

import numpy as np
import pandas as pd

from factors.volatility import volatility_regime


class TestVolatilityRegime:
    def _make_close(self, n: int = 100, vol: float = 0.01) -> pd.Series:
        np.random.seed(42)
        dates = pd.bdate_range("2023-01-01", periods=n)
        return pd.Series(100 + np.cumsum(np.random.randn(n) * vol), index=dates)

    def test_stable_market_near_one(self) -> None:
        """Constant volatility → regime ratio ≈ 1.0."""
        close = self._make_close(200, vol=0.01)
        result = volatility_regime(close, 20, 60)
        valid = result.dropna()
        # Should be near 1.0 in stable market
        assert 0.5 < valid.iloc[-1] < 2.0

    def test_high_vol_spike(self) -> None:
        """After a vol spike, short vol > long vol → ratio > 1."""
        close = self._make_close(200, vol=0.005)
        # Add spike at end
        spike = close.copy()
        spike.iloc[-10:] += np.random.randn(10) * 3
        result = volatility_regime(spike, 20, 60)
        valid = result.dropna()
        assert valid.iloc[-1] > 1.0

    def test_initial_nan(self) -> None:
        """First ~60 values should be NaN (long window)."""
        close = self._make_close(100)
        result = volatility_regime(close, 20, 60)
        assert result.iloc[:60].isna().all()

    def test_same_length_as_input(self) -> None:
        close = self._make_close(100)
        result = volatility_regime(close, 20, 60)
        assert len(result) == len(close)

    def test_positive_values(self) -> None:
        """Ratio of positive quantities should be positive."""
        close = self._make_close(200)
        result = volatility_regime(close, 20, 60)
        valid = result.dropna()
        assert (valid > 0).all()
