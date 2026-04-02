"""Grid trading strategy (网格交易).

Logic:
1. Divide a price range into N equal grids.
2. Place buy orders at each grid line below current price.
3. Place sell orders at each grid line above current price.
4. When price drops to a grid → buy; when rises to a grid → sell.

Good for range-bound markets. Parameters: grid_count, grid_width_pct.
"""

from __future__ import annotations

import logging

import pandas as pd

from engine.types import Position, Side, Signal
from strategies.base import Strategy

logger = logging.getLogger(__name__)


class GridStrategy(Strategy):
    """Single-symbol grid trading within a price band."""

    def __init__(
        self,
        symbol: str = "510300",
        grid_count: int = 10,
        grid_width_pct: float = 0.02,
        position_per_grid: float = 0.08,
    ) -> None:
        """
        Args:
            symbol: ETF to trade.
            grid_count: Number of grid levels above and below entry price.
            grid_width_pct: Price distance between grids as percentage.
            position_per_grid: Fraction of total portfolio per grid level.
        """
        self.symbol = symbol
        self.grid_count = grid_count
        self.grid_width_pct = grid_width_pct
        self.position_per_grid = position_per_grid
        self._center_price: float | None = None
        self._grids: list[float] = []
        self._last_grid_idx: int | None = None

    def _init_grids(self, price: float) -> None:
        """Initialize grid levels centered on current price."""
        self._center_price = price
        self._grids = []
        for i in range(-self.grid_count, self.grid_count + 1):
            grid_price = price * (1 + i * self.grid_width_pct)
            self._grids.append(grid_price)
        self._grids.sort()

    def _find_grid_index(self, price: float) -> int:
        """Find which grid level the price is at."""
        for i, g in enumerate(self._grids):
            if price <= g:
                return i
        return len(self._grids) - 1

    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
        positions: dict[str, Position],
        cash: float,
        current_date: pd.Timestamp,
    ) -> list[Signal]:
        if self.symbol not in data:
            return []

        df = data[self.symbol]
        if len(df) < 2:
            return []

        current_price = float(df["close"].iloc[-1])

        # Initialize grids on first day
        if self._center_price is None:
            self._init_grids(current_price)
            self._last_grid_idx = self._find_grid_index(current_price)
            # Buy initial position
            return [
                Signal(
                    date=current_date,
                    symbol=self.symbol,
                    side=Side.BUY,
                    weight=0.5,
                )
            ]

        current_grid = self._find_grid_index(current_price)

        if self._last_grid_idx is None or current_grid == self._last_grid_idx:
            return []

        signals: list[Signal] = []

        # Price crossed grid lines
        if current_grid < self._last_grid_idx:
            # Price dropped through grids → buy
            signals.append(
                Signal(
                    date=current_date,
                    symbol=self.symbol,
                    side=Side.BUY,
                    weight=self.position_per_grid,
                )
            )
            logger.info(
                "Grid BUY on %s: price=%.4f, grid %d→%d",
                current_date.date(),
                current_price,
                self._last_grid_idx,
                current_grid,
            )
        elif current_grid > self._last_grid_idx:
            # Price rose through grids → sell (if we have position)
            if self.symbol in positions and positions[self.symbol].shares > 0:
                signals.append(
                    Signal(
                        date=current_date,
                        symbol=self.symbol,
                        side=Side.SELL,
                    )
                )
                # Rebuy smaller position
                remaining_weight = max(0.3, 0.5 - current_grid * self.position_per_grid)
                signals.append(
                    Signal(
                        date=current_date,
                        symbol=self.symbol,
                        side=Side.BUY,
                        weight=remaining_weight,
                    )
                )
                logger.info(
                    "Grid SELL+REBUY on %s: price=%.4f, grid %d→%d",
                    current_date.date(),
                    current_price,
                    self._last_grid_idx,
                    current_grid,
                )

        self._last_grid_idx = current_grid
        return signals
