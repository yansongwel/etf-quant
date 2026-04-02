"""Base strategy interface and common utilities."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from engine.types import Position, Signal


class Strategy(ABC):
    """Abstract base class for all trading strategies.

    Subclasses implement `generate_signals()` which is called on each trading day
    with data up to (and including) that day. No look-ahead allowed.
    """

    @abstractmethod
    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
        positions: dict[str, Position],
        cash: float,
        current_date: pd.Timestamp,
    ) -> list[Signal]:
        """Produce trading signals for the current date.

        Args:
            data: Dict of symbol → OHLCV DataFrame, sliced up to current_date.
            positions: Current holdings.
            cash: Available cash.
            current_date: Today's date.

        Returns:
            List of Signal objects. These will be executed on T+1.
        """
        ...

    def __call__(
        self,
        data: dict[str, pd.DataFrame],
        positions: dict[str, Position],
        cash: float,
        current_date: pd.Timestamp,
    ) -> list[Signal]:
        return self.generate_signals(data, positions, cash, current_date)
