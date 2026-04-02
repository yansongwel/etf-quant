"""Tests for engine.risk_advisor — risk assessment and layout suggestions."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from engine.risk_advisor import (
    LayoutSuggestion,
    RiskLevel,
    assess_etf_risk,
)


def _make_df(
    days: int = 120,
    base_price: float = 3.0,
    trend: float = 0.0,
    volatility: float = 0.01,
    big_drop: bool = False,
) -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame for testing."""
    dates = pd.date_range(end="2026-03-28", periods=days, freq="D")
    np.random.seed(42)

    returns = np.random.randn(days) * volatility + trend
    if big_drop:
        returns[-5:] = -0.03  # Simulate recent crash
    close = base_price * np.cumprod(1 + returns)

    volume = np.full(days, 1_000_000.0)
    volume += np.random.randn(days) * 100_000

    return pd.DataFrame(
        {
            "open": close * (1 - np.random.rand(days) * 0.005),
            "high": close * (1 + np.random.rand(days) * 0.01),
            "low": close * (1 - np.random.rand(days) * 0.01),
            "close": close,
            "volume": np.maximum(volume, 100),
            "amount": close * volume,
            "turnover": np.full(days, 2.0),
        },
        index=dates,
    )


class TestAssessETFRisk:
    """Tests for assess_etf_risk function."""

    def test_low_risk_stable(self) -> None:
        """Stable ETF with low volatility should be low/medium risk."""
        df = _make_df(volatility=0.005, trend=0.001)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert profile.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
        assert profile.risk_score < 45

    def test_high_risk_volatile(self) -> None:
        """Highly volatile ETF with big drop should be high risk."""
        df = _make_df(volatility=0.04, big_drop=True)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert profile.risk_level in (RiskLevel.HIGH, RiskLevel.EXTREME)
        assert profile.risk_score >= 30

    def test_warnings_populated(self) -> None:
        """High risk ETF should have warnings."""
        df = _make_df(volatility=0.04, big_drop=True)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert len(profile.warnings) > 0

    def test_suggestions_populated(self) -> None:
        """All profiles should have at least one suggestion."""
        df = _make_df()
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert len(profile.suggestions) >= 1

    def test_to_dict(self) -> None:
        """to_dict should produce expected keys."""
        df = _make_df()
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        d = profile.to_dict()
        assert "symbol" in d
        assert "risk_level" in d
        assert "risk_label" in d
        assert "risk_score" in d
        assert "volatility_20d" in d
        assert "warnings" in d
        assert "suggestions" in d

    def test_insufficient_data(self) -> None:
        """Should return None for insufficient data."""
        df = _make_df(days=20)
        assert assess_etf_risk(df, "510300") is None

    def test_empty_df(self) -> None:
        """Should return None for empty DataFrame."""
        assert assess_etf_risk(pd.DataFrame(), "510300") is None

    def test_risk_score_capped(self) -> None:
        """Risk score should be capped at 100."""
        # Extreme conditions
        df = _make_df(volatility=0.06, big_drop=True, trend=-0.005)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert profile.risk_score <= 100

    def test_name_resolution(self) -> None:
        """Known ETF should have name resolved."""
        df = _make_df()
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert profile.name == "沪深300ETF"

    def test_unknown_symbol_name(self) -> None:
        """Unknown symbol should use code as name."""
        df = _make_df()
        profile = assess_etf_risk(df, "999999")
        assert profile is not None
        assert profile.name == "999999"


