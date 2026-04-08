"""Single-ETF signal generation and market regime detection."""

from __future__ import annotations

import logging

import pandas as pd

from engine.signals.helpers import _safe_at, _safe_last
from engine.signals.scoring import precompute_factors, score_at_index
from engine.signals.types import SignalDirection, TradingSignal, classify_tier
from factors.momentum import momentum, moving_average_ratio, rsi
from factors.value import ma_deviation

logger = logging.getLogger(__name__)


def generate_signal(
    df: pd.DataFrame,
    symbol: str = "",
    market_regime: str | None = None,
    aggressive: bool = False,
) -> TradingSignal | None:
    """Generate a trading signal for a single ETF.

    Args:
        df: OHLCV DataFrame with DatetimeIndex. Needs >= 60 rows.
        symbol: ETF code for labeling.
        market_regime: "bull", "bear", or "range". If None, no regime filter.
        aggressive: If True, reduce bear-market penalty (0.4 -> 0.1) to show
            more buy signals. For users with higher risk tolerance.

    Returns:
        TradingSignal or None if insufficient data.
    """
    required = {"open", "high", "low", "close", "volume"}
    if df.empty or len(df) < 60 or not required.issubset(df.columns):
        return None

    close = df["close"]
    current_price = float(close.iloc[-1])

    # Use precompute + score_at_index (single source of truth)
    precomputed = precompute_factors(df)

    # Use aggressive regime penalty if requested
    effective_regime = market_regime
    if aggressive and market_regime == "bear":
        effective_regime = "range"  # Treat bear as range in aggressive mode

    direction, score, n_sell_signals = score_at_index(
        precomputed, len(df) - 1, current_price, market_regime=effective_regime
    )

    # -- Build factor dict for response --
    factors: dict[str, float | None] = {}
    factor_keys = [
        "momentum_20d",
        "momentum_5d",
        "ret_5d",
        "rsi_14",
        "ma_ratio_5_20",
        "ma_dev_20d",
        "hvol_20d",
        "atr_14",
        "mdd_60d",
        "price_pctile_120d",
        "volume_ratio",
        "momentum_accel",
        "mfi_14",
        "obv_trend_20d",
        "vol_price_div_10d",
        "smart_flow_20d",
    ]
    for k in factor_keys:
        s = precomputed.get(k, pd.Series(dtype=float))
        factors[k] = _safe_at(s, len(df) - 1) if len(s) > 0 else None

    # MA deviation 60d (for display only)
    ma_dev_60 = _safe_last(ma_deviation(close, 60))
    factors["ma_dev_60d"] = ma_dev_60

    # ATR for price targets
    atr_val = factors.get("atr_14")

    # -- Generate reasons from factor values --
    reasons: list[str] = []
    ret_5d = factors.get("ret_5d")
    mom_20 = factors.get("momentum_20d")
    rsi_val = factors.get("rsi_14")
    ma_dev = factors.get("ma_dev_20d")
    ma_ratio = factors.get("ma_ratio_5_20")
    vol_ratio = factors.get("volume_ratio")
    mom_accel = factors.get("momentum_accel")
    pctile = factors.get("price_pctile_120d")
    mfi_val = factors.get("mfi_14")

    if ma_dev is not None and abs(ma_dev) > 0.03:
        reasons.append(f"MA20偏离({ma_dev:+.1%})")
    if rsi_val is not None and (rsi_val < 30 or rsi_val > 70):
        reasons.append(f"RSI{'超卖' if rsi_val < 30 else '超买'}({rsi_val:.0f})")
    if ret_5d is not None and abs(ret_5d) > 0.02:
        reasons.append(f"5日{'下跌' if ret_5d < 0 else '上涨'}({ret_5d:+.1%})")
    if mom_accel is not None and abs(mom_accel) > 0.02:
        reasons.append(f"动量{'加速' if mom_accel > 0 else '减速'}")
    if ma_ratio is not None and ma_ratio < 0.99:
        reasons.append("MA5下穿MA20")
    elif ma_ratio is not None and ma_ratio > 1.01:
        reasons.append("MA5上穿MA20")
    if vol_ratio is not None and vol_ratio > 1.8:
        reasons.append(f"放量({vol_ratio:.1f}倍)")
    if pctile is not None and (pctile < 0.15 or pctile > 0.85):
        reasons.append(f"价格{'低位' if pctile < 0.15 else '高位'}(P{pctile:.0%})")
    if mfi_val is not None and (mfi_val < 25 or mfi_val > 75):
        reasons.append(f"MFI{'超卖' if mfi_val < 25 else '超买'}({mfi_val:.0f})")
    if mom_20 is not None and abs(mom_20) > 0.03:
        reasons.append(f"20日{'上涨' if mom_20 > 0 else '下跌'}({mom_20:+.1%})")

    # Pattern layer
    from engine.pattern import compute_pattern_score

    pattern_score, detected_patterns = compute_pattern_score(df)
    if pattern_score != 0:
        score += pattern_score
        for p in detected_patterns:
            if p.confidence >= 50:
                reasons.append(f"K线: {p.name}")
        factors["pattern_score"] = pattern_score

    if not reasons:
        reasons.append("综合评分中性")

    # -- Price targets --
    atr_for_calc = atr_val if atr_val and atr_val > 0 else current_price * 0.02

    if direction in (SignalDirection.STRONG_BUY, SignalDirection.BUY):
        entry_price = current_price * 1.002
        target_price = current_price + 3 * atr_for_calc
        stop_loss = current_price - 1.5 * atr_for_calc
    elif direction in (SignalDirection.STRONG_SELL, SignalDirection.SELL):
        entry_price = current_price * 0.998
        target_price = current_price - 3 * atr_for_calc
        stop_loss = current_price + 2 * atr_for_calc
    else:
        entry_price = current_price
        target_price = current_price + 2 * atr_for_calc
        stop_loss = current_price - 2 * atr_for_calc

    # -- Position sizing --
    strength = min(abs(score), 100)
    position_pct = min(0.03 + (strength / 100) * 0.20, 0.25)

    from factors.volatility import volatility_regime

    if len(close) >= 65:
        vol_reg = _safe_last(volatility_regime(close, 20, 60))
        if vol_reg is not None:
            factors["vol_regime"] = vol_reg
            if vol_reg > 1.5:
                position_pct *= 0.6
                reasons.append(f"波动扩张减仓(VR={vol_reg:.1f})")
            elif vol_reg < 0.7:
                position_pct = min(position_pct * 1.3, 0.30)
                reasons.append(f"波动收敛加仓(VR={vol_reg:.1f})")

    tier = classify_tier(direction, score, n_sell_signals)

    # V5.2: Data-driven holding period recommendation
    is_buy = direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)
    is_sell = direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL)
    holding_days = 5 if is_buy else 10 if is_sell else 0

    return TradingSignal(
        symbol=symbol,
        direction=direction,
        strength=strength,
        current_price=current_price,
        entry_price=entry_price,
        target_price=target_price,
        stop_loss=stop_loss,
        position_pct=position_pct,
        reason=" | ".join(reasons),
        factors=factors,
        score=score,
        tier=tier,
        holding_days=holding_days,
    )


def _detect_market_regime() -> str:
    """Detect current market regime using 510300 (CSI300) as proxy."""
    from data.storage.parquet_store import load_hist

    df = load_hist("510300")
    if df.empty or len(df) < 60:
        return "range"

    close = df["close"]
    m20 = _safe_last(momentum(close, 20))
    m60 = _safe_last(momentum(close, 60)) if len(close) >= 60 else None
    r = _safe_last(rsi(close, 14))
    mar = _safe_last(moving_average_ratio(close, 20, 60)) if len(close) >= 60 else None

    bull_count = 0
    bear_count = 0

    if m20 is not None:
        if m20 > 0.02:
            bull_count += 1
        elif m20 < -0.02:
            bear_count += 1

    if m60 is not None:
        if m60 > 0.05:
            bull_count += 1
        elif m60 < -0.05:
            bear_count += 1

    if r is not None:
        if r > 55:
            bull_count += 1
        elif r < 45:
            bear_count += 1

    if mar is not None:
        if mar > 1.01:
            bull_count += 1
        elif mar < 0.99:
            bear_count += 1

    if bull_count >= 3:
        return "bull"
    if bear_count >= 3:
        return "bear"
    return "range"
