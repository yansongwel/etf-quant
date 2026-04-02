"""Tests for flow and risk API endpoints using TestClient."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _mock_df(days: int = 120, vol_spike: bool = False) -> pd.DataFrame:
    dates = pd.date_range(end="2026-03-28", periods=days, freq="D")
    np.random.seed(42)
    close = 3.0 + np.cumsum(np.random.randn(days) * 0.01)
    volume = np.full(days, 1_000_000.0) + np.random.randn(days) * 50_000
    if vol_spike:
        volume[-1] = 3_000_000
    return pd.DataFrame(
        {
            "open": close - 0.01,
            "high": close + 0.02,
            "low": close - 0.02,
            "close": close,
            "volume": np.maximum(volume, 100),
            "amount": close * np.maximum(volume, 100),
            "turnover": np.full(days, 2.0),
        },
        index=dates,
    )


def _mock_load(symbol: str, category: str = "etf_hist") -> pd.DataFrame:
    if symbol == "EMPTY":
        return pd.DataFrame()
    return _mock_df(vol_spike=symbol in ("512010", "159992"))


class TestFlowScanAPI:
    @patch("api.routers.flow.load_hist", side_effect=_mock_load)
    def test_scan_with_symbols(self, _m: object) -> None:
        res = client.get("/api/flow/scan?symbols=510300,510500")
        assert res.status_code == 200
        d = res.json()
        assert d["total_scanned"] == 2
        assert "signals" in d

    @patch("api.routers.flow.load_hist", return_value=pd.DataFrame())
    def test_scan_no_data(self, _m: object) -> None:
        res = client.get("/api/flow/scan?symbols=EMPTY")
        assert res.status_code == 404


class TestFlowDetailAPI:
    @patch("api.routers.flow.load_hist", side_effect=_mock_load)
    def test_detail_ok(self, _m: object) -> None:
        res = client.get("/api/flow/detail/510300")
        assert res.status_code == 200
        d = res.json()
        assert d["symbol"] == "510300"
        assert "flow_type" in d
        assert "advice" in d

    def test_detail_invalid(self) -> None:
        assert client.get("/api/flow/detail/abc").status_code == 400

    @patch("api.routers.flow.load_hist", return_value=pd.DataFrame())
    def test_detail_no_data(self, _m: object) -> None:
        assert client.get("/api/flow/detail/999999").status_code == 404

    @patch("api.routers.flow.load_hist", return_value=_mock_df(days=10))
    def test_detail_insufficient(self, _m: object) -> None:
        assert client.get("/api/flow/detail/510300").status_code == 422


class TestRiskETFAPI:
    @patch("api.routers.flow.load_hist", side_effect=_mock_load)
    def test_risk_ok(self, _m: object) -> None:
        res = client.get("/api/risk/etf/510300")
        assert res.status_code == 200
        d = res.json()
        assert "risk_level" in d
        assert "risk_score" in d
        assert "warnings" in d
        assert "suggestions" in d

    def test_risk_invalid(self) -> None:
        assert client.get("/api/risk/etf/bad").status_code == 400

    @patch("api.routers.flow.load_hist", return_value=pd.DataFrame())
    def test_risk_no_data(self, _m: object) -> None:
        assert client.get("/api/risk/etf/999999").status_code == 404


class TestRiskReportAPI:
    @patch("api.routers.flow.full_risk_report")
    def test_report(self, _mock_report: object) -> None:
        _mock_report.return_value = {
            "capital": 500000,
            "portfolio_risk": "medium",
            "portfolio_risk_label": "🟡 中风险",
            "avg_risk_score": 30.0,
            "high_risk_count": 2,
            "total_etfs": 10,
            "risk_profiles": [],
            "layout_suggestions": [],
            "risk_rules": [
                {"rule": "单笔止损", "value": "2%", "priority": "必须执行"},
                {"rule": "单只仓位", "value": "30%", "priority": "必须执行"},
                {"rule": "同板块", "value": "40%", "priority": "建议执行"},
                {"rule": "现金保留", "value": "10-20%", "priority": "必须执行"},
                {"rule": "亏损熔断", "value": "5%", "priority": "必须执行"},
                {"rule": "盈利保护", "value": "3%", "priority": "建议执行"},
            ],
            "disclaimer": "仅供参考",
        }
        res = client.post("/api/risk/report", json={"capital": 500000})
        assert res.status_code == 200
        d = res.json()
        assert d["portfolio_risk"] == "medium"
        assert len(d["risk_rules"]) == 6


class TestLayoutAPI:
    @patch("engine.risk_advisor.load_hist", side_effect=_mock_load)
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_layout_suggestions(self, _sectors: object, _load: object) -> None:
        from engine.sector import SectorAnalysis, SectorPhase

        _sectors.return_value = [
            SectorAnalysis(
                sector_name="测试板块",
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
                risk_level="中低风险",
                action="提前布局",
                allocation_pct=20.0,
            ),
        ]
        res = client.post("/api/risk/layout", json={"capital": 500000})
        assert res.status_code == 200
        d = res.json()
        assert d["total_suggestions"] >= 1
        s = d["suggestions"][0]
        assert "提前布局" in s["action"]
        assert s["position_pct"] > 0

    @patch("engine.risk_advisor.load_hist", side_effect=_mock_load)
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_layout_weakening(self, _sectors: object, _load: object) -> None:
        from engine.sector import SectorAnalysis, SectorPhase

        _sectors.return_value = [
            SectorAnalysis(
                sector_name="走弱板块",
                phase=SectorPhase.WEAKENING,
                etf_symbols=["510300"],
                best_etf="510300",
                best_etf_name="沪深300ETF",
                momentum_20d=0.05,
                momentum_5d=0.01,
                momentum_acceleration=-0.04,
                rsi=72.0,
                ma_ratio=1.02,
                volatility=0.25,
                score=3.0,
                risk_level="高风险",
                action="减仓",
                allocation_pct=5.0,
            ),
        ]
        res = client.post("/api/risk/layout", json={"capital": 300000})
        assert res.status_code == 200
        d = res.json()
        assert d["suggestions"][0]["position_pct"] == 0

    @patch("engine.risk_advisor.load_hist", side_effect=_mock_load)
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_layout_leading(self, _sectors: object, _load: object) -> None:
        from engine.sector import SectorAnalysis, SectorPhase

        _sectors.return_value = [
            SectorAnalysis(
                sector_name="领涨板块",
                phase=SectorPhase.LEADING,
                etf_symbols=["510300"],
                best_etf="510300",
                best_etf_name="沪深300ETF",
                momentum_20d=0.08,
                momentum_5d=0.03,
                momentum_acceleration=0.05,
                rsi=62.0,
                ma_ratio=1.03,
                volatility=0.2,
                score=8.0,
                risk_level="中风险",
                action="持有",
                allocation_pct=15.0,
            ),
        ]
        res = client.post("/api/risk/layout", json={"capital": 500000})
        assert res.status_code == 200
        d = res.json()
        assert "顺势" in d["suggestions"][0]["action"]

    @patch("engine.risk_advisor.load_hist", side_effect=_mock_load)
    @patch("engine.risk_advisor.analyze_all_sectors")
    def test_layout_lagging(self, _sectors: object, _load: object) -> None:
        from engine.sector import SectorAnalysis, SectorPhase

        _sectors.return_value = [
            SectorAnalysis(
                sector_name="底部板块",
                phase=SectorPhase.LAGGING,
                etf_symbols=["510300"],
                best_etf="510300",
                best_etf_name="沪深300ETF",
                momentum_20d=-0.08,
                momentum_5d=-0.05,
                momentum_acceleration=-0.03,
                rsi=28.0,
                ma_ratio=0.95,
                volatility=0.3,
                score=-2.0,
                risk_level="低风险",
                action="观望",
                allocation_pct=3.0,
            ),
        ]
        res = client.post("/api/risk/layout", json={"capital": 500000})
        assert res.status_code == 200
        d = res.json()
        assert "观望" in d["suggestions"][0]["action"]
