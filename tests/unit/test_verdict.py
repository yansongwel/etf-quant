"""Tests for market verdict generation — covers all decision branches."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from engine.alerts import AlertType, PriceAlert
from engine.signals import SignalDirection, TradingSignal
from engine.verdict import generate_verdict

# ── Helpers ────────────────────────────────────────────────────────────


def _make_price_data(days: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=days)
    close = 3.0 * np.cumprod(1 + np.random.normal(0.001, 0.02, days))
    df = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": [1_000_000] * days,
        },
        index=dates,
    )
    df.index.name = "date"
    return df


def _make_signal(
    symbol: str,
    direction: SignalDirection,
    score: float = 50.0,
    price: float = 3.0,
) -> TradingSignal:
    return TradingSignal(
        symbol=symbol,
        direction=direction,
        strength=abs(score),
        current_price=price,
        entry_price=price * 1.002,
        target_price=price * 1.05,
        stop_loss=price * 0.97,
        position_pct=0.1,
        reason="test",
        factors={"momentum": 0.5, "value": 0.3},
        score=score,
    )


def _make_stop_loss_alert() -> PriceAlert:
    return PriceAlert(
        symbol="510300",
        alert_type=AlertType.STOP_LOSS,
        signal_price=3.0,
        trigger_price=2.9,
        current_price=2.85,
        distance_pct=-1.7,
        message="已触发止损!",
    )


# Use a small ETF list for testing
_TEST_ETF_LIST = [
    {"symbol": "A", "name": "ETF_A"},
    {"symbol": "B", "name": "ETF_B"},
    {"symbol": "C", "name": "ETF_C"},
    {"symbol": "D", "name": "ETF_D"},
    {"symbol": "E", "name": "ETF_E"},
]


# ── Test Class ─────────────────────────────────────────────────────────


class TestGenerateVerdict:
    """Cover all 8 verdict branches."""

    def _run_verdict(
        self,
        regime: str,
        regime_label: str,
        signals: list[TradingSignal],
        alerts: list | None = None,
    ) -> dict:
        """Helper: run generate_verdict with controlled mocks."""
        test_data = {etf["symbol"]: _make_price_data() for etf in _TEST_ETF_LIST}

        with (
            patch("engine.verdict.DEFAULT_ETF_LIST", _TEST_ETF_LIST),
            patch("engine.verdict.load_hist") as mock_load,
            patch("engine.verdict.detect_regime") as mock_regime,
            patch("engine.verdict.check_alerts") as mock_alerts,
            patch("engine.verdict.generate_signals_batch") as mock_signals,
        ):
            mock_regime.return_value = {"regime": regime, "label": regime_label}
            mock_load.side_effect = lambda sym: test_data.get(sym, pd.DataFrame())
            mock_alerts.return_value = alerts or []
            mock_signals.return_value = signals
            return generate_verdict()

    def test_stop_loss_alert_verdict(self):
        """Branch 1: stop_loss alerts present → 止损."""
        signals = [_make_signal("A", SignalDirection.HOLD)]
        alerts = [_make_stop_loss_alert()]

        result = self._run_verdict("range", "震荡市", signals, alerts)

        assert result["action"] == "止损"
        assert result["risk_level"] == "极高"
        assert result["color"] == "#ef4444"
        assert "止损" in result["verdict"]

    def test_bear_sell_heavy(self):
        """Branch 2: bear market + >50% sell → 观望."""
        signals = [
            _make_signal("A", SignalDirection.SELL),
            _make_signal("B", SignalDirection.STRONG_SELL),
            _make_signal("C", SignalDirection.SELL),
            _make_signal("D", SignalDirection.HOLD),
            _make_signal("E", SignalDirection.SELL),
        ]

        result = self._run_verdict("bear", "熊市", signals)

        assert result["action"] == "观望"
        assert result["risk_level"] == "高"

    def test_bear_with_buy_opportunities(self):
        """Branch 3: bear market + >20% buy → 轻仓试探."""
        signals = [
            _make_signal("A", SignalDirection.BUY),
            _make_signal("B", SignalDirection.BUY),
            _make_signal("C", SignalDirection.SELL),
            _make_signal("D", SignalDirection.HOLD),
            _make_signal("E", SignalDirection.HOLD),
        ]

        result = self._run_verdict("bear", "熊市", signals)

        assert result["action"] == "轻仓试探"
        assert result["risk_level"] == "中高"

    def test_bull_strong_buy(self):
        """Branch 4: bull market + >30% buy → 加仓."""
        signals = [
            _make_signal("A", SignalDirection.BUY),
            _make_signal("B", SignalDirection.STRONG_BUY),
            _make_signal("C", SignalDirection.HOLD),
            _make_signal("D", SignalDirection.HOLD),
            _make_signal("E", SignalDirection.HOLD),
        ]

        result = self._run_verdict("bull", "牛市", signals)

        assert result["action"] == "加仓"
        assert result["risk_level"] == "中低"
        assert result["color"] == "#22c55e"

    def test_bull_hold(self):
        """Branch 5: bull market + low buy% → 持有."""
        signals = [
            _make_signal("A", SignalDirection.HOLD),
            _make_signal("B", SignalDirection.HOLD),
            _make_signal("C", SignalDirection.HOLD),
            _make_signal("D", SignalDirection.HOLD),
            _make_signal("E", SignalDirection.BUY),
        ]

        result = self._run_verdict("bull", "牛市", signals)

        assert result["action"] == "持有"
        assert result["risk_level"] == "中"

    def test_range_buy_opportunity(self):
        """Branch 6: range market + buy > sell + buy > 15% → 精选买入."""
        signals = [
            _make_signal("A", SignalDirection.BUY),
            _make_signal("B", SignalDirection.BUY),
            _make_signal("C", SignalDirection.HOLD),
            _make_signal("D", SignalDirection.HOLD),
            _make_signal("E", SignalDirection.SELL),
        ]

        result = self._run_verdict("range", "震荡市", signals)

        assert result["action"] == "精选买入"
        assert result["risk_level"] == "中"
        assert result["color"] == "#3b82f6"

    def test_range_sell_heavy(self):
        """Branch 7: sell% > 60% → 减仓."""
        signals = [
            _make_signal("A", SignalDirection.SELL),
            _make_signal("B", SignalDirection.STRONG_SELL),
            _make_signal("C", SignalDirection.SELL),
            _make_signal("D", SignalDirection.SELL),
            _make_signal("E", SignalDirection.HOLD),
        ]

        result = self._run_verdict("range", "震荡市", signals)

        assert result["action"] == "减仓"
        assert result["risk_level"] == "高"

    def test_neutral_verdict(self):
        """Branch 8: no clear direction → 等待."""
        signals = [
            _make_signal("A", SignalDirection.HOLD),
            _make_signal("B", SignalDirection.HOLD),
            _make_signal("C", SignalDirection.HOLD),
            _make_signal("D", SignalDirection.HOLD),
            _make_signal("E", SignalDirection.HOLD),
        ]

        result = self._run_verdict("range", "震荡市", signals)

        assert result["action"] == "等待"
        assert result["risk_level"] == "中"
        assert result["color"] == "#94a3b8"

    def test_top_buy_included(self):
        """When buy signals exist, top_buy should be populated."""
        signals = [
            _make_signal("A", SignalDirection.BUY, score=80, price=3.5),
            _make_signal("B", SignalDirection.HOLD),
            _make_signal("C", SignalDirection.HOLD),
            _make_signal("D", SignalDirection.HOLD),
            _make_signal("E", SignalDirection.HOLD),
        ]

        result = self._run_verdict("bull", "牛市", signals)

        assert result["top_buy"] is not None
        assert result["top_buy"]["symbol"] == "A"
        assert result["top_buy"]["score"] == 80.0

    def test_no_buy_signals_top_buy_none(self):
        """When no buy signals, top_buy should be None."""
        signals = [
            _make_signal("A", SignalDirection.HOLD),
            _make_signal("B", SignalDirection.SELL),
        ]

        result = self._run_verdict("range", "震荡市", signals)

        assert result["top_buy"] is None

    def test_result_structure(self):
        """Verify all expected keys are present."""
        signals = [_make_signal("A", SignalDirection.HOLD)]
        result = self._run_verdict("range", "震荡市", signals)

        expected_keys = {
            "verdict",
            "action",
            "risk_level",
            "color",
            "regime",
            "signal_summary",
            "top_buy",
            "alert_count",
            "generated_at",
        }
        assert expected_keys == set(result.keys())

    def test_signal_summary_format(self):
        """Signal summary should show buy/hold/sell counts."""
        signals = [
            _make_signal("A", SignalDirection.BUY),
            _make_signal("B", SignalDirection.HOLD),
            _make_signal("C", SignalDirection.SELL),
        ]

        result = self._run_verdict("range", "震荡市", signals)

        assert "1买" in result["signal_summary"]
        assert "1持" in result["signal_summary"]
        assert "1卖" in result["signal_summary"]

    def test_empty_data_handled(self):
        """When no ETF data is loadable, should still return a verdict."""
        with (
            patch("engine.verdict.DEFAULT_ETF_LIST", _TEST_ETF_LIST),
            patch("engine.verdict.load_hist", return_value=pd.DataFrame()),
            patch(
                "engine.verdict.detect_regime",
                return_value={"regime": "range", "label": "震荡"},
            ),
            patch("engine.verdict.check_alerts", return_value=[]),
            patch("engine.verdict.generate_signals_batch", return_value=[]),
        ):
            result = generate_verdict()
            assert result["action"] == "等待"
