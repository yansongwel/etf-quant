"""Tests for collect_daily.py — timezone and trading day logic."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd

from scripts.collect_daily import _beijing_today, _is_up_to_date, _last_trading_day


class TestBeijingToday:
    def test_returns_date(self) -> None:
        result = _beijing_today()
        assert isinstance(result, date)

    def test_uses_utc_plus_8(self) -> None:
        """Beijing time is UTC+8. When UTC is 23:00 on day N, Beijing is 07:00 on day N+1."""
        utc_late = datetime(2026, 3, 30, 23, 0, tzinfo=UTC)
        with patch("scripts.collect_daily.datetime") as mock_dt:
            mock_dt.now.return_value = utc_late.astimezone(timezone(timedelta(hours=8)))
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            # At UTC 23:00 Mar 30 → Beijing Mar 31 07:00
            result = _beijing_today()
            assert result == date(2026, 3, 31)


class TestLastTradingDay:
    def test_weekday_returns_same(self) -> None:
        """Monday through Friday should return the same date."""
        monday = date(2026, 3, 30)  # Monday
        assert _last_trading_day(monday) == monday

    def test_friday_returns_friday(self) -> None:
        friday = date(2026, 3, 27)
        assert _last_trading_day(friday) == friday

    def test_saturday_returns_friday(self) -> None:
        saturday = date(2026, 3, 28)
        assert _last_trading_day(saturday) == date(2026, 3, 27)

    def test_sunday_returns_friday(self) -> None:
        sunday = date(2026, 3, 29)
        assert _last_trading_day(sunday) == date(2026, 3, 27)


class TestIsUpToDate:
    @patch("scripts.collect_daily.load_hist")
    @patch("scripts.collect_daily._last_trading_day", return_value=date(2026, 3, 30))
    def test_data_on_last_trading_day(self, _td, mock_load) -> None:
        """Data up to last trading day → up to date."""
        df = pd.DataFrame(
            {"close": [1.0]},
            index=pd.DatetimeIndex([pd.Timestamp("2026-03-30")]),
        )
        mock_load.return_value = df
        assert _is_up_to_date("510300") is True

    @patch("scripts.collect_daily.load_hist")
    @patch("scripts.collect_daily._last_trading_day", return_value=date(2026, 3, 30))
    def test_data_missing_last_day(self, _td, mock_load) -> None:
        """Data only up to Friday → NOT up to date on Monday."""
        df = pd.DataFrame(
            {"close": [1.0]},
            index=pd.DatetimeIndex([pd.Timestamp("2026-03-27")]),
        )
        mock_load.return_value = df
        assert _is_up_to_date("510300") is False

    @patch("scripts.collect_daily.load_hist")
    def test_empty_data(self, mock_load) -> None:
        mock_load.return_value = pd.DataFrame()
        assert _is_up_to_date("510300") is False

    @patch("scripts.collect_daily.load_hist")
    @patch("scripts.collect_daily._last_trading_day", return_value=date(2026, 3, 27))
    def test_weekend_data_on_friday(self, _td, mock_load) -> None:
        """On weekend, last trading day is Friday. Data on Friday → up to date."""
        df = pd.DataFrame(
            {"close": [1.0]},
            index=pd.DatetimeIndex([pd.Timestamp("2026-03-27")]),
        )
        mock_load.return_value = df
        assert _is_up_to_date("510300") is True
