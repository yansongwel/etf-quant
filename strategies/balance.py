"""Stock-bond balance strategy (风险平价 / 股债平衡).

Logic:
1. Allocate between a stock ETF and a bond ETF at target ratio (e.g. 60/40).
2. When allocation drifts beyond threshold, rebalance back to target.
3. Defensive strategy — low turnover, reduced drawdown.

Parameters: stock_weight, drift_threshold, min_rebalance_days.
"""

from __future__ import annotations

import logging

import pandas as pd

from engine.types import Position, Side, Signal
from strategies.base import Strategy

logger = logging.getLogger(__name__)


class BalanceStrategy(Strategy):
    """Stock-bond balance with drift-based rebalancing."""

    def __init__(
        self,
        stock_symbol: str = "510300",
        bond_symbol: str = "511010",
        stock_weight: float = 0.6,
        drift_threshold: float = 0.1,
        min_rebalance_days: int = 10,
    ) -> None:
        self.stock_symbol = stock_symbol
        self.bond_symbol = bond_symbol
        self.stock_weight = stock_weight
        self.bond_weight = 1.0 - stock_weight
        self.drift_threshold = drift_threshold
        self.min_rebalance_days = min_rebalance_days
        self._day_count = 0
        self._initialized = False

    def _calc_current_weights(
        self,
        positions: dict[str, Position],
        data: dict[str, pd.DataFrame],
        cash: float,
    ) -> tuple[float, float]:
        """Calculate current portfolio weights for stock and bond."""
        stock_val = 0.0
        bond_val = 0.0

        stock_pos = positions.get(self.stock_symbol)
        bond_pos = positions.get(self.bond_symbol)

        if stock_pos and self.stock_symbol in data:
            stock_val = stock_pos.shares * float(data[self.stock_symbol]["close"].iloc[-1])
        if bond_pos and self.bond_symbol in data:
            bond_val = bond_pos.shares * float(data[self.bond_symbol]["close"].iloc[-1])

        total = stock_val + bond_val + cash
        if total <= 0:
            return 0.0, 0.0

        return stock_val / total, bond_val / total

    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
        positions: dict[str, Position],
        cash: float,
        current_date: pd.Timestamp,
    ) -> list[Signal]:
        if self.stock_symbol not in data or self.bond_symbol not in data:
            return []

        self._day_count += 1

        # First day: initial allocation
        if not self._initialized:
            self._initialized = True
            return [
                Signal(
                    date=current_date,
                    symbol=self.stock_symbol,
                    side=Side.BUY,
                    weight=self.stock_weight,
                ),
                Signal(
                    date=current_date,
                    symbol=self.bond_symbol,
                    side=Side.BUY,
                    weight=self.bond_weight,
                ),
            ]

        # Check if enough time since last rebalance
        if self._day_count < self.min_rebalance_days:
            return []

        # Calculate drift
        cur_stock_w, cur_bond_w = self._calc_current_weights(positions, data, cash)

        stock_drift = abs(cur_stock_w - self.stock_weight)
        bond_drift = abs(cur_bond_w - self.bond_weight)

        if stock_drift < self.drift_threshold and bond_drift < self.drift_threshold:
            return []

        # Rebalance: sell everything, rebuy at target weights
        signals: list[Signal] = []

        if self.stock_symbol in positions:
            signals.append(Signal(date=current_date, symbol=self.stock_symbol, side=Side.SELL))
        if self.bond_symbol in positions:
            signals.append(Signal(date=current_date, symbol=self.bond_symbol, side=Side.SELL))

        signals.append(
            Signal(
                date=current_date,
                symbol=self.stock_symbol,
                side=Side.BUY,
                weight=self.stock_weight,
            )
        )
        signals.append(
            Signal(
                date=current_date,
                symbol=self.bond_symbol,
                side=Side.BUY,
                weight=self.bond_weight,
            )
        )

        self._day_count = 0
        logger.info(
            "Rebalance on %s: stock=%.1f%% (target=%.1f%%), bond=%.1f%% (target=%.1f%%)",
            current_date.date(),
            cur_stock_w * 100,
            self.stock_weight * 100,
            cur_bond_w * 100,
            self.bond_weight * 100,
        )

        return signals