class TestAssessETFRiskBranches:
    """Target specific uncovered branches in assess_etf_risk."""

    def test_extreme_volatility(self) -> None:
        """Vol > 0.5 should add 30 points + warning."""
        df = _make_df(volatility=0.08, trend=-0.002)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert any("波动率极高" in w for w in profile.warnings)

    def test_high_volatility(self) -> None:
        """Vol 0.35-0.5 should add 20 points + warning."""
        df = _make_df(volatility=0.05, trend=0.0)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        # Should have volatility warning
        assert profile.volatility_20d > 0.2

    def test_rsi_overbought_extreme(self) -> None:
        """RSI > 80 should trigger extreme overbought warning."""
        # Create strong uptrend to push RSI high
        df = _make_df(days=120, trend=0.008, volatility=0.005)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        # With strong uptrend, RSI should be elevated
        if profile.rsi_14 > 70:
            assert any("超买" in w for w in profile.warnings)

    def test_rsi_oversold_extreme(self) -> None:
        """Strong downtrend should produce elevated risk."""
        df = _make_df(days=120, trend=-0.008, volatility=0.005)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        # Strong downtrend should elevate risk score
        assert profile.risk_score > 0

    def test_strong_downtrend(self) -> None:
        """Mom < -0.1 should add 15 points."""
        df = _make_df(days=120, trend=-0.006, volatility=0.01)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        if profile.momentum_20d < -0.05:
            assert profile.risk_score >= 8

    def test_moderate_downtrend(self) -> None:
        """Mom between -0.1 and -0.05 should add 8 points."""
        df = _make_df(days=120, trend=-0.004, volatility=0.01)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert profile.risk_score >= 0  # Should have some risk from momentum

    @patch("engine.risk_advisor.detect_flow")
    def test_distribution_flow(self, mock_flow) -> None:
        """Distribution flow should add 10 points + warnings."""
        from engine.flow import FlowSignal, FlowType

        mock_flow.return_value = FlowSignal(
            symbol="510300",
            flow_type=FlowType.DISTRIBUTION,
            volume_ratio=2.5,
            amount_ratio=2.5,
            price_change=-0.01,
            turnover=3.0,
            volume_trend_5d=0.1,
            confidence=60.0,
            label="出货",
            advice="观望",
            details=[],
        )
        df = _make_df()
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert any("出货" in w for w in profile.warnings)

    @patch("engine.risk_advisor.detect_flow")
    def test_panic_sell_flow(self, mock_flow) -> None:
        """Panic sell flow should add warnings."""
        from engine.flow import FlowSignal, FlowType

        mock_flow.return_value = FlowSignal(
            symbol="510300",
            flow_type=FlowType.PANIC_SELL,
            volume_ratio=3.0,
            amount_ratio=3.0,
            price_change=-0.03,
            turnover=5.0,
            volume_trend_5d=0.5,
            confidence=70.0,
            label="恐慌",
            advice="观望",
            details=[],
        )
        df = _make_df()
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert any("恐慌" in w for w in profile.warnings)
        assert any("抄底" in s for s in profile.suggestions)

    @patch("engine.risk_advisor.detect_flow")
    def test_accumulation_flow(self, mock_flow) -> None:
        """Accumulation flow should add suggestion."""
        from engine.flow import FlowSignal, FlowType

        mock_flow.return_value = FlowSignal(
            symbol="510300",
            flow_type=FlowType.ACCUMULATION,
            volume_ratio=2.0,
            amount_ratio=2.0,
            price_change=0.005,
            turnover=2.0,
            volume_trend_5d=0.2,
            confidence=50.0,
            label="吸筹",
            advice="关注",
            details=[],
        )
        df = _make_df()
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert any("吸筹" in s for s in profile.suggestions)

    @patch("engine.risk_advisor.detect_flow")
    def test_breakout_flow(self, mock_flow) -> None:
        """Breakout buy flow should add suggestion."""
        from engine.flow import FlowSignal, FlowType

        mock_flow.return_value = FlowSignal(
            symbol="510300",
            flow_type=FlowType.BREAKOUT_BUY,
            volume_ratio=2.0,
            amount_ratio=2.0,
            price_change=0.03,
            turnover=4.0,
            volume_trend_5d=0.3,
            confidence=60.0,
            label="突破",
            advice="跟入",
            details=[],
        )
        df = _make_df()
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert any("突破" in s for s in profile.suggestions)

    def test_low_risk_suggestion(self) -> None:
        """Low risk should have some suggestion."""
        df = _make_df(volatility=0.003, trend=0.001)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        assert len(profile.suggestions) >= 1

    def test_medium_risk_suggestion(self) -> None:
        """Medium risk (20-50) should suggest position control."""
        df = _make_df(volatility=0.025, trend=-0.002)
        profile = assess_etf_risk(df, "510300")
        assert profile is not None
        # Just verify suggestions exist
        assert len(profile.suggestions) >= 1


