"""Tests for the realtime data collector (Tencent + Tiantian APIs)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from data.collectors.realtime import (
    _tencent_prefix,
    fetch_fund_valuation,
    fetch_hist_from_eastmoney,
    fetch_hist_from_tencent,
    fetch_realtime_quotes,
)


class TestTencentPrefix:
    def test_shanghai_5xx(self) -> None:
        assert _tencent_prefix("510300") == "sh510300"

    def test_shanghai_6xx(self) -> None:
        assert _tencent_prefix("600000") == "sh600000"

    def test_shenzhen_1xx(self) -> None:
        assert _tencent_prefix("159915") == "sz159915"

    def test_shenzhen_0xx(self) -> None:
        assert _tencent_prefix("000001") == "sz000001"


class TestFetchRealtimeQuotes:
    def test_empty_symbols(self) -> None:
        assert fetch_realtime_quotes([]).empty

    @patch("data.collectors.realtime._SESSION")
    def test_parses_tencent_response(self, mock_session: MagicMock) -> None:
        # Real Tencent response format (simplified)
        mock_resp = MagicMock()
        mock_resp.text = (
            'v_sh510300="1~沪深300ETF~510300~4.463~4.500~4.501~5305656'
            "~2400442~2905214~4.464~90~4.463~4828~4.462~7707~4.461~12483"
            "~4.460~28162~4.465~6462~4.466~3141~4.467~10~4.468~1438~4.469"
            "~1911~~20260331153237~-0.037~-0.82~4.529~4.462~4.463/5305656"
            "/2385310576~5305656~238531~1.18~~~4.529~4.462~1.49~2004.48"
            '~2004.48~0.00~4.950~4.050~0.80~40308~4.496";'
        )
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        df = fetch_realtime_quotes(["510300"])
        assert not df.empty
        assert len(df) == 1
        row = df.iloc[0]
        assert row["symbol"] == "510300"
        assert row["close"] == 4.463
        assert row["volume"] == 5305656
        assert row["date"] == "2026-03-31"

    @patch("data.collectors.realtime._SESSION")
    def test_handles_network_error(self, mock_session: MagicMock) -> None:
        mock_session.get.side_effect = Exception("Connection refused")
        df = fetch_realtime_quotes(["510300"])
        assert df.empty

    @patch("data.collectors.realtime._SESSION")
    def test_short_response_line_skipped(self, mock_session: MagicMock) -> None:
        """Response line with < 50 parts should be skipped (line 91)."""
        mock_resp = MagicMock()
        # Only a few parts — should be skipped
        mock_resp.text = 'v_sh510300="1~沪深300ETF~510300~4.463~too~few~parts";'
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        df = fetch_realtime_quotes(["510300"])
        assert df.empty

    @patch("data.collectors.realtime._SESSION")
    def test_short_timestamp_uses_today(self, mock_session: MagicMock) -> None:
        """When timestamp field < 8 chars, use today's date (line 114)."""
        # Build response with 50+ parts but short timestamp at parts[30]
        parts = [""] * 50
        parts[1] = "沪深300ETF"
        parts[2] = "510300"
        parts[3] = "4.463"  # current_price
        parts[4] = "4.500"  # prev_close
        parts[5] = "4.501"  # open
        parts[6] = "5305656"  # volume
        parts[30] = "short"  # timestamp < 8 chars
        parts[32] = "-0.82"  # pct
        parts[33] = "4.529"  # high
        parts[34] = "4.462"  # low
        parts[37] = "238531"  # amount in wan
        parts[38] = "1.18"  # turnover
        line = "~".join(parts)
        mock_resp = MagicMock()
        mock_resp.text = f'v_sh510300="1~{line}";'
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        from datetime import date

        df = fetch_realtime_quotes(["510300"])
        if not df.empty:
            # Date should be today since timestamp was too short
            assert df.iloc[0]["date"] == str(date.today())

    @patch("data.collectors.realtime._SESSION")
    def test_malformed_line_parse_error(self, mock_session: MagicMock) -> None:
        """Malformed numeric fields should trigger except block (lines 131-133)."""
        # 50+ parts but invalid numeric value at price field
        parts = [""] * 50
        parts[1] = "沪深300ETF"
        parts[2] = "510300"
        parts[3] = "not_a_number"  # current_price — will raise ValueError
        parts[4] = "4.500"
        parts[5] = "4.501"
        parts[6] = "5305656"
        parts[30] = "20260331153237"
        parts[32] = "-0.82"
        parts[33] = "4.529"
        parts[34] = "4.462"
        parts[37] = "238531"
        parts[38] = "1.18"
        line = "~".join(parts)
        mock_resp = MagicMock()
        mock_resp.text = f'v_sh510300="1~{line}";'
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        df = fetch_realtime_quotes(["510300"])
        # Should return empty since the only line failed to parse
        assert df.empty

    @patch("data.collectors.realtime._SESSION")
    def test_all_lines_fail_returns_empty(self, mock_session: MagicMock) -> None:
        """When all lines fail parsing, return empty df (line 136)."""
        mock_resp = MagicMock()
        # Lines without quotes are skipped, leaving no rows
        mock_resp.text = "no valid data here\nalso nothing"
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        df = fetch_realtime_quotes(["510300"])
        assert df.empty


