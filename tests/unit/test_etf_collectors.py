"""Tests for ETF history and spot collectors using mocked AkShare calls."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd

from data.collectors.etf_hist import collect_etf_hist, collect_etf_hist_batch
from data.collectors.etf_spot import collect_etf_spot


def _make_raw_hist() -> pd.DataFrame:
    """Simulate AkShare fund_etf_hist_em return value."""
    return pd.DataFrame(
        {
            "日期": ["2025-01-02", "2025-01-03"],
            "开盘": [3.8, 3.7],
            "收盘": [3.7, 3.65],
            "最高": [3.81, 3.71],
            "最低": [3.67, 3.64],
            "成交量": [21000000, 15000000],
            "成交额": [8.5e9, 6.1e9],
            "振幅": [3.67, 1.84],
            "涨跌幅": [-2.97, -1.08],
            "涨跌额": [-0.113, -0.04],
            "换手率": [4.81, 3.53],
        }
    )


def _make_raw_spot() -> pd.DataFrame:
    """Simulate AkShare fund_etf_spot_em return value."""
    return pd.DataFrame(
        {
            "代码": ["510300", "510500", "510050"],
            "名称": ["沪深300ETF", "中证500ETF", "上证50ETF"],
            "最新价": [3.65, 5.80, 2.70],
            "涨跌额": [-0.05, 0.02, -0.03],
            "涨跌幅": [-1.35, 0.35, -1.10],
            "成交量": [12000000, 8000000, 6000000],
            "成交额": [5.0e9, 3.2e9, 2.1e9],
            "开盘价": [3.70, 5.78, 2.73],
            "最高价": [3.71, 5.82, 2.74],
            "最低价": [3.63, 5.77, 2.69],
            "昨收": [3.70, 5.78, 2.73],
            "换手率": [2.5, 1.8, 1.2],
        }
    )


class TestCollectEtfHist:
    @patch("data.collectors.etf_hist.fetch_with_retry")
    def test_returns_normalized_df(self, mock_fetch):
        mock_fetch.return_value = _make_raw_hist()

        df = collect_etf_hist("510300", date(2025, 1, 1), date(2025, 1, 31))

        assert not df.empty
        assert df.index.name == "date"
        assert "close" in df.columns
        assert "symbol" in df.columns
        assert (df["symbol"] == "510300").all()
        assert pd.api.types.is_datetime64_any_dtype(df.index)

    @patch("data.collectors.etf_hist.fetch_with_retry")
    def test_empty_response(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()

        df = collect_etf_hist("510300", date(2025, 1, 1), date(2025, 1, 31))

        assert df.empty


class TestCollectEtfHistBatch:
    @patch("data.collectors.etf_hist.collect_etf_hist")
    def test_concatenates_multiple_symbols(self, mock_collect):
        df1 = pd.DataFrame(
            {"close": [3.7], "symbol": ["510300"]},
            index=pd.to_datetime(["2025-01-02"]),
        )
        df1.index.name = "date"
        df2 = pd.DataFrame(
            {"close": [5.8], "symbol": ["510500"]},
            index=pd.to_datetime(["2025-01-02"]),
        )
        df2.index.name = "date"
        mock_collect.side_effect = [df1, df2]

        result = collect_etf_hist_batch(["510300", "510500"], date(2025, 1, 1), date(2025, 1, 31))

        assert len(result) == 2
        assert set(result["symbol"]) == {"510300", "510500"}

    @patch("data.collectors.etf_hist.collect_etf_hist")
    def test_skips_failed_symbols(self, mock_collect):
        df1 = pd.DataFrame(
            {"close": [3.7], "symbol": ["510300"]},
            index=pd.to_datetime(["2025-01-02"]),
        )
        df1.index.name = "date"
        mock_collect.side_effect = [pd.DataFrame(), df1]

        result = collect_etf_hist_batch(["999999", "510300"], date(2025, 1, 1), date(2025, 1, 31))

        assert len(result) == 1
        assert (result["symbol"] == "510300").all()

    @patch("data.collectors.etf_hist.collect_etf_hist")
    def test_all_fail_returns_empty(self, mock_collect):
        mock_collect.return_value = pd.DataFrame()

        result = collect_etf_hist_batch(["999999"], date(2025, 1, 1), date(2025, 1, 31))

        assert result.empty


class TestCollectEtfSpot:
    @patch("data.collectors.etf_spot.fetch_with_retry")
    def test_returns_all_etfs(self, mock_fetch):
        mock_fetch.return_value = _make_raw_spot()

        df = collect_etf_spot()

        assert len(df) == 3
        assert "symbol" in df.columns
        assert "price" in df.columns

    @patch("data.collectors.etf_spot.fetch_with_retry")
    def test_filters_by_symbols(self, mock_fetch):
        mock_fetch.return_value = _make_raw_spot()

        df = collect_etf_spot(["510300", "510500"])

        assert len(df) == 2
        assert set(df["symbol"]) == {"510300", "510500"}

    @patch("data.collectors.etf_spot.fetch_with_retry")
    def test_warns_on_missing_symbols(self, mock_fetch):
        mock_fetch.return_value = _make_raw_spot()

        df = collect_etf_spot(["510300", "999999"])

        assert len(df) == 1

    @patch("data.collectors.etf_spot.fetch_with_retry")
    def test_empty_response(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()

        df = collect_etf_spot()

        assert df.empty
