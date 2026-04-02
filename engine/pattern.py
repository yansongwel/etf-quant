"""K-line pattern recognition — technical formation signals.

Identifies classic candlestick patterns and support/resistance levels
to provide secondary confirmation for factor-based trading signals.

Inspired by CZSC (缠论) concepts but simplified for practical ETF trading:
- Single and multi-candle reversal patterns
- Support/resistance from recent pivots
- Pattern confirmation scoring for signal engine integration

All functions are pure: same input → same output. No look-ahead bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class PatternType(str, Enum):  # noqa: UP042
    """Pattern classification."""

    BULLISH_REVERSAL = "bullish_reversal"
    BEARISH_REVERSAL = "bearish_reversal"
    BULLISH_CONTINUATION = "bullish_continuation"
    BEARISH_CONTINUATION = "bearish_continuation"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class PatternSignal:
    """A detected candlestick pattern."""

    name: str
    pattern_type: PatternType
    confidence: float  # 0-100
    description: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.pattern_type.value,
            "confidence": round(self.confidence, 1),
            "description": self.description,
        }


# ─── Single Candle Patterns ─────────────────────────────


def _body(o: float, c: float) -> float:
    return abs(c - o)


def _upper_shadow(h: float, o: float, c: float) -> float:
    return h - max(o, c)


def _lower_shadow(lo: float, o: float, c: float) -> float:
    return min(o, c) - lo


def _is_doji(o: float, h: float, lo: float, c: float) -> bool:
    """Doji: body < 10% of total range."""
    total = h - lo
    if total == 0:
        return True
    return _body(o, c) / total < 0.1


def _is_hammer(o: float, h: float, lo: float, c: float) -> bool:
    """Hammer/Hanging Man: long lower shadow, small body at top."""
    body = _body(o, c)
    lower = _lower_shadow(lo, o, c)
    upper = _upper_shadow(h, o, c)
    total = h - lo
    if total == 0 or body == 0:
        return False
    return lower >= body * 2 and upper < body * 0.5


def _is_shooting_star(o: float, h: float, lo: float, c: float) -> bool:
    """Shooting Star: long upper shadow, small body at bottom."""
    body = _body(o, c)
    lower = _lower_shadow(lo, o, c)
    upper = _upper_shadow(h, o, c)
    if body == 0:
        return False
    return upper >= body * 2 and lower < body * 0.5


def _is_marubozu(o: float, h: float, lo: float, c: float) -> bool:
    """Marubozu: strong body with minimal shadows (>90% body/range)."""
    total = h - lo
    if total == 0:
        return False
    return _body(o, c) / total > 0.9


# ─── Multi-Candle Patterns ──────────────────────────────


def _is_bullish_engulfing(
    o1: float,
    c1: float,
    o2: float,
    c2: float,
) -> bool:
    """Bullish engulfing: prev red, current green body engulfs prev."""
    prev_red = c1 < o1
    curr_green = c2 > o2
    engulfs = o2 <= c1 and c2 >= o1
    return prev_red and curr_green and engulfs


def _is_bearish_engulfing(
    o1: float,
    c1: float,
    o2: float,
    c2: float,
) -> bool:
    """Bearish engulfing: prev green, current red body engulfs prev."""
    prev_green = c1 > o1
    curr_red = c2 < o2
    engulfs = o2 >= c1 and c2 <= o1
    return prev_green and curr_red and engulfs


def _is_morning_star(
    o1: float,
    c1: float,
    o2: float,
    h2: float,
    l2: float,
    c2: float,
    o3: float,
    c3: float,
) -> bool:
    """Morning Star: large red → small body (gap down) → large green."""
    big_red = c1 < o1 and _body(o1, c1) > 0
    small_body = _body(o2, c2) < _body(o1, c1) * 0.3
    big_green = c3 > o3 and c3 > (o1 + c1) / 2
    return big_red and small_body and big_green


def _is_evening_star(
    o1: float,
    c1: float,
    o2: float,
    h2: float,
    l2: float,
    c2: float,
    o3: float,
    c3: float,
) -> bool:
    """Evening Star: large green → small body (gap up) → large red."""
    big_green = c1 > o1 and _body(o1, c1) > 0
    small_body = _body(o2, c2) < _body(o1, c1) * 0.3
    big_red = c3 < o3 and c3 < (o1 + c1) / 2
    return big_green and small_body and big_red


# ─── Support / Resistance ───────────────────────────────


def find_support_resistance(
    df: pd.DataFrame,
    window: int = 20,
    num_levels: int = 3,
) -> dict[str, list[float]]:
    """Find key support and resistance levels from recent pivot points.

    Uses local minima/maxima within rolling windows.
    Returns {'support': [...], 'resistance': [...]}.
    """
    if len(df) < window * 2:
        return {"support": [], "resistance": []}

    high = df["high"]
    low = df["low"]
    close_last = float(df["close"].iloc[-1])

    # Find local maxima (resistance) and minima (support)
    resistances = []
    supports = []

    for i in range(window, len(df) - 1):
        # Local max: highest high in window
        if high.iloc[i] == high.iloc[i - window : i + 1].max():
            resistances.append(float(high.iloc[i]))
        # Local min: lowest low in window
        if low.iloc[i] == low.iloc[i - window : i + 1].min():
            supports.append(float(low.iloc[i]))

    # Filter: support below current price, resistance above
    supports = sorted(set(s for s in supports if s < close_last), reverse=True)[:num_levels]
    resistances = sorted(set(r for r in resistances if r > close_last))[:num_levels]

    return {"support": supports, "resistance": resistances}


# ─── Pattern Detection Engine ───────────────────────────


def detect_patterns(df: pd.DataFrame) -> list[PatternSignal]:
    """Detect candlestick patterns in the last few bars.

    Analyzes the most recent 1-3 candles for reversal and
    continuation patterns. Returns a list of detected patterns.
    """
    if len(df) < 5:
        return []

    patterns: list[PatternSignal] = []
    o, h, lo, c = (
        float(df["open"].iloc[-1]),
        float(df["high"].iloc[-1]),
        float(df["low"].iloc[-1]),
        float(df["close"].iloc[-1]),
    )

    # Previous candles
    o1 = float(df["open"].iloc[-2])
    c1 = float(df["close"].iloc[-2])

    # 3-bar lookback
    o_3 = float(df["open"].iloc[-3])
    c_3 = float(df["close"].iloc[-3])

    # Trend context: 10-day price direction
    recent_trend = float(df["close"].iloc[-1] / df["close"].iloc[-10] - 1) if len(df) >= 10 else 0

    # ── Single candle patterns ──
    if _is_doji(o, h, lo, c):
        conf = 40 if abs(recent_trend) > 0.03 else 20
        patterns.append(
            PatternSignal(
                name="十字星",
                pattern_type=PatternType.BULLISH_REVERSAL
                if recent_trend < -0.02
                else PatternType.BEARISH_REVERSAL
                if recent_trend > 0.02
                else PatternType.NEUTRAL,
                confidence=conf,
                description="市场犹豫不决，可能变盘",
            )
        )

    if _is_hammer(o, h, lo, c) and recent_trend < -0.02:
        patterns.append(
            PatternSignal(
                name="锤子线",
                pattern_type=PatternType.BULLISH_REVERSAL,
                confidence=65,
                description="下跌趋势中出现锤子线，底部反转信号",
            )
        )

    if _is_shooting_star(o, h, lo, c) and recent_trend > 0.02:
        patterns.append(
            PatternSignal(
                name="射击之星",
                pattern_type=PatternType.BEARISH_REVERSAL,
                confidence=60,
                description="上涨趋势中出现射击之星，顶部警告",
            )
        )

    if _is_marubozu(o, h, lo, c):
        if c > o:
            patterns.append(
                PatternSignal(
                    name="光头阳线",
                    pattern_type=PatternType.BULLISH_CONTINUATION,
                    confidence=55,
                    description="强势阳线，买方主导",
                )
            )
        else:
            patterns.append(
                PatternSignal(
                    name="光脚阴线",
                    pattern_type=PatternType.BEARISH_CONTINUATION,
                    confidence=55,
                    description="强势阴线，卖方主导",
                )
            )

    # ── Two candle patterns ──
    if _is_bullish_engulfing(o1, c1, o, c):
        patterns.append(
            PatternSignal(
                name="看涨吞没",
                pattern_type=PatternType.BULLISH_REVERSAL,
                confidence=70,
                description="阳线完全包裹前一根阴线，强烈反转信号",
            )
        )

    if _is_bearish_engulfing(o1, c1, o, c):
        patterns.append(
            PatternSignal(
                name="看跌吞没",
                pattern_type=PatternType.BEARISH_REVERSAL,
                confidence=70,
                description="阴线完全包裹前一根阳线，强烈见顶信号",
            )
        )

    # ── Three candle patterns ──
    if _is_morning_star(
        o_3, c_3, o1, float(df["high"].iloc[-2]), float(df["low"].iloc[-2]), c1, o, c
    ):
        patterns.append(
            PatternSignal(
                name="早晨之星",
                pattern_type=PatternType.BULLISH_REVERSAL,
                confidence=80,
                description="经典三根K线底部反转形态",
            )
        )

    if _is_evening_star(
        o_3, c_3, o1, float(df["high"].iloc[-2]), float(df["low"].iloc[-2]), c1, o, c
    ):
        patterns.append(
            PatternSignal(
                name="黄昏之星",
                pattern_type=PatternType.BEARISH_REVERSAL,
                confidence=80,
                description="经典三根K线顶部反转形态",
            )
        )

    return patterns


def compute_pattern_score(df: pd.DataFrame) -> tuple[float, list[PatternSignal]]:
    """Compute a pattern-based confirmation score.

    Returns (score, patterns) where:
    - score > 0: bullish patterns detected (supports buy signals)
    - score < 0: bearish patterns detected (supports sell signals)
    - score = 0: no clear pattern or neutral

    The score is designed to be added to the factor-based signal score
    as a secondary confirmation layer (max ±15 points).
    """
    patterns = detect_patterns(df)
    if not patterns:
        return 0.0, []

    score = 0.0
    for p in patterns:
        weight = p.confidence / 100.0
        if p.pattern_type == PatternType.BULLISH_REVERSAL:
            score += 10 * weight
        elif p.pattern_type == PatternType.BEARISH_REVERSAL:
            score -= 10 * weight
        elif p.pattern_type == PatternType.BULLISH_CONTINUATION:
            score += 5 * weight
        elif p.pattern_type == PatternType.BEARISH_CONTINUATION:
            score -= 5 * weight

    # Cap at ±15 to prevent pattern from dominating factor signals
    score = max(min(score, 15), -15)
    return round(score, 1), patterns
