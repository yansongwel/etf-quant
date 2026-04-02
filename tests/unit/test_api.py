"""Tests for FastAPI endpoints using TestClient."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from api.deps import require_api_key
from api.main import app

# Override auth for most tests — auth-specific tests use a separate client
app.dependency_overrides[require_api_key] = lambda: "test-key"
client = TestClient(app)


class TestSystemEndpoints:
    def test_health_check(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "services" in data

    def test_health_returns_server_time_cst(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "server_time_cst" in data
        # Verify format: YYYY-MM-DD HH:MM:SS
        time_str = data["server_time_cst"]
        assert len(time_str) == 19
        assert time_str[4] == "-" and time_str[10] == " " and time_str[13] == ":"

    def test_health_returns_etf_count(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "etf_count" in data
        assert isinstance(data["etf_count"], int)
        assert data["etf_count"] >= 0

    def test_etf_list(self):
        resp = client.get("/etf/list")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "symbol" in data[0]
        assert "name" in data[0]

    @patch("data.collectors.realtime.fetch_realtime_quotes")
    def test_market_realtime(self, mock_fetch):
        """Test /market/realtime returns proper structure."""
        import api.routers.system as sys_mod

        sys_mod._realtime_cache = None  # Clear cache
        mock_fetch.return_value = pd.DataFrame(
            {
                "symbol": ["510300", "518880"],
                "name": ["沪深300", "黄金ETF"],
                "close": [3.5, 5.2],
                "pct_change": [1.2, -0.5],
                "volume": [100000, 50000],
                "high": [3.55, 5.3],
                "low": [3.45, 5.1],
                "open": [3.48, 5.15],
            }
        )
        resp = client.get("/market/realtime")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert data["count"] == 2
        assert "quotes" in data
        assert data["source"] == "tencent"
        assert "generated_at" in data

    @patch("data.collectors.realtime.fetch_realtime_quotes")
    def test_market_realtime_empty(self, mock_fetch):
        """Test /market/realtime with empty data."""
        import api.routers.system as sys_mod

        sys_mod._realtime_cache = None
        mock_fetch.return_value = pd.DataFrame()
        resp = client.get("/market/realtime")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["quotes"] == []

    @patch("api.routers.system.detect_regime")
    def test_market_regime(self, mock_regime):
        """Test /market/regime endpoint."""
        mock_regime.return_value = {
            "regime": "bear",
            "confidence": 0.7,
            "indicators": {},
        }
        resp = client.get("/market/regime")
        assert resp.status_code == 200
        data = resp.json()
        assert "regime" in data

    @patch("api.routers.system.generate_verdict")
    def test_market_verdict(self, mock_verdict):
        """Test /market/verdict endpoint."""
        import api.routers.system as sys_mod

        sys_mod._verdict_cache = None
        mock_verdict.return_value = {
            "verdict": "观望",
            "confidence": 0.6,
            "reason": "市场震荡",
        }
        resp = client.get("/market/verdict")
        assert resp.status_code == 200
        data = resp.json()
        assert "verdict" in data

    @patch("api.routers.system.generate_verdict")
    def test_market_verdict_cached(self, mock_verdict):
        """Test verdict cache works — second call doesn't invoke function."""
        import api.routers.system as sys_mod

        sys_mod._verdict_cache = None
        mock_verdict.return_value = {"verdict": "买入", "confidence": 0.8}
        client.get("/market/verdict")
        client.get("/market/verdict")  # Should hit cache
        assert mock_verdict.call_count == 1


