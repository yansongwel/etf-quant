"""Tests for sector rotation analyzer — covers all phases and portfolio planning."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from engine.sector import (
    PHASE_LABELS,
    PHASE_RISK,
    SectorAnalysis,
    SectorPhase,
    _get_name,
    analyze_all_sectors,
    analyze_sector,
    generate_portfolio_plan,
)

# ── Data Generators ────────────────────────────────────────────────────


def _make_data(
    trend: float = 0.002,
    days: int = 100,
    seed: int = 42,
) -> pd.DataFrame:
    np.random.seed(seed)
    dates = pd.bdate_range("2024-01-01", periods=days)
    close = 3.0 * np.cumprod(1 + np.random.normal(trend, 0.02, days))
    df = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.random.randint(1_000_000, 10_000_000, days),
        },
        index=dates,
    )
    df.index.name = "date"
    return df


def _make_trending_up(days: int = 100) -> pd.DataFrame:
    """Strong uptrend with accelerating momentum."""
    return _make_data(trend=0.008, days=days, seed=10)


def _make_trending_down(days: int = 100) -> pd.DataFrame:
    """Strong downtrend."""
    return _make_data(trend=-0.008, days=days, seed=20)


def _make_decelerating(days: int = 100) -> pd.DataFrame:
    """Strong 20d momentum but slowing 5d (weakening)."""
    np.random.seed(30)
    dates = pd.bdate_range("2024-01-01", periods=days)
    # Strong up first 80 days, then flat/decline last 20
    close1 = 3.0 * np.cumprod(1 + np.random.normal(0.01, 0.01, 80))
    close2 = close1[-1] * np.cumprod(1 + np.random.normal(-0.002, 0.01, 20))
    close = np.concatenate([close1, close2])
    df = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.random.randint(1_000_000, 10_000_000, days),
        },
        index=dates,
    )
    df.index.name = "date"
    return df


def _make_recovering(days: int = 100) -> pd.DataFrame:
    """Weak 20d momentum but improving 5d (recovering)."""
    np.random.seed(40)
    dates = pd.bdate_range("2024-01-01", periods=days)
    # Down first 80 days, then bouncing last 20
    close1 = 3.0 * np.cumprod(1 + np.random.normal(-0.008, 0.01, 80))
    close2 = close1[-1] * np.cumprod(1 + np.random.normal(0.005, 0.01, 20))
    close = np.concatenate([close1, close2])
    df = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.random.randint(1_000_000, 10_000_000, days),
        },
        index=dates,
    )
    df.index.name = "date"
    return df


_TEST_ETF_LIST = [
    {"symbol": "A", "name": "ETF_A"},
    {"symbol": "B", "name": "ETF_B"},
    {"symbol": "C", "name": "ETF_C"},
]

_TEST_SECTORS = {
    "科技": ["A", "B"],
    "消费": ["C"],
}


# ── Tests ──────────────────────────────────────────────────────────────


class TestGetName:
    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    def test_known_symbol(self):
        assert _get_name("A") == "ETF_A"

    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    def test_unknown_symbol(self):
        assert _get_name("UNKNOWN") == "UNKNOWN"


class TestAnalyzeSector:
    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    @patch("engine.sector.historical_volatility")
    @patch("engine.sector.moving_average_ratio")
    @patch("engine.sector.rsi")
    @patch("engine.sector.momentum")
    def test_leading_phase(self, mock_mom, mock_rsi, mock_mar, mock_vol, mock_load):
        """m20 > 0.02 and accel > 0 → LEADING."""
        mock_load.side_effect = lambda sym: _make_data()
        # m20=0.05, m5=0.08 → accel=0.03 > 0
        mock_mom.side_effect = lambda close, period: pd.Series(
            [0.05 if period == 20 else 0.08], index=[close.index[-1]]
        )
        mock_rsi.return_value = pd.Series([50.0], index=[_make_data().index[-1]])
        mock_mar.return_value = pd.Series([1.01], index=[_make_data().index[-1]])
        mock_vol.return_value = pd.Series([0.15], index=[_make_data().index[-1]])

        result = analyze_sector("科技", ["A", "B"])
        assert result is not None
        assert result.phase == SectorPhase.LEADING
        assert "持有" in result.action or "加仓" in result.action

    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    @patch("engine.sector.historical_volatility")
    @patch("engine.sector.moving_average_ratio")
    @patch("engine.sector.rsi")
    @patch("engine.sector.momentum")
    def test_weakening_phase(self, mock_mom, mock_rsi, mock_mar, mock_vol, mock_load):
        """m20 > 0.02 and accel <= 0 → WEAKENING."""
        mock_load.side_effect = lambda sym: _make_data()
        # m20=0.05, m5=0.02 → accel=-0.03 <= 0
        mock_mom.side_effect = lambda close, period: pd.Series(
            [0.05 if period == 20 else 0.02], index=[close.index[-1]]
        )
        mock_rsi.return_value = pd.Series([60.0], index=[_make_data().index[-1]])
        mock_mar.return_value = pd.Series([1.02], index=[_make_data().index[-1]])
        mock_vol.return_value = pd.Series([0.15], index=[_make_data().index[-1]])

        result = analyze_sector("科技", ["A", "B"])
        assert result is not None
        assert result.phase == SectorPhase.WEAKENING
        assert "减仓" in result.action

    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    @patch("engine.sector.historical_volatility")
    @patch("engine.sector.moving_average_ratio")
    @patch("engine.sector.rsi")
    @patch("engine.sector.momentum")
    def test_lagging_phase(self, mock_mom, mock_rsi, mock_mar, mock_vol, mock_load):
        """m20 <= -0.02 and accel < 0 → LAGGING (else branch)."""
        mock_load.side_effect = lambda sym: _make_data()
        # m20=-0.05, m5=-0.08 → accel=-0.03 < 0
        mock_mom.side_effect = lambda close, period: pd.Series(
            [-0.05 if period == 20 else -0.08], index=[close.index[-1]]
        )
        mock_rsi.return_value = pd.Series([35.0], index=[_make_data().index[-1]])
        mock_mar.return_value = pd.Series([0.97], index=[_make_data().index[-1]])
        mock_vol.return_value = pd.Series([0.20], index=[_make_data().index[-1]])

        result = analyze_sector("消费", ["C"])
        assert result is not None
        assert result.phase == SectorPhase.LAGGING
        assert "观望" in result.action

    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    @patch("engine.sector.historical_volatility")
    @patch("engine.sector.moving_average_ratio")
    @patch("engine.sector.rsi")
    @patch("engine.sector.momentum")
    def test_recovering_phase(self, mock_mom, mock_rsi, mock_mar, mock_vol, mock_load):
        """m20 <= -0.02 and accel >= 0 → RECOVERING."""
        mock_load.side_effect = lambda sym: _make_data()
        # m20=-0.05, m5=-0.01 → accel=0.04 >= 0
        mock_mom.side_effect = lambda close, period: pd.Series(
            [-0.05 if period == 20 else -0.01], index=[close.index[-1]]
        )
        mock_rsi.return_value = pd.Series([40.0], index=[_make_data().index[-1]])
        mock_mar.return_value = pd.Series([0.98], index=[_make_data().index[-1]])
        mock_vol.return_value = pd.Series([0.18], index=[_make_data().index[-1]])

        result = analyze_sector("消费", ["C"])
        assert result is not None
        assert result.phase == SectorPhase.RECOVERING
        assert "布局" in result.action

    @patch("engine.sector.load_hist")
    def test_empty_data_returns_none(self, mock_load):
        mock_load.return_value = pd.DataFrame()
        assert analyze_sector("empty", ["X"]) is None

    @patch("engine.sector.load_hist")
    def test_insufficient_data(self, mock_load):
        mock_load.return_value = _make_data(days=30)  # < 60 days
        assert analyze_sector("short", ["X"]) is None

    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    def test_to_dict_structure(self, mock_load):
        mock_load.side_effect = lambda sym: _make_data()
        result = analyze_sector("test", ["A", "B"])

        assert result is not None
        d = result.to_dict()

        expected_keys = {
            "sector_name",
            "phase",
            "phase_label",
            "etf_symbols",
            "best_etf",
            "best_etf_name",
            "momentum_20d",
            "momentum_5d",
            "momentum_acceleration",
            "rsi",
            "ma_ratio",
            "volatility",
            "score",
            "risk_level",
            "action",
            "allocation_pct",
        }
        assert expected_keys == set(d.keys())

    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    def test_nan_data_handled(self, mock_load):
        """If factor calculations return NaN, ETF is skipped."""
        df = _make_data(days=100)
        df.iloc[-5:, df.columns.get_loc("close")] = np.nan
        mock_load.return_value = df
        # Should not crash, may return None if all NaN
        result = analyze_sector("nan_test", ["X"])
        # Either None or valid result
        assert result is None or isinstance(result, SectorAnalysis)


class TestAnalyzeAllSectors:
    @patch("engine.sector.SECTOR_GROUPS", _TEST_SECTORS)
    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    def test_returns_sorted_list(self, mock_load):
        mock_load.side_effect = lambda sym: _make_data(seed=hash(sym) % 100)
        results = analyze_all_sectors()

        assert len(results) <= len(_TEST_SECTORS)
        # Sorted by score descending
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    @patch("engine.sector.SECTOR_GROUPS", _TEST_SECTORS)
    @patch("engine.sector.load_hist")
    def test_empty_data_returns_empty(self, mock_load):
        mock_load.return_value = pd.DataFrame()
        assert analyze_all_sectors() == []


class TestGeneratePortfolioPlan:
    @patch("engine.sector.SECTOR_GROUPS", _TEST_SECTORS)
    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    def test_aggressive_plan(self, mock_load):
        mock_load.side_effect = lambda sym: _make_data(seed=hash(sym) % 100)
        plan = generate_portfolio_plan(500_000, risk_appetite="aggressive")

        assert plan["capital"] == 500_000
        assert plan["risk_appetite"] == "aggressive"
        assert plan["invested"] + plan["remaining"] == pytest.approx(500_000, abs=1000)
        assert len(plan["positions"]) > 0
        assert plan["disclaimer"] != ""

    @patch("engine.sector.SECTOR_GROUPS", _TEST_SECTORS)
    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    def test_conservative_plan(self, mock_load):
        mock_load.side_effect = lambda sym: _make_data(seed=hash(sym) % 100)
        plan = generate_portfolio_plan(300_000, risk_appetite="conservative")

        assert plan["risk_appetite"] == "conservative"
        for pos in plan["positions"]:
            # Conservative: max 20%
            assert pos["pct_of_portfolio"] <= 25  # Allow small rounding

    @patch("engine.sector.SECTOR_GROUPS", _TEST_SECTORS)
    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    def test_moderate_plan(self, mock_load):
        mock_load.side_effect = lambda sym: _make_data(seed=hash(sym) % 100)
        plan = generate_portfolio_plan(400_000, risk_appetite="moderate")

        assert plan["risk_appetite"] == "moderate"

    @patch("engine.sector.SECTOR_GROUPS", _TEST_SECTORS)
    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    def test_risk_warning_aggressive_target(self, mock_load):
        """Small capital → high weekly % target → strong warning."""
        mock_load.side_effect = lambda sym: _make_data(seed=hash(sym) % 100)
        plan = generate_portfolio_plan(100_000)  # 10000/100000 = 10%/week

        assert "极为激进" in plan["risk_warning"] or "激进" in plan["risk_warning"]

    @patch("engine.sector.SECTOR_GROUPS", _TEST_SECTORS)
    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    def test_risk_warning_moderate_target(self, mock_load):
        """Larger capital → lower weekly % → moderate warning."""
        mock_load.side_effect = lambda sym: _make_data(seed=hash(sym) % 100)
        plan = generate_portfolio_plan(800_000)  # 10000/800000 = 1.25%/week

        assert "止损" in plan["risk_warning"]

    @patch("engine.sector.SECTOR_GROUPS", _TEST_SECTORS)
    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    def test_positions_have_lots_of_100(self, mock_load):
        """ETF shares must be in lots of 100."""
        mock_load.side_effect = lambda sym: _make_data(seed=hash(sym) % 100)
        plan = generate_portfolio_plan(500_000)

        for pos in plan["positions"]:
            assert pos["shares"] % 100 == 0
            assert pos["shares"] > 0

    @patch("engine.sector.SECTOR_GROUPS", _TEST_SECTORS)
    @patch("engine.sector.load_hist")
    def test_no_data_returns_empty_plan(self, mock_load):
        mock_load.return_value = pd.DataFrame()
        plan = generate_portfolio_plan(500_000)

        assert plan["positions"] == []
        assert plan["remaining"] == 500_000

    @patch("engine.sector.SECTOR_GROUPS", _TEST_SECTORS)
    @patch("engine.sector.DEFAULT_ETF_LIST", _TEST_ETF_LIST)
    @patch("engine.sector.load_hist")
    def test_sectors_analysis_included(self, mock_load):
        mock_load.side_effect = lambda sym: _make_data(seed=hash(sym) % 100)
        plan = generate_portfolio_plan(500_000)

        assert "sectors_analysis" in plan
        for sa in plan["sectors_analysis"]:
            assert "sector_name" in sa
            assert "phase" in sa


class TestSectorPhaseConstants:
    def test_all_phases_have_labels(self):
        for phase in SectorPhase:
            assert phase in PHASE_LABELS

    def test_all_phases_have_risk(self):
        for phase in SectorPhase:
            assert phase in PHASE_RISK
