"""Multi-factor scoring strategy (多因子打分).

Logic:
1. Compute momentum, value, and volatility factors for each ETF.
2. Rank ETFs on each factor, then combine rankings with configurable weights.
3. Hold the top-K scoring ETFs with equal weight.
4. Rebalance periodically.

This is more sophisticated than pure momentum rotation — it considers
value (buy cheap) and volatility (avoid risky) in addition to trend.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.types import Position, Side, Signal
from factors.momentum import momentum, returns
from factors.value import ma_deviation
from factors.volatility import historical_volatility
from strategies.base import Strategy

logger = logging.getLogger(__name__)


class MultiFactorStrategy(Strategy):
    """Multi-factor ETF selection with configurable factor weights."""

    def __init__(
        self,
        lookback: int = 20,
        top_k: int = 3,
        rebalance_days: int = 20,
        momentum_weight: float = 0.5,
        value_weight: float = 0.3,
        volatility_weight: float = 0.2,
        reversal_weight: float = 0.0,
    ) -> None:
        self.lookback = lookback
        self.top_k = top_k
        self.rebalance_days = rebalance_days
        self.momentum_weight = momentum_weight
        self.value_weight = value_weight
        self.volatility_weight = volatility_weight
        self.reversal_weight = reversal_weight
        self._day_count = 0
        self._last_rebalance: pd.Timestamp | None = None

    def _should_rebalance(self, current_date: pd.Timestamp) -> bool:
        if self._last_rebalance is None:
            return True
        self._day_count += 1
        return self._day_count >= self.rebalance_days

    def _score_symbols(self, data: dict[str, pd.DataFrame]) -> list[tuple[str, float]]:
        """Score each symbol using multi-factor ranking."""
        factor_data: dict[str, dict[str, float]] = {}

        for symbol, df in data.items():
            if len(df) < self.lookback + 1 or "close" not in df.columns:
                continue

            close = df["close"]

            # Momentum: higher is better → rank ascending (high rank = good)
            mom = momentum(close, self.lookback)
            mom_val = float(mom.iloc[-1]) if not np.isnan(mom.iloc[-1]) else 0.0

            # Value (MA deviation): more negative = cheaper = better
            # Invert: lower deviation → higher score
            ma_dev = ma_deviation(close, self.lookback)
            val_val = float(-ma_dev.iloc[-1]) if not np.isnan(ma_dev.iloc[-1]) else 0.0

            # Volatility: lower is better → invert
            hvol = historical_volatility(close, min(self.lookback, len(close) - 1))
            vol_val = float(-hvol.iloc[-1]) if not np.isnan(hvol.iloc[-1]) else 0.0

            # Reversal: more negative 5d return = stronger buy (IC=-0.022)
            # Invert: negative return → high score
            ret_5d = returns(close, 5)
            rev_val = float(-ret_5d.iloc[-1]) if not np.isnan(ret_5d.iloc[-1]) else 0.0

            factor_data[symbol] = {
                "momentum": mom_val,
                "value": val_val,
                "volatility": vol_val,
                "reversal": rev_val,
            }

        if not factor_data:
            return []

        symbols = list(factor_data.keys())

        # Rank each factor (percentile)
        def _rank_factor(factor_name: str) -> dict[str, float]:
            values = [(s, factor_data[s][factor_name]) for s in symbols]
            values.sort(key=lambda x: x[1])
            n = len(values)
            return {s: (i + 1) / n for i, (s, _) in enumerate(values)}

        mom_ranks = _rank_factor("momentum")
        val_ranks = _rank_factor("value")
        vol_ranks = _rank_factor("volatility")
        rev_ranks = _rank_factor("reversal") if self.reversal_weight > 0 else {}

        # Composite score
        scores = []
        for s in symbols:
            score = (
                self.momentum_weight * mom_ranks[s]
                + self.value_weight * val_ranks[s]
                + self.volatility_weight * vol_ranks[s]
                + self.reversal_weight * rev_ranks.get(s, 0.5)
            )
            scores.append((s, score))

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

        scores = self._score_symbols(data)
        if not scores:
            return []

        target_symbols = {sym for sym, _ in scores[: self.top_k]}
        current_symbols = set(positions.keys())

        signals: list[Signal] = []

        for sym in current_symbols - target_symbols:
            signals.append(Signal(date=current_date, symbol=sym, side=Side.SELL))

        weight = 1.0 / self.top_k
        for sym in target_symbols - current_symbols:
            signals.append(
                Signal(
                    date=current_date,
                    symbol=sym,
                    side=Side.BUY,
                    weight=weight,
                )
            )

        if signals:
            self._last_rebalance = current_date
            self._day_count = 0
            top_str = ", ".join(f"{s}({sc:.2f})" for s, sc in scores[: self.top_k])
            logger.info(
                "MultiFactor rebalance %s: top %d = [%s]",
                current_date.date(),
                self.top_k,
                top_str,
            )

        return signals