class TestDataEndpoints:
    def _make_sample_df(self) -> pd.DataFrame:
        dates = pd.bdate_range("2024-01-01", periods=10)
        return pd.DataFrame(
            {
                "open": [3.8] * 10,
                "high": [3.9] * 10,
                "low": [3.7] * 10,
                "close": [3.85] * 10,
                "volume": [1000000] * 10,
                "symbol": ["510300"] * 10,
            },
            index=dates,
        )

    @patch("api.routers.data.load_hist")
    @patch("api.routers.data.cache_json_get", return_value=None)
    @patch("api.routers.data.cache_json_set", return_value=True)
    def test_get_historical(self, mock_set, mock_get, mock_load):
        mock_load.return_value = self._make_sample_df()
        resp = client.get("/api/data/hist/510300")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "510300"
        assert data["count"] == 10

    @patch("api.routers.data.load_hist")
    @patch("api.routers.data.cache_json_get", return_value=None)
    def test_get_historical_not_found(self, mock_get, mock_load):
        mock_load.return_value = pd.DataFrame()
        resp = client.get("/api/data/hist/999999")
        assert resp.status_code == 404

    def test_invalid_symbol_format(self):
        resp = client.get("/api/data/hist/abc")
        assert resp.status_code == 400

    def test_list_symbols(self):
        resp = client.get("/api/data/symbols")
        assert resp.status_code == 200
        data = resp.json()
        assert "symbols" in data
        assert "count" in data


class TestFactorEndpoints:
    def _make_sample_df(self, n: int = 150) -> pd.DataFrame:
        np.random.seed(42)
        dates = pd.bdate_range("2024-01-01", periods=n)
        close = 3.0 * np.cumprod(1 + np.random.normal(0.001, 0.02, n))
        return pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.random.randint(1_000_000, 10_000_000, n),
                "symbol": ["510300"] * n,
            },
            index=dates,
        )

    @patch("api.routers.factors.load_hist")
    @patch("api.routers.factors.cache_json_get", return_value=None)
    @patch("api.routers.factors.cache_json_set", return_value=True)
    def test_get_momentum_factors(self, mock_set, mock_get, mock_load):
        mock_load.return_value = self._make_sample_df()
        resp = client.get("/api/factors/510300?category=momentum&tail=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "510300"
        assert data["category"] == "momentum"
        assert len(data["data"]) == 10

    @patch("api.routers.factors.load_hist")
    @patch("api.routers.factors.cache_json_get", return_value=None)
    @patch("api.routers.factors.cache_json_set", return_value=True)
    def test_get_volatility_factors(self, mock_set, mock_get, mock_load):
        mock_load.return_value = self._make_sample_df()
        resp = client.get("/api/factors/510300?category=volatility&tail=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "volatility"

    def test_invalid_category(self):
        resp = client.get("/api/factors/510300?category=invalid")
        assert resp.status_code == 400


class TestDataQualityEndpoints:
    def _make_sample_df(self) -> pd.DataFrame:
        dates = pd.bdate_range("2024-01-01", periods=100)
        np.random.seed(42)
        close = 3.0 * np.cumprod(1 + np.random.normal(0.001, 0.02, 100))
        return pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.random.randint(1_000_000, 10_000_000, 100),
            },
            index=dates,
        )

    @patch("api.routers.data.load_hist")
    def test_quality_single(self, mock_load) -> None:
        mock_load.return_value = self._make_sample_df()
        resp = client.get("/api/data/quality/510300")
        assert resp.status_code == 200
        data = resp.json()
        assert "quality_score" in data
        assert "symbol" in data

    def test_quality_single_invalid(self) -> None:
        resp = client.get("/api/data/quality/abc")
        assert resp.status_code == 400

    @patch("api.routers.data.load_hist", return_value=pd.DataFrame())
    def test_quality_single_not_found(self, _m: object) -> None:
        resp = client.get("/api/data/quality/999999")
        assert resp.status_code == 404

    @patch("api.routers.data.load_hist")
    def test_quality_all(self, mock_load) -> None:
        mock_load.return_value = self._make_sample_df()
        resp = client.get("/api/data/quality")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "average_score" in data
        assert "reports" in data

    @patch("api.routers.data.load_hist")
    @patch("api.routers.data.cache_json_get", return_value=None)
    @patch("api.routers.data.cache_json_set", return_value=True)
    def test_hist_with_date_range(self, mock_set, mock_get, mock_load) -> None:
        mock_load.return_value = self._make_sample_df()
        resp = client.get("/api/data/hist/510300?start=2024-03-01&end=2024-05-01&limit=50")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] <= 50


