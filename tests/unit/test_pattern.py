"""Tests for K-line pattern recognition engine."""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine.pattern import (
    _is_bearish_engulfing,
    _is_bullish_engulfing,
    _is_doji,
    _is_hammer,
    _is_marubozu,
    _is_shooting_star,
    compute_pattern_score,
    detect_patterns,
    find_support_resistance,
)


def _make_ohlcv(days: int = 100, trend: float = 0.001) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=days)
    close = 4.0 * np.cumprod(1 + np.random.normal(trend, 0.02, days))
    high = close * (1 + np.random.uniform(0, 0.02, days))
    low = close * (1 - np.random.uniform(0, 0.02, days))
    return pd.DataFrame(
        {
            "open": close * (1 + np.random.normal(0, 0.005, days)),
            "high": high,
            "low": low,
            "close": close,
            "volume": np.random.randint(1_000_000, 10_000_000, days).astype(float),
        },
        index=dates,
    )


class TestSingleCandlePatterns:
    def test_doji(self) -> None:
        assert _is_doji(4.50, 4.55, 4.45, 4.50)  # body = 0
        assert _is_doji(4.50, 4.55, 4.45, 4.505)  # body = 0.005, range = 0.10, ratio = 5%
        assert not _is_doji(4.40, 4.55, 4.35, 4.50)  # body = 0.10, range = 0.20

    def test_hammer(self) -> None:
        # Long lower shadow (0.10), small body (0.02), tiny upper shadow
        assert _is_hammer(4.50, 4.52, 4.40, 4.52)
        assert not _is_hammer(4.40, 4.55, 4.39, 4.50)  # Upper shadow too long

    def test_shooting_star(self) -> None:
        # Long upper shadow, small body at bottom
        assert _is_shooting_star(4.50, 4.62, 4.49, 4.48)
        assert not _is_shooting_star(4.40, 4.42, 4.30, 4.41)  # Lower shadow too long

    def test_marubozu(self) -> None:
        # Body > 90% of range
        assert _is_marubozu(4.40, 4.50, 4.40, 4.50)  # Perfect marubozu
        assert not _is_marubozu(4.40, 4.55, 4.35, 4.50)  # Too much shadow


class TestMultiCandlePatterns:
    def test_bullish_engulfing(self) -> None:
        # Prev: red (open=4.5, close=4.4), Curr: green engulfing (open=4.38, close=4.52)
        assert _is_bullish_engulfing(4.5, 4.4, 4.38, 4.52)
        assert not _is_bullish_engulfing(4.5, 4.4, 4.42, 4.48)  # Doesn't engulf

    def test_bearish_engulfing(self) -> None:
        # Prev: green (open=4.4, close=4.5), Curr: red engulfing (open=4.52, close=4.38)
        assert _is_bearish_engulfing(4.4, 4.5, 4.52, 4.38)
        assert not _is_bearish_engulfing(4.4, 4.5, 4.48, 4.42)  # Doesn't engulf


class TestDetectPatterns:
    def test_returns_list(self) -> None:
        df = _make_ohlcv()
        result = detect_patterns(df)
        assert isinstance(result, list)

    def test_insufficient_data(self) -> None:
        df = _make_ohlcv(days=3)
        result = detect_patterns(df)
        assert result == []

    def test_pattern_has_correct_fields(self) -> None:
        df = _make_ohlcv(days=200)
        result = detect_patterns(df)
        for p in result:
            assert hasattr(p, "name")
            assert hasattr(p, "pattern_type")
            assert hasattr(p, "confidence")
            assert 0 <= p.confidence <= 100
            d = p.to_dict()
            assert "name" in d and "type" in d and "confidence" in d


class TestComputePatternScore:
    def test_score_range(self) -> None:
        df = _make_ohlcv()
        score, patterns = compute_pattern_score(df)
        assert -15 <= score <= 15

    def test_no_patterns_zero_score(self) -> None:
        # Create a boring flat series — unlikely to have patterns
        dates = pd.bdate_range("2024-01-01", periods=50)
        df = pd.DataFrame(
            {
                "open": [4.50] * 50,
                "high": [4.51] * 50,
                "low": [4.49] * 50,
                "close": [4.50] * 50,
                "volume": [5000000.0] * 50,
            },
            index=dates,
        )
        score, patterns = compute_pattern_score(df)
        # Flat candles are dojis but in flat trend → neutral
        assert -5 <= score <= 5


class TestSupportResistance:
    def test_finds_levels(self) -> None:
        df = _make_ohlcv(days=200)
        sr = find_support_resistance(df)
        assert "support" in sr
        assert "resistance" in sr
        # Should find at least some levels
        assert len(sr["support"]) + len(sr["resistance"]) > 0

    def test_support_below_price(self) -> None:
        df = _make_ohlcv(days=200)
        sr = find_support_resistance(df)
        current = float(df["close"].iloc[-1])
        for s in sr["support"]:
            assert s < current

    def test_resistance_above_price(self) -> None:
        df = _make_ohlcv(days=200)
        sr = find_support_resistance(df)
        current = float(df["close"].iloc[-1])
        for r in sr["resistance"]:
            assert r > current

    def test_insufficient_data(self) -> None:
        df = _make_ohlcv(days=10)
        sr = find_support_resistance(df)
        assert sr == {"support": [], "resistance": []}
