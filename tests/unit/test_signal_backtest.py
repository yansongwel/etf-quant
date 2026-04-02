"""Tests for engine.signal_backtest — signal accuracy validation."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from engine.signal_backtest import backtest_signals


def _mock_df(days: int = 200, trend: float = 0.001) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=days, freq="D")
    close = 3.0 * np.cumprod(1 + np.random.normal(trend, 0.015, days))
    volume = np.full(days, 2_000_000.0) + np.random.randn(days) * 200_000
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.maximum(volume, 100),
        },
        index=dates,
    )


def _mock_load(symbol: str, category: str = "etf_hist") -> pd.DataFrame:
    if symbol == "NODATA":
        return pd.DataFrame()
    trend = 0.003 if symbol == "UP" else -0.003 if symbol == "DOWN" else 0.0
    return _mock_df(trend=trend)


class TestBacktestSignals:
    @patch("engine.signal_backtest.load_hist", side_effect=_mock_load)
    def test_basic_backtest(self, _m: object) -> None:
        result = backtest_signals(["UP", "DOWN"], test_days=20)
        assert "overall_accuracy_1d" in result
        assert "overall_accuracy_nd" in result
        assert "by_direction" in result
        assert "buy_total" in result
        assert "buy_accuracy_1d" in result
        assert "buy_accuracy_nd" in result
        assert "eval_horizon" in result
        assert result["total_signals"] > 0

    @patch("engine.signal_backtest.load_hist", side_effect=_mock_load)
    def test_no_data(self, _m: object) -> None:
        result = backtest_signals(["NODATA"], test_days=20)
        assert result["total_signals"] == 0
        assert result["overall_accuracy_1d"] == 0.0
        assert result["overall_accuracy_nd"] == 0.0

    @patch("engine.signal_backtest.load_hist", side_effect=_mock_load)
    def test_by_direction_keys(self, _m: object) -> None:
        result = backtest_signals(["UP"], test_days=15)
        dirs = result["by_direction"]
        assert "buy" in dirs
        assert "sell" in dirs
        assert "hold" in dirs
        for d in dirs.values():
            assert "total" in d
            assert "accuracy_1d" in d
            assert "accuracy_nd" in d
            assert "avg_return_1d" in d
            assert "avg_return_nd" in d

    @patch("engine.signal_backtest.load_hist", side_effect=_mock_load)
    def test_score_buckets(self, _m: object) -> None:
        result = backtest_signals(["UP"], test_days=30)
        assert "buy_score_buckets" in result
        for bucket in result["buy_score_buckets"]:
            assert "range" in bucket
            assert "count" in bucket
            assert "accuracy_1d" in bucket
            assert "accuracy_nd" in bucket

    @patch("engine.signal_backtest.load_hist", side_effect=_mock_load)
    def test_eval_horizon_default(self, _m: object) -> None:
        result = backtest_signals(["UP"], test_days=15)
        assert result["eval_horizon"] == 5

    @patch("engine.signal_backtest.load_hist", side_effect=_mock_load)
    def test_eval_horizon_custom(self, _m: object) -> None:
        result = backtest_signals(["UP"], test_days=15, eval_horizon=3)
        assert result["eval_horizon"] == 3

    @patch("engine.signal_backtest.score_at_index")
    @patch("engine.signal_backtest.precompute_factors", return_value={})
    @patch("engine.signal_backtest._detect_market_regime", return_value="neutral")
    @patch("engine.signal_backtest.load_hist")
    def test_score_buckets_all_ranges(
        self, mock_load: object, _regime: object, _factors: object, mock_score: object
    ) -> None:
        """Ensure score bucket analysis covers all four ranges."""
        from engine.signals import SignalDirection

        # Need lookback(60) + test_days(8) + eval_horizon(5) = 73
        days = 80
        dates = pd.date_range("2025-01-01", periods=days, freq="D")
        close = np.full(days, 3.0)
        # Make returns positive for buy correctness
        close[-15:] = np.linspace(3.0, 3.15, 15)
        mock_load.return_value = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.full(days, 2_000_000.0),
            },
            index=dates,
        )

        scores = [15.0, 25.0, 35.0, 55.0, 15.0, 25.0, 35.0, 55.0]
        call_count = {"n": 0}

        def _fake_score(*_args: object, **_kwargs: object) -> tuple:
            idx = call_count["n"] % len(scores)
            call_count["n"] += 1
            return (SignalDirection.BUY, scores[idx])

        mock_score.side_effect = _fake_score

        result = backtest_signals(["TEST"], test_days=8, eval_horizon=5)

        buckets = result["buy_score_buckets"]
        bucket_ranges = {b["range"] for b in buckets}
        assert "10-20" in bucket_ranges
        assert "20-30" in bucket_ranges
        assert "30-50" in bucket_ranges
        assert "50-100" in bucket_ranges

        for b in buckets:
            assert b["count"] > 0
            assert isinstance(b["accuracy_1d"], float)
            assert isinstance(b["accuracy_nd"], float)

    @patch("engine.signal_backtest.score_at_index")
    @patch("engine.signal_backtest.precompute_factors", return_value={})
    @patch("engine.signal_backtest._detect_market_regime", return_value="neutral")
    @patch("engine.signal_backtest.load_hist")
    def test_score_buckets_strong_buy_included(
        self, mock_load: object, _regime: object, _factors: object, mock_score: object
    ) -> None:
        """Strong buy signals should also be included in bucket analysis."""
        from engine.signals import SignalDirection

        days = 80
        dates = pd.date_range("2025-01-01", periods=days, freq="D")
        close = np.linspace(3.0, 3.2, days)
        mock_load.return_value = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.full(days, 2_000_000.0),
            },
            index=dates,
        )

        call_count = {"n": 0}

        def _fake_score(*_args: object, **_kwargs: object) -> tuple:
            call_count["n"] += 1
            direction = (
                SignalDirection.STRONG_BUY if call_count["n"] % 2 == 0 else SignalDirection.BUY
            )
            return (direction, 60.0)

        mock_score.side_effect = _fake_score

        result = backtest_signals(["TEST"], test_days=8, eval_horizon=5)

        buckets = result["buy_score_buckets"]
        assert len(buckets) == 1
        assert buckets[0]["range"] == "50-100"
        assert buckets[0]["count"] == 8
