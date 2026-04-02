"""Tests for multi-factor scoring strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine.backtest import run_backtest
from engine.metrics import summary
from engine.types import BacktestConfig, Side
from strategies.multifactor import MultiFactorStrategy


def _make_multi_data(
    symbols: list[str], days: int = 80, trends: list[float] | None = None
) -> dict[str, pd.DataFrame]:
    np.random.seed(42)
    if trends is None:
        trends = [0.002 * (i + 1) for i in range(len(symbols))]

    dates = pd.bdate_range("2024-01-01", periods=days)
    data = {}

    for sym, trend in zip(symbols, trends, strict=True):
        close = 3.0 * np.cumprod(1 + np.random.normal(trend, 0.02, days))
        data[sym] = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.random.randint(1_000_000, 10_000_000, days),
            },
            index=dates,
        )
        data[sym].index.name = "date"

    return data


class TestMultiFactorStrategy:
    def test_selects_top_k(self):
        data = _make_multi_data(["A", "B", "C"], days=80, trends=[-0.005, 0.001, 0.005])
        # Use pure momentum weight so C (strongest trend) must be selected
        strategy = MultiFactorStrategy(
            lookback=20,
            top_k=1,
            rebalance_days=20,
            momentum_weight=1.0,
            value_weight=0.0,
            volatility_weight=0.0,
        )
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, strategy, config)

        buy_symbols = {t.symbol for t in result.trades if t.side == Side.BUY}
        # C has best momentum, should be selected with pure momentum weight
        assert "C" in buy_symbols

    def test_factor_weights_matter(self):
        # With 100% momentum weight, should behave like rotation
        data = _make_multi_data(["A", "B", "C"], days=80)
        strategy_mom = MultiFactorStrategy(
            lookback=20,
            top_k=2,
            momentum_weight=1.0,
            value_weight=0.0,
            volatility_weight=0.0,
        )
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, strategy_mom, config)
        assert len(result.trades) >= 1

    def test_insufficient_data(self):
        data = _make_multi_data(["A"], days=5)
        strategy = MultiFactorStrategy(lookback=20, top_k=1)
        result = run_backtest(data, strategy)
        assert len(result.trades) == 0

    def test_empty_data(self):
        strategy = MultiFactorStrategy()
        result = run_backtest({}, strategy)
        assert len(result.trades) == 0

    def test_end_to_end_metrics(self):
        data = _make_multi_data(["510300", "510500", "159915", "512010"], days=120)
        strategy = MultiFactorStrategy(lookback=20, top_k=2, rebalance_days=20)
        result = run_backtest(data, strategy)
        metrics = summary(result)
        assert metrics["total_trades"] > 0
        assert isinstance(metrics["sharpe_ratio"], float)
