"""Tests for backtest engine helper functions."""

from __future__ import annotations

import pandas as pd

from engine.backtest import _apply_slippage, _calc_commission, _get_price
from engine.types import Side


class TestGetPrice:
    def test_returns_price_when_exists(self) -> None:
        dates = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
        df = pd.DataFrame({"close": [3.5, 3.6], "open": [3.4, 3.5]}, index=dates)
        data = {"510300": df}
        result = _get_price(data, "510300", pd.Timestamp("2024-01-01"), "close")
        assert result == 3.5

    def test_returns_none_for_missing_symbol(self) -> None:
        data = {}
        result = _get_price(data, "510300", pd.Timestamp("2024-01-01"), "close")
        assert result is None

    def test_returns_none_for_missing_date(self) -> None:
        dates = pd.DatetimeIndex(["2024-01-01"])
        df = pd.DataFrame({"close": [3.5]}, index=dates)
        data = {"510300": df}
        result = _get_price(data, "510300", pd.Timestamp("2024-01-05"), "close")
        assert result is None


class TestApplySlippage:
    def test_buy_slippage_increases_price(self) -> None:
        result = _apply_slippage(100.0, Side.BUY, 0.001)
        assert result == 100.1

    def test_sell_slippage_decreases_price(self) -> None:
        result = _apply_slippage(100.0, Side.SELL, 0.001)
        assert result == 99.9

    def test_zero_slippage(self) -> None:
        assert _apply_slippage(100.0, Side.BUY, 0.0) == 100.0
        assert _apply_slippage(100.0, Side.SELL, 0.0) == 100.0


class TestCalcCommission:
    def test_normal_commission(self) -> None:
        result = _calc_commission(100_000, 0.0002, 5.0)
        assert result == 20.0  # 100000 * 0.0002

    def test_minimum_commission(self) -> None:
        result = _calc_commission(1000, 0.0002, 5.0)
        assert result == 5.0  # min(0.2, 5.0) = 5.0

    def test_negative_amount_uses_abs(self) -> None:
        result = _calc_commission(-50_000, 0.0002, 5.0)
        assert result == 10.0
