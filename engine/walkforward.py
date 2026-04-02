"""Walk-forward validation — rolling out-of-sample testing.

Splits data into rolling windows: train on N years, test on M years.
This is the gold standard for verifying a strategy isn't overfitted.

Default: 2-year train / 1-year test, rolling forward by 6 months.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from engine.backtest import run_backtest
from engine.metrics import summary
from engine.types import BacktestConfig
from strategies.multifactor import MultiFactorStrategy
from strategies.rotation import RotationStrategy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WindowResult:
    """Result for a single train/test window."""

    train_start: str
    train_end: str
    test_start: str
    test_end: str
    test_return: float
    test_sharpe: float
    test_max_drawdown: float
    test_trades: int


def walk_forward(
    data: dict[str, pd.DataFrame],
    strategy_type: str = "rotation",
    params: dict | None = None,
    train_years: int = 2,
    test_months: int = 12,
    step_months: int = 6,
    capital: float = 500_000,
) -> dict:
    """Run walk-forward validation on a strategy.

    Args:
        data: Symbol → OHLCV DataFrame.
        strategy_type: "rotation" or "multifactor".
        params: Strategy parameters.
        train_years: Training window in years.
        test_months: Test window in months.
        step_months: How far to slide the window each step.
        capital: Initial capital.

    Returns:
        Dict with per-window results and aggregate stats.
    """
    if params is None:
        params = {}

    # Find common date range
    all_dates: set[pd.Timestamp] = set()
    for df in data.values():
        all_dates.update(df.index)
    all_dates_sorted = sorted(all_dates)

    if len(all_dates_sorted) < 252 * (train_years + 1):
        return {"error": "数据不足", "windows": [], "aggregate": {}}

    start = all_dates_sorted[0]
    end = all_dates_sorted[-1]

    config = BacktestConfig(initial_cash=capital, commission_rate=0.0002, slippage=0.001)

    windows: list[WindowResult] = []

    # Slide the window
    train_start = start
    while True:
        train_end = train_start + pd.DateOffset(years=train_years)
        test_start = train_end
        test_end = test_start + pd.DateOffset(months=test_months)

        if test_end > end:
            break

        # Slice data for test period only
        # (We don't actually re-train — our strategies don't have a fit step.
        #  But we limit the data the strategy sees to simulate real deployment.)
        test_data = {}
        for sym, df in data.items():
            # Give the strategy training data for context + test period for execution
            window = df[(df.index >= train_start) & (df.index <= test_end)]
            if len(window) >= 60:
                test_data[sym] = window

        if len(test_data) < 2:
            train_start += pd.DateOffset(months=step_months)
            continue

        # Build strategy
        if strategy_type == "multifactor":
            strategy = MultiFactorStrategy(
                lookback=params.get("lookback", 20),
                top_k=params.get("top_k", 2),
                rebalance_days=params.get("rebalance_days", 20),
                momentum_weight=params.get("momentum_weight", 0.5),
                value_weight=params.get("value_weight", 0.3),
                volatility_weight=params.get("volatility_weight", 0.2),
            )
        else:
            strategy = RotationStrategy(
                lookback=params.get("lookback", 20),
                top_k=params.get("top_k", 2),
                rebalance_days=params.get("rebalance_days", 20),
            )

        result = run_backtest(test_data, strategy, config)
        m = summary(result)

        # Only count the test period performance
        equity = result.equity_curve
        test_equity = equity[equity.index >= test_start]
        if len(test_equity) >= 2:
            test_return = float(test_equity.iloc[-1] / test_equity.iloc[0] - 1)
        else:
            test_return = 0.0

        windows.append(
            WindowResult(
                train_start=str(train_start.date()),
                train_end=str(train_end.date()),
                test_start=str(test_start.date()),
                test_end=str(test_end.date()),
                test_return=test_return,
                test_sharpe=m["sharpe_ratio"],
                test_max_drawdown=m["max_drawdown"],
                test_trades=m["total_trades"],
            )
        )

        logger.info(
            "WF window %s~%s: test return %.1f%%",
            test_start.date(),
            test_end.date(),
            test_return * 100,
        )

        train_start += pd.DateOffset(months=step_months)

    # Aggregate
    if windows:
        returns = [w.test_return for w in windows]
        profitable_windows = sum(1 for r in returns if r > 0)
        avg_return = sum(returns) / len(returns)
        worst_window = min(returns)
        best_window = max(returns)

        aggregate = {
            "total_windows": len(windows),
            "profitable_windows": profitable_windows,
            "win_rate": round(profitable_windows / len(windows) * 100, 1),
            "avg_test_return": round(avg_return * 100, 2),
            "best_window": round(best_window * 100, 2),
            "worst_window": round(worst_window * 100, 2),
            "verdict": "通过" if profitable_windows > len(windows) * 0.5 else "未通过",
        }
    else:
        aggregate = {"total_windows": 0, "verdict": "数据不足"}

    return {
        "strategy_type": strategy_type,
        "params": params,
        "train_years": train_years,
        "test_months": test_months,
        "windows": [
            {
                "train": f"{w.train_start} ~ {w.train_end}",
                "test": f"{w.test_start} ~ {w.test_end}",
                "return": round(w.test_return * 100, 2),
                "sharpe": round(w.test_sharpe, 2),
                "max_drawdown": round(w.test_max_drawdown * 100, 1),
                "trades": w.test_trades,
            }
            for w in windows
        ],
        "aggregate": aggregate,
    }
