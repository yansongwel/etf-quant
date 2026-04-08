"""Batch signal generation and position calculation."""

from __future__ import annotations

import logging

import pandas as pd

from engine.signals.generator import _detect_market_regime, generate_signal
from engine.signals.types import SignalDirection, SignalTier, TradingSignal

logger = logging.getLogger(__name__)


def generate_signals_batch(
    data: dict[str, pd.DataFrame],
) -> list[TradingSignal]:
    """Generate signals for multiple ETFs and sort by score.

    V5.1: Per-ETF signal quality gating. Low-confidence ETFs have
    buy signals downgraded to HOLD. High-confidence ETFs get tier boost.
    """
    regime = _detect_market_regime()
    logger.info("Market regime: %s", regime)

    # Load per-ETF quality scores (cached for 1 hour)
    try:
        from engine.signal_quality import compute_signal_quality

        quality = compute_signal_quality()
    except Exception:
        quality = {}

    signals = []
    for symbol, df in data.items():
        sig = generate_signal(df, symbol, market_regime=regime)
        if sig is None:
            continue

        # V5.0: Per-ETF confidence gating — downgrade signals for unreliable ETFs
        q = quality.get(symbol, {})
        confidence = q.get("confidence", "medium")
        buy_acc = q.get("buy_accuracy", 50.0)

        if confidence == "low" and sig.direction in (
            SignalDirection.BUY,
            SignalDirection.STRONG_BUY,
        ):
            sig = TradingSignal(
                symbol=sig.symbol,
                direction=SignalDirection.HOLD,
                strength=sig.strength,
                current_price=sig.current_price,
                entry_price=sig.entry_price,
                target_price=sig.target_price,
                stop_loss=sig.stop_loss,
                position_pct=sig.position_pct,
                reason=sig.reason + f" | 该ETF历史买入准确率{buy_acc:.0f}%，信号降级",
                factors=sig.factors,
                score=sig.score,
                tier=SignalTier.NOISE,
            )

        # V5.0: Boost high-confidence ETF signals to higher tier
        if confidence == "high" and sig.tier == SignalTier.WATCH:
            sig = TradingSignal(
                symbol=sig.symbol,
                direction=sig.direction,
                strength=sig.strength,
                current_price=sig.current_price,
                entry_price=sig.entry_price,
                target_price=sig.target_price,
                stop_loss=sig.stop_loss,
                position_pct=min(sig.position_pct * 1.3, 0.30),
                reason=sig.reason + f" | 高置信ETF({buy_acc:.0f}%准确率)",
                factors=sig.factors,
                score=sig.score,
                tier=SignalTier.ACTION,
            )

        signals.append(sig)

    # V5.2: Multi-signal resonance boost
    buy_count = sum(
        1 for s in signals if s.direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)
    )
    if buy_count >= 3:
        boosted = []
        for sig in signals:
            if (
                sig.direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)
                and sig.tier == SignalTier.WATCH
            ):
                sig = TradingSignal(
                    symbol=sig.symbol,
                    direction=sig.direction,
                    strength=sig.strength,
                    current_price=sig.current_price,
                    entry_price=sig.entry_price,
                    target_price=sig.target_price,
                    stop_loss=sig.stop_loss,
                    position_pct=sig.position_pct,
                    reason=sig.reason + f" | 多信号共振({buy_count}只同时买入)",
                    factors=sig.factors,
                    score=sig.score,
                    tier=SignalTier.ACTION,
                    holding_days=sig.holding_days,
                )
            boosted.append(sig)
        signals = boosted

    signals.sort(key=lambda s: s.score, reverse=True)
    return signals


def calculate_positions(
    signals: list[TradingSignal],
    capital: float,
    max_positions: int = 5,
) -> list[dict]:
    """Convert signals to concrete position recommendations.

    Args:
        signals: Sorted signals (best first).
        capital: Available capital in CNY.
        max_positions: Maximum number of simultaneous positions.

    Returns:
        List of position dicts with buy_amount, shares, etc.
    """
    buy_signals = [
        s for s in signals if s.direction in (SignalDirection.STRONG_BUY, SignalDirection.BUY)
    ]
    positions: list[dict] = []
    remaining = capital

    for sig in buy_signals[:max_positions]:
        if remaining <= 100:
            break

        # Position size based on signal strength and portfolio limit
        alloc = min(sig.position_pct * capital, remaining * 0.8)
        alloc = max(alloc, 100)  # At least 100 CNY

        # ETF shares must be in lots of 100
        shares = int(alloc / sig.entry_price / 100) * 100
        if shares <= 0:
            shares = 100  # Minimum 1 lot

        buy_amount = shares * sig.entry_price
        if buy_amount > remaining:
            shares = int(remaining / sig.entry_price / 100) * 100
            if shares <= 0:
                continue
            buy_amount = shares * sig.entry_price

        remaining -= buy_amount

        positions.append(
            {
                "symbol": sig.symbol,
                "direction": sig.direction.value,
                "score": round(sig.score, 1),
                "strength": round(sig.strength, 1),
                "current_price": round(sig.current_price, 4),
                "entry_price": round(sig.entry_price, 4),
                "target_price": round(sig.target_price, 4),
                "stop_loss": round(sig.stop_loss, 4),
                "shares": shares,
                "buy_amount": round(buy_amount, 2),
                "expected_gain": round((sig.target_price - sig.entry_price) * shares, 2),
                "max_loss": round((sig.entry_price - sig.stop_loss) * shares, 2),
                "risk_reward": round(
                    (sig.target_price - sig.entry_price)
                    / max(sig.entry_price - sig.stop_loss, 0.001),
                    2,
                ),
                "reason": sig.reason,
            }
        )

    return positions
