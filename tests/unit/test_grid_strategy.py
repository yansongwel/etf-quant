"""Tests for grid trading strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine.backtest import run_backtest
from engine.metrics import summary
from engine.types import BacktestConfig, Side
from strategies.grid import GridStrategy


def _make_range_bound_data(days: int = 100) -> dict[str, pd.DataFrame]:
    """Create price data that oscillates in a range (good for grid)."""
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=days)
    # Oscillating price: sine wave + noise
    t = np.linspace(0, 4 * np.pi, days)
    close = 3.5 + 0.3 * np.sin(t) + np.random.normal(0, 0.05, days)
    close = np.maximum(close, 2.5)  # Floor

    data = {
        "510300": pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.005,
                "low": close * 0.995,
                "close": close,
                "volume": np.random.randint(1_000_000, 10_000_000, days),
            },
            index=dates,
        )
    }
    data["510300"].index.name = "date"
    return data


class TestGridStrategy:
    def test_initial_buy(self):
        data = _make_range_bound_data()
        strategy = GridStrategy(symbol="510300", grid_count=5, grid_width_pct=0.02)
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, strategy, config)

        # Should have at least the initial buy
        assert len(result.trades) >= 1
        assert result.trades[0].side == Side.BUY

    def test_trades_generated_in_range(self):
        data = _make_range_bound_data(days=200)
        strategy = GridStrategy(symbol="510300", grid_count=5, grid_width_pct=0.015)
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, strategy, config)

        # Oscillating market should generate grid trades
        assert len(result.trades) >= 2

    def test_empty_data(self):
        strategy = GridStrategy()
        result = run_backtest({}, strategy)
        assert len(result.trades) == 0

    def test_metrics_exist(self):
        data = _make_range_bound_data()
        strategy = GridStrategy(symbol="510300")
        result = run_backtest(data, strategy)
        metrics = summary(result)
        assert "total_return" in metrics
        assert "total_trades" in metrics

    def test_symbol_not_in_data(self):
        """Line 73: grid symbol missing from data dict returns no signals."""
        data = _make_range_bound_data()
        strategy = GridStrategy(symbol="999999")  # Not in data
        result = run_backtest(data, strategy)
        assert len(result.trades) == 0