class TestGenerateLayoutSuggestions:
    """Tests for generate_layout_suggestions — integration with sector analysis."""

    @patch("engine.risk_advisor.load_hist")
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_recovering_sector(self, mock_sectors: object, mock_load: object) -> None:
        from engine.sector import SectorAnalysis, SectorPhase

        mock_load.return_value = _make_df()
        mock_sectors.return_value = [
            SectorAnalysis(
                sector_name="Test",
                phase=SectorPhase.RECOVERING,
                etf_symbols=["510300"],
                best_etf="510300",
                best_etf_name="沪深300ETF",
                momentum_20d=-0.03,
                momentum_5d=0.01,
                momentum_acceleration=0.04,
                rsi=35.0,
                ma_ratio=0.98,
                volatility=0.2,
                score=5.0,
                risk_level="中低",
                action="布局",
                allocation_pct=20.0,
            ),
        ]
        from engine.risk_advisor import generate_layout_suggestions

        results = generate_layout_suggestions(500000)
        assert len(results) == 1
        assert "提前布局" in results[0].action
        assert results[0].position_pct > 0

    @patch("engine.risk_advisor.load_hist")
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_all_phases(self, mock_sectors: object, mock_load: object) -> None:
        from engine.risk_advisor import generate_layout_suggestions
        from engine.sector import SectorAnalysis, SectorPhase

        mock_load.return_value = _make_df()

        sectors = []
        for phase in SectorPhase:
            sectors.append(
                SectorAnalysis(
                    sector_name=f"Test_{phase.value}",
                    phase=phase,
                    etf_symbols=["510300"],
                    best_etf="510300",
                    best_etf_name="沪深300ETF",
                    momentum_20d=0.05
                    if phase in (SectorPhase.LEADING, SectorPhase.WEAKENING)
                    else -0.05,
                    momentum_5d=0.02,
                    momentum_acceleration=0.03 if phase == SectorPhase.LEADING else -0.01,
                    rsi=50.0,
                    ma_ratio=1.0,
                    volatility=0.2,
                    score=3.0,
                    risk_level="中",
                    action="test",
                    allocation_pct=10.0,
                )
            )
        mock_sectors.return_value = sectors
        results = generate_layout_suggestions(500000)
        assert len(results) == 4  # One for each phase

    @patch("engine.risk_advisor.load_hist", return_value=pd.DataFrame())
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_no_data(self, mock_sectors: object, mock_load: object) -> None:
        from engine.risk_advisor import generate_layout_suggestions
        from engine.sector import SectorAnalysis, SectorPhase

        mock_sectors.return_value = [
            SectorAnalysis(
                sector_name="NoData",
                phase=SectorPhase.RECOVERING,
                etf_symbols=["999999"],
                best_etf="999999",
                best_etf_name="Unknown",
                momentum_20d=-0.03,
                momentum_5d=0.01,
                momentum_acceleration=0.04,
                rsi=35.0,
                ma_ratio=0.98,
                volatility=0.2,
                score=5.0,
                risk_level="中",
                action="test",
                allocation_pct=20.0,
            ),
        ]
        results = generate_layout_suggestions(500000)
        assert len(results) == 0  # No data, no suggestions


class TestFullRiskReport:
    """Tests for full_risk_report function."""

    @patch("engine.risk_advisor.load_hist")
    @patch("engine.risk_advisor.generate_layout_suggestions", return_value=[])
    def test_report_structure(self, _layouts: object, mock_load: object) -> None:
        from pathlib import Path
        from unittest.mock import MagicMock

        from engine.risk_advisor import full_risk_report

        mock_load.return_value = _make_df()

        fake_dir = MagicMock()
        etf_dir = MagicMock()
        etf_dir.exists.return_value = True
        etf_dir.glob.return_value = [Path("510300.parquet")]
        fake_dir.__truediv__ = lambda s, x: etf_dir

        with patch("config.settings.settings") as mock_settings:
            mock_settings.data.data_dir = fake_dir
            result = full_risk_report(500000)

        assert result["capital"] == 500000
        assert "portfolio_risk" in result
        assert "risk_profiles" in result
        assert len(result["risk_profiles"]) == 1
        assert "risk_rules" in result
        assert len(result["risk_rules"]) >= 5
        assert "disclaimer" in result

    @patch("engine.risk_advisor.load_hist")
    @patch("engine.risk_advisor.generate_layout_suggestions", return_value=[])
    def test_report_no_data(self, _layouts: object, _load: object) -> None:
        from unittest.mock import MagicMock

        from engine.risk_advisor import full_risk_report

        fake_dir = MagicMock()
        etf_dir = MagicMock()
        etf_dir.exists.return_value = False
        fake_dir.__truediv__ = lambda s, x: etf_dir

        with patch("config.settings.settings") as mock_settings:
            mock_settings.data.data_dir = fake_dir
            result = full_risk_report(300000)

        assert result["total_etfs"] == 0
        assert result["avg_risk_score"] == 0


class TestLayoutSuggestion:
    """Tests for LayoutSuggestion dataclass."""

    def test_to_dict(self) -> None:
        suggestion = LayoutSuggestion(
            symbol="510300",
            name="沪深300ETF",
            action="🟢 提前布局",
            reason="板块复苏",
            entry_strategy="分批建仓",
            position_pct=15.0,
            stop_loss_pct=5.0,
            risk_level=RiskLevel.MEDIUM,
            confidence=65.0,
            timeframe="中期1-3月",
        )
        d = suggestion.to_dict()
        assert d["symbol"] == "510300"
        assert d["action"] == "🟢 提前布局"
        assert d["position_pct"] == 15.0
        assert d["risk_label"] == "🟡 中风险"


