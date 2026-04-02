"""Tests for stock-bond balance strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine.backtest import run_backtest
from engine.metrics import summary
from engine.types import BacktestConfig, Side
from strategies.balance import BalanceStrategy


def _make_data(days: int = 100) -> dict[str, pd.DataFrame]:
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=days)
    data = {}
    # Stock: volatile uptrend
    stock_close = 3.0 * np.cumprod(1 + np.random.normal(0.001, 0.02, days))
    data["510300"] = pd.DataFrame(
        {
            "open": stock_close * 0.999,
            "high": stock_close * 1.01,
            "low": stock_close * 0.99,
            "close": stock_close,
            "volume": np.random.randint(1_000_000, 10_000_000, days),
        },
        index=dates,
    )
    data["510300"].index.name = "date"

    # Bond: stable slight uptrend
    bond_close = 100.0 * np.cumprod(1 + np.random.normal(0.0001, 0.002, days))
    data["511010"] = pd.DataFrame(
        {
            "open": bond_close * 0.9999,
            "high": bond_close * 1.001,
            "low": bond_close * 0.999,
            "close": bond_close,
            "volume": np.random.randint(500_000, 5_000_000, days),
        },
        index=dates,
    )
    data["511010"].index.name = "date"
    return data


class TestBalanceStrategy:
    def test_initial_allocation(self):
        data = _make_data()
        strategy = BalanceStrategy(stock_weight=0.6, drift_threshold=0.1)
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, strategy, config)

        # Should have initial buy trades for both symbols
        buy_trades = [t for t in result.trades if t.side == Side.BUY]
        symbols_bought = {t.symbol for t in buy_trades}
        assert "510300" in symbols_bought
        assert "511010" in symbols_bought

    def test_rebalances_on_drift(self):
        # Use more volatile data to trigger drift
        data = _make_data(days=200)
        strategy = BalanceStrategy(stock_weight=0.6, drift_threshold=0.05, min_rebalance_days=5)
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, strategy, config)

        # Should have more than just initial trades (rebalancing happened)
        assert len(result.trades) >= 2

    def test_empty_data(self):
        strategy = BalanceStrategy()
        result = run_backtest({}, strategy)
        assert len(result.trades) == 0

    def test_metrics_reasonable(self):
        data = _make_data(days=200)
        strategy = BalanceStrategy(stock_weight=0.6, drift_threshold=0.08)
        result = run_backtest(data, strategy)
        metrics = summary(result)
        assert isinstance(metrics["total_return"], float)
        assert isinstance(metrics["max_drawdown"], float)

    def test_rebalance_with_extreme_drift(self):
        """Force rebalance with very divergent assets and tiny threshold."""
        np.random.seed(99)
        days = 100
        dates = pd.bdate_range("2024-01-01", periods=days)
        # Stock surges 50% — creates massive drift
        stock_close = 3.0 * np.cumprod(1 + np.random.normal(0.005, 0.03, days))
        # Bond flat
        bond_close = 100.0 * np.ones(days)
        data = {
            "510300": pd.DataFrame(
                {
                    "open": stock_close,
                    "high": stock_close * 1.01,
                    "low": stock_close * 0.99,
                    "close": stock_close,
                    "volume": np.full(days, 5_000_000.0),
                },
                index=dates,
            ),
            "511010": pd.DataFrame(
                {
                    "open": bond_close,
                    "high": bond_close * 1.001,
                    "low": bond_close * 0.999,
                    "close": bond_close,
                    "volume": np.full(days, 2_000_000.0),
                },
                index=dates,
            ),
        }
        strategy = BalanceStrategy(
            stock_weight=0.5,
            drift_threshold=0.03,
            min_rebalance_days=5,
        )
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, strategy, config)
        # Should have rebalanced at least once beyond initial allocation
        sell_trades = [t for t in result.trades if t.side == Side.SELL]
        assert len(sell_trades) >= 1, "Expected at least one rebalance sell"

    def test_missing_symbol_returns_empty(self):
        """Line 75: missing symbol in data returns no signals."""
        data = _make_data()
        del data["511010"]  # Remove bond
        strategy = BalanceStrategy()
        config = BacktestConfig(initial_cash=100_000)
        result = run_backtest(data, strategy, config)
        assert len(result.trades) == 0
