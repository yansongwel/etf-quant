"""Tests for smart_money_flow factor."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors.flow import smart_money_flow


class TestSmartMoneyFlow:
    @pytest.fixture()
    def uptrend_data(self) -> tuple[pd.Series, pd.Series]:
        """Steadily rising prices with consistent volume."""
        dates = pd.bdate_range("2023-01-01", periods=50)
        close = pd.Series(100 + np.arange(50) * 0.5, index=dates)
        volume = pd.Series(np.full(50, 1_000_000), index=dates)
        return close, volume

    @pytest.fixture()
    def downtrend_data(self) -> tuple[pd.Series, pd.Series]:
        """Steadily falling prices with consistent volume."""
        dates = pd.bdate_range("2023-01-01", periods=50)
        close = pd.Series(100 - np.arange(50) * 0.5, index=dates)
        volume = pd.Series(np.full(50, 1_000_000), index=dates)
        return close, volume

    def test_uptrend_positive_flow(self, uptrend_data: tuple[pd.Series, pd.Series]) -> None:
        close, volume = uptrend_data
        result = smart_money_flow(close, volume, 20)
        # In pure uptrend, most days are "up" → positive flow
        last_val = result.dropna().iloc[-1]
        assert last_val > 0

    def test_downtrend_negative_flow(self, downtrend_data: tuple[pd.Series, pd.Series]) -> None:
        close, volume = downtrend_data
        result = smart_money_flow(close, volume, 20)
        # In pure downtrend, most days are "down" → negative flow
        last_val = result.dropna().iloc[-1]
        assert last_val < 0

    def test_range_bounded(self) -> None:
        """Output should be in [-1, 1]."""
        dates = pd.bdate_range("2023-01-01", periods=100)
        np.random.seed(42)
        close = pd.Series(100 + np.cumsum(np.random.randn(100)), index=dates)
        volume = pd.Series(np.random.randint(500_000, 2_000_000, 100), index=dates)
        result = smart_money_flow(close, volume, 20)
        valid = result.dropna()
        assert valid.max() <= 1.0
        assert valid.min() >= -1.0

    def test_initial_nan(self) -> None:
        """First window-1 values should be NaN."""
        dates = pd.bdate_range("2023-01-01", periods=50)
        close = pd.Series(np.linspace(100, 110, 50), index=dates)
        volume = pd.Series(np.full(50, 1_000_000), index=dates)
        result = smart_money_flow(close, volume, 20)
        assert result.iloc[:19].isna().all()
        assert result.iloc[20:].notna().all()

    def test_zero_volume_returns_nan(self) -> None:
        """Zero volume should produce NaN (division by zero handled)."""
        dates = pd.bdate_range("2023-01-01", periods=30)
        close = pd.Series(np.linspace(100, 105, 30), index=dates)
        volume = pd.Series(np.zeros(30), index=dates)
        result = smart_money_flow(close, volume, 20)
        # All NaN because total volume is 0
        assert result.dropna().empty or result.iloc[-1] != result.iloc[-1]

    def test_same_length_as_input(self) -> None:
        dates = pd.bdate_range("2023-01-01", periods=50)
        close = pd.Series(np.linspace(100, 110, 50), index=dates)
        volume = pd.Series(np.full(50, 1_000_000), index=dates)
        result = smart_money_flow(close, volume, 20)
        assert len(result) == len(close)
