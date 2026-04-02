"""Performance metrics for backtest results."""

from __future__ import annotations

import numpy as np

from engine.types import BacktestResult

TRADING_DAYS_PER_YEAR = 252


def total_return(result: BacktestResult) -> float:
    """Total cumulative return."""
    curve = result.equity_curve
    if curve.empty:
        return 0.0
    return (curve.iloc[-1] / curve.iloc[0]) - 1


def annualized_return(result: BacktestResult) -> float:
    """Annualized return (CAGR)."""
    curve = result.equity_curve
    if len(curve) < 2:
        return 0.0
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return (curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1


def max_drawdown(result: BacktestResult) -> float:
    """Maximum drawdown as a positive fraction (e.g. 0.2 = 20% drawdown)."""
    curve = result.equity_curve
    if curve.empty:
        return 0.0
    peak = curve.cummax()
    dd = (peak - curve) / peak
    return float(dd.max())


def sharpe_ratio(result: BacktestResult, risk_free_rate: float = 0.03) -> float:
    """Annualized Sharpe ratio.

    risk_free_rate: Annual risk-free rate (default 3% for China).
    """
    rets = result.returns_series
    if len(rets) < 2:
        return 0.0
    daily_rf = (1 + risk_free_rate) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    excess = rets - daily_rf
    if excess.std() == 0:
        return 0.0
    return float(excess.mean() / excess.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def calmar_ratio(result: BacktestResult) -> float:
    """Calmar ratio = annualized return / max drawdown."""
    mdd = max_drawdown(result)
    if mdd == 0:
        return 0.0
    return annualized_return(result) / mdd


def win_rate(result: BacktestResult) -> float:
    """Percentage of profitable trades."""
    if not result.trades:
        return 0.0
    # Group trades by symbol to compute P&L per round-trip
    buy_prices: dict[str, list[float]] = {}
    wins = 0
    total = 0
    for trade in result.trades:
        if trade.side.value == "buy":
            buy_prices.setdefault(trade.symbol, []).append(trade.price)
        elif trade.side.value == "sell" and trade.symbol in buy_prices:
            buys = buy_prices[trade.symbol]
            if buys:
                avg_buy = sum(buys) / len(buys)
                total += 1
                if trade.price > avg_buy:
                    wins += 1
                buy_prices[trade.symbol] = []
    return wins / total if total > 0 else 0.0


def summary(result: BacktestResult) -> dict[str, float]:
    """Generate a summary dict of all key metrics."""
    return {
        "total_return": total_return(result),
        "annualized_return": annualized_return(result),
        "max_drawdown": max_drawdown(result),
        "sharpe_ratio": sharpe_ratio(result),
        "calmar_ratio": calmar_ratio(result),
        "win_rate": win_rate(result),
        "total_trades": len(result.trades),
    }
