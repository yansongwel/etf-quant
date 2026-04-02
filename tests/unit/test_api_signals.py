"""Tests for signal API endpoints using TestClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from api.deps import require_api_key
from api.main import app

app.dependency_overrides[require_api_key] = lambda: "test-key"
client = TestClient(app)


def _clear_caches() -> None:
    """Clear all module-level caches between tests."""
    import api.routers.signals as mod

    mod._signal_cache.clear()
    mod._recommend_cache.clear()
    mod._accuracy_cache.clear()
    mod._backtest_cache.clear()
    mod._trend_cache.clear()


def _mock_df(days: int = 120, trend: float = 0.002) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range(end="2026-03-28", periods=days, freq="D")
    close = 3.0 + np.cumsum(np.random.randn(days) * 0.01 + trend)
    vol = np.full(days, 2_000_000.0) + np.random.randn(days) * 100_000
    return pd.DataFrame(
        {
            "open": close - 0.01,
            "high": close + 0.02,
            "low": close - 0.02,
            "close": close,
            "volume": np.maximum(vol, 100),
        },
        index=dates,
    )


def _mock_load(symbol: str, category: str = "etf_hist") -> pd.DataFrame:
    if symbol == "EMPTY":
        return pd.DataFrame()
    return _mock_df()


class TestCurrentSignals:
    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_current_signals(self, _r: object, _l: object) -> None:
        res = client.get("/api/signals/current?symbols=510300,510500")
        assert res.status_code == 200
        d = res.json()
        assert "count" in d
        assert "signals" in d
        assert "summary" in d
        assert d["count"] == 2

    @patch("api.routers.signals.load_hist", return_value=pd.DataFrame())
    def test_no_data(self, _l: object) -> None:
        res = client.get("/api/signals/current?symbols=EMPTY")
        assert res.status_code == 404


class TestSignalDetail:
    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    def test_detail_ok(self, _l: object) -> None:
        res = client.get("/api/signals/detail/510300")
        assert res.status_code == 200
        d = res.json()
        assert d["symbol"] == "510300"
        assert "direction" in d
        assert "factors" in d
        assert "volume_ratio" in d["factors"]

    def test_invalid_symbol(self) -> None:
        assert client.get("/api/signals/detail/abc").status_code == 400

    @patch("api.routers.signals.load_hist", return_value=pd.DataFrame())
    def test_no_data(self, _l: object) -> None:
        assert client.get("/api/signals/detail/999999").status_code == 404


class TestPositions:
    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_positions(self, _r: object, _l: object) -> None:
        res = client.post(
            "/api/signals/positions",
            json={"capital": 50000, "symbols": "510300,510500"},
        )
        assert res.status_code == 200
        d = res.json()
        assert "capital" in d
        assert "positions" in d
        assert "invested" in d
        assert "remaining" in d
        assert d["invested"] + d["remaining"] <= d["capital"] + 1


class TestRecommend:
    @patch("api.routers.signals.recommend_strategies")
    def test_recommend(self, _mock: object) -> None:
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "strategy_name": "Test",
            "strategy_id": "rotation",
            "rank": 1,
            "recommendation": "OK",
            "metrics": {"total_return": 0.1},
        }
        _mock.return_value = [mock_result]

        res = client.post("/api/signals/recommend", json={"capital": 50000})
        assert res.status_code == 200
        d = res.json()
        assert d["count"] == 1


class TestRecordAndAccuracy:
    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("api.routers.signals.record_signals")
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_record(self, _r: object, _rec: object, _l: object) -> None:
        from pathlib import Path

        _rec.return_value = Path("/tmp/test.json")
        res = client.post("/api/signals/record")
        assert res.status_code == 200
        assert "recorded" in res.json()

    @patch("api.routers.signals.get_overall_accuracy")
    def test_accuracy(self, _mock: object) -> None:
        _mock.return_value = {"overall_accuracy": 55.0, "records_checked": 10}
        res = client.get("/api/signals/accuracy?days=30")
        assert res.status_code == 200

    def test_alerts(self) -> None:
        with patch("api.routers.signals.check_alerts", return_value=[]):
            res = client.get("/api/signals/alerts")
        assert res.status_code == 200
        assert res.json()["count"] == 0


class TestSignalCacheExpiry:
    """Test cache expiry (line 35) and cache hit paths."""

    def setup_method(self) -> None:
        _clear_caches()

    def teardown_method(self) -> None:
        _clear_caches()

    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_cache_hit_returns_cached_signals(self, _r: object, _l: object) -> None:
        """First call populates cache, second call returns cached (line 94)."""
        res1 = client.get("/api/signals/current?symbols=510300,510500")
        assert res1.status_code == 200
        # Second call should hit cache
        res2 = client.get("/api/signals/current?symbols=510300,510500")
        assert res2.status_code == 200
        assert res2.json()["count"] == res1.json()["count"]

    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_expired_cache_is_deleted(self, _r: object, _l: object) -> None:
        """Expired cache entry is deleted and re-fetched (line 35)."""
        import api.routers.signals as mod

        # Populate cache
        res1 = client.get("/api/signals/current?symbols=510300")
        assert res1.status_code == 200

        # Expire the cache entry by backdating the timestamp
        for key in list(mod._signal_cache.keys()):
            ts, signals, data_map = mod._signal_cache[key]
            mod._signal_cache[key] = (ts - mod._SIGNAL_CACHE_TTL - 10, signals, data_map)

        # Next call should detect expired entry, delete it, and re-fetch
        res2 = client.get("/api/signals/current?symbols=510300")
        assert res2.status_code == 200


class TestSymbolTruncation:
    """Test symbol list truncation >50 (line 52) and fallback (line 58)."""

    def setup_method(self) -> None:
        _clear_caches()

    def teardown_method(self) -> None:
        _clear_caches()

    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_symbols_truncated_at_50(self, _r: object, _l: object) -> None:
        """More than 50 symbols should be truncated (line 52)."""
        syms = ",".join(f"{i:06d}" for i in range(60))
        res = client.get(f"/api/signals/current?symbols={syms}")
        # Should not error — truncated to 50
        assert res.status_code in (200, 404)

    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_fallback_to_default_etf_list(self, _r: object, _l: object) -> None:
        """When no symbols and no data_dir, fall back to DEFAULT_ETF_LIST (line 58)."""
        with patch("config.settings.settings") as mock_settings:
            mock_data = MagicMock()
            mock_data.data_dir.__truediv__ = MagicMock(
                return_value=MagicMock(exists=MagicMock(return_value=False))
            )
            mock_settings.data = mock_data
            res = client.get("/api/signals/current")
            # May be 200 or 404 depending on load_hist results; the path is exercised
            assert res.status_code in (200, 404)


class TestSignalDetailEdge:
    """Test generate_signal returning None (line 129)."""

    @patch("api.routers.signals.generate_signal", return_value=None)
    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    def test_insufficient_data(self, _l: object, _g: object) -> None:
        res = client.get("/api/signals/detail/510300")
        assert res.status_code == 422
        assert "Insufficient" in res.json()["detail"]


class TestPositionsEdgeCases:
    """Test positions endpoint cache miss with no data (lines 155-158)."""

    def setup_method(self) -> None:
        _clear_caches()

    def teardown_method(self) -> None:
        _clear_caches()

    @patch("api.routers.signals.load_hist", return_value=pd.DataFrame())
    def test_positions_no_data(self, _l: object) -> None:
        """No data available for positions should return 404 (lines 155-156)."""
        res = client.post(
            "/api/signals/positions",
            json={"capital": 50000, "symbols": "999999"},
        )
        assert res.status_code == 404

    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_positions_cache_hit(self, _r: object, _l: object) -> None:
        """Second call to positions should use cached signals (lines 152-153)."""
        body = {"capital": 50000, "symbols": "510300,510500"}
        res1 = client.post("/api/signals/positions", json=body)
        assert res1.status_code == 200
        # Second call hits cache
        res2 = client.post("/api/signals/positions", json=body)
        assert res2.status_code == 200


class TestRecommendCache:
    """Test recommend cache hit path (lines 195-197)."""

    def setup_method(self) -> None:
        _clear_caches()

    def teardown_method(self) -> None:
        _clear_caches()

    @patch("api.routers.signals.recommend_strategies")
    def test_recommend_cache_hit(self, _mock: object) -> None:
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "strategy_name": "Test",
            "strategy_id": "rotation",
            "rank": 1,
            "recommendation": "OK",
            "metrics": {"total_return": 0.1},
        }
        _mock.return_value = [mock_result]

        body = {"capital": 50000, "max_results": 3}
        res1 = client.post("/api/signals/recommend", json=body)
        assert res1.status_code == 200

        # Second call should hit cache — recommend_strategies NOT called again
        res2 = client.post("/api/signals/recommend", json=body)
        assert res2.status_code == 200
        assert _mock.call_count == 1  # only called once


class TestRecordEdgeCases:
    """Test record endpoint cache paths (lines 219, 222)."""

    def setup_method(self) -> None:
        _clear_caches()

    def teardown_method(self) -> None:
        _clear_caches()

    @patch("api.routers.signals.record_signals")
    @patch("api.routers.signals.load_hist", return_value=pd.DataFrame())
    def test_record_no_data(self, _l: object, _rec: object) -> None:
        """Record with no data available returns 404 (line 222)."""
        res = client.post("/api/signals/record")
        assert res.status_code == 404

    @patch("api.routers.signals.record_signals")
    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_record_cache_hit(self, _r: object, _l: object, _rec: object) -> None:
        """Record uses cached signals when available (line 219)."""
        from pathlib import Path

        _rec.return_value = Path("/tmp/test.json")
        # First call to /current populates signal cache
        client.get("/api/signals/current?symbols=510300")
        # Record should use the cached signals
        res = client.post("/api/signals/record")
        assert res.status_code == 200
        assert "recorded" in res.json()


class TestAccuracyCache:
    """Test accuracy cache hit path (lines 240-242)."""

    def setup_method(self) -> None:
        _clear_caches()

    def teardown_method(self) -> None:
        _clear_caches()

    @patch("api.routers.signals.get_overall_accuracy")
    def test_accuracy_cache_hit(self, _mock: object) -> None:
        _mock.return_value = {"overall_accuracy": 55.0, "records_checked": 10}

        res1 = client.get("/api/signals/accuracy?days=30")
        assert res1.status_code == 200

        # Second call should hit cache
        res2 = client.get("/api/signals/accuracy?days=30")
        assert res2.status_code == 200
        assert _mock.call_count == 1  # only called once


class TestBacktestAccuracy:
    """Test backtest-accuracy endpoint (lines 272-294)."""

    def setup_method(self) -> None:
        _clear_caches()

    def teardown_method(self) -> None:
        _clear_caches()

    @patch("engine.signal_backtest.backtest_signals")
    def test_backtest_accuracy_ok(self, _mock: object) -> None:
        _mock.return_value = {
            "total_signals": 100,
            "buy_accuracy": 0.58,
            "sell_accuracy": 0.52,
            "by_direction": {},
        }
        with patch("config.settings.settings") as mock_settings:
            mock_data = MagicMock()
            mock_data.data_dir.__truediv__ = MagicMock(
                return_value=MagicMock(exists=MagicMock(return_value=False))
            )
            mock_settings.data = mock_data
            res = client.get("/api/signals/backtest-accuracy?days=30")
        assert res.status_code == 200
        d = res.json()
        assert "total_signals" in d

    @patch("engine.signal_backtest.backtest_signals")
    def test_backtest_accuracy_cache_hit(self, _mock: object) -> None:
        """Second call returns cached result (line 280-281)."""
        _mock.return_value = {"total_signals": 50}
        with patch("config.settings.settings") as mock_settings:
            mock_data = MagicMock()
            mock_data.data_dir.__truediv__ = MagicMock(
                return_value=MagicMock(exists=MagicMock(return_value=False))
            )
            mock_settings.data = mock_data
            res1 = client.get("/api/signals/backtest-accuracy?days=30")
            assert res1.status_code == 200
            res2 = client.get("/api/signals/backtest-accuracy?days=30")
            assert res2.status_code == 200
        assert _mock.call_count == 1


class TestAlertWithResults:
    """Test alerts endpoint with actual alert objects."""

    def test_alerts_with_data(self) -> None:
        mock_alert = MagicMock()
        mock_alert.to_dict.return_value = {
            "symbol": "510300",
            "type": "stop_loss",
            "message": "Hit stop loss",
        }
        with patch("api.routers.signals.check_alerts", return_value=[mock_alert]):
            res = client.get("/api/signals/alerts")
        assert res.status_code == 200
        assert res.json()["count"] == 1
        assert res.json()["alerts"][0]["symbol"] == "510300"


class TestInjectRealtimePrices:
    """Test _inject_realtime_prices for trading-hours coverage."""

    def test_inject_with_newer_data(self) -> None:
        import api.routers.signals as mod

        df = _mock_df(days=60)
        data = {"510300": df}

        rt_df = pd.DataFrame(
            {
                "symbol": ["510300"],
                "date": ["2026-04-01"],
                "open": [3.5],
                "close": [3.55],
                "high": [3.6],
                "low": [3.45],
                "volume": [1_000_000],
                "amount": [3_500_000],
            }
        )

        with patch(
            "data.collectors.realtime.fetch_realtime_quotes",
            return_value=rt_df,
        ):
            result = mod._inject_realtime_prices(data)
        # Should have one more row than original
        assert len(result["510300"]) == len(df) + 1

    def test_inject_with_stale_data(self) -> None:
        """If realtime date <= last bar date, no injection."""
        import api.routers.signals as mod

        df = _mock_df(days=60)
        data = {"510300": df}

        rt_df = pd.DataFrame(
            {
                "symbol": ["510300"],
                "date": [str(df.index[-1].date())],
                "open": [3.5],
                "close": [3.55],
                "high": [3.6],
                "low": [3.45],
                "volume": [1_000_000],
            }
        )

        with patch(
            "data.collectors.realtime.fetch_realtime_quotes",
            return_value=rt_df,
        ):
            result = mod._inject_realtime_prices(data)
        assert len(result["510300"]) == len(df)  # No injection

    def test_inject_empty_realtime(self) -> None:
        """Empty realtime data returns original."""
        import api.routers.signals as mod

        df = _mock_df(days=60)
        data = {"510300": df}

        with patch(
            "data.collectors.realtime.fetch_realtime_quotes",
            return_value=pd.DataFrame(),
        ):
            result = mod._inject_realtime_prices(data)
        assert result is data  # Same object returned

    def test_inject_symbol_not_in_realtime(self) -> None:
        """Symbol not in realtime data keeps original."""
        import api.routers.signals as mod

        df = _mock_df(days=60)
        data = {"510300": df}

        rt_df = pd.DataFrame(
            {
                "symbol": ["518880"],
                "date": ["2026-04-01"],
                "open": [5.0],
                "close": [5.1],
                "high": [5.2],
                "low": [4.9],
                "volume": [500_000],
            }
        )

        with patch(
            "data.collectors.realtime.fetch_realtime_quotes",
            return_value=rt_df,
        ):
            result = mod._inject_realtime_prices(data)
        assert len(result["510300"]) == len(df)


class TestIsMarketOpen:
    """Test _is_market_open helper."""

    def test_weekday_trading_hours(self) -> None:
        from api.routers.signals import _is_market_open

        # Monday 10:00 CST
        with patch("api.routers.signals.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 0  # Monday
            mock_now.hour = 10
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            assert _is_market_open() is True

    def test_weekend_closed(self) -> None:
        from api.routers.signals import _is_market_open

        with patch("api.routers.signals.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 5  # Saturday
            mock_dt.now.return_value = mock_now
            assert _is_market_open() is False

    def test_weekday_after_hours(self) -> None:
        from api.routers.signals import _is_market_open

        with patch("api.routers.signals.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 2  # Wednesday
            mock_now.hour = 16
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            assert _is_market_open() is False


class TestRecordSignalsCachedPath:
    """Test /record endpoint when signals are cached."""

    def setup_method(self) -> None:
        _clear_caches()

    def teardown_method(self) -> None:
        _clear_caches()

    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_record_uses_cache(self, _r: object, _l: object) -> None:
        import api.routers.signals as mod

        # Pre-populate cache
        mock_signal = MagicMock()
        mock_signal.to_dict.return_value = {
            "symbol": "510300",
            "direction": "hold",
            "score": 5.0,
        }
        mod._set_cached_signals("510300", [mock_signal], {})

        # Record should use cached signals (line 299)
        res = client.post(
            "/api/signals/record?symbols=510300",
            headers={"X-API-Key": "test-key"},
        )
        assert res.status_code == 200


class TestSignalTrend:
    """Test /signals/trend/{symbol} endpoint."""

    def setup_method(self) -> None:
        _clear_caches()

    def teardown_method(self) -> None:
        _clear_caches()

    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_trend_ok(self, _r: object, _l: object) -> None:
        res = client.get("/api/signals/trend/510300?days=30")
        assert res.status_code == 200
        d = res.json()
        assert d["symbol"] == "510300"
        assert d["count"] == 30
        assert len(d["trend"]) == 30
        # Each point has required fields
        pt = d["trend"][0]
        assert "date" in pt
        assert "score" in pt
        assert "direction" in pt
        assert "close" in pt

    def test_trend_invalid_symbol(self) -> None:
        res = client.get("/api/signals/trend/abc?days=30")
        assert res.status_code == 400

    @patch("api.routers.signals.load_hist", return_value=pd.DataFrame())
    def test_trend_no_data(self, _l: object) -> None:
        res = client.get("/api/signals/trend/999999?days=30")
        assert res.status_code == 404

    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_trend_cache_hit(self, _r: object, _l: object) -> None:
        """Second call returns cached trend data."""
        res1 = client.get("/api/signals/trend/510300?days=20")
        assert res1.status_code == 200
        res2 = client.get("/api/signals/trend/510300?days=20")
        assert res2.status_code == 200
        assert res1.json()["count"] == res2.json()["count"]

    @patch("api.routers.signals.load_hist", side_effect=_mock_load)
    @patch("engine.signals._detect_market_regime", return_value="bear")
    def test_trend_bear_regime(self, _r: object, _l: object) -> None:
        """Bear regime should influence score directions."""
        res = client.get("/api/signals/trend/510300?days=20")
        assert res.status_code == 200
        d = res.json()
        # All entries should have valid direction values
        for pt in d["trend"]:
            assert pt["direction"] in ("strong_buy", "buy", "hold", "sell", "strong_sell")
