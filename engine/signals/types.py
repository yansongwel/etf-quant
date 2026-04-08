"""Signal types and tier classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SignalDirection(StrEnum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class SignalTier(StrEnum):
    """Signal urgency tier — controls how prominently the signal is displayed.

    Based on backtest data (2026-04-02, 45 ETFs, 60 days):
    - ACTION: score>=50 buy or 3+ sell signals → 80% accuracy, +2.81% avg return
    - WATCH: score 30-49 buy or 2 sell signals → 58% accuracy, +0.41% avg return
    - REFERENCE: score 20-29 buy or weak signals → 57% accuracy, marginal edge
    - NOISE: hold or sub-threshold → no actionable edge
    """

    ACTION = "action"  # 🔴 立即行动 — ~every 12 days, 80% accuracy
    WATCH = "watch"  # 🟡 关注观察 — ~1-2/day, 58% accuracy
    REFERENCE = "reference"  # ⚪ 仅供参考 — noise-adjacent
    NOISE = "noise"  # hold signals, not displayed


def classify_tier(direction: SignalDirection, score: float, sell_signals: int = 0) -> SignalTier:
    """Classify a signal into an urgency tier based on direction and score."""
    if direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY):
        if score >= 50:
            return SignalTier.ACTION
        if score >= 30:
            return SignalTier.WATCH
        return SignalTier.REFERENCE
    if direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL):
        # V5.2: sell tier based on reversal_in_trend + confirmations
        if sell_signals >= 2:
            return SignalTier.ACTION  # reversal_in_trend + confirmation = 76% T+10
        return SignalTier.WATCH  # single reversal_in_trend = 60% T+5
    return SignalTier.NOISE


@dataclass(frozen=True)
class TradingSignal:
    """A real-time trading signal for a single ETF."""

    symbol: str
    direction: SignalDirection
    strength: float  # 0-100, higher = stronger signal
    current_price: float
    entry_price: float  # Suggested buy price (next day open estimate)
    target_price: float  # Take-profit target
    stop_loss: float  # Stop-loss level
    position_pct: float  # Suggested position size as % of portfolio (0-1)
    reason: str  # Human-readable explanation
    factors: dict[str, float | None]  # Key factor values
    score: float  # Composite score (-100 to 100)
    tier: SignalTier = SignalTier.NOISE
    holding_days: int = 5  # Recommended holding period in trading days

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "strength": round(self.strength, 1),
            "current_price": round(self.current_price, 4),
            "entry_price": round(self.entry_price, 4),
            "target_price": round(self.target_price, 4),
            "stop_loss": round(self.stop_loss, 4),
            "position_pct": round(self.position_pct, 4),
            "reason": self.reason,
            "factors": {k: round(v, 4) if v is not None else None for k, v in self.factors.items()},
            "score": round(self.score, 2),
            "tier": self.tier.value,
            "holding_days": self.holding_days,
        }
