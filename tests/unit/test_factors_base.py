"""Tests for factors.base — validation, NaN checking, cross-sectional ranking."""

from __future__ import annotations

import pandas as pd
import pytest

from factors.base import check_nan_ratio, rank_cross_section, validate_ohlcv


class TestValidateOhlcv:
    def test_valid_df(self) -> None:
        df = pd.DataFrame(
            {
                "open": [1.0, 2.0],
                "high": [1.5, 2.5],
                "low": [0.5, 1.5],
                "close": [1.2, 2.2],
                "volume": [1000, 2000],
            }
        )
        assert validate_ohlcv(df) is True

    def test_missing_columns(self) -> None:
        df = pd.DataFrame({"close": [1.0, 2.0], "volume": [100, 200]})
        assert validate_ohlcv(df) is False

    def test_insufficient_rows(self) -> None:
        df = pd.DataFrame(
            {
                "open": [1.0],
                "high": [1.5],
                "low": [0.5],
                "close": [1.2],
                "volume": [1000],
            }
        )
        assert validate_ohlcv(df, min_rows=2) is False

    def test_custom_min_rows(self) -> None:
        df = pd.DataFrame(
            {
                "open": [1.0, 2.0, 3.0],
                "high": [1.5, 2.5, 3.5],
                "low": [0.5, 1.5, 2.5],
                "close": [1.2, 2.2, 3.2],
                "volume": [1000, 2000, 3000],
            }
        )
        assert validate_ohlcv(df, min_rows=3) is True
        assert validate_ohlcv(df, min_rows=4) is False


class TestCheckNanRatio:
    def test_empty_series(self) -> None:
        s = pd.Series([], dtype=float)
        result = check_nan_ratio(s, "test")
        assert result.empty

    def test_no_nans(self) -> None:
        s = pd.Series([1.0, 2.0, 3.0])
        result = check_nan_ratio(s, "test")
        pd.testing.assert_series_equal(result, s)

    def test_high_nan_ratio_logs_warning(self, caplog: object) -> None:
        # >5% NaN should trigger warning
        data = [1.0] * 90 + [float("nan")] * 10  # 10% NaN
        s = pd.Series(data, name="test_factor")
        result = check_nan_ratio(s, "test_factor")
        assert len(result) == 100
        assert "test_factor" in caplog.text  # type: ignore[attr-defined]
        assert "10.0%" in caplog.text  # type: ignore[attr-defined]

    def test_low_nan_ratio_no_warning(self, caplog: object) -> None:
        # <5% NaN should NOT trigger warning
        data = [1.0] * 99 + [float("nan")]  # 1% NaN
        s = pd.Series(data, name="low_nan")
        check_nan_ratio(s, "low_nan")
        assert "low_nan" not in caplog.text  # type: ignore[attr-defined]

    def test_unnamed_series(self, caplog: object) -> None:
        data = [float("nan")] * 10 + [1.0] * 10  # 50% NaN
        s = pd.Series(data)
        check_nan_ratio(s)
        assert "unnamed" in caplog.text  # type: ignore[attr-defined]


class TestRankCrossSection:
    def test_multiindex(self) -> None:
        idx = pd.MultiIndex.from_tuples(
            [
                ("2024-01-01", "510300"),
                ("2024-01-01", "510500"),
                ("2024-01-01", "159915"),
                ("2024-01-02", "510300"),
                ("2024-01-02", "510500"),
                ("2024-01-02", "159915"),
            ],
            names=["date", "symbol"],
        )
        df = pd.DataFrame({"momentum": [0.05, 0.10, 0.02, -0.01, 0.03, 0.08]}, index=idx)
        ranks = rank_cross_section(df, "momentum")

        # At each date, rank is pct [0,1], highest = 1.0
        assert ranks.loc[("2024-01-01", "510500")] == 1.0  # 0.10 is highest
        assert ranks.loc[("2024-01-01", "159915")] == pytest.approx(1 / 3)  # 0.02 is lowest

    def test_date_column(self) -> None:
        df = pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"],
                "symbol": ["A", "B", "A", "B"],
                "score": [10, 20, 30, 5],
            }
        )
        ranks = rank_cross_section(df, "score")
        # At date 2024-01-01: B(20) > A(10), so B=1.0, A=0.5
        assert ranks.iloc[0] == 0.5
        assert ranks.iloc[1] == 1.0
