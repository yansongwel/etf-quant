"""Core types for the backtest engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pandas as pd


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Signal:
    """A trading signal produced by a strategy.

    date: The date the signal is generated (T day).
    symbol: ETF code.
    side: Buy or sell.
    weight: Target portfolio weight [0, 1]. Only meaningful for BUY.
    """

    date: pd.Timestamp
    symbol: str
    side: Side
    weight: float = 1.0


@dataclass(frozen=True)
class Trade:
    """An executed trade (after T+1 delay, commission, slippage)."""

    date: pd.Timestamp  # Execution date (T+1)
    symbol: str
    side: Side
    price: float  # Execution price (with slippage)
    shares: int
    commission: float
    signal_date: pd.Timestamp  # Original signal date (T)


@dataclass(frozen=True)
class Position:
    """Current holding of a single symbol."""

    symbol: str
    shares: int
    avg_cost: float  # Average cost basis per share
    entry_date: pd.Timestamp


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Portfolio state at a specific point in time."""

    date: pd.Timestamp
    cash: float
    positions: tuple[Position, ...]
    total_value: float
    daily_return: float = 0.0


@dataclass(frozen=True)
class BacktestConfig:
    """Backtest parameters."""

    initial_cash: float = 1_000_000.0
    commission_rate: float = 0.0002  # 万2
    slippage: float = 0.001  # 1 tick for ETF
    min_commission: float = 5.0  # 最低佣金 5 元


@dataclass(frozen=True)
class BacktestResult:
    """Complete backtest output."""

    config: BacktestConfig
    snapshots: tuple[PortfolioSnapshot, ...]
    trades: tuple[Trade, ...]

    @property
    def equity_curve(self) -> pd.Series:
        dates = [s.date for s in self.snapshots]
        values = [s.total_value for s in self.snapshots]
        return pd.Series(values, index=pd.DatetimeIndex(dates), name="equity")

    @property
    def returns_series(self) -> pd.Series:
        dates = [s.date for s in self.snapshots]
        rets = [s.daily_return for s in self.snapshots]
        return pd.Series(rets, index=pd.DatetimeIndex(dates), name="returns")

    @property
    def drawdown_series(self) -> pd.Series:
        """Rolling drawdown from peak: (peak - current) / peak."""
        equity = self.equity_curve
        peak = equity.cummax()
        dd = (peak - equity) / peak
        dd.name = "drawdown"
        return dd

    @property
    def underwater_series(self) -> pd.Series:
        """Underwater equity: negative drawdown for charting below zero."""
        return -self.drawdown_series