class TestFactorCompareEndpoint:
    def _make_sample_df(self, n: int = 150) -> pd.DataFrame:
        np.random.seed(42)
        dates = pd.bdate_range("2024-01-01", periods=n)
        close = 3.0 * np.cumprod(1 + np.random.normal(0.001, 0.02, n))
        return pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.random.randint(1_000_000, 10_000_000, n),
            },
            index=dates,
        )

    @patch("api.routers.factors.load_hist")
    def test_compare_momentum(self, mock_load) -> None:
        mock_load.return_value = self._make_sample_df()
        resp = client.post(
            "/api/factors/compare",
            json={"symbols": ["510300", "510500"], "category": "momentum"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "momentum"
        assert data["count"] == 2
        assert "factors" in data
        assert "data" in data

    @patch("api.routers.factors.load_hist")
    def test_compare_value(self, mock_load) -> None:
        mock_load.return_value = self._make_sample_df()
        resp = client.post(
            "/api/factors/compare",
            json={"symbols": ["510300"], "category": "value"},
        )
        assert resp.status_code == 200
        assert resp.json()["category"] == "value"

    @patch("api.routers.factors.load_hist")
    def test_compare_volatility(self, mock_load) -> None:
        mock_load.return_value = self._make_sample_df()
        resp = client.post(
            "/api/factors/compare",
            json={"symbols": ["510300"], "category": "volatility"},
        )
        assert resp.status_code == 200

    def test_compare_invalid_category(self) -> None:
        resp = client.post(
            "/api/factors/compare",
            json={"symbols": ["510300"], "category": "fake"},
        )
        assert resp.status_code == 400

    def test_compare_invalid_symbol(self) -> None:
        resp = client.post(
            "/api/factors/compare",
            json={"symbols": ["abc"], "category": "momentum"},
        )
        assert resp.status_code == 400

    @patch("api.routers.factors.load_hist", return_value=pd.DataFrame())
    def test_compare_missing_data(self, _m: object) -> None:
        resp = client.post(
            "/api/factors/compare",
            json={"symbols": ["999999"], "category": "momentum"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["missing"] == ["999999"]

    @patch("api.routers.factors.load_hist")
    @patch("api.routers.factors.cache_json_get", return_value=None)
    @patch("api.routers.factors.cache_json_set", return_value=True)
    def test_get_factors_no_data(self, mock_set, mock_get, mock_load) -> None:
        mock_load.return_value = pd.DataFrame()
        resp = client.get("/api/factors/999999")
        assert resp.status_code == 404

    def test_get_factors_invalid_symbol(self) -> None:
        resp = client.get("/api/factors/bad")
        assert resp.status_code == 400


class TestRecommendEndpoint:
    def _make_data_dict(self) -> dict[str, pd.DataFrame]:
        np.random.seed(42)
        data = {}
        for sym in ["510300", "518880", "511010", "512480", "513100"]:
            n = 200
            dates = pd.bdate_range("2024-01-01", periods=n)
            close = 3.0 * np.cumprod(1 + np.random.normal(0.001, 0.015, n))
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
        return data

    @patch("api.routers.recommend.load_hist")
    def test_proven_strategies(self, mock_load) -> None:
        test_data = self._make_data_dict()
        mock_load.side_effect = lambda sym, **kw: test_data.get(sym, pd.DataFrame())
        resp = client.post(
            "/api/recommend/proven",
            json={"capital": 500000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "capital" in data
        assert "strategies" in data
        assert "disclaimer" in data
        assert data["capital"] == 500000

    @patch("api.routers.recommend.load_hist")
    def test_proven_strategies_small_capital(self, mock_load) -> None:
        test_data = self._make_data_dict()
        mock_load.side_effect = lambda sym, **kw: test_data.get(sym, pd.DataFrame())
        resp = client.post(
            "/api/recommend/proven",
            json={"capital": 10000},
        )
        assert resp.status_code == 200

    @patch("api.routers.recommend.load_hist", return_value=pd.DataFrame())
    def test_proven_no_data(self, _m: object) -> None:
        # Clear the cache so mock takes effect
        from api.routers.recommend import _proven_cache

        _proven_cache.clear()

        resp = client.post(
            "/api/recommend/proven",
            json={"capital": 500000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategies"] == []


class TestBacktestEndpoints:
    def _make_data_dict(self) -> dict[str, pd.DataFrame]:
        np.random.seed(42)
        data = {}
        for sym in ["510300", "510500", "159915"]:
            n = 100
            dates = pd.bdate_range("2024-01-01", periods=n)
            close = 3.0 * np.cumprod(1 + np.random.normal(0.001, 0.02, n))
            df = pd.DataFrame(
                {
                    "open": close * 0.999,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": np.random.randint(1_000_000, 10_000_000, n),
                    "symbol": [sym] * n,
                },
                index=dates,
            )
            df.index.name = "date"
            data[sym] = df
        return data

    @patch("api.routers.backtest.load_hist")
    def test_rotation_backtest(self, mock_load):
        test_data = self._make_data_dict()
        mock_load.side_effect = lambda sym: test_data.get(sym, pd.DataFrame())

        resp = client.post(
            "/api/backtest/rotation",
            json={
                "symbols": ["510300", "510500", "159915"],
                "lookback": 20,
                "top_k": 2,
                "rebalance_days": 20,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        assert "equity_curve" in data
        assert "trades" in data
        assert data["metrics"]["total_trades"] >= 0

    @patch("api.routers.backtest.load_hist")
    def test_rotation_no_data(self, mock_load):
        mock_load.return_value = pd.DataFrame()
        resp = client.post(
            "/api/backtest/rotation",
            json={"symbols": ["999999"]},
        )
        assert resp.status_code == 404

    def test_rotation_invalid_symbol(self):
        resp = client.post(
            "/api/backtest/rotation",
            json={"symbols": ["abc"]},
        )
        assert resp.status_code == 400

    @patch("api.routers.backtest.load_hist")
    def test_balance_backtest(self, mock_load):
        test_data = self._make_data_dict()
        # Add bond-like data
        np.random.seed(99)
        n = 100
        dates = pd.bdate_range("2024-01-01", periods=n)
        bond_close = 100.0 * np.cumprod(1 + np.random.normal(0.0001, 0.002, n))
        test_data["511010"] = pd.DataFrame(
            {
                "open": bond_close * 0.999,
                "high": bond_close * 1.001,
                "low": bond_close * 0.999,
                "close": bond_close,
                "volume": np.random.randint(500_000, 5_000_000, n),
            },
            index=dates,
        )
        test_data["511010"].index.name = "date"
        mock_load.side_effect = lambda sym: test_data.get(sym, pd.DataFrame())

        resp = client.post(
            "/api/backtest/balance",
            json={"stock_symbol": "510300", "bond_symbol": "511010", "stock_weight": 0.6},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        assert data["metrics"]["total_trades"] >= 0

    @patch("api.routers.backtest.load_hist")
    def test_grid_backtest(self, mock_load):
        test_data = self._make_data_dict()
        mock_load.side_effect = lambda sym: test_data.get(sym, pd.DataFrame())

        resp = client.post(
            "/api/backtest/grid",
            json={"symbol": "510300", "grid_count": 5, "grid_width_pct": 0.02},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data

    @patch("api.routers.backtest.load_hist")
    def test_multifactor_backtest(self, mock_load):
        test_data = self._make_data_dict()
        mock_load.side_effect = lambda sym: test_data.get(sym, pd.DataFrame())

        resp = client.post(
            "/api/backtest/multifactor",
            json={
                "symbols": ["510300", "510500", "159915"],
                "lookback": 20,
                "top_k": 2,
                "momentum_weight": 0.5,
                "value_weight": 0.3,
                "volatility_weight": 0.2,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data

    def test_strategies_list(self):
        resp = client.get("/api/backtest/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4
        ids = {s["id"] for s in data}
        assert ids == {"rotation", "balance", "grid", "multifactor"}


class TestSectorEndpoints:
    @patch("api.routers.sector.analyze_all_sectors")
    def test_rotation(self, mock_analyze) -> None:
        from unittest.mock import MagicMock

        sector = MagicMock()
        sector.to_dict.return_value = {"sector": "科技", "phase": "复苏"}
        mock_analyze.return_value = [sector]
        resp = client.get("/api/sector/rotation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["sectors"][0]["sector"] == "科技"

    @patch("api.routers.sector.generate_portfolio_plan")
    def test_plan(self, mock_plan) -> None:
        mock_plan.return_value = {"positions": [], "total": 500000}
        resp = client.post(
            "/api/sector/plan",
            json={"capital": 500000, "risk_appetite": "aggressive"},
        )
        assert resp.status_code == 200

    def test_plan_invalid_risk_appetite(self) -> None:
        resp = client.post(
            "/api/sector/plan",
            json={"capital": 500000, "risk_appetite": "invalid_value"},
        )
        assert resp.status_code == 422  # Pydantic validation error


class TestAPIAuthentication:
    """Test that write endpoints require X-API-Key header."""

    def _request_without_override(self, method: str, url: str, **kwargs) -> object:
        """Send a request with the auth override temporarily removed."""
        saved = app.dependency_overrides.pop(require_api_key, None)
        try:
            c = TestClient(app)
            resp = getattr(c, method)(url, **kwargs)
        finally:
            if saved is not None:
                app.dependency_overrides[require_api_key] = saved
        return resp

    def test_portfolio_add_requires_auth(self) -> None:
        """POST /api/portfolio/add without key → 422 (missing header)."""
        resp = self._request_without_override(
            "post",
            "/api/portfolio/add",
            json={"symbol": "510300", "buy_price": 4.0, "shares": 100},
        )
        assert resp.status_code == 422

    def test_portfolio_add_wrong_key(self) -> None:
        """POST /api/portfolio/add with wrong key → 401 or 503."""
        resp = self._request_without_override(
            "post",
            "/api/portfolio/add",
            json={"symbol": "510300", "buy_price": 4.0, "shares": 100},
            headers={"X-API-Key": "wrong-key"},
        )
        # 503 when default key not configured
        assert resp.status_code in (401, 503)

    def test_read_endpoints_no_auth_needed(self) -> None:
        """GET endpoints should work without any auth."""
        resp = client.get("/health")
        assert resp.status_code == 200
        resp = client.get("/etf/list")
        assert resp.status_code == 200

    def test_wrong_key_returns_401(self) -> None:
        """When API_SECRET_KEY is configured, wrong key → 401."""
        resp = self._request_without_override(
            "post",
            "/api/portfolio/add",
            json={"symbol": "510300", "buy_price": 4.0, "shares": 100},
            headers={"X-API-Key": "definitely-wrong-key"},
        )
        # 401 when key doesn't match configured value
        assert resp.status_code == 401

    def test_signals_record_requires_auth(self) -> None:
        """POST /api/signals/record without key → 422."""
        resp = self._request_without_override("post", "/api/signals/record")
        assert resp.status_code == 422


class TestRequireApiKeyDep:
    """Unit tests for the require_api_key dependency function."""

    def _mock_settings(self, secret_key: str):
        """Mock the settings object used by api.deps with a given secret_key."""
        from unittest.mock import MagicMock

        mock_api = MagicMock()
        mock_api.secret_key = secret_key
        mock_settings = MagicMock()
        mock_settings.api = mock_api
        return patch("api.deps.settings", mock_settings)

    def test_default_key_raises_503(self) -> None:
        """When secret key is still the default, should raise 503."""
        import pytest
        from fastapi import HTTPException as FastHTTPExc

        from api.deps import require_api_key as dep
        from config.settings import DEFAULT_API_SECRET_KEY

        with self._mock_settings(DEFAULT_API_SECRET_KEY), pytest.raises(FastHTTPExc) as exc:
            dep(x_api_key="anything")
        assert exc.value.status_code == 503

    def test_wrong_key_raises_401(self) -> None:
        import pytest
        from fastapi import HTTPException as FastHTTPExc

        from api.deps import require_api_key as dep

        with self._mock_settings("my-secret"), pytest.raises(FastHTTPExc) as exc:
            dep(x_api_key="wrong")
        assert exc.value.status_code == 401

    def test_correct_key_passes(self) -> None:
        from api.deps import require_api_key as dep

        with self._mock_settings("my-secret"):
            result = dep(x_api_key="my-secret")
            assert result == "my-secret"
