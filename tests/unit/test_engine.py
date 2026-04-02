"""Tests for the backtest engine — T+1 enforcement, commission, slippage."""

from __future__ import annotations

import pandas as pd

from engine.backtest import run_backtest
from engine.metrics import (
    annualized_return,
    max_drawdown,
    sharpe_ratio,
    summary,
    total_return,
    win_rate,
)
from engine.types import BacktestConfig, BacktestResult, PortfolioSnapshot, Position, Side, Signal


def _make_data(prices: list[list[float]], symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Create test data dict. Each inner list = [open, high, low, close, volume]."""
    result = {}
    for sym, price_rows in zip(symbols, prices, strict=True):
        dates = pd.bdate_range("2024-01-01", periods=len(price_rows))
        rows = []
        for p in price_rows:
            rows.append(
                {
                    "open": p[0],
                    "high": p[1],
                    "low": p[2],
                    "close": p[3],
                    "volume": p[4],
                }
            )
        df = pd.DataFrame(rows, index=dates)
        df.index.name = "date"
        result[sym] = df
    return result


def _simple_buy_strategy(
    data: dict[str, pd.DataFrame],
    positions: dict[str, Position],
    cash: float,
    current_date: pd.Timestamp,
) -> list[Signal]:
    """Buy 510300 on day 1 only."""
    dates = sorted(data.get("510300", pd.DataFrame()).index)
    if dates and current_date == dates[0] and "510300" not in positions:
        return [Signal(date=current_date, symbol="510300", side=Side.BUY, weight=0.5)]
    return []


def _buy_sell_strategy(
    data: dict[str, pd.DataFrame],
    positions: dict[str, Position],
    cash: float,
    current_date: pd.Timestamp,
) -> list[Signal]:
    """Buy on day 1, sell on day 3."""
    dates = sorted(data.get("510300", pd.DataFrame()).index)
    if not dates:
        return []
    if current_date == dates[0] and "510300" not in positions:
        return [Signal(date=current_date, symbol="510300", side=Side.BUY, weight=0.5)]
    if len(dates) >= 3 and current_date == dates[2] and "510300" in positions:
        return [Signal(date=current_date, symbol="510300", side=Side.SELL)]
    return []


# ── Sample data: 5 trading days ──
SAMPLE_PRICES = [
    [3.80, 3.85, 3.75, 3.82, 10_000_000],
    [3.82, 3.90, 3.80, 3.88, 12_000_000],
    [3.88, 3.92, 3.85, 3.90, 11_000_000],
    [3.90, 3.95, 3.87, 3.93, 9_000_000],
    [3.93, 3.98, 3.91, 3.96, 10_500_000],
]


class TestT1Enforcement:
    """Verify that signals on T are executed on T+1."""

    def test_buy_executes_on_t_plus_1(self):
        data = _make_data([SAMPLE_PRICES], ["510300"])
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, _simple_buy_strategy, config)

        assert len(result.trades) == 1
        trade = result.trades[0]
        dates = sorted(data["510300"].index)

        # Signal on day 0, execution on day 1
        assert trade.signal_date == dates[0]
        assert trade.date == dates[1]
        assert trade.side == Side.BUY

    def test_sell_executes_on_t_plus_1(self):
        data = _make_data([SAMPLE_PRICES], ["510300"])
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, _buy_sell_strategy, config)

        # Should have buy on day 1, sell on day 3
        assert len(result.trades) == 2
        buy_trade = result.trades[0]
        sell_trade = result.trades[1]
        dates = sorted(data["510300"].index)

        assert buy_trade.date == dates[1]  # T+1 of signal on day 0
        assert sell_trade.date == dates[3]  # T+1 of signal on day 2


class TestCommissionSlippage:
    def test_commission_applied(self):
        data = _make_data([SAMPLE_PRICES], ["510300"])
        config = BacktestConfig(
            initial_cash=100_000, commission_rate=0.0002, slippage=0, min_commission=5.0
        )
        result = run_backtest(data, _simple_buy_strategy, config)
        trade = result.trades[0]
        assert trade.commission >= 5.0  # At least min_commission

    def test_slippage_makes_buy_more_expensive(self):
        data = _make_data([SAMPLE_PRICES], ["510300"])
        dates = sorted(data["510300"].index)
        open_price_day1 = data["510300"].loc[dates[1], "open"]

        config = BacktestConfig(initial_cash=100_000, slippage=0.001, commission_rate=0)
        result = run_backtest(data, _simple_buy_strategy, config)
        trade = result.trades[0]

        assert trade.price > open_price_day1  # Slippage makes buy more expensive


class TestPortfolioTracking:
    def test_initial_cash(self):
        data = _make_data([SAMPLE_PRICES], ["510300"])
        config = BacktestConfig(initial_cash=100_000)

        def no_op(data, pos, cash, date):
            return []

        result = run_backtest(data, no_op, config)
        assert result.snapshots[0].total_value == 100_000
        assert result.snapshots[0].cash == 100_000

    def test_equity_curve_length(self):
        data = _make_data([SAMPLE_PRICES], ["510300"])
        config = BacktestConfig(initial_cash=100_000)

        def no_op(data, pos, cash, date):
            return []

        result = run_backtest(data, no_op, config)
        assert len(result.equity_curve) == 5

    def test_no_data_returns_empty(self):
        result = run_backtest({}, _simple_buy_strategy)
        assert len(result.snapshots) == 0
        assert len(result.trades) == 0


class TestMetrics:
    def test_total_return_no_trades(self):
        data = _make_data([SAMPLE_PRICES], ["510300"])
        config = BacktestConfig(initial_cash=100_000)

        def no_op(data, pos, cash, date):
            return []

        result = run_backtest(data, no_op, config)
        assert total_return(result) == 0.0

    def test_max_drawdown_no_loss(self):
        data = _make_data([SAMPLE_PRICES], ["510300"])
        config = BacktestConfig(initial_cash=100_000)

        def no_op(data, pos, cash, date):
            return []

        result = run_backtest(data, no_op, config)
        assert max_drawdown(result) == 0.0

    def test_summary_keys(self):
        data = _make_data([SAMPLE_PRICES], ["510300"])
        result = run_backtest(data, _simple_buy_strategy)
        s = summary(result)
        expected_keys = [
            "total_return",
            "annualized_return",
            "max_drawdown",
            "sharpe_ratio",
            "calmar_ratio",
            "win_rate",
            "total_trades",
        ]
        for key in expected_keys:
            assert key in s

    def test_win_rate_with_profitable_trade(self):
        # Prices go up after buy → profitable sell
        data = _make_data([SAMPLE_PRICES], ["510300"])
        config = BacktestConfig(initial_cash=100_000, slippage=0, commission_rate=0)
        result = run_backtest(data, _buy_sell_strategy, config)
        assert win_rate(result) == 1.0  # Buy low, sell higher


class TestMetricsEdgeCases:
    """Edge-case tests for metric functions with empty/minimal data."""

    def _empty_result(self) -> BacktestResult:
        """BacktestResult with no snapshots and no trades."""
        return BacktestResult(
            config=BacktestConfig(),
            snapshots=(),
            trades=(),
        )

    def _single_snapshot_result(self) -> BacktestResult:
        """BacktestResult with exactly one snapshot (len < 2)."""
        snap = PortfolioSnapshot(
            date=pd.Timestamp("2024-01-01"),
            cash=100_000,
            positions=(),
            total_value=100_000,
            daily_return=0.0,
        )
        return BacktestResult(
            config=BacktestConfig(),
            snapshots=(snap,),
            trades=(),
        )

    def _constant_equity_result(self) -> BacktestResult:
        """BacktestResult where equity never changes (zero std returns)."""
        dates = pd.bdate_range("2024-01-01", periods=5)
        snaps = tuple(
            PortfolioSnapshot(
                date=d, cash=100_000, positions=(), total_value=100_000, daily_return=0.0
            )
            for d in dates
        )
        return BacktestResult(config=BacktestConfig(), snapshots=snaps, trades=())

    def _same_day_result(self) -> BacktestResult:
        """BacktestResult with two snapshots on the same date (years <= 0)."""
        d = pd.Timestamp("2024-01-01")
        snaps = tuple(
            PortfolioSnapshot(
                date=d, cash=100_000, positions=(), total_value=100_000, daily_return=0.0
            )
            for _ in range(2)
        )
        return BacktestResult(config=BacktestConfig(), snapshots=snaps, trades=())

    # Line 16: total_return — empty equity curve
    def test_total_return_empty(self):
        assert total_return(self._empty_result()) == 0.0

    # Line 24: annualized_return — fewer than 2 data points
    def test_annualized_return_single_point(self):
        assert annualized_return(self._single_snapshot_result()) == 0.0

    # Line 27: annualized_return — years <= 0 (same-day snapshots)
    def test_annualized_return_zero_years(self):
        assert annualized_return(self._same_day_result()) == 0.0

    # Line 35: max_drawdown — empty equity curve
    def test_max_drawdown_empty(self):
        assert max_drawdown(self._empty_result()) == 0.0

    # Line 48: sharpe_ratio — fewer than 2 returns
    def test_sharpe_ratio_insufficient_data(self):
        assert sharpe_ratio(self._single_snapshot_result()) == 0.0

    # Line 52: sharpe_ratio — zero standard deviation (constant returns)
    def test_sharpe_ratio_zero_std(self):
        assert sharpe_ratio(self._constant_equity_result()) == 0.0

    # Line 67: win_rate — no trades
    def test_win_rate_no_trades(self):
        assert win_rate(self._empty_result()) == 0.0
