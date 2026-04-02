"""Tests for market regime detection."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from engine.regime import detect_regime


def _make_trend_data(trend: float, days: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=days)
    close = 3.0 * np.cumprod(1 + np.random.normal(trend, 0.01, days))
    df = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": [1000000] * days,
        },
        index=dates,
    )
    df.index.name = "date"
    return df


class TestDetectRegime:
    @patch("engine.regime.load_hist")
    def test_bull_market(self, mock_load):
        mock_load.return_value = _make_trend_data(0.005)
        result = detect_regime()
        assert result["regime"] == "bull"
        assert "weights" in result

    @patch("engine.regime.load_hist")
    def test_bear_market(self, mock_load):
        mock_load.return_value = _make_trend_data(-0.005)
        result = detect_regime()
        assert result["regime"] == "bear"

    @patch("engine.regime.load_hist")
    def test_range_market(self, mock_load):
        mock_load.return_value = _make_trend_data(0.0)
        result = detect_regime()
        assert result["regime"] == "range"

    @patch("engine.regime.load_hist")
    def test_empty_data(self, mock_load):
        mock_load.return_value = pd.DataFrame()
        result = detect_regime()
        assert result["regime"] == "range"
        assert "数据不足" in result.get("note", "")
