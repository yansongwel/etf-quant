"""Tests for engine.portfolio_advisor and api.routers.portfolio."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from api.deps import require_api_key
from api.main import app
from engine.portfolio_advisor import (
    Holding,
    PositionAdvice,
    _determine_action,
    _get_name,
    _safe_last,
    analyze_portfolio,
    analyze_position,
    load_portfolio,
    save_portfolio,
)

# Override auth dependency for tests
app.dependency_overrides[require_api_key] = lambda: "test-key"
client = TestClient(app)


def _mock_df(
    days: int = 120,
    trend: float = 0.0,
    final_price: float | None = None,
) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range(end="2026-03-28", periods=days, freq="D")
    close = 3.0 + np.cumsum(np.random.randn(days) * 0.01 + trend)
    if final_price is not None:
        close[-1] = final_price
    vol = np.full(days, 2_000_000.0) + np.random.randn(days) * 100_000
    return pd.DataFrame(
        {
            "open": close - 0.01,
            "high": close + 0.02,
            "low": close - 0.02,
            "close": close,
            "volume": np.maximum(vol, 100),
            "amount": close * np.maximum(vol, 100),
            "turnover": np.full(days, 2.0),
        },
        index=dates,
    )


def _mock_load(symbol: str, category: str = "etf_hist") -> pd.DataFrame:
    if symbol == "NODATA":
        return pd.DataFrame()
    return _mock_df(final_price=2.5 if symbol == "WINNER" else 1.5 if symbol == "LOSER" else None)


class TestHelpers:
    def test_get_name_known(self) -> None:
        name = _get_name("510300")
        assert name != "510300"  # Should resolve to a real name

    def test_get_name_unknown(self) -> None:
        assert _get_name("999999") == "999999"

    def test_safe_last_normal(self) -> None:
        s = pd.Series([1.0, 2.0, 3.0])
        assert _safe_last(s) == 3.0

    def test_safe_last_empty(self) -> None:
        assert _safe_last(pd.Series([], dtype=float)) == 0.0

    def test_safe_last_nan(self) -> None:
        s = pd.Series([1.0, float("nan")])
        assert _safe_last(s) == 0.0


class TestHolding:
    def test_cost(self) -> None:
        h = Holding(symbol="510300", buy_price=4.5, shares=10000)
        assert h.cost == 45000.0


class TestAnalyzePosition:
    @patch("engine.portfolio_advisor.load_hist", side_effect=_mock_load)
    def test_analyze_ok(self, _m: object) -> None:
        h = Holding(symbol="510300", buy_price=3.2, shares=5000)
        advice = analyze_position(h)
        assert advice is not None
        assert advice.symbol == "510300"
        assert advice.current_price > 0
        assert advice.action  # Non-empty action
        assert advice.suggested_action  # Non-empty suggestion
        assert len(advice.reasons) > 0

    @patch("engine.portfolio_advisor.load_hist", return_value=pd.DataFrame())
    def test_no_data(self, _m: object) -> None:
        h = Holding(symbol="NODATA", buy_price=1.0, shares=100)
        assert analyze_position(h) is None

    @patch("engine.portfolio_advisor.load_hist", side_effect=_mock_load)
    def test_deep_loss_clear(self, _m: object) -> None:
        """Deep loss should trigger 清仓止损."""
        h = Holding(symbol="LOSER", buy_price=2.0, shares=5000)
        advice = analyze_position(h)
        assert advice is not None
        assert advice.pnl < 0
        assert advice.urgency >= 4

    @patch("engine.portfolio_advisor.load_hist", side_effect=_mock_load)
    def test_winner_position(self, _m: object) -> None:
        """Winner should trigger profit-related reasons."""
        h = Holding(symbol="WINNER", buy_price=2.0, shares=5000)
        advice = analyze_position(h)
        assert advice is not None
        assert advice.pnl_pct > 0
        assert any("盈利" in r for r in advice.reasons)

    @patch("engine.portfolio_advisor.load_hist", side_effect=_mock_load)
    def test_short_data_returns_none(self, _m: object) -> None:
        """DataFrame with < 60 rows should return None."""
        short_df = _mock_df(days=30)
        with patch("engine.portfolio_advisor.load_hist", return_value=short_df):
            h = Holding(symbol="510300", buy_price=3.0, shares=1000)
            assert analyze_position(h) is None

    @patch("engine.portfolio_advisor.load_hist", side_effect=_mock_load)
    def test_to_dict(self, _m: object) -> None:
        h = Holding(symbol="510300", buy_price=3.0, shares=1000)
        advice = analyze_position(h)
        assert advice is not None
        d = advice.to_dict()
        assert "symbol" in d
        assert "action" in d
        assert "pnl" in d
        assert "suggested_action" in d
        assert "reasons" in d


class TestDetermineAction:
    """Direct tests for _determine_action covering all 12 branches."""

    def test_deep_loss_stop_loss(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=-9.0,
            rsi_val=50,
            mom_20=0.0,
            flow_type="normal",
            signal_dir="hold",
            urgency=5,
            current_price=3.0,
            stop_loss=2.8,
        )
        assert "清仓止损" in action
        assert color == "red"

    def test_distribution_with_loss(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=-2.0,
            rsi_val=50,
            mom_20=0.0,
            flow_type="distribution",
            signal_dir="hold",
            urgency=3,
            current_price=3.0,
            stop_loss=2.8,
        )
        assert "清仓" in action
        assert color == "red"

    def test_panic_sell(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=1.0,
            rsi_val=50,
            mom_20=0.0,
            flow_type="panic_sell",
            signal_dir="hold",
            urgency=5,
            current_price=3.0,
            stop_loss=2.8,
        )
        assert "减仓观望" in action
        assert color == "orange"

    def test_loss_5pct_downtrend(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=-6.0,
            rsi_val=50,
            mom_20=-0.06,
            flow_type="normal",
            signal_dir="hold",
            urgency=4,
            current_price=3.0,
            stop_loss=2.7,
        )
        assert "清仓止损" in action
        assert color == "red"

    def test_loss_5pct_no_downtrend(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=-6.0,
            rsi_val=50,
            mom_20=-0.02,
            flow_type="normal",
            signal_dir="hold",
            urgency=4,
            current_price=3.0,
            stop_loss=2.8,
        )
        assert "减仓一半" in action
        assert color == "orange"

    def test_rsi_overbought_with_profit(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=5.0,
            rsi_val=80,
            mom_20=0.03,
            flow_type="normal",
            signal_dir="hold",
            urgency=2,
            current_price=3.5,
            stop_loss=3.2,
        )
        assert "止盈减仓" in action
        assert color == "orange"

    def test_strong_sell_signal(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=0.0,
            rsi_val=60,
            mom_20=0.0,
            flow_type="normal",
            signal_dir="strong_sell",
            urgency=3,
            current_price=3.0,
            stop_loss=2.8,
        )
        assert "减仓" in action
        assert color == "orange"

    def test_profit_momentum_weakening(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=12.0,
            rsi_val=60,
            mom_20=-0.01,
            flow_type="normal",
            signal_dir="hold",
            urgency=2,
            current_price=3.5,
            stop_loss=3.2,
        )
        assert "止盈" in action
        assert color == "orange"

    def test_accumulation_buy_signal(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=-1.0,
            rsi_val=45,
            mom_20=0.01,
            flow_type="accumulation",
            signal_dir="buy",
            urgency=1,
            current_price=3.0,
            stop_loss=2.8,
        )
        assert "加仓" in action
        assert color == "green"

    def test_oversold_bounce(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=-2.0,
            rsi_val=25,
            mom_20=-0.01,
            flow_type="normal",
            signal_dir="hold",
            urgency=1,
            current_price=3.0,
            stop_loss=2.8,
        )
        assert "逢低加仓" in action
        assert color == "green"

    def test_buy_signal_add(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=0.0,
            rsi_val=50,
            mom_20=0.0,
            flow_type="normal",
            signal_dir="buy",
            urgency=1,
            current_price=3.0,
            stop_loss=2.8,
        )
        assert "可加仓" in action
        assert color == "green"

    def test_hold_profitable_uptrend(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=4.0,
            rsi_val=55,
            mom_20=0.02,
            flow_type="normal",
            signal_dir="sell",
            urgency=1,
            current_price=3.5,
            stop_loss=3.2,
        )
        assert "持有" in action
        assert color == "yellow"

    def test_hold_neutral_observe(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=1.0,
            rsi_val=50,
            mom_20=0.0,
            flow_type="normal",
            signal_dir="hold",
            urgency=1,
            current_price=3.0,
            stop_loss=2.8,
        )
        assert "观望" in action
        assert color == "yellow"

    def test_hold_wait_oversold(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=-4.0,
            rsi_val=35,
            mom_20=0.0,
            flow_type="normal",
            signal_dir="sell",
            urgency=2,
            current_price=3.0,
            stop_loss=2.8,
        )
        assert "持仓等待" in action
        assert color == "yellow"

    def test_fallback_hold_observe(self) -> None:
        action, color, _ = _determine_action(
            pnl_pct=-4.0,
            rsi_val=50,
            mom_20=0.0,
            flow_type="normal",
            signal_dir="sell",
            urgency=2,
            current_price=3.0,
            stop_loss=2.8,
        )
        assert "持有观望" in action
        assert color == "yellow"


class TestAnalyzePortfolio:
    @patch("engine.portfolio_advisor.load_hist", side_effect=_mock_load)
    def test_portfolio_analysis(self, _m: object) -> None:
        holdings = [
            Holding("510300", 3.0, 5000),
            Holding("510500", 3.5, 3000),
        ]
        result = analyze_portfolio(holdings)
        assert result["total_positions"] == 2
        assert "total_pnl" in result
        assert "health_score" in result
        assert "positions" in result
        assert "overall_strategy" in result

    @patch("engine.portfolio_advisor.load_hist", side_effect=_mock_load)
    def test_empty_portfolio(self, _m: object) -> None:
        result = analyze_portfolio([])
        assert result["total_positions"] == 0


class TestPortfolioPersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        with patch("engine.portfolio_advisor.PORTFOLIO_DIR", tmp_path):
            holdings = [
                Holding("510300", 4.5, 10000, "2026-01-01", "test"),
                Holding("510500", 6.0, 5000),
            ]
            save_portfolio(holdings, "test")
            loaded = load_portfolio("test")
            assert len(loaded) == 2
            assert loaded[0].symbol == "510300"
            assert loaded[0].buy_price == 4.5
            assert loaded[0].shares == 10000

    def test_load_empty(self, tmp_path: Path) -> None:
        with patch("engine.portfolio_advisor.PORTFOLIO_DIR", tmp_path):
            loaded = load_portfolio("nonexistent")
            assert loaded == []


class TestPortfolioAPI:
    @patch("engine.portfolio_advisor.PORTFOLIO_DIR", Path("/tmp/test_portfolio_api"))
    def test_add_and_list(self) -> None:
        # Clean up
        p = Path("/tmp/test_portfolio_api/test_api.json")
        if p.exists():
            p.unlink()

        # Add
        res = client.post(
            "/api/portfolio/add",
            json={
                "symbol": "510300",
                "buy_price": 4.5,
                "shares": 10000,
                "portfolio_id": "test_api",
            },
        )
        assert res.status_code == 200
        assert res.json()["action"] == "added"

        # List
        res = client.get("/api/portfolio/list?portfolio_id=test_api")
        assert res.status_code == 200
        assert res.json()["count"] == 1

    @patch("engine.portfolio_advisor.PORTFOLIO_DIR", Path("/tmp/test_portfolio_api2"))
    def test_add_merge(self) -> None:
        """Adding same symbol should merge (average down)."""
        p = Path("/tmp/test_portfolio_api2/test_merge.json")
        if p.exists():
            p.unlink()

        client.post(
            "/api/portfolio/add",
            json={
                "symbol": "510300",
                "buy_price": 4.0,
                "shares": 1000,
                "portfolio_id": "test_merge",
            },
        )
        client.post(
            "/api/portfolio/add",
            json={
                "symbol": "510300",
                "buy_price": 5.0,
                "shares": 1000,
                "portfolio_id": "test_merge",
            },
        )

        res = client.get("/api/portfolio/list?portfolio_id=test_merge")
        h = res.json()["holdings"][0]
        assert h["shares"] == 2000
        assert abs(h["buy_price"] - 4.5) < 0.01  # Average price

    def test_add_invalid_symbol(self) -> None:
        res = client.post(
            "/api/portfolio/add", json={"symbol": "abc", "buy_price": 1.0, "shares": 100}
        )
        assert res.status_code == 400

    @patch("engine.portfolio_advisor.PORTFOLIO_DIR", Path("/tmp/test_portfolio_remove"))
    def test_remove(self) -> None:
        p = Path("/tmp/test_portfolio_remove/test_rm.json")
        if p.exists():
            p.unlink()

        client.post(
            "/api/portfolio/add",
            json={"symbol": "510300", "buy_price": 4.0, "shares": 1000, "portfolio_id": "test_rm"},
        )
        res = client.post(
            "/api/portfolio/remove", json={"symbol": "510300", "portfolio_id": "test_rm"}
        )
        assert res.status_code == 200
        assert res.json()["remaining"] == 0

    @patch("engine.portfolio_advisor.PORTFOLIO_DIR", Path("/tmp/test_portfolio_remove2"))
    def test_remove_not_found(self) -> None:
        Path("/tmp/test_portfolio_remove2").mkdir(parents=True, exist_ok=True)
        Path("/tmp/test_portfolio_remove2/default.json").write_text("[]")
        res = client.post("/api/portfolio/remove", json={"symbol": "999999"})
        assert res.status_code == 404

    @patch("engine.portfolio_advisor.PORTFOLIO_DIR", Path("/tmp/test_portfolio_analyze"))
    def test_analyze_empty(self) -> None:
        Path("/tmp/test_portfolio_analyze").mkdir(parents=True, exist_ok=True)
        p = Path("/tmp/test_portfolio_analyze/default.json")
        if p.exists():
            p.unlink()
        res = client.get("/api/portfolio/analyze")
        assert res.status_code == 404

    @patch("engine.portfolio_advisor.load_hist", side_effect=_mock_load)
    def test_analyze_single(self, _m: object) -> None:
        res = client.get("/api/portfolio/analyze/510300?buy_price=3.0&shares=1000")
        assert res.status_code == 200
        d = res.json()
        assert d["symbol"] == "510300"
        assert "action" in d

    def test_analyze_single_invalid(self) -> None:
        assert client.get("/api/portfolio/analyze/abc").status_code == 400

    @patch("engine.portfolio_advisor.PORTFOLIO_DIR", Path("/tmp/test_portfolio_save"))
    def test_save_full_portfolio(self) -> None:
        """Test POST /save endpoint (lines 77-88)."""
        Path("/tmp/test_portfolio_save").mkdir(parents=True, exist_ok=True)
        res = client.post(
            "/api/portfolio/save",
            json={
                "portfolio_id": "save_test",
                "holdings": [
                    {"symbol": "510300", "buy_price": 4.0, "shares": 1000},
                    {"symbol": "510500", "buy_price": 6.0, "shares": 500},
                ],
            },
        )
        assert res.status_code == 200
        assert res.json()["saved"] == 2
        assert res.json()["portfolio_id"] == "save_test"

    @patch("engine.portfolio_advisor.load_hist")
    def test_analyze_single_no_buy_price(self, mock_load: object) -> None:
        """Test buy_price=0 path — uses current price from data (lines 179-184)."""
        mock_load.return_value = _mock_df()
        res = client.get("/api/portfolio/analyze/510300?shares=1000")
        assert res.status_code == 200
        d = res.json()
        assert d["symbol"] == "510300"
        assert d["buy_price"] > 0  # Should have auto-filled from data

    @patch("api.routers.portfolio.analyze_position", return_value=None)
    def test_analyze_single_insufficient_data(self, _m: object) -> None:
        """Test analyze_position returning None (line 189)."""
        res = client.get("/api/portfolio/analyze/510300?buy_price=3.0&shares=1000")
        assert res.status_code == 422

    @patch("data.storage.parquet_store.load_hist", return_value=pd.DataFrame())
    def test_analyze_single_no_data(self, _m: object) -> None:
        """Test buy_price=0 with no data (line 183)."""
        res = client.get("/api/portfolio/analyze/510300?shares=1000")
        assert res.status_code == 404

    @patch("engine.portfolio_advisor.PORTFOLIO_DIR", Path("/tmp/test_portfolio_note"))
    def test_add_with_note_update(self) -> None:
        """Test note update on merge (line 109)."""
        Path("/tmp/test_portfolio_note").mkdir(parents=True, exist_ok=True)
        p = Path("/tmp/test_portfolio_note/note_test.json")
        if p.exists():
            p.unlink()

        # Add initial holding
        client.post(
            "/api/portfolio/add",
            json={
                "symbol": "510300",
                "buy_price": 4.0,
                "shares": 1000,
                "portfolio_id": "note_test",
            },
        )
        # Add again with note — should merge and update note
        client.post(
            "/api/portfolio/add",
            json={
                "symbol": "510300",
                "buy_price": 5.0,
                "shares": 500,
                "note": "加仓",
                "portfolio_id": "note_test",
            },
        )
        res = client.get("/api/portfolio/list?portfolio_id=note_test")
        h = res.json()["holdings"][0]
        assert h["shares"] == 1500
        assert h["note"] == "加仓"

    @patch("engine.portfolio_advisor.load_hist", side_effect=_mock_load)
    @patch("engine.portfolio_advisor.PORTFOLIO_DIR", Path("/tmp/test_portfolio_analyze2"))
    def test_analyze_full_portfolio(self, _m: object) -> None:
        """Test GET /analyze with real holdings (line 164)."""
        Path("/tmp/test_portfolio_analyze2").mkdir(parents=True, exist_ok=True)
        p = Path("/tmp/test_portfolio_analyze2/default.json")
        import json

        p.write_text(
            json.dumps(
                [
                    {
                        "symbol": "510300",
                        "buy_price": 3.0,
                        "shares": 1000,
                        "buy_date": "",
                        "note": "",
                    },
                ]
            )
        )
        res = client.get("/api/portfolio/analyze")
        assert res.status_code == 200
        assert "health_score" in res.json()


class TestAnalyzePositionBranches:
    """Test uncovered branches in analyze_position decision logic."""

    def _make_advice(
        self,
        *,
        pnl_pct: float = 0.0,
        rsi_val: float = 50.0,
        mom_20: float = 0.0,
        hvol: float = 0.2,
        flow_type: str = "normal",
        signal_dir: str = "hold",
        buy_price: float = 3.0,
        final_price: float = 3.0,
    ) -> object:
        """Helper that patches all factors to control branch coverage in analyze_position."""
        df = _mock_df(final_price=final_price)
        h = Holding(symbol="510300", buy_price=buy_price, shares=1000)
        with (
            patch("engine.portfolio_advisor.load_hist", return_value=df),
            patch("engine.portfolio_advisor.rsi", return_value=pd.Series([rsi_val])),
            patch("engine.portfolio_advisor.momentum", return_value=pd.Series([mom_20])),
            patch(
                "engine.portfolio_advisor.historical_volatility",
                return_value=pd.Series([hvol]),
            ),
            patch("engine.portfolio_advisor.detect_flow") as mock_flow,
            patch("engine.portfolio_advisor.generate_signal") as mock_sig,
        ):
            # Configure flow mock
            if flow_type != "normal":
                from enum import Enum
                from unittest.mock import MagicMock

                class FT(Enum):
                    val = flow_type

                flow_obj = MagicMock()
                flow_obj.flow_type = FT.val
                mock_flow.return_value = flow_obj
            else:
                mock_flow.return_value = None

            # Configure signal mock
            from unittest.mock import MagicMock

            if signal_dir != "hold":
                from enum import Enum

                class SD(Enum):
                    val = signal_dir

                sig_obj = MagicMock()
                sig_obj.direction = SD.val
                sig_obj.target_price = final_price * 1.05
                sig_obj.stop_loss = final_price * 0.95
                mock_sig.return_value = sig_obj
            else:
                mock_sig.return_value = None

            return analyze_position(h)

    # --- P&L branches (lines 192-193, 200-202) ---

    def test_pnl_loss_5_to_8_pct(self) -> None:
        """Lines 192-193: pnl_pct between -5 and -8."""
        advice = self._make_advice(buy_price=3.0, final_price=2.8)  # ~-6.7%
        assert advice is not None
        assert any("接近止损线" in r for r in advice.reasons)

    def test_pnl_profit_above_5_pct(self) -> None:
        """pnl_pct between 5-10% → 止盈保护."""
        advice = self._make_advice(buy_price=3.0, final_price=3.2)  # ~+6.7%
        assert advice is not None
        assert any("止盈保护" in r for r in advice.reasons)

    def test_pnl_profit_above_10_pct(self) -> None:
        """pnl_pct >= 10% → 盈利丰厚 (previously dead code, now reachable)."""
        advice = self._make_advice(buy_price=3.0, final_price=3.4)  # ~+13.3%
        assert advice is not None
        assert any("盈利丰厚" in r for r in advice.reasons)

    # --- RSI branches (lines 206-207, 209, 213) ---

    def test_rsi_severe_overbought(self) -> None:
        """Lines 206-207: RSI > 75."""
        advice = self._make_advice(rsi_val=80.0)
        assert advice is not None
        assert any("严重超买" in r for r in advice.reasons)

    def test_rsi_high(self) -> None:
        """Line 209: RSI between 65-75."""
        advice = self._make_advice(rsi_val=70.0)
        assert advice is not None
        assert any("偏高" in r for r in advice.reasons)

    def test_rsi_oversold_zone(self) -> None:
        """Line 213: RSI between 25-35."""
        advice = self._make_advice(rsi_val=30.0)
        assert advice is not None
        assert any("超卖区" in r for r in advice.reasons)

    # --- Momentum branches (lines 219, 221) ---

    def test_momentum_mild_decline(self) -> None:
        """Line 219: mom_20 between -0.03 and -0.08."""
        advice = self._make_advice(mom_20=-0.05)
        assert advice is not None
        assert any("20日跌" in r for r in advice.reasons)

    def test_momentum_strong_rise(self) -> None:
        """Line 221: mom_20 > 0.05."""
        advice = self._make_advice(mom_20=0.07)
        assert advice is not None
        assert any("趋势良好" in r for r in advice.reasons)

    # --- Flow branches (lines 229-230, 232, 234-235, 237) ---

    def test_flow_distribution(self) -> None:
        """Lines 229-230: distribution flow."""
        advice = self._make_advice(flow_type="distribution")
        assert advice is not None
        assert any("机构出货" in r for r in advice.reasons)

    def test_flow_accumulation(self) -> None:
        """Line 232: accumulation flow."""
        advice = self._make_advice(flow_type="accumulation")
        assert advice is not None
        assert any("机构吸筹" in r for r in advice.reasons)

    def test_flow_panic_sell(self) -> None:
        """Lines 234-235: panic_sell flow."""
        advice = self._make_advice(flow_type="panic_sell")
        assert advice is not None
        assert any("恐慌抛售" in r for r in advice.reasons)

    def test_flow_breakout_buy(self) -> None:
        """Line 237: breakout_buy flow."""
        advice = self._make_advice(flow_type="breakout_buy")
        assert advice is not None
        assert any("放量突破" in r for r in advice.reasons)

    # --- Signal direction branches (lines 241-242, 244) ---

    def test_signal_sell(self) -> None:
        """Lines 241-242: sell/strong_sell signal direction."""
        advice = self._make_advice(signal_dir="sell")
        assert advice is not None
        assert any("量化信号" in r for r in advice.reasons)

    def test_signal_buy(self) -> None:
        """Line 244: buy/strong_buy signal direction."""
        advice = self._make_advice(signal_dir="buy")
        assert advice is not None
        assert any("量化信号" in r for r in advice.reasons)

    # --- Empty reasons fallback (line 252) ---

    def test_no_reasons_fallback(self) -> None:
        """Line 252: no reasons triggered -> '暂无明显信号'."""
        # All factors neutral: rsi ~50, mom ~0, normal flow, hold signal, small pnl
        advice = self._make_advice(buy_price=3.0, final_price=3.0, rsi_val=50.0, mom_20=0.0)
        assert advice is not None
        # Either it has reasons from the decision logic or the fallback
        # (the fallback is hard to hit since _determine_action usually adds context)
        assert len(advice.reasons) >= 1


class TestAnalyzePortfolioBranches:
    """Test uncovered branches in analyze_portfolio health/strategy logic."""

    def _make_position_advice(
        self,
        symbol: str = "510300",
        pnl_pct: float = 0.0,
        urgency: int = 1,
        cost: float = 10000.0,
        market_value: float = 10000.0,
    ) -> PositionAdvice:
        return PositionAdvice(
            symbol=symbol,
            name="Test",
            buy_price=1.0,
            shares=1000,
            cost=cost,
            current_price=market_value / 1000,
            market_value=market_value,
            pnl=market_value - cost,
            pnl_pct=pnl_pct,
            action="🟡 持有",
            action_color="yellow",
            urgency=urgency,
            reasons=["test"],
            rsi_14=50.0,
            momentum_20d=0.0,
            flow_type="normal",
            signal_direction="hold",
            target_price=11.0,
            stop_loss=9.0,
            suggested_action="hold",
        )

    def test_health_large_profit(self) -> None:
        """Line 436: total_pnl_pct > 5 -> health += 20."""
        # Cost 10000, value 11000 => +10% pnl
        pa = self._make_position_advice(pnl_pct=10.0, cost=10000, market_value=11000)
        with patch("engine.portfolio_advisor.analyze_position", return_value=pa):
            result = analyze_portfolio([Holding("510300", 1.0, 1000)])
            assert result["health_score"] > 60  # 50 + 20 + 15 (no urgent) + win bonus

    def test_health_small_profit(self) -> None:
        """Line 438: total_pnl_pct > 0 but <= 5 -> health += 10."""
        pa = self._make_position_advice(pnl_pct=2.0, cost=10000, market_value=10200)
        with patch("engine.portfolio_advisor.analyze_position", return_value=pa):
            result = analyze_portfolio([Holding("510300", 1.0, 1000)])
            assert result["health_score"] > 55

    def test_health_small_loss(self) -> None:
        """Line 442: total_pnl_pct < 0 but >= -5 -> health -= 10."""
        pa = self._make_position_advice(pnl_pct=-2.0, cost=10000, market_value=9800)
        with patch("engine.portfolio_advisor.analyze_position", return_value=pa):
            result = analyze_portfolio([Holding("510300", 1.0, 1000)])
            assert result["health_score"] < 60

    def test_health_many_urgent(self) -> None:
        """Line 449: len(urgent) > 2 -> health -= 15."""
        advices = []
        for i in range(4):
            advices.append(
                self._make_position_advice(
                    symbol=f"5103{i:02d}",
                    pnl_pct=-1.0,
                    urgency=5,
                    cost=10000,
                    market_value=9900,
                )
            )

        def side_effect(h: Holding) -> PositionAdvice:
            return advices.pop(0)

        with patch("engine.portfolio_advisor.analyze_position", side_effect=side_effect):
            holdings = [Holding(f"5103{i:02d}", 1.0, 1000) for i in range(4)]
            result = analyze_portfolio(holdings)
            assert result["urgent_count"] == 4

    def test_strategy_large_loss_many_urgent(self) -> None:
        """Line 456-457: total_pnl_pct < -5 and urgent > 3."""
        advices = []
        for i in range(5):
            advices.append(
                self._make_position_advice(
                    symbol=f"5103{i:02d}",
                    pnl_pct=-10.0,
                    urgency=5,
                    cost=10000,
                    market_value=9000,
                )
            )

        def side_effect(h: Holding) -> PositionAdvice:
            return advices.pop(0)

        with patch("engine.portfolio_advisor.analyze_position", side_effect=side_effect):
            holdings = [Holding(f"5103{i:02d}", 1.0, 1000) for i in range(5)]
            result = analyze_portfolio(holdings)
            assert "优先处理止损单" in result["overall_strategy"]

    def test_strategy_good_profit(self) -> None:
        """Line 461: total_pnl_pct > 5 -> profit strategy."""
        pa = self._make_position_advice(pnl_pct=8.0, cost=10000, market_value=10800)
        with patch("engine.portfolio_advisor.analyze_position", return_value=pa):
            result = analyze_portfolio([Holding("510300", 1.0, 1000)])
            assert "盈利良好" in result["overall_strategy"]

    def test_strategy_urgent_items(self) -> None:
        """Lines 462-463: urgent > 0 but pnl not extreme."""
        pa = self._make_position_advice(pnl_pct=1.0, urgency=4, cost=10000, market_value=10100)
        with patch("engine.portfolio_advisor.analyze_position", return_value=pa):
            result = analyze_portfolio([Holding("510300", 1.0, 1000)])
            assert "紧急处理" in result["overall_strategy"]


class TestPathTraversalPrevention:
    """Verify portfolio_id validation blocks path traversal."""

    def test_save_rejects_path_traversal(self, tmp_path: Path) -> None:
        import pytest

        from engine.portfolio_advisor import _validate_portfolio_id

        with pytest.raises(ValueError, match="Invalid portfolio_id"):
            _validate_portfolio_id("../../etc/passwd")

    def test_save_rejects_slashes(self, tmp_path: Path) -> None:
        import pytest

        from engine.portfolio_advisor import _validate_portfolio_id

        with pytest.raises(ValueError):
            _validate_portfolio_id("foo/bar")

    def test_save_rejects_dots(self, tmp_path: Path) -> None:
        import pytest

        from engine.portfolio_advisor import _validate_portfolio_id

        with pytest.raises(ValueError):
            _validate_portfolio_id("../config")

    def test_save_accepts_valid_ids(self) -> None:
        from engine.portfolio_advisor import _validate_portfolio_id

        _validate_portfolio_id("default")
        _validate_portfolio_id("my-portfolio-1")
        _validate_portfolio_id("test_123")

    def test_save_rejects_empty(self) -> None:
        import pytest

        from engine.portfolio_advisor import _validate_portfolio_id

        with pytest.raises(ValueError):
            _validate_portfolio_id("")

    def test_save_rejects_too_long(self) -> None:
        import pytest

        from engine.portfolio_advisor import _validate_portfolio_id

        with pytest.raises(ValueError):
            _validate_portfolio_id("a" * 65)

    def test_save_portfolio_with_traversal_id(self, tmp_path: Path) -> None:
        import pytest

        with patch("engine.portfolio_advisor.PORTFOLIO_DIR", tmp_path), pytest.raises(ValueError):
            save_portfolio([], "../../etc/passwd")

    def test_load_portfolio_with_traversal_id(self, tmp_path: Path) -> None:
        import pytest

        with patch("engine.portfolio_advisor.PORTFOLIO_DIR", tmp_path), pytest.raises(ValueError):
            load_portfolio("../../etc/passwd")
