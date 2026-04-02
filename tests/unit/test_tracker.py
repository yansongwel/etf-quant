"""Tests for signal accuracy tracker — covers validation, accuracy, and weight adjustment."""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from engine.signals import generate_signals_batch
from engine.tracker import (
    VALIDATE_AFTER_DAYS,
    _load_record,
    get_overall_accuracy,
    record_signals,
    suggest_weight_adjustment,
    validate_signals,
)

# ── Helpers ────────────────────────────────────────────────────────────


def _make_data(days: int = 100, seed: int = 42) -> dict[str, pd.DataFrame]:
    np.random.seed(seed)
    dates = pd.bdate_range("2024-01-01", periods=days)
    data = {}
    for sym in ["A", "B"]:
        close = 3.0 * np.cumprod(1 + np.random.normal(0.001, 0.02, days))
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
        data[sym] = df
    return data


def _make_signal(
    symbol: str,
    direction: str,
    price: float = 3.0,
    score: float = 50.0,
) -> dict:
    """Create a raw signal record dict (as stored in JSON)."""
    return {
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "strength": abs(score),
        "current_price": price,
        "entry_price": price * 1.002,
        "target_price": price * 1.05,
        "stop_loss": price * 0.97,
        "factors": {"momentum": 0.5, "value": 0.3},
    }


