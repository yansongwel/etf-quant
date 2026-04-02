"""Tests for the strategy recommendation engine."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from engine.recommender import (
    _build_recommendation,
    _load_all_available,
    _score_strategy,
    recommend_strategies,
)


def _make_mock_data() -> dict[str, pd.DataFrame]:
    """Create mock ETF data for recommendations."""
    np.random.seed(42)
    data = {}
    symbols = ["510300", "510500", "511010"]
    trends = [0.001, 0.002, 0.0001]  # stock, stock, bond

    for sym, trend in zip(symbols, trends, strict=True):
        n = 200
        dates = pd.bdate_range("2024-01-01", periods=n)
        close = 3.0 * np.cumprod(1 + np.random.normal(trend, 0.015, n))
        data[sym] = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.random.randint(1_000_000, 10_000_000, n),
            },
            index=dates,
        )
        data[sym].index.name = "date"
    return data


class TestScoreStrategy:
    def test_positive_score_for_good_metrics(self):
        metrics = {
            "annualized_return": 0.1,
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.1,
            "calmar_ratio": 1.0,
        }
        score = _score_strategy(metrics)
        assert score > 0

    def test_negative_score_for_bad_metrics(self):
        metrics = {
            "annualized_return": -0.1,
            "sharpe_ratio": -0.5,
            "max_drawdown": 0.5,
            "calmar_ratio": -0.2,
        }
        score = _score_strategy(metrics)
        assert score < 0


class TestRecommendStrategies:
    @patch("engine.recommender._load_all_available")
    def test_returns_recommendations(self, mock_load):
        mock_load.return_value = _make_mock_data()
        results = recommend_strategies(capital=5000, max_results=3)
        assert len(results) <= 3
        assert len(results) > 0

        # Should be ranked
        for i, r in enumerate(results):
            assert r.rank == i + 1
            assert r.strategy_name
            assert r.recommendation
            assert isinstance(r.metrics, dict)

    @patch("engine.recommender._load_all_available")
    def test_to_dict(self, mock_load):
        mock_load.return_value = _make_mock_data()
        results = recommend_strategies(capital=5000, max_results=1)
        assert len(results) >= 1
        d = results[0].to_dict()
        assert "strategy_name" in d
        assert "metrics" in d
        assert "recommendation" in d

    @patch("engine.recommender._load_all_available")
    def test_empty_data_returns_empty(self, mock_load):
        mock_load.return_value = {}
        results = recommend_strategies(capital=5000)
        assert results == []

    @patch("engine.recommender._load_all_available")
    def test_top_k_exceeds_symbols_skipped(self, mock_load):
        """When top_k > len(symbols), that rotation variant is skipped (line 109)."""
        # Only 1 symbol so top_k=2 and top_k=3 should be skipped
        np.random.seed(42)
        n = 200
        dates = pd.bdate_range("2024-01-01", periods=n)
        close = 3.0 * np.cumprod(1 + np.random.normal(0.001, 0.015, n))
        single = {
            "510300": pd.DataFrame(
                {
                    "open": close * 0.999,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": np.random.randint(1_000_000, 10_000_000, n),
                },
                index=dates,
            )
        }
        single["510300"].index.name = "date"
        mock_load.return_value = single

        results = recommend_strategies(capital=5000, max_results=20)
        # Should still return results (rotation with top_k=2,3 skipped, multifactor runs)
        assert len(results) > 0
        # No balance candidates (no bond ETF 511010), no rotation with top_k>1
        for r in results:
            if r.strategy_id == "rotation":
                assert r.params["top_k"] <= 1


class TestLoadAllAvailable:
    @patch("config.settings.settings")
    @patch("engine.recommender.load_hist")
    def test_no_data_dir(self, mock_load_hist, mock_settings, tmp_path):
        """When data_dir/etf_hist doesn't exist, return empty dict (lines 58-59)."""
        mock_settings.data.data_dir = tmp_path
        # etf_hist subdir does not exist
        result = _load_all_available()
        assert result == {}
        mock_load_hist.assert_not_called()

    @patch("config.settings.settings")
    @patch("engine.recommender.load_hist")
    def test_loads_parquet_files(self, mock_load_hist, mock_settings, tmp_path):
        """Loads parquet files with >= 60 rows, skips short/empty ones (lines 60-66)."""
        data_dir = tmp_path / "etf_hist"
        data_dir.mkdir()
        # Create dummy parquet files
        (data_dir / "510300.parquet").touch()
        (data_dir / "510500.parquet").touch()
        (data_dir / "short.parquet").touch()

        mock_settings.data.data_dir = tmp_path

        n = 100
        dates = pd.bdate_range("2024-01-01", periods=n)
        good_df = pd.DataFrame({"close": range(n)}, index=dates)
        short_df = pd.DataFrame({"close": range(30)})

        def side_effect(stem):
            if stem == "short":
                return short_df
            return good_df

        mock_load_hist.side_effect = side_effect

        result = _load_all_available()
        assert "510300" in result
        assert "510500" in result
        assert "short" not in result  # too few rows

    @patch("config.settings.settings")
    @patch("engine.recommender.load_hist")
    def test_skips_empty_df(self, mock_load_hist, mock_settings, tmp_path):
        """Empty DataFrames are skipped (line 64)."""
        data_dir = tmp_path / "etf_hist"
        data_dir.mkdir()
        (data_dir / "empty.parquet").touch()
        mock_settings.data.data_dir = tmp_path
        mock_load_hist.return_value = pd.DataFrame()

        result = _load_all_available()
        assert result == {}


class TestBuildRecommendation:
    def test_negative_return_warning(self):
        """Negative total_return appends risk warning (line 240)."""
        metrics = {"total_return": -0.05, "max_drawdown": 0.1, "total_trades": 10}
        text = _build_recommendation("rotation", metrics, 50000.0, 3)
        assert "注意风险" in text
        assert "-5.0%" in text

    def test_positive_return_no_warning(self):
        """Positive total_return has no risk warning."""
        metrics = {"total_return": 0.15, "max_drawdown": 0.08, "total_trades": 20}
        text = _build_recommendation("rotation", metrics, 50000.0, 3)
        assert "注意风险" not in text
        assert "+15.0%" in text

    def test_balance_strategy_text(self):
        """Balance strategy shows stock/bond split."""
        metrics = {"total_return": 0.1, "max_drawdown": 0.05, "total_trades": 5}
        text = _build_recommendation("balance", metrics, 100000.0, 2, stock_weight=0.6)
        assert "股票ETF" in text
        assert "债券ETF" in text
        assert "¥60000" in text
        assert "¥40000" in text
