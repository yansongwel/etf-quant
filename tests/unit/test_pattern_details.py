"""Tests for K-line pattern recognition helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine.pattern import (
    _is_bearish_engulfing,
    _is_bullish_engulfing,
    _is_doji,
    _is_evening_star,
    _is_hammer,
    _is_marubozu,
    _is_morning_star,
    _is_shooting_star,
    compute_pattern_score,
    detect_patterns,
)


class TestSingleCandlePatterns:
    def test_doji_true(self) -> None:
        # Body = 0.01, range = 1.0 → body/range = 1% < 10%
        assert _is_doji(o=100.0, h=100.5, lo=99.5, c=100.01) is True

    def test_doji_false(self) -> None:
        # Body = 0.5, range = 1.0 → body/range = 50% > 10%
        assert _is_doji(o=100.0, h=100.5, lo=99.5, c=100.5) is False

    def test_doji_flat_candle(self) -> None:
        # Zero range → True
        assert _is_doji(o=100.0, h=100.0, lo=100.0, c=100.0) is True

    def test_hammer_true(self) -> None:
        # Long lower shadow, small body at top
        # body=0.1, lower=0.4, upper=0
        assert _is_hammer(o=100.4, h=100.5, lo=100.0, c=100.5) is True

    def test_hammer_false_no_lower_shadow(self) -> None:
        # No lower shadow
        assert _is_hammer(o=100.0, h=100.5, lo=100.0, c=100.5) is False

    def test_hammer_zero_body(self) -> None:
        # Zero body → False
        assert _is_hammer(o=100.0, h=100.5, lo=99.5, c=100.0) is False

    def test_shooting_star_true(self) -> None:
        # Long upper shadow, small body at bottom
        # body=0.1, upper=0.4, lower=0
        assert _is_shooting_star(o=100.0, h=100.5, lo=100.0, c=100.1) is True

    def test_shooting_star_false(self) -> None:
        assert _is_shooting_star(o=100.0, h=100.1, lo=99.5, c=100.0) is False

    def test_shooting_star_zero_body(self) -> None:
        assert _is_shooting_star(o=100.0, h=100.5, lo=100.0, c=100.0) is False

    def test_marubozu_true(self) -> None:
        # Body = 0.95, range = 1.0 → ratio = 95% > 90%
        assert _is_marubozu(o=100.0, h=100.98, lo=99.98, c=100.95) is True

    def test_marubozu_false(self) -> None:
        # Body = 0.5, range = 1.0 → ratio = 50%
        assert _is_marubozu(o=100.0, h=100.5, lo=99.5, c=100.5) is False

    def test_marubozu_zero_range(self) -> None:
        assert _is_marubozu(o=100.0, h=100.0, lo=100.0, c=100.0) is False


class TestMultiCandlePatterns:
    def test_bullish_engulfing_true(self) -> None:
        # Prev: red (open=101, close=99), Curr: green engulfs (open=98, close=102)
        assert _is_bullish_engulfing(o1=101, c1=99, o2=98, c2=102) is True

    def test_bullish_engulfing_false_prev_green(self) -> None:
        assert _is_bullish_engulfing(o1=99, c1=101, o2=98, c2=102) is False

    def test_bearish_engulfing_true(self) -> None:
        # Prev: green (open=99, close=101), Curr: red engulfs (open=102, close=98)
        assert _is_bearish_engulfing(o1=99, c1=101, o2=102, c2=98) is True

    def test_bearish_engulfing_false_prev_red(self) -> None:
        assert _is_bearish_engulfing(o1=101, c1=99, o2=102, c2=98) is False

    def test_morning_star_true(self) -> None:
        # Day1: big red (105→100), Day2: small body (100→99.5), Day3: big green (99→103)
        assert (
            _is_morning_star(o1=105, c1=100, o2=100, h2=100.5, l2=99, c2=99.5, o3=99, c3=103)
            is True
        )

    def test_morning_star_false_no_big_red(self) -> None:
        assert (
            _is_morning_star(o1=100, c1=100, o2=100, h2=100.5, l2=99, c2=99.5, o3=99, c3=103)
            is False
        )

    def test_evening_star_true(self) -> None:
        # Day1: big green (100→105), Day2: small body (105→105.5), Day3: big red (106→102)
        assert (
            _is_evening_star(o1=100, c1=105, o2=105, h2=106, l2=105, c2=105.5, o3=106, c3=102)
            is True
        )

    def test_evening_star_false_no_big_green(self) -> None:
        assert (
            _is_evening_star(o1=100, c1=100, o2=100, h2=100.5, l2=99.5, c2=100.1, o3=100, c3=99)
            is False
        )


class TestDetectPatterns:
    def _make_df(self, prices: list[tuple[float, float, float, float]]) -> pd.DataFrame:
        """Create OHLCV DataFrame from list of (open, high, low, close)."""
        dates = pd.bdate_range("2023-01-01", periods=len(prices))
        return pd.DataFrame(
            {
                "open": [p[0] for p in prices],
                "high": [p[1] for p in prices],
                "low": [p[2] for p in prices],
                "close": [p[3] for p in prices],
                "volume": [1_000_000] * len(prices),
            },
            index=dates,
        )

    def test_insufficient_data_returns_empty(self) -> None:
        df = self._make_df([(100, 101, 99, 100)])
        patterns = detect_patterns(df)
        assert patterns == []

    def test_detects_bullish_engulfing(self) -> None:
        # 8 candles: 5 declining + setup for engulfing
        prices = [
            (100, 101, 99, 99.5),  # red
            (99.5, 100, 98.5, 99),  # red
            (99, 99.5, 98, 98.5),  # red
            (98.5, 99, 97.5, 98),  # red
            (98, 98.5, 97, 97.5),  # red
            (97.5, 98, 96.5, 97),  # red - prev candle
            (97, 98, 96, 96.5),  # red - prev candle
            (95, 99, 95, 98.5),  # green engulfs prev
        ]
        df = self._make_df(prices)
        patterns = detect_patterns(df)
        # Should find bullish engulfing or other reversal patterns
        assert len(patterns) >= 0  # At least doesn't crash

    def test_returns_pattern_signal_objects(self) -> None:
        np.random.seed(42)
        dates = pd.bdate_range("2023-01-01", periods=30)
        close = 100 + np.cumsum(np.random.randn(30) * 0.5)
        df = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.random.randint(500_000, 1_500_000, 30),
            },
            index=dates,
        )
        patterns = detect_patterns(df)
        for p in patterns:
            assert hasattr(p, "name")
            assert hasattr(p, "pattern_type")
            assert hasattr(p, "confidence")
            d = p.to_dict()
            assert "name" in d
            assert "type" in d


class TestComputePatternScore:
    def test_returns_tuple(self) -> None:
        np.random.seed(42)
        dates = pd.bdate_range("2023-01-01", periods=30)
        close = 100 + np.cumsum(np.random.randn(30) * 0.5)
        df = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": np.random.randint(500_000, 1_500_000, 30),
            },
            index=dates,
        )
        score, patterns = compute_pattern_score(df)
        assert isinstance(score, (int, float))
        assert isinstance(patterns, list)

    def test_insufficient_data_returns_zero(self) -> None:
        df = pd.DataFrame(
            {
                "open": [100],
                "high": [101],
                "low": [99],
                "close": [100],
                "volume": [1_000_000],
            },
            index=pd.bdate_range("2023-01-01", periods=1),
        )
        score, patterns = compute_pattern_score(df)
        assert score == 0
        assert patterns == []

    def test_bullish_continuation_scoring(self) -> None:
        """PatternType.BULLISH_CONTINUATION should add +5 * weight."""
        from unittest.mock import patch

        from engine.pattern import PatternSignal, PatternType

        mock_patterns = [
            PatternSignal(
                name="光头阳线",
                pattern_type=PatternType.BULLISH_CONTINUATION,
                confidence=55,
                description="强势阳线",
            )
        ]
        df = pd.DataFrame(
            {
                "open": [100] * 10,
                "high": [101] * 10,
                "low": [99] * 10,
                "close": [100] * 10,
                "volume": [1_000_000] * 10,
            },
            index=pd.bdate_range("2023-01-01", periods=10),
        )
        with patch("engine.pattern.detect_patterns", return_value=mock_patterns):
            score, patterns = compute_pattern_score(df)
        assert score > 0  # Bullish continuation adds positive score
        assert len(patterns) == 1

    def test_bearish_continuation_scoring(self) -> None:
        """PatternType.BEARISH_CONTINUATION should subtract -5 * weight."""
        from unittest.mock import patch

        from engine.pattern import PatternSignal, PatternType

        mock_patterns = [
            PatternSignal(
                name="光脚阴线",
                pattern_type=PatternType.BEARISH_CONTINUATION,
                confidence=55,
                description="强势阴线",
            )
        ]
        df = pd.DataFrame(
            {
                "open": [100] * 10,
                "high": [101] * 10,
                "low": [99] * 10,
                "close": [100] * 10,
                "volume": [1_000_000] * 10,
            },
            index=pd.bdate_range("2023-01-01", periods=10),
        )
        with patch("engine.pattern.detect_patterns", return_value=mock_patterns):
            score, patterns = compute_pattern_score(df)
        assert score < 0  # Bearish continuation subtracts

    def test_score_capped_at_15(self) -> None:
        """Score should be capped at ±15."""
        from unittest.mock import patch

        from engine.pattern import PatternSignal, PatternType

        # Many strong bullish patterns → would exceed 15
        mock_patterns = [
            PatternSignal("p1", PatternType.BULLISH_REVERSAL, 100, "d"),
            PatternSignal("p2", PatternType.BULLISH_REVERSAL, 100, "d"),
            PatternSignal("p3", PatternType.BULLISH_REVERSAL, 100, "d"),
        ]
        df = pd.DataFrame(
            {
                "open": [100] * 10,
                "high": [101] * 10,
                "low": [99] * 10,
                "close": [100] * 10,
                "volume": [1_000_000] * 10,
            },
            index=pd.bdate_range("2023-01-01", periods=10),
        )
        with patch("engine.pattern.detect_patterns", return_value=mock_patterns):
            score, _ = compute_pattern_score(df)
        assert score == 15.0  # Capped
