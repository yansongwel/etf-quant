"""Factor precomputation and signal scoring logic.

V5.2 asymmetric buy/sell scoring:
- BUY: IC-weighted mean-reversion (14 factors, threshold 20, 3+ consensus)
- SELL: structural-only (reversal_in_trend + confirmations)
"""

from __future__ import annotations

import pandas as pd

from engine.signals.helpers import _safe_at
from engine.signals.types import SignalDirection
from factors.momentum import momentum, moving_average_ratio, returns, rsi
from factors.value import ma_deviation, price_percentile
from factors.volatility import atr, historical_volatility, max_drawdown


def precompute_factors(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Precompute all factor series for a full DataFrame.

    Returns a dict of factor name -> pd.Series, all aligned to df's index.
    Used by backtest to avoid recomputing factors per-day.

    V3.5: Added ret_5d (short-term reversal, IC=-0.022), the strongest predictor.
    """
    close = df["close"]
    volume = df["volume"]

    mom_20 = momentum(close, 20)
    mom_5 = momentum(close, 5)
    rsi_14 = rsi(close, 14)
    ma_ratio_val = moving_average_ratio(close, 5, 20)
    ma_dev_20 = ma_deviation(close, 20)
    hvol_20 = historical_volatility(close, 20)
    atr_14 = atr(df, 14)
    mdd_60_s = max_drawdown(close, 60)
    pctile = price_percentile(close, 120) if len(close) >= 120 else pd.Series(dtype=float)

    # V3.5: Short-term reversal factor (IC=-0.022, strongest predictor)
    ret_5d = returns(close, 5)

    # Volume ratio as a series
    vol_ma20 = volume.rolling(20).mean().shift(1)
    vol_ratio = volume / vol_ma20

    # Momentum acceleration as a series
    mom_accel = mom_5 - mom_20

    # Flow factors
    from factors.flow import (
        money_flow_index,
        on_balance_volume_trend,
        smart_money_flow,
        volume_price_divergence,
    )

    mfi_14 = money_flow_index(df, 14) if len(df) >= 20 else pd.Series(dtype=float)
    obv_trend = (
        on_balance_volume_trend(close, volume, 20) if len(df) >= 30 else pd.Series(dtype=float)
    )
    vol_price_div = (
        volume_price_divergence(close, volume, 10) if len(df) >= 20 else pd.Series(dtype=float)
    )
    # V3.5.1: Smart money flow (5d IC=+0.023, medium-term confirmation)
    smf_20 = smart_money_flow(close, volume, 20) if len(df) >= 25 else pd.Series(dtype=float)

    # V4.1: Reversal-in-trend combo (5d reversal within 20d trend direction)
    reversal_in_trend = pd.Series(0.0, index=close.index)
    if len(close) >= 25:
        buy_combo = (ret_5d < -0.02) & (mom_20 > 0)
        sell_combo = (ret_5d > 0.02) & (mom_20 < 0)
        reversal_in_trend = buy_combo.astype(float) * 1.0 - sell_combo.astype(float) * 1.0

    # V4.1: ATR trailing stop (sell when price drops below peak - 2*ATR)
    atr_trail_stop = pd.Series(0.0, index=close.index)
    if len(close) >= 20:
        rolling_peak = close.rolling(10).max()
        trail_line = rolling_peak - 2.0 * atr_14
        atr_trail_stop = (close < trail_line).astype(float)

    # V4.1: Volume climax (vol > 3x average at price near peak -> distribution)
    vol_climax = pd.Series(0.0, index=close.index)
    if len(close) >= 25:
        price_near_peak = close / close.rolling(20).max() > 0.95
        extreme_vol = vol_ratio > 3.0
        vol_climax = (price_near_peak & extreme_vol).astype(float)

    # V4.1: RSI divergence (price new high but RSI lower -> bearish)
    rsi_divergence = pd.Series(0.0, index=close.index)
    if len(close) >= 25:
        price_at_20h = close >= close.rolling(20).max()
        rsi_below_prev_peak = rsi_14 < rsi_14.rolling(20).max().shift(1)
        rsi_divergence = (price_at_20h & rsi_below_prev_peak).astype(float)

    return {
        "momentum_20d": mom_20,
        "momentum_5d": mom_5,
        "ret_5d": ret_5d,
        "rsi_14": rsi_14,
        "ma_ratio_5_20": ma_ratio_val,
        "ma_dev_20d": ma_dev_20,
        "hvol_20d": hvol_20,
        "atr_14": atr_14,
        "mdd_60d": mdd_60_s,
        "price_pctile_120d": pctile,
        "volume_ratio": vol_ratio,
        "momentum_accel": mom_accel,
        "mfi_14": mfi_14,
        "obv_trend_20d": obv_trend,
        "vol_price_div_10d": vol_price_div,
        "smart_flow_20d": smf_20,
        # V4.1 new factors
        "reversal_in_trend": reversal_in_trend,
        "atr_trail_stop": atr_trail_stop,
        "vol_climax": vol_climax,
        "rsi_divergence": rsi_divergence,
    }


def score_at_index(
    factors: dict[str, pd.Series],
    idx: int,
    current_price: float,
    market_regime: str | None = None,
) -> tuple[SignalDirection, float, int]:
    """Score a single time point using precomputed factor series.

    Returns (direction, score, sell_signals) where sell_signals is the count
    of structural sell triggers (used for tier classification).

    V5.0 — Asymmetric buy/sell redesign (2026-04-02):
    Problem diagnosed: V4.3 sell accuracy 48.7% (worse than random).
    Root cause: "overbought=sell" is wrong for A-share ETFs — momentum persists.

    V5.0 changes:
    1. BUY side: keep IC-weighted mean-reversion scoring (works at 61.9% for high-score)
    2. SELL side: remove individual-factor sell scores, use ONLY structural signals
    3. BUY threshold: 20 (was 12) — cut 52% noise signals
    4. BUY gate: 3+ bullish factors (was 2) — require consensus
    5. SELL gate: 2+ structural signals required (was 1 bearish factor)
    """
    mom_20 = _safe_at(factors["momentum_20d"], idx)
    mom_5 = _safe_at(factors["momentum_5d"], idx)
    ret_5d = _safe_at(factors.get("ret_5d", pd.Series(dtype=float)), idx)
    rsi_14 = _safe_at(factors["rsi_14"], idx)
    ma_ratio = _safe_at(factors["ma_ratio_5_20"], idx)
    ma_dev_20 = _safe_at(factors["ma_dev_20d"], idx)
    hvol = _safe_at(factors["hvol_20d"], idx)
    mdd_60 = _safe_at(factors["mdd_60d"], idx)
    pctile = (
        _safe_at(factors["price_pctile_120d"], idx)
        if len(factors["price_pctile_120d"]) > 0
        else None
    )
    vol_ratio = _safe_at(factors["volume_ratio"], idx)
    mom_accel = _safe_at(factors["momentum_accel"], idx)
    mfi = _safe_at(factors.get("mfi_14", pd.Series(dtype=float)), idx)
    obv_t = _safe_at(factors.get("obv_trend_20d", pd.Series(dtype=float)), idx)
    vpd = _safe_at(factors.get("vol_price_div_10d", pd.Series(dtype=float)), idx)
    smf = _safe_at(factors.get("smart_flow_20d", pd.Series(dtype=float)), idx)

    # ═══════════════════════════════════════════════════════
    # BUY SCORING — IC-weighted mean-reversion (proven at 62%)
    # ═══════════════════════════════════════════════════════
    score = 0.0
    bullish_factors = 0

    # --- #1 MA deviation (IC=0.193, STRONGEST) ---
    if ma_dev_20 is not None:
        if ma_dev_20 < -0.08:
            score += 14
            bullish_factors += 1
        elif ma_dev_20 < -0.05:
            score += 8
            bullish_factors += 1

    # --- #2 RSI oversold (IC=0.158) ---
    if rsi_14 is not None:
        if rsi_14 < 20:
            score += 12
            bullish_factors += 1
        elif rsi_14 < 30:
            score += 6
            bullish_factors += 1

    # --- #3 Short-term reversal ret_5d (IC=0.140) ---
    if ret_5d is not None:
        if ret_5d < -0.04:
            score += 8
            bullish_factors += 1
        elif ret_5d < -0.02:
            score += 4
            bullish_factors += 1

    # --- #4 Momentum 5d + 20d (IC=0.140/0.144) ---
    if mom_5 is not None and mom_5 < -0.03:
        score += 6
        bullish_factors += 1

    if mom_20 is not None and mom_20 < -0.05:
        score += 5
        bullish_factors += 1

    # --- #5 MA ratio oversold (IC=0.129) ---
    if ma_ratio is not None:
        if ma_ratio < 0.97:
            score += 5
            bullish_factors += 1
        elif ma_ratio < 0.99:
            score += 2

    # --- #6 Volume-price divergence bullish (IC=0.130) ---
    if vpd is not None:
        if vpd > 1.0:
            score += 6
            bullish_factors += 1
        elif vpd > 0.5:
            score += 3

    # --- #7 MFI oversold (IC=0.119) ---
    if mfi is not None:
        if mfi < 20:
            score += 5
            bullish_factors += 1
        elif mfi < 30:
            score += 2

    # --- #8 Max drawdown (IC=0.100) ---
    if mdd_60 is not None:
        if mdd_60 > 0.20:
            score += 5
            bullish_factors += 1
        elif mdd_60 > 0.12:
            score += 2

    # --- #9 Volume confirms buy direction (IC=0.079) ---
    if vol_ratio is not None:
        if vol_ratio >= 2.0 and score > 0:
            score += 5
            bullish_factors += 1
        elif vol_ratio >= 1.2 and score > 0:
            score += 2
        elif vol_ratio < 0.5 and score > 0:
            score -= 3  # Low volume strongly weakens buy

    # --- #10 Price percentile low (weak) ---
    if pctile is not None and pctile < 0.10:
        score += 3
        bullish_factors += 1

    # --- #11 Smart money flow contrarian (IC=0.050) ---
    if smf is not None and smf < -0.3:
        score += 3
        bullish_factors += 1

    # --- #12 Reversal-in-trend buy: dip in uptrend ---
    rit = _safe_at(factors.get("reversal_in_trend", pd.Series(dtype=float)), idx)
    if rit is not None and rit > 0.5:
        score += 6
        bullish_factors += 1

    # --- #13 OBV + hvol (weak, confirmation only) ---
    if obv_t is not None and obv_t > 0.02 and score > 5:
        score += 2

    if hvol is not None and hvol > 0.4:
        score += 2

    # --- #14 Momentum acceleration (weak, buy boost only) ---
    if mom_accel is not None and mom_accel > 0.03:
        score += 3

    # --- #15 Calendar effect ---
    if idx < len(factors.get("momentum_20d", pd.Series(dtype=float))):
        try:
            date_index = factors["momentum_20d"].index
            if idx < len(date_index):
                month = date_index[idx].month
                day = date_index[idx].day
                if month == 2 or (month == 12 and day >= 15):
                    score += 2
        except (IndexError, AttributeError):
            pass

    # ═══════════════════════════════════════════════════════
    # SELL SCORING — V5.2 data-driven (only proven signals)
    # ═══════════════════════════════════════════════════════
    sell_score = 0.0
    sell_signals = 0

    # --- S1: Reversal-in-trend sell (76% at T+10, STRONGEST) ---
    if rit is not None and rit < -0.5:
        sell_score -= 12
        sell_signals += 1

    # --- S2: Death cross + volume decline (62% at T+10) ---
    has_death_cross = ma_ratio is not None and ma_ratio < 0.98
    has_vol_decline = vol_ratio is not None and vol_ratio < 0.8
    if has_death_cross and has_vol_decline:
        sell_score -= 8
        sell_signals += 1

    # --- S3: Death cross + momentum deceleration (weaker confirmation) ---
    has_mom_decel = mom_accel is not None and mom_accel < -0.02
    if has_death_cross and has_mom_decel and not has_vol_decline:
        sell_score -= 5
        sell_signals += 1

    # --- S4: Volume-price bearish divergence (moderate) ---
    if vpd is not None and vpd < -1.5:
        sell_score -= 4
        sell_signals += 1

    # ═══════════════════════════════════════════════════════
    # COMBINE buy score and sell score
    # ═══════════════════════════════════════════════════════
    if score > 0 and sell_signals >= 2:
        score = score + sell_score
    elif sell_signals >= 1:
        score = score + sell_score * 0.5

    # Regime filter
    if market_regime == "bear" and score > 0:
        score -= score * 0.20

    # ═══════════════════════════════════════════════════════
    # DIRECTION DECISION — V5.2 asymmetric thresholds
    # ═══════════════════════════════════════════════════════
    has_vol_confirm = vol_ratio is not None and vol_ratio >= 1.2
    has_strong_vol = vol_ratio is not None and vol_ratio >= 1.5
    has_oversold = rsi_14 is not None and rsi_14 < 30
    has_deep_dd = (mdd_60 or 0) > 0.15
    has_low_mfi = mfi is not None and mfi < 25
    has_buy_confirm = has_vol_confirm or has_oversold or has_deep_dd

    # V5.2: Score 30+ needs standard confirmation
    # Score 20-29 needs stronger confirmation (vol>=1.5 or MFI<25 or mom_20<-8%)
    has_strong_confirm = has_strong_vol or has_low_mfi or (mom_20 is not None and mom_20 < -0.08)

    if score >= 30 and has_buy_confirm and bullish_factors >= 3:
        direction = SignalDirection.STRONG_BUY
    elif score >= 20 and has_strong_confirm and bullish_factors >= 3:
        direction = SignalDirection.BUY
    elif sell_signals >= 2 and rit is not None and rit < -0.5:
        direction = SignalDirection.STRONG_SELL
    elif sell_signals >= 1 and rit is not None and rit < -0.5:
        direction = SignalDirection.SELL
    else:
        direction = SignalDirection.HOLD

    # Buy quality gate: anti-chase filter
    if (
        direction == SignalDirection.BUY
        and mom_accel is not None
        and mom_accel > 0.02
        and not has_vol_confirm
    ):
        direction = SignalDirection.HOLD

    # Sell quality gate: protect strong uptrends
    if (
        direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL)
        and mom_20 is not None
        and mom_20 > 0.10
        and rsi_14 is not None
        and rsi_14 < 65
    ):
        direction = SignalDirection.HOLD

    return direction, score, sell_signals