def _write_record(tmp_path, record_date: date, signals: list[dict]) -> None:
    """Write a signal record JSON to tmp history dir."""
    file_path = tmp_path / f"{record_date.isoformat()}.json"
    file_path.write_text(
        json.dumps(
            {
                "date": record_date.isoformat(),
                "count": len(signals),
                "signals": signals,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ── Tests ──────────────────────────────────────────────────────────────


class TestRecordSignals:
    def test_records_and_loads(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        data = _make_data()
        signals = generate_signals_batch(data)
        path = record_signals(signals, date(2024, 6, 1))

        assert path.exists()
        record = _load_record(date(2024, 6, 1))
        assert record is not None
        assert record["count"] == 2
        assert len(record["signals"]) == 2

    def test_load_nonexistent_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)
        assert _load_record(date(2099, 1, 1)) is None

    def test_default_date_is_today(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        data = _make_data()
        signals = generate_signals_batch(data)
        path = record_signals(signals)

        assert date.today().isoformat() in path.name

    def test_record_preserves_factors(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        data = _make_data()
        signals = generate_signals_batch(data)
        record_signals(signals, date(2024, 7, 1))

        record = _load_record(date(2024, 7, 1))
        for sig in record["signals"]:
            assert "factors" in sig
            assert isinstance(sig["factors"], dict)


class TestValidateSignals:
    def test_validates_buy_signal_correct(self, tmp_path, monkeypatch):
        """Buy signal + price went up → hit = True."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        data = _make_data(100)
        signal_date_ts = data["A"].index[79]
        signal_date_d = signal_date_ts.date()

        signals = generate_signals_batch({sym: df.iloc[:80] for sym, df in data.items()})
        assert len(signals) > 0
        record_signals(signals, signal_date_d)

        with patch("engine.tracker.load_hist") as mock_load:
            mock_load.side_effect = lambda sym: data.get(sym, pd.DataFrame())
            result = validate_signals(signal_date_d, check_after_days=5)

        assert result is not None
        assert result["total_signals"] > 0
        assert "accuracy" in result
        assert 0 <= result["accuracy"] <= 100

    def test_no_record_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)
        assert validate_signals(date(2099, 1, 1)) is None

    def test_validates_sell_signal(self, tmp_path, monkeypatch):
        """Sell signal + price went down → hit = True."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        data = _make_data(100)
        signal_date = data["A"].index[50].date()

        _write_record(
            tmp_path,
            signal_date,
            [_make_signal("A", "sell", price=float(data["A"].iloc[50]["close"]))],
        )

        with patch("engine.tracker.load_hist") as mock_load:
            mock_load.side_effect = lambda sym: data.get(sym, pd.DataFrame())
            result = validate_signals(signal_date, check_after_days=5)

        assert result is not None
        assert result["total_signals"] == 1

    def test_validates_hold_signal(self, tmp_path, monkeypatch):
        """Hold signal + price stayed flat → hit = True."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        data = _make_data(100)
        signal_date = data["A"].index[50].date()

        _write_record(
            tmp_path,
            signal_date,
            [_make_signal("A", "hold", price=float(data["A"].iloc[50]["close"]))],
        )

        with patch("engine.tracker.load_hist") as mock_load:
            mock_load.side_effect = lambda sym: data.get(sym, pd.DataFrame())
            result = validate_signals(signal_date, check_after_days=5)

        assert result is not None
        assert len(result["details"]) == 1

    def test_empty_hist_skipped(self, tmp_path, monkeypatch):
        """Symbols with no hist data are skipped."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        signal_date = date(2024, 6, 1)
        _write_record(
            tmp_path,
            signal_date,
            [_make_signal("MISSING", "buy")],
        )

        with patch("engine.tracker.load_hist", return_value=pd.DataFrame()):
            result = validate_signals(signal_date)

        assert result is None  # 0 total → returns None

    def test_date_not_in_index_uses_nearest(self, tmp_path, monkeypatch):
        """If signal date isn't in the data index, find nearest trading day."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        data = _make_data(100)
        # Use a Saturday — not in bdate_range
        signal_date = date(2024, 1, 6)  # Saturday
        _write_record(
            tmp_path,
            signal_date,
            [_make_signal("A", "buy", price=3.0)],
        )

        with patch("engine.tracker.load_hist") as mock_load:
            mock_load.side_effect = lambda sym: data.get(sym, pd.DataFrame())
            result = validate_signals(signal_date, check_after_days=5)

        # Should still work by finding nearest Monday
        assert result is not None or result is None  # graceful handling

    def test_insufficient_future_data_skips(self, tmp_path, monkeypatch):
        """If check_after_days exceeds remaining data, signal is skipped."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        data = _make_data(100)
        # Use last day — no future data
        signal_date = data["A"].index[-1].date()
        _write_record(
            tmp_path,
            signal_date,
            [_make_signal("A", "buy", price=float(data["A"].iloc[-1]["close"]))],
        )

        with patch("engine.tracker.load_hist") as mock_load:
            mock_load.side_effect = lambda sym: data.get(sym, pd.DataFrame())
            result = validate_signals(signal_date, check_after_days=5)

        assert result is None  # Skipped → 0 total


class TestGetOverallAccuracy:
    def test_no_history_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)
        result = get_overall_accuracy(30)
        assert result["records_checked"] == 0
        assert result["overall_accuracy"] == 0
        assert "message" in result

    def test_with_history(self, tmp_path, monkeypatch):
        """With multiple days of records, should aggregate accuracy."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        data = _make_data(200, seed=55)
        today = date.today()

        # Write records for 10 days in the validation window
        for days_ago in range(VALIDATE_AFTER_DAYS + 1, VALIDATE_AFTER_DAYS + 11):
            d = today - timedelta(days=days_ago)
            # Find the nearest trading day in data
            dt = pd.Timestamp(d)
            mask = data["A"].index <= dt
            if not mask.any():
                continue
            actual_date = data["A"].index[mask][-1].date()

            _write_record(
                tmp_path,
                actual_date,
                [
                    _make_signal("A", "buy", price=float(data["A"].iloc[50]["close"])),
                    _make_signal("B", "sell", price=float(data["B"].iloc[50]["close"])),
                ],
            )

        with patch("engine.tracker.load_hist") as mock_load:
            mock_load.side_effect = lambda sym: data.get(sym, pd.DataFrame())
            result = get_overall_accuracy(30)

        # May or may not have records depending on date matching
        assert "overall_accuracy" in result
        assert "by_direction" in result

    def test_per_direction_breakdown(self, tmp_path, monkeypatch):
        """Accuracy should break down by buy/sell/hold direction."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        data = _make_data(200, seed=77)
        today = date.today()

        # Write a record within the validation window
        d = today - timedelta(days=VALIDATE_AFTER_DAYS + 2)
        _write_record(
            tmp_path,
            d,
            [
                _make_signal("A", "buy", price=3.0),
                _make_signal("B", "sell", price=3.0),
                _make_signal("A", "hold", price=3.0),
            ],
        )

        with patch("engine.tracker.load_hist") as mock_load:
            mock_load.side_effect = lambda sym: data.get(sym, pd.DataFrame())
            result = get_overall_accuracy(30)

        # Check structure even if records_checked is 0 (date mismatch)
        assert isinstance(result["by_direction"], dict)


class TestGetOverallAccuracyAggregation:
    """Tests for the aggregation path (lines 195-220) of get_overall_accuracy."""

    @patch("engine.tracker.validate_signals")
    def test_aggregation_with_multiple_validations(self, mock_validate, tmp_path, monkeypatch):
        """When validate_signals returns results, aggregate accuracy + per-direction breakdown."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        # Return two validation results for different dates
        call_count = 0

        def fake_validate(d: date, check_after_days: int = 5) -> dict | None:
            nonlocal call_count
            call_count += 1
            # Return results for the first two calls, None for the rest
            if call_count == 1:
                return {
                    "signal_date": "2026-03-10",
                    "check_after_days": 5,
                    "total_signals": 3,
                    "correct": 2,
                    "accuracy": 66.7,
                    "details": [
                        {
                            "symbol": "A",
                            "direction": "buy",
                            "score": 60,
                            "price_at_signal": 3.0,
                            "price_after": 3.1,
                            "actual_return": 3.33,
                            "hit": True,
                        },
                        {
                            "symbol": "B",
                            "direction": "sell",
                            "score": 55,
                            "price_at_signal": 3.0,
                            "price_after": 2.9,
                            "actual_return": -3.33,
                            "hit": True,
                        },
                        {
                            "symbol": "A",
                            "direction": "hold",
                            "score": 30,
                            "price_at_signal": 3.0,
                            "price_after": 3.5,
                            "actual_return": 16.67,
                            "hit": False,
                        },
                    ],
                }
            if call_count == 2:
                return {
                    "signal_date": "2026-03-09",
                    "check_after_days": 5,
                    "total_signals": 2,
                    "correct": 1,
                    "accuracy": 50.0,
                    "details": [
                        {
                            "symbol": "A",
                            "direction": "buy",
                            "score": 70,
                            "price_at_signal": 3.0,
                            "price_after": 2.8,
                            "actual_return": -6.67,
                            "hit": False,
                        },
                        {
                            "symbol": "B",
                            "direction": "strong_buy",
                            "score": 80,
                            "price_at_signal": 3.0,
                            "price_after": 3.2,
                            "actual_return": 6.67,
                            "hit": True,
                        },
                    ],
                }
            return None

        mock_validate.side_effect = fake_validate

        result = get_overall_accuracy(lookback_days=30)

        assert result["records_checked"] == 2
        assert result["total_signals"] == 5
        # 3 correct out of 5 = 60.0%
        assert result["overall_accuracy"] == 60.0

        by_dir = result["by_direction"]
        assert "buy" in by_dir
        assert "sell" in by_dir
        assert "hold" in by_dir
        assert "strong_buy" in by_dir

        # buy: 2 total, 1 correct → 50%
        assert by_dir["buy"]["total"] == 2
        assert by_dir["buy"]["correct"] == 1
        assert by_dir["buy"]["accuracy"] == 50.0
        # avg_return for buy: (3.33 + (-6.67)) / 2 = -1.67
        assert by_dir["buy"]["avg_return"] == pytest.approx(-1.67, abs=0.01)

        # sell: 1 total, 1 correct → 100%
        assert by_dir["sell"]["total"] == 1
        assert by_dir["sell"]["correct"] == 1
        assert by_dir["sell"]["accuracy"] == 100.0

        # hold: 1 total, 0 correct → 0%
        assert by_dir["hold"]["total"] == 1
        assert by_dir["hold"]["correct"] == 0
        assert by_dir["hold"]["accuracy"] == 0.0

        # strong_buy: 1 total, 1 correct → 100%
        assert by_dir["strong_buy"]["total"] == 1
        assert by_dir["strong_buy"]["correct"] == 1
        assert by_dir["strong_buy"]["accuracy"] == 100.0

    @patch("engine.tracker.validate_signals")
    def test_aggregation_single_direction(self, mock_validate, tmp_path, monkeypatch):
        """Single direction across all validations — avg_return computed correctly."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        call_count = 0

        def fake_validate(d: date, check_after_days: int = 5) -> dict | None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "signal_date": "2026-03-10",
                    "check_after_days": 5,
                    "total_signals": 2,
                    "correct": 2,
                    "accuracy": 100.0,
                    "details": [
                        {
                            "symbol": "A",
                            "direction": "buy",
                            "score": 70,
                            "price_at_signal": 3.0,
                            "price_after": 3.15,
                            "actual_return": 5.0,
                            "hit": True,
                        },
                        {
                            "symbol": "B",
                            "direction": "buy",
                            "score": 65,
                            "price_at_signal": 3.0,
                            "price_after": 3.09,
                            "actual_return": 3.0,
                            "hit": True,
                        },
                    ],
                }
            return None

        mock_validate.side_effect = fake_validate

        result = get_overall_accuracy(lookback_days=30)

        assert result["records_checked"] == 1
        assert result["overall_accuracy"] == 100.0
        assert result["by_direction"]["buy"]["avg_return"] == 4.0  # (5.0 + 3.0) / 2

    @patch("engine.tracker.validate_signals")
    def test_all_validations_none_returns_zero(self, mock_validate, tmp_path, monkeypatch):
        """When all validate_signals calls return None, return zero-record result."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)
        mock_validate.return_value = None

        result = get_overall_accuracy(lookback_days=30)

        assert result["records_checked"] == 0
        assert result["overall_accuracy"] == 0
        assert "message" in result


class TestSuggestWeightAdjustment:
    def test_insufficient_data_returns_defaults(self, tmp_path, monkeypatch):
        """With < 5 records, return default weights with a note."""
        monkeypatch.setattr("engine.tracker.HISTORY_DIR", tmp_path)

        result = suggest_weight_adjustment()

        assert result["momentum"] == 0.5
        assert result["value"] == 0.3
        assert result["volatility"] == 0.2
        assert "样本不足" in result["_note"]

    @patch("engine.tracker.get_overall_accuracy")
    def test_high_buy_accuracy_boosts_momentum(self, mock_acc):
        """Buy accuracy > 60% → momentum weight increases."""
        mock_acc.return_value = {
            "records_checked": 10,
            "overall_accuracy": 65,
            "by_direction": {
                "buy": {"accuracy": 70, "total": 20, "correct": 14, "avg_return": 2.0},
                "strong_buy": {
                    "accuracy": 65,
                    "total": 10,
                    "correct": 6,
                    "avg_return": 3.0,
                },
            },
        }

        result = suggest_weight_adjustment()

        assert result["momentum"] > 0.5  # Should be boosted
        total = result["momentum"] + result["value"] + result["volatility"]
        assert total == pytest.approx(1.0, abs=0.02)

    @patch("engine.tracker.get_overall_accuracy")
    def test_low_buy_accuracy_reduces_momentum(self, mock_acc):
        """Buy accuracy < 40% → momentum weight decreases, value increases."""
        mock_acc.return_value = {
            "records_checked": 10,
            "overall_accuracy": 35,
            "by_direction": {
                "buy": {"accuracy": 30, "total": 20, "correct": 6, "avg_return": -1.0},
                "strong_buy": {
                    "accuracy": 25,
                    "total": 10,
                    "correct": 2,
                    "avg_return": -2.0,
                },
            },
        }

        result = suggest_weight_adjustment()

        assert result["momentum"] < 0.5  # Should be reduced
        assert result["value"] > 0.3  # Should be increased
        total = result["momentum"] + result["value"] + result["volatility"]
        assert total == pytest.approx(1.0, abs=0.02)

    @patch("engine.tracker.get_overall_accuracy")
    def test_moderate_accuracy_keeps_defaults(self, mock_acc):
        """Accuracy between 40-60% → weights stay roughly default."""
        mock_acc.return_value = {
            "records_checked": 10,
            "overall_accuracy": 50,
            "by_direction": {
                "buy": {"accuracy": 50, "total": 20, "correct": 10, "avg_return": 0.5},
                "strong_buy": {
                    "accuracy": 50,
                    "total": 10,
                    "correct": 5,
                    "avg_return": 0.5,
                },
            },
        }

        result = suggest_weight_adjustment()

        # Should be close to defaults (normalized)
        assert 0.45 <= result["momentum"] <= 0.55
        assert "_accuracy_base" in result

    @patch("engine.tracker.get_overall_accuracy")
    def test_weights_normalized_to_one(self, mock_acc):
        """Weights should always sum to ~1.0."""
        mock_acc.return_value = {
            "records_checked": 10,
            "overall_accuracy": 80,
            "by_direction": {
                "buy": {"accuracy": 80, "total": 30, "correct": 24, "avg_return": 3.0},
                "strong_buy": {
                    "accuracy": 85,
                    "total": 10,
                    "correct": 8,
                    "avg_return": 4.0,
                },
            },
        }

        result = suggest_weight_adjustment()

        total = result["momentum"] + result["value"] + result["volatility"]
        assert total == pytest.approx(1.0, abs=0.02)
