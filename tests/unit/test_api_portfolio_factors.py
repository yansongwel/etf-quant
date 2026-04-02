"""Tests for portfolio equity-curve and factor correlation API endpoints."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from api.deps import require_api_key
from api.main import app
from engine.portfolio_advisor import Holding

app.dependency_overrides[require_api_key] = lambda: "test-key"
client = TestClient(app)


# ─── helpers ──────────────────────────────────────────


def _make_price_df(days: int = 60, base_price: float = 3.0) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=days, freq="B")
    np.random.seed(42)
    closes = base_price + np.cumsum(np.random.randn(days) * 0.02)
    return pd.DataFrame(
        {
            "open": closes - 0.01,
            "high": closes + 0.02,
            "low": closes - 0.02,
            "close": closes,
            "volume": np.random.randint(1000000, 5000000, days).astype(float),
            "amount": np.random.randint(3000000, 15000000, days).astype(float),
            "pct_change": np.random.randn(days) * 0.5,
            "amplitude": np.abs(np.random.randn(days)) * 0.3,
            "change": np.random.randn(days) * 0.02,
            "turnover": np.abs(np.random.randn(days)) * 0.5,
        },
        index=dates,
    )


# ─── Portfolio Equity Curve ──────────────────────────


class TestPortfolioEquityCurve:
    @patch("api.routers.portfolio.load_portfolio")
    @patch("data.storage.parquet_store.load_hist")
    def test_equity_curve_basic(self, mock_hist, mock_portfolio):
        mock_portfolio.return_value = [
            Holding(symbol="510300", buy_price=3.5, shares=1000, buy_date="2026-01-01"),
        ]
        mock_hist.return_value = _make_price_df(days=30, base_price=3.5)

        resp = client.get("/api/portfolio/equity-curve?portfolio_id=default&days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert "curve" in data
        assert len(data["curve"]) > 0
        assert "total_cost" in data
        assert "generated_at" in data
        # Each point has date, value, pnl, pnl_pct
        point = data["curve"][0]
        assert "date" in point
        assert "value" in point
        assert "pnl" in point
        assert "pnl_pct" in point

    @patch("api.routers.portfolio.load_portfolio")
    def test_equity_curve_empty_portfolio(self, mock_portfolio):
        mock_portfolio.return_value = []
        resp = client.get("/api/portfolio/equity-curve")
        assert resp.status_code == 404

    @patch("api.routers.portfolio.load_portfolio")
    @patch("data.storage.parquet_store.load_hist")
    def test_equity_curve_no_price_data(self, mock_hist, mock_portfolio):
        mock_portfolio.return_value = [
            Holding(symbol="510300", buy_price=3.5, shares=1000, buy_date="2026-01-01"),
        ]
        mock_hist.return_value = pd.DataFrame()

        resp = client.get("/api/portfolio/equity-curve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["curve"] == []

    @patch("api.routers.portfolio.load_portfolio")
    @patch("data.storage.parquet_store.load_hist")
    def test_equity_curve_multiple_holdings(self, mock_hist, mock_portfolio):
        mock_portfolio.return_value = [
            Holding(symbol="510300", buy_price=3.5, shares=1000, buy_date="2026-01-01"),
            Holding(symbol="510500", buy_price=5.0, shares=500, buy_date="2026-01-01"),
        ]
        df1 = _make_price_df(days=20, base_price=3.5)
        df2 = _make_price_df(days=20, base_price=5.0)
        mock_hist.side_effect = [df1, df2]

        resp = client.get("/api/portfolio/equity-curve?days=20")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == round(3.5 * 1000 + 5.0 * 500, 2)
        assert len(data["curve"]) > 0


# ─── Factor Correlation ─────────────────────────────


class TestFactorCorrelation:
    @patch("api.routers.factors.cache_json_get", return_value=None)
    @patch("api.routers.factors.cache_json_set")
    @patch("api.routers.factors.load_hist")
    def test_correlation_basic(self, mock_hist, mock_cache_set, mock_cache_get):
        df = _make_price_df(days=150, base_price=3.0)
        mock_hist.return_value = df

        resp = client.get("/api/factors/correlation/510300?tail=120")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "510300"
        assert "factors" in data
        assert "matrix" in data
        assert data["size"] == len(data["factors"])
        # Matrix should be square
        assert len(data["matrix"]) == data["size"]
        if data["size"] > 0:
            assert len(data["matrix"][0]) == data["size"]

    @patch("api.routers.factors.cache_json_get", return_value=None)
    @patch("api.routers.factors.load_hist")
    def test_correlation_invalid_symbol(self, mock_hist, mock_cache_get):
        resp = client.get("/api/factors/correlation/abc")
        assert resp.status_code == 400

    @patch("api.routers.factors.cache_json_get", return_value=None)
    @patch("api.routers.factors.load_hist")
    def test_correlation_insufficient_data(self, mock_hist, mock_cache_get):
        mock_hist.return_value = _make_price_df(days=10, base_price=3.0)
        resp = client.get("/api/factors/correlation/510300?tail=120")
        assert resp.status_code == 404

    @patch("api.routers.factors.cache_json_get", return_value=None)
    @patch("api.routers.factors.load_hist")
    def test_correlation_empty_data(self, mock_hist, mock_cache_get):
        mock_hist.return_value = pd.DataFrame()
        resp = client.get("/api/factors/correlation/510300")
        assert resp.status_code == 404

    @patch("api.routers.factors.cache_json_get")
    def test_correlation_cache_hit(self, mock_cache_get):
        cached = {
            "symbol": "510300",
            "factors": ["rsi_14d", "ma_ratio_5_20"],
            "size": 2,
            "matrix": [[1.0, 0.5], [0.5, 1.0]],
        }
        mock_cache_get.return_value = cached
        resp = client.get("/api/factors/correlation/510300")
        assert resp.status_code == 200
        assert resp.json() == cached
