"""Real-time trading signal generator — V5.2 asymmetric buy/sell engine.

V5.2 design:
1. BUY: IC-weighted mean-reversion scoring (threshold 20, 3+ factor consensus)
2. SELL: structural-only signals (ATR stop + MA death cross + RSI div, 2+ required)
3. TIER: action(80%)/watch(58%)/reference — guides trading frequency
4. Per-ETF confidence gating — blacklist unreliable ETFs, boost reliable ones
5. Tightened thresholds: MA偏离<-5%, RSI<30, 量比>=1.2

IMPORTANT: This is for research/education only. Not investment advice.
A-share ETFs follow T+1 rule — signals generated today execute tomorrow.
"""

from engine.signals.batch import calculate_positions, generate_signals_batch
from engine.signals.generator import _detect_market_regime, generate_signal
from engine.signals.helpers import _momentum_acceleration, _safe_at, _safe_last, _volume_ratio
from engine.signals.scoring import precompute_factors, score_at_index
from engine.signals.types import (
    SignalDirection,
    SignalTier,
    TradingSignal,
    classify_tier,
)

__all__ = [
    "SignalDirection",
    "SignalTier",
    "TradingSignal",
    "_detect_market_regime",
    "_momentum_acceleration",
    "_safe_at",
    "_safe_last",
    "_volume_ratio",
    "calculate_positions",
    "classify_tier",
    "generate_signal",
    "generate_signals_batch",
    "precompute_factors",
    "score_at_index",
]
