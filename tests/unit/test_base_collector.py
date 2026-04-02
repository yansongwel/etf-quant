"""Tests for base collector: rate limiter, retry, column normalization."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pandas as pd

from data.collectors.base import RateLimiter, fetch_with_retry, normalize_columns


class TestRateLimiter:
    def test_first_call_no_delay(self) -> None:
        limiter = RateLimiter(delay=1.0)
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_second_call_waits(self) -> None:
        limiter = RateLimiter(delay=0.2)
        limiter.wait()
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.15  # Allow small tolerance


class TestFetchWithRetry:
    def test_success_on_first_try(self) -> None:
        expected = pd.DataFrame({"a": [1, 2]})
        fn = MagicMock(return_value=expected)

        result = fetch_with_retry(fn, max_retries=3)

        fn.assert_called_once()
        pd.testing.assert_frame_equal(result, expected)

    def test_retries_on_exception(self) -> None:
        expected = pd.DataFrame({"a": [1]})
        fn = MagicMock(side_effect=[ValueError("boom"), expected])

        result = fetch_with_retry(fn, max_retries=2)

        assert fn.call_count == 2
        pd.testing.assert_frame_equal(result, expected)

    def test_returns_empty_after_exhausted_retries(self) -> None:
        fn = MagicMock(side_effect=ValueError("always fails"))

        result = fetch_with_retry(fn, max_retries=2)

        assert fn.call_count == 2
        assert result.empty

    def test_retries_on_empty_result(self) -> None:
        expected = pd.DataFrame({"a": [1]})
        fn = MagicMock(side_effect=[pd.DataFrame(), expected])

        result = fetch_with_retry(fn, max_retries=2)

        assert fn.call_count == 2
        pd.testing.assert_frame_equal(result, expected)


class TestNormalizeColumns:
    def test_renames_matching_columns(self) -> None:
        df = pd.DataFrame({"日期": ["2025-01-01"], "开盘": [3.8], "unknown": [99]})
        mapping = {"日期": "date", "开盘": "open", "收盘": "close"}

        result = normalize_columns(df, mapping)

        assert list(result.columns) == ["date", "open", "unknown"]

    def test_does_not_mutate_original(self) -> None:
        df = pd.DataFrame({"日期": ["2025-01-01"]})
        mapping = {"日期": "date"}

        normalize_columns(df, mapping)

        assert "日期" in df.columns

    def test_empty_mapping(self) -> None:
        df = pd.DataFrame({"a": [1]})
        result = normalize_columns(df, {})
        pd.testing.assert_frame_equal(result, df)
