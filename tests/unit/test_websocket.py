"""Tests for WebSocket real-time market data endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestIsMarketOpen:
    """Test _is_market_open helper."""

    def test_weekday_trading(self) -> None:
        from api.routers.websocket import _is_market_open

        with patch("api.routers.websocket.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 1  # Tuesday
            mock_now.hour = 10
            mock_now.minute = 30
            mock_dt.now.return_value = mock_now
            assert _is_market_open() is True

    def test_weekday_before_open(self) -> None:
        from api.routers.websocket import _is_market_open

        with patch("api.routers.websocket.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 1
            mock_now.hour = 9
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            assert _is_market_open() is False

    def test_weekday_after_close(self) -> None:
        from api.routers.websocket import _is_market_open

        with patch("api.routers.websocket.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 3  # Thursday
            mock_now.hour = 16
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            assert _is_market_open() is False

    def test_weekend_closed(self) -> None:
        from api.routers.websocket import _is_market_open

        with patch("api.routers.websocket.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 6  # Sunday
            mock_dt.now.return_value = mock_now
            assert _is_market_open() is False

    def test_lunch_break_still_open(self) -> None:
        """Lunch break (11:30-13:00) should still count as open."""
        from api.routers.websocket import _is_market_open

        with patch("api.routers.websocket.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 2  # Wednesday
            mock_now.hour = 12
            mock_now.minute = 0
            mock_dt.now.return_value = mock_now
            assert _is_market_open() is True


class TestGetRealtimeSnapshot:
    """Test _get_realtime_snapshot helper."""

    @patch("data.collectors.realtime.fetch_realtime_quotes")
    def test_returns_quotes(self, mock_fetch: MagicMock) -> None:
        from api.routers.websocket import _get_realtime_snapshot

        mock_fetch.return_value = pd.DataFrame(
            {
                "symbol": ["510300", "510500"],
                "close": [4.5, 7.8],
                "pct_change": [1.5, -0.8],
            }
        )

        result = _get_realtime_snapshot()
        assert result["type"] == "market_update"
        assert "quotes" in result
        assert len(result["quotes"]) == 2
        assert "timestamp" in result
        assert "signal_summary" in result

    @patch("data.collectors.realtime.fetch_realtime_quotes")
    def test_empty_quotes_returns_error(self, mock_fetch: MagicMock) -> None:
        from api.routers.websocket import _get_realtime_snapshot

        mock_fetch.return_value = pd.DataFrame()
        result = _get_realtime_snapshot()
        assert result["type"] == "error"

    @patch("data.collectors.realtime.fetch_realtime_quotes")
    def test_quotes_sorted_by_abs_change(self, mock_fetch: MagicMock) -> None:
        from api.routers.websocket import _get_realtime_snapshot

        mock_fetch.return_value = pd.DataFrame(
            {
                "symbol": ["A", "B", "C"],
                "close": [1.0, 2.0, 3.0],
                "pct_change": [0.5, -3.0, 1.5],
            }
        )
        result = _get_realtime_snapshot()
        changes = [abs(q["change_pct"]) for q in result["quotes"]]
        assert changes == sorted(changes, reverse=True)

    @patch("data.collectors.realtime.fetch_realtime_quotes")
    def test_signal_summary_included(self, mock_fetch: MagicMock) -> None:
        from api.routers.websocket import _get_realtime_snapshot

        mock_fetch.return_value = pd.DataFrame(
            {"symbol": ["510300"], "close": [4.5], "pct_change": [1.0]}
        )
        result = _get_realtime_snapshot()
        summary = result["signal_summary"]
        assert "buy" in summary
        assert "hold" in summary
        assert "sell" in summary


class TestWebSocketEndpoint:
    """Test the WebSocket connection lifecycle."""

    @patch("api.routers.websocket._get_realtime_snapshot")
    @patch("api.routers.websocket._is_market_open", return_value=False)
    def test_connect_receive_disconnect(
        self, _mock_market: MagicMock, mock_snapshot: MagicMock
    ) -> None:
        """Client should connect, receive one message, then disconnect."""
        mock_snapshot.return_value = {
            "type": "market_update",
            "market_open": False,
            "timestamp": "2026-04-01 16:00:00",
            "quotes": [],
            "signal_summary": {"buy": 0, "hold": 0, "sell": 0},
        }

        with client.websocket_connect("/ws/market") as ws:
            data = ws.receive_json()
            assert data["type"] == "market_update"
            assert data["market_open"] is False

    @patch("api.routers.websocket._get_realtime_snapshot")
    @patch("api.routers.websocket._is_market_open", return_value=False)
    def test_error_during_snapshot(self, _mock_market: MagicMock, mock_snapshot: MagicMock) -> None:
        """If snapshot fails, should send error message instead of crashing."""
        mock_snapshot.side_effect = Exception("Network error")

        with client.websocket_connect("/ws/market") as ws:
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "Network error" in data["message"]
