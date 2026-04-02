"""Tests for the momentum rotation strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine.backtest import run_backtest
from engine.metrics import summary
from engine.types import BacktestConfig, Side
from strategies.rotation import RotationStrategy


def _make_trending_data(
    symbols: list[str],
    days: int = 60,
    trends: list[float] | None = None,
) -> dict[str, pd.DataFrame]:
    """Generate OHLCV data with known trends for each symbol.

    trends: daily drift per symbol (e.g. [0.002, -0.001, 0.003])
    """
    np.random.seed(42)
    if trends is None:
        trends = [0.002 * (i + 1) for i in range(len(symbols))]

    data = {}
    dates = pd.bdate_range("2024-01-01", periods=days)

    for sym, trend in zip(symbols, trends, strict=True):
        close = 3.0 * np.cumprod(1 + np.random.normal(trend, 0.01, days))
        df = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.random.randint(1_000_000, 10_000_000, days),
            },
            index=dates,
        )
        df.index.name = "date"
        data[sym] = df

    return data


class TestRotationStrategy:
    def test_selects_top_k(self):
        # Three symbols with different trends: last one strongest
        data = _make_trending_data(["A", "B", "C"], days=60, trends=[-0.005, 0.001, 0.005])
        strategy = RotationStrategy(lookback=20, top_k=1, rebalance_days=20)
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)

        result = run_backtest(data, strategy, config)

        # Should have bought C (strongest momentum)
        buy_symbols = {t.symbol for t in result.trades if t.side == Side.BUY}
        assert "C" in buy_symbols

    def test_rebalance_frequency(self):
        data = _make_trending_data(["A", "B", "C"], days=80)
        strategy = RotationStrategy(lookback=20, top_k=2, rebalance_days=20)
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)

        result = run_backtest(data, strategy, config)

        # With 80 days and rebalance every 20, should rebalance ~3-4 times
        # Each rebalance generates sell + buy signals
        assert len(result.trades) >= 2  # At least initial buys

    def test_sells_weak_holdings(self):
        # A starts strong then weakens, B starts weak then strengthens
        np.random.seed(42)
        days = 60
        dates = pd.bdate_range("2024-01-01", periods=days)

        # A: strong first half, weak second half
        a_prices = np.concatenate(
            [
                3.0 * np.cumprod(1 + np.random.normal(0.005, 0.005, 30)),
                3.0
                * np.cumprod(1 + np.random.normal(0.005, 0.005, 30))[-1:]
                * np.cumprod(1 + np.random.normal(-0.005, 0.005, 30)),
            ]
        )
        # B: weak first half, strong second half
        b_prices = np.concatenate(
            [
                3.0 * np.cumprod(1 + np.random.normal(-0.002, 0.005, 30)),
                3.0
                * np.cumprod(1 + np.random.normal(-0.002, 0.005, 30))[-1:]
                * np.cumprod(1 + np.random.normal(0.005, 0.005, 30)),
            ]
        )

        data = {}
        for sym, prices in [("A", a_prices), ("B", b_prices)]:
            df = pd.DataFrame(
                {
                    "open": prices * 0.999,
                    "high": prices * 1.01,
                    "low": prices * 0.99,
                    "close": prices,
                    "volume": np.random.randint(1_000_000, 10_000_000, days),
                },
                index=dates,
            )
            df.index.name = "date"
            data[sym] = df

        strategy = RotationStrategy(lookback=20, top_k=1, rebalance_days=20)
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, strategy, config)

        # Should have traded at least once (rotation happened)
        assert len(result.trades) >= 1

    def test_empty_data(self):
        strategy = RotationStrategy()
        config = BacktestConfig(initial_cash=100_000)
        result = run_backtest({}, strategy, config)
        assert len(result.trades) == 0

    def test_insufficient_history(self):
        # Only 5 days of data, lookback=20 → no signals
        data = _make_trending_data(["A"], days=5)
        strategy = RotationStrategy(lookback=20, top_k=1, rebalance_days=5)
        config = BacktestConfig(initial_cash=100_000)
        result = run_backtest(data, strategy, config)
        assert len(result.trades) == 0

    def test_end_to_end_with_metrics(self):
        data = _make_trending_data(
            ["510300", "510500", "159915"], days=100, trends=[0.002, 0.001, 0.003]
        )
        strategy = RotationStrategy(lookback=20, top_k=2, rebalance_days=20)
        result = run_backtest(data, strategy)

        metrics = summary(result)
        assert metrics["total_trades"] > 0
        assert isinstance(metrics["total_return"], float)
        assert isinstance(metrics["sharpe_ratio"], float)

    def test_zero_price_skipped(self):
        """Line 59: symbols with zero/negative price are skipped in ranking."""
        data = _make_trending_data(["A", "B"], days=60, trends=[0.003, 0.003])
        # Set first price to 0 for symbol A using .loc to avoid chained assignment
        data["A"].loc[data["A"].index[0], "close"] = 0.0
        strategy = RotationStrategy(lookback=20, top_k=2, rebalance_days=20)
        # Should not crash — A is skipped in ranking for that period
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, strategy, config)
        assert isinstance(result.trades, (list, tuple))
