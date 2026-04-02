"""Tests for walk-forward validation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine.walkforward import walk_forward


def _make_long_data(years: int = 5) -> dict[str, pd.DataFrame]:
    np.random.seed(42)
    days = years * 252
    dates = pd.bdate_range("2020-01-01", periods=days)
    data = {}
    for sym in ["A", "B", "C"]:
        close = 3.0 * np.cumprod(1 + np.random.normal(0.0003, 0.02, days))
        data[sym] = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.random.randint(1_000_000, 10_000_000, days),
            },
            index=dates,
        )
        data[sym].index.name = "date"
    return data


class TestWalkForward:
    def test_produces_windows(self):
        data = _make_long_data(5)
        result = walk_forward(
            data,
            strategy_type="rotation",
            params={"lookback": 20, "top_k": 2, "rebalance_days": 20},
            train_years=2,
            test_months=12,
            step_months=6,
        )
        assert len(result["windows"]) > 0
        assert "aggregate" in result
        assert result["aggregate"]["total_windows"] > 0

    def test_insufficient_data(self):
        np.random.seed(42)
        dates = pd.bdate_range("2024-01-01", periods=50)
        data = {
            "A": pd.DataFrame(
                {
                    "open": [1] * 50,
                    "high": [2] * 50,
                    "low": [0.5] * 50,
                    "close": [1.5] * 50,
                    "volume": [100] * 50,
                },
                index=dates,
            )
        }
        result = walk_forward(data, train_years=2, test_months=12)
        assert result.get("error") == "数据不足"