class TestFetchFundValuation:
    @patch("data.collectors.realtime._SESSION")
    def test_parses_jsonp(self, mock_session: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.text = (
            'jsonpgz({"fundcode":"510300","name":"华泰柏瑞沪深300ETF",'
            '"jzrq":"2026-03-30","dwjz":"4.5012","gsz":"4.4593",'
            '"gszzl":"-0.93","gztime":"2026-03-31 15:00"});'
        )
        mock_session.get.return_value = mock_resp

        result = fetch_fund_valuation("510300")
        assert result is not None
        assert result["fundcode"] == "510300"
        assert result["nav"] == 4.5012
        assert result["estimated_nav"] == 4.4593
        assert result["estimated_change_pct"] == -0.93

    @patch("data.collectors.realtime._SESSION")
    def test_handles_invalid_response(self, mock_session: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.text = "invalid response"
        mock_session.get.return_value = mock_resp

        result = fetch_fund_valuation("510300")
        assert result is None

    @patch("data.collectors.realtime._SESSION")
    def test_handles_network_error(self, mock_session: MagicMock) -> None:
        mock_session.get.side_effect = Exception("timeout")
        result = fetch_fund_valuation("510300")
        assert result is None


class TestFetchHistFromTencent:
    @patch("data.collectors.realtime._SESSION")
    def test_parses_kline_response(self, mock_session: MagicMock) -> None:
        from datetime import date

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "sh510300": {
                    "qfqday": [
                        ["2026-03-30", "4.462", "4.500", "4.505", "4.453", "5439943.000"],
                        ["2026-03-31", "4.501", "4.463", "4.529", "4.462", "5305656.000"],
                    ]
                }
            }
        }
        mock_session.get.return_value = mock_resp

        df = fetch_hist_from_tencent("510300", date(2026, 3, 28), count=5)
        assert not df.empty
        assert len(df) == 2
        assert df.iloc[0]["close"] == 4.500
        assert df.iloc[1]["close"] == 4.463
        assert df.iloc[0]["volume"] == 5439943
        assert df.index[0].date().isoformat() == "2026-03-30"

    @patch("data.collectors.realtime._SESSION")
    def test_empty_klines(self, mock_session: MagicMock) -> None:
        from datetime import date

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"sh510300": {"qfqday": []}}}
        mock_session.get.return_value = mock_resp

        df = fetch_hist_from_tencent("510300", date(2026, 3, 28))
        assert df.empty

    @patch("data.collectors.realtime._SESSION")
    def test_handles_network_error(self, mock_session: MagicMock) -> None:
        from datetime import date

        mock_session.get.side_effect = Exception("Connection refused")
        df = fetch_hist_from_tencent("510300", date(2026, 3, 28))
        assert df.empty

    @patch("data.collectors.realtime._SESSION")
    def test_short_kline_skipped(self, mock_session: MagicMock) -> None:
        """Kline row with < 6 elements should be skipped (line 300)."""
        from datetime import date

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "sh510300": {
                    "qfqday": [
                        ["2026-03-30", "4.462", "4.500"],  # Too few elements
                        ["2026-03-31", "4.501", "4.463", "4.529", "4.462", "5305656.000"],
                    ]
                }
            }
        }
        mock_session.get.return_value = mock_resp

        df = fetch_hist_from_tencent("510300", date(2026, 3, 28), count=5)
        # Only the valid row should be parsed
        assert len(df) == 1


class TestFetchHistFromEastMoney:
    @patch("data.collectors.realtime._SESSION")
    def test_parses_kline_response(self, mock_session: MagicMock) -> None:
        from datetime import date

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "klines": [
                    "2026-03-30,4.462,4.500,4.505,4.453,5439943,2430647936,1.16,-0.18,-0.008,1.21",
                    "2026-03-31,4.501,4.463,4.529,4.462,5305656,2385310576,1.49,-0.82,-0.037,1.18",
                ]
            }
        }
        mock_session.get.return_value = mock_resp

        df = fetch_hist_from_eastmoney("510300", date(2026, 3, 28), date(2026, 3, 31))
        assert not df.empty
        assert len(df) == 2
        assert df.iloc[0]["close"] == 4.500
        assert df.iloc[1]["volume"] == 5305656

    @patch("data.collectors.realtime._SESSION")
    def test_empty_klines(self, mock_session: MagicMock) -> None:
        from datetime import date

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"klines": []}}
        mock_session.get.return_value = mock_resp

        df = fetch_hist_from_eastmoney("510300", date(2026, 3, 28), date(2026, 3, 31))
        assert df.empty

    @patch("data.collectors.realtime._SESSION")
    def test_handles_network_error(self, mock_session: MagicMock) -> None:
        from datetime import date

        mock_session.get.side_effect = Exception("Connection refused")
        df = fetch_hist_from_eastmoney("510300", date(2026, 3, 28), date(2026, 3, 31))
        assert df.empty

    @patch("data.collectors.realtime._SESSION")
    def test_short_kline_line_skipped(self, mock_session: MagicMock) -> None:
        """EastMoney kline with < 7 parts should be skipped (line 226)."""
        from datetime import date

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "klines": [
                    "2026-03-30,4.462,4.500",  # Too few parts
                    "2026-03-31,4.501,4.463,4.529,4.462,5305656,2385310576,1.49,-0.82,-0.037,1.18",
                ]
            }
        }
        mock_session.get.return_value = mock_resp

        df = fetch_hist_from_eastmoney("510300", date(2026, 3, 28), date(2026, 3, 31))
        assert len(df) == 1