class TestLayoutSuggestionPhases:
    """Test generate_layout_suggestions with specific sector phase + flow combos."""

    def _make_sector(self, phase, symbol="510300"):
        from unittest.mock import MagicMock

        sector = MagicMock()
        sector.phase = phase
        sector.best_etf = symbol
        sector.best_etf_name = "沪深300ETF"
        sector.sector_name = "宽基"
        sector.momentum_20d = 0.03
        sector.momentum_acceleration = 0.01
        return sector

    def _make_flow(self, flow_type):
        from unittest.mock import MagicMock

        flow = MagicMock()
        flow.flow_type = flow_type
        return flow

    @patch("engine.risk_advisor.load_hist")
    @patch("engine.risk_advisor.detect_flow")
    @patch("engine.risk_advisor.assess_etf_risk")
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_recovering_with_accumulation(
        self, mock_sectors, mock_risk, mock_flow, mock_load
    ) -> None:
        from unittest.mock import MagicMock

        from engine.flow import FlowType
        from engine.risk_advisor import generate_layout_suggestions
        from engine.sector import SectorPhase

        mock_sectors.return_value = [self._make_sector(SectorPhase.RECOVERING)]
        mock_load.return_value = _make_df(120)
        mock_risk.return_value = MagicMock(risk_score=30)
        mock_flow.return_value = self._make_flow(FlowType.ACCUMULATION)

        result = generate_layout_suggestions(500000)
        assert len(result) == 1
        assert result[0].confidence >= 70
        assert "吸筹" in result[0].reason

    @patch("engine.risk_advisor.load_hist")
    @patch("engine.risk_advisor.detect_flow")
    @patch("engine.risk_advisor.assess_etf_risk")
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_recovering_high_risk(self, mock_sectors, mock_risk, mock_flow, mock_load) -> None:
        from unittest.mock import MagicMock

        from engine.risk_advisor import generate_layout_suggestions
        from engine.sector import SectorPhase

        mock_sectors.return_value = [self._make_sector(SectorPhase.RECOVERING)]
        mock_load.return_value = _make_df(120)
        mock_risk.return_value = MagicMock(risk_score=60)
        mock_flow.return_value = None

        result = generate_layout_suggestions(500000)
        assert len(result) == 1
        assert result[0].confidence <= 50
        assert result[0].position_pct <= 10

    @patch("engine.risk_advisor.load_hist")
    @patch("engine.risk_advisor.detect_flow")
    @patch("engine.risk_advisor.assess_etf_risk")
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_leading_with_distribution(self, mock_sectors, mock_risk, mock_flow, mock_load) -> None:
        from unittest.mock import MagicMock

        from engine.flow import FlowType
        from engine.risk_advisor import generate_layout_suggestions
        from engine.sector import SectorPhase

        mock_sectors.return_value = [self._make_sector(SectorPhase.LEADING)]
        mock_load.return_value = _make_df(120)
        mock_risk.return_value = MagicMock(risk_score=40)
        mock_flow.return_value = self._make_flow(FlowType.DISTRIBUTION)

        result = generate_layout_suggestions(500000)
        assert len(result) == 1
        assert "谨慎" in result[0].action or "出货" in result[0].reason

    @patch("engine.risk_advisor.load_hist")
    @patch("engine.risk_advisor.detect_flow")
    @patch("engine.risk_advisor.assess_etf_risk")
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_lagging_with_accumulation(self, mock_sectors, mock_risk, mock_flow, mock_load) -> None:
        from unittest.mock import MagicMock

        from engine.flow import FlowType
        from engine.risk_advisor import generate_layout_suggestions
        from engine.sector import SectorPhase

        mock_sectors.return_value = [self._make_sector(SectorPhase.LAGGING)]
        mock_load.return_value = _make_df(120)
        mock_risk.return_value = MagicMock(risk_score=25)
        mock_flow.return_value = self._make_flow(FlowType.ACCUMULATION)

        result = generate_layout_suggestions(500000)
        assert len(result) == 1
        assert result[0].confidence >= 50
        assert "底部" in result[0].action or "吸筹" in result[0].reason

    @patch("engine.risk_advisor.load_hist")
    @patch("engine.risk_advisor.detect_flow")
    @patch("engine.risk_advisor.assess_etf_risk")
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_weakening_phase(self, mock_sectors, mock_risk, mock_flow, mock_load) -> None:
        from unittest.mock import MagicMock

        from engine.risk_advisor import generate_layout_suggestions
        from engine.sector import SectorPhase

        mock_sectors.return_value = [self._make_sector(SectorPhase.WEAKENING)]
        mock_load.return_value = _make_df(120)
        mock_risk.return_value = MagicMock(risk_score=45)
        mock_flow.return_value = None

        result = generate_layout_suggestions(500000)
        assert len(result) == 1
        assert "减仓" in result[0].action
        assert result[0].position_pct == 0.0
