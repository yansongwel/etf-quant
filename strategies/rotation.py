"""Momentum-based ETF rotation strategy.

Logic:
1. Every `rebalance_days` trading days, rank ETFs by N-day momentum.
2. Hold the top `top_k` ETFs with equal weight.
3. Sell holdings that drop out of top-k, buy new entries.
4. All signals respect T+1: generated today, executed tomorrow.

Anti-overfitting: only 3 parameters (lookback, top_k, rebalance_days).
"""

from __future__ import annotations

import logging

import pandas as pd

from engine.types import Position, Side, Signal
from strategies.base import Strategy

logger = logging.getLogger(__name__)


class RotationStrategy(Strategy):
    """Momentum rotation across a universe of ETFs."""

    def __init__(
        self,
        lookback: int = 20,
        top_k: int = 3,
        rebalance_days: int = 20,
    ) -> None:
        self.lookback = lookback
        self.top_k = top_k
        self.rebalance_days = rebalance_days
        self._day_count = 0
        self._last_rebalance: pd.Timestamp | None = None

    def _should_rebalance(self, current_date: pd.Timestamp) -> bool:
        if self._last_rebalance is None:
            return True
        self._day_count += 1
        return self._day_count >= self.rebalance_days

    def _rank_by_momentum(
        self, data: dict[str, pd.DataFrame], current_date: pd.Timestamp
    ) -> list[tuple[str, float]]:
        """Rank symbols by momentum (return over lookback period).

        Returns list of (symbol, momentum) sorted descending.
        """
        scores: list[tuple[str, float]] = []

        for symbol, df in data.items():
            if len(df) < self.lookback + 1:
                continue
            close = df["close"]
            if close.iloc[-1] <= 0 or close.iloc[-self.lookback - 1] <= 0:
                continue
            mom = close.iloc[-1] / close.iloc[-self.lookback - 1] - 1
            scores.append((symbol, mom))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
        positions: dict[str, Position],
        cash: float,
        current_date: pd.Timestamp,
    ) -> list[Signal]:
        if not self._should_rebalance(current_date):
            return []

        rankings = self._rank_by_momentum(data, current_date)
        if not rankings:
            return []

        # Select top K symbols
        target_symbols = {sym for sym, _ in rankings[: self.top_k]}
        current_symbols = set(positions.keys())

        signals: list[Signal] = []

        # Sell positions not in target
        for sym in current_symbols - target_symbols:
            signals.append(Signal(date=current_date, symbol=sym, side=Side.SELL))

        # Buy new positions (equal weight among top_k)
        weight = 1.0 / self.top_k
        for sym in target_symbols - current_symbols:
            signals.append(Signal(date=current_date, symbol=sym, side=Side.BUY, weight=weight))

        if signals:
            self._last_rebalance = current_date
            self._day_count = 0
            top_str = ", ".join(f"{s}({m:+.2%})" for s, m in rankings[: self.top_k])
            logger.info("Rebalance on %s: top %d = [%s]", current_date.date(), self.top_k, top_str)

        return signals
