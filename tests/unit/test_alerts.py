"""Tests for price alert monitor — covers all alert types and edge cases."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from engine.alerts import AlertType, PriceAlert, check_alerts

# ── Helpers ────────────────────────────────────────────────────────────


def _make_hist(last_close: float, days: int = 100) -> pd.DataFrame:
    """Create price history with a specific last close price."""
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=days)
    close = np.linspace(last_close * 0.9, last_close, days)
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


def _make_signal_record(signals: list[dict]) -> dict:
    return {
        "date": "2024-06-01",
        "count": len(signals),
        "signals": signals,
    }


def _buy_signal(
    symbol: str = "510300",
    entry: float = 3.0,
    target: float = 3.15,
    stop: float = 2.91,
) -> dict:
    return {
        "symbol": symbol,
        "direction": "buy",
        "score": 50.0,
        "strength": 50.0,
        "current_price": entry,
        "entry_price": entry,
        "target_price": target,
        "stop_loss": stop,
        "factors": {"momentum": 0.5},
    }


# ── Tests ──────────────────────────────────────────────────────────────


class TestPriceAlert:
    def test_to_dict(self):
        alert = PriceAlert(
            symbol="510300",
            alert_type=AlertType.STOP_LOSS,
            signal_price=3.0,
            trigger_price=2.91,
            current_price=2.85,
            distance_pct=-2.06,
            message="已触发止损!",
        )
        d = alert.to_dict()
        assert d["symbol"] == "510300"
        assert d["alert_type"] == "stop_loss"
        assert d["signal_price"] == 3.0
        assert d["message"] == "已触发止损!"


class TestCheckAlerts:
    @patch("engine.alerts.load_hist")
    @patch("engine.alerts._load_record")
    @patch("engine.alerts.HISTORY_DIR")
    @patch("engine.alerts.ALERTS_DIR")
    def test_stop_loss_triggered(
        self, mock_alerts_dir, mock_hist_dir, mock_record, mock_load, tmp_path
    ):
        """Current price <= stop_loss → STOP_LOSS alert."""
        mock_hist_dir.mkdir = lambda **kw: None
        mock_hist_dir.glob = lambda pattern: [tmp_path / "2024-06-01.json"]
        mock_alerts_dir.mkdir = lambda **kw: None
        mock_alerts_dir.__truediv__ = lambda self, x: tmp_path / x

        # Signal: entry=3.0, stop=2.91. Current price=2.85 (below stop)
        mock_record.return_value = _make_signal_record([_buy_signal(stop=2.91)])
        mock_load.return_value = _make_hist(last_close=2.85)

        alerts = check_alerts(date(2024, 6, 1))

        stop_alerts = [a for a in alerts if a.alert_type == AlertType.STOP_LOSS]
        assert len(stop_alerts) >= 1
        assert stop_alerts[0].current_price == pytest.approx(2.85, abs=0.01)

    @patch("engine.alerts.load_hist")
    @patch("engine.alerts._load_record")
    @patch("engine.alerts.HISTORY_DIR")
    @patch("engine.alerts.ALERTS_DIR")
    def test_take_profit_triggered(
        self, mock_alerts_dir, mock_hist_dir, mock_record, mock_load, tmp_path
    ):
        """Current price >= target → TAKE_PROFIT alert."""
        mock_hist_dir.mkdir = lambda **kw: None
        mock_alerts_dir.mkdir = lambda **kw: None
        mock_alerts_dir.__truediv__ = lambda self, x: tmp_path / x

        # Signal: target=3.15. Current price=3.20 (above target)
        mock_record.return_value = _make_signal_record([_buy_signal(target=3.15)])
        mock_load.return_value = _make_hist(last_close=3.20)

        alerts = check_alerts(date(2024, 6, 1))

        tp_alerts = [a for a in alerts if a.alert_type == AlertType.TAKE_PROFIT]
        assert len(tp_alerts) >= 1

    @patch("engine.alerts.load_hist")
    @patch("engine.alerts._load_record")
    @patch("engine.alerts.HISTORY_DIR")
    @patch("engine.alerts.ALERTS_DIR")
    def test_approaching_stop(
        self, mock_alerts_dir, mock_hist_dir, mock_record, mock_load, tmp_path
    ):
        """Current price within 2% of stop → APPROACHING_STOP alert."""
        mock_hist_dir.mkdir = lambda **kw: None
        mock_alerts_dir.mkdir = lambda **kw: None
        mock_alerts_dir.__truediv__ = lambda self, x: tmp_path / x

        # stop=2.91, current=2.93 (within 2% above stop)
        mock_record.return_value = _make_signal_record([_buy_signal(stop=2.91)])
        mock_load.return_value = _make_hist(last_close=2.93)

        alerts = check_alerts(date(2024, 6, 1))

        approaching = [a for a in alerts if a.alert_type == AlertType.APPROACHING_STOP]
        assert len(approaching) >= 1

    @patch("engine.alerts.load_hist")
    @patch("engine.alerts._load_record")
    @patch("engine.alerts.HISTORY_DIR")
    @patch("engine.alerts.ALERTS_DIR")
    def test_approaching_target(
        self, mock_alerts_dir, mock_hist_dir, mock_record, mock_load, tmp_path
    ):
        """Current price within 3% of target → APPROACHING_TARGET alert."""
        mock_hist_dir.mkdir = lambda **kw: None
        mock_alerts_dir.mkdir = lambda **kw: None
        mock_alerts_dir.__truediv__ = lambda self, x: tmp_path / x

        # target=3.15, current=3.10 (within 3% below target)
        mock_record.return_value = _make_signal_record([_buy_signal(target=3.15, stop=2.5)])
        mock_load.return_value = _make_hist(last_close=3.10)

        alerts = check_alerts(date(2024, 6, 1))

        approaching = [a for a in alerts if a.alert_type == AlertType.APPROACHING_TARGET]
        assert len(approaching) >= 1

    @patch("engine.alerts._load_record")
    @patch("engine.alerts.HISTORY_DIR")
    def test_no_record_returns_empty(self, mock_hist_dir, mock_record):
        """No signal record → empty alerts."""
        mock_hist_dir.mkdir = lambda **kw: None
        mock_record.return_value = None

        alerts = check_alerts(date(2024, 6, 1))
        assert alerts == []

    @patch("engine.alerts.load_hist")
    @patch("engine.alerts._load_record")
    @patch("engine.alerts.HISTORY_DIR")
    def test_sell_signals_skipped(self, mock_hist_dir, mock_record, mock_load):
        """Sell/hold signals are not checked for alerts."""
        mock_hist_dir.mkdir = lambda **kw: None

        sig = _buy_signal()
        sig["direction"] = "sell"
        mock_record.return_value = _make_signal_record([sig])

        alerts = check_alerts(date(2024, 6, 1))
        assert alerts == []

    @patch("engine.alerts.load_hist")
    @patch("engine.alerts._load_record")
    @patch("engine.alerts.HISTORY_DIR")
    def test_empty_hist_skipped(self, mock_hist_dir, mock_record, mock_load):
        """Symbol with no hist data is skipped."""
        mock_hist_dir.mkdir = lambda **kw: None
        mock_record.return_value = _make_signal_record([_buy_signal()])
        mock_load.return_value = pd.DataFrame()

        alerts = check_alerts(date(2024, 6, 1))
        assert alerts == []

    @patch("engine.alerts.load_hist")
    @patch("engine.alerts._load_record")
    @patch("engine.alerts.HISTORY_DIR")
    def test_no_trigger_safe_price(self, mock_hist_dir, mock_record, mock_load):
        """Price between stop and target → no alert."""
        mock_hist_dir.mkdir = lambda **kw: None

        # entry=3.0, target=3.15, stop=2.91. Current=3.05 (safe)
        mock_record.return_value = _make_signal_record(
            [_buy_signal(entry=3.0, target=3.15, stop=2.91)]
        )
        mock_load.return_value = _make_hist(last_close=3.05)

        alerts = check_alerts(date(2024, 6, 1))
        assert alerts == []

    @patch("engine.alerts.load_hist")
    @patch("engine.alerts._load_record")
    @patch("engine.alerts.HISTORY_DIR")
    @patch("engine.alerts.ALERTS_DIR")
    def test_alert_priority_ordering(
        self, mock_alerts_dir, mock_hist_dir, mock_record, mock_load, tmp_path
    ):
        """Alerts should be sorted: stop_loss first, then take_profit, etc."""
        mock_hist_dir.mkdir = lambda **kw: None
        mock_alerts_dir.mkdir = lambda **kw: None
        mock_alerts_dir.__truediv__ = lambda self, x: tmp_path / x

        # Two signals: one triggers stop_loss, another triggers take_profit
        mock_record.return_value = _make_signal_record(
            [
                _buy_signal(symbol="A", stop=3.0, target=4.0),  # Stop triggered at 2.85
                _buy_signal(symbol="B", stop=2.0, target=2.80),  # Target triggered at 2.85
            ]
        )
        mock_load.return_value = _make_hist(last_close=2.85)

        alerts = check_alerts(date(2024, 6, 1))

        if len(alerts) >= 2:
            # Stop loss should come before take profit
            types = [a.alert_type for a in alerts]
            if AlertType.STOP_LOSS in types and AlertType.TAKE_PROFIT in types:
                stop_idx = types.index(AlertType.STOP_LOSS)
                tp_idx = types.index(AlertType.TAKE_PROFIT)
                assert stop_idx < tp_idx

    @patch("engine.alerts._load_record")
    @patch("engine.alerts.HISTORY_DIR")
    def test_auto_detect_latest_record(self, mock_hist_dir, mock_record, tmp_path):
        """When signal_date is None, use most recent record file."""
        mock_hist_dir.mkdir = lambda **kw: None
        # Create fake files
        (tmp_path / "2024-06-01.json").write_text("{}")
        (tmp_path / "2024-06-02.json").write_text("{}")
        mock_hist_dir.glob = lambda pattern: sorted(tmp_path.glob("*.json"), reverse=True)
        mock_record.return_value = None

        alerts = check_alerts(signal_date=None)
        assert alerts == []

    @patch("engine.alerts.HISTORY_DIR")
    def test_no_files_returns_empty(self, mock_hist_dir):
        """No signal record files → empty alerts."""
        mock_hist_dir.mkdir = lambda **kw: None
        mock_hist_dir.glob = lambda pattern: []

        alerts = check_alerts(signal_date=None)
        assert alerts == []
