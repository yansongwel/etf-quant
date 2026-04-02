"""Tests for BacktestResult properties (drawdown_series, underwater_series)."""

from __future__ import annotations

import pandas as pd

from engine.types import BacktestConfig, BacktestResult, PortfolioSnapshot


class TestBacktestResultProperties:
    def _make_result(self) -> BacktestResult:
        """Create a simple backtest result with known equity curve."""
        dates = pd.bdate_range("2024-01-01", periods=5)
        snapshots = tuple(
            PortfolioSnapshot(
                date=d,
                cash=c,
                positions=(),
                total_value=c,
                daily_return=r,
            )
            for d, c, r in zip(
                dates,
                [100_000, 110_000, 105_000, 115_000, 108_000],
                [0.0, 0.1, -0.0455, 0.0952, -0.0609],
                strict=True,
            )
        )
        return BacktestResult(
            config=BacktestConfig(),
            snapshots=snapshots,
            trades=(),
        )

    def test_equity_curve(self) -> None:
        result = self._make_result()
        eq = result.equity_curve
        assert len(eq) == 5
        assert eq.iloc[0] == 100_000
        assert eq.iloc[1] == 110_000

    def test_drawdown_series(self) -> None:
        result = self._make_result()
        dd = result.drawdown_series
        assert len(dd) == 5
        assert dd.name == "drawdown"
        # At peak (110k), drawdown = 0
        assert dd.iloc[1] == 0.0
        # After drop to 105k from peak 110k: dd = (110-105)/110 ≈ 0.0455
        assert abs(dd.iloc[2] - 5000 / 110000) < 0.001

    def test_underwater_series(self) -> None:
        result = self._make_result()
        uw = result.underwater_series
        dd = result.drawdown_series
        # Underwater = -drawdown
        assert (uw == -dd).all()

    def test_empty_result(self) -> None:
        result = BacktestResult(
            config=BacktestConfig(),
            snapshots=(),
            trades=(),
        )
        eq = result.equity_curve
        assert len(eq) == 0
