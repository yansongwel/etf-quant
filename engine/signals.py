"""Real-time trading signal generator — V5.1 asymmetric buy/sell engine.

V5.1 design:
1. BUY: IC-weighted mean-reversion scoring (threshold 20, 3+ factor consensus)
2. SELL: structural-only signals (ATR stop + MA death cross + RSI div, 2+ required)
3. TIER: action(80%)/watch(58%)/reference — guides trading frequency
4. Per-ETF confidence gating — blacklist unreliable ETFs, boost reliable ones
5. Tightened thresholds: MA偏离<-5%, RSI<30, 量比≥1.2

IMPORTANT: This is for research/education only. Not investment advice.
A-share ETFs follow T+1 rule — signals generated today execute tomorrow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from factors.momentum import momentum, moving_average_ratio, rsi
from factors.value import ma_deviation, price_percentile
from factors.volatility import atr, historical_volatility, max_drawdown

logger = logging.getLogger(__name__)


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


def _safe_last(series: pd.Series) -> float | None:
    """Get last non-NaN value from a series."""
    if series.empty:
        return None
    val = series.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def _volume_ratio(volume: pd.Series) -> float | None:
    """Compute current volume / 20-day moving average."""
    if len(volume) < 21:
        return None
    current = float(volume.iloc[-1])
    ma20 = float(volume.iloc[-21:-1].mean())
    return current / ma20 if ma20 > 0 else None


def _momentum_acceleration(close: pd.Series) -> float | None:
    """5-day momentum minus 20-day momentum. Positive = accelerating up."""
    if len(close) < 21:
        return None
    m5 = _safe_last(momentum(close, 5))
    m20 = _safe_last(momentum(close, 20))
    if m5 is None or m20 is None:
        return None
    return m5 - m20


def _safe_at(series: pd.Series, idx: int) -> float | None:
    """Get value at index, returning None if NaN or out of bounds."""
    if idx < 0 or idx >= len(series):
        return None
    val = series.iloc[idx]
    if pd.isna(val):
        return None
    return float(val)


def precompute_factors(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Precompute all factor series for a full DataFrame.

    Returns a dict of factor name → pd.Series, all aligned to df's index.
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
    from factors.momentum import returns

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
    # IC expected: 0.030-0.035 — strongest when combined
    reversal_in_trend = pd.Series(0.0, index=close.index)
    if len(close) >= 25:
        # Buy: 5d down within 20d uptrend
        buy_combo = (ret_5d < -0.02) & (mom_20 > 0)
        # Sell: 5d up within 20d downtrend
        sell_combo = (ret_5d > 0.02) & (mom_20 < 0)
        reversal_in_trend = buy_combo.astype(float) * 1.0 - sell_combo.astype(float) * 1.0

    # V4.1: ATR trailing stop (sell when price drops below peak - 2*ATR)
    atr_trail_stop = pd.Series(0.0, index=close.index)
    if len(close) >= 20:
        rolling_peak = close.rolling(10).max()
        trail_line = rolling_peak - 2.0 * atr_14
        # 1 = below trailing stop (sell signal), 0 = above
        atr_trail_stop = (close < trail_line).astype(float)

    # V4.1: Volume climax (vol > 3x average at price near peak → distribution)
    vol_climax = pd.Series(0.0, index=close.index)
    if len(close) >= 25:
        price_near_peak = close / close.rolling(20).max() > 0.95
        extreme_vol = vol_ratio > 3.0
        vol_climax = (price_near_peak & extreme_vol).astype(float)

    # V4.1: RSI divergence (price new high but RSI lower → bearish)
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
    2. SELL side: remove individual-factor sell scores, use ONLY structural signals:
       - ATR trailing stop break (trend breakdown)
       - MA death cross + volume decline (trend reversal confirmed)
       - RSI divergence + volume climax (distribution top)
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
    # V5.1: Tightened — correct buys avg -7.6%, wrong avg -5.9%
    # Removed -3% tier (noise), only score at -5% and -8%
    if ma_dev_20 is not None:
        if ma_dev_20 < -0.08:
            score += 14
            bullish_factors += 1
        elif ma_dev_20 < -0.05:
            score += 8
            bullish_factors += 1

    # --- #2 RSI oversold (IC=0.158) ---
    # V5.1: Tightened — correct buys avg RSI=32.7, wrong avg 34.8
    # Removed RSI<35 tier, only score at RSI<30 and RSI<20
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
    # V5.1: Correct buys avg vol_ratio=1.33, wrong=1.17
    # Raised confirmation threshold from 1.0 to 1.2
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
    # Backtested 2026-04-02: individual signal accuracy at T+10:
    #   reversal_in_trend: 76% ← ONLY reliable signal
    #   death_cross+缩量:  62% ← moderate, used as confirmation
    #   ATR stop: 47% ← REMOVED (noise)
    #   RSI div: 49% ← REMOVED (noise)
    #   vol_climax: 40% ← REMOVED (anti-signal)
    #   mom_decel: 47% ← REMOVED (noise)
    # ═══════════════════════════════════════════════════════
    sell_score = 0.0
    sell_signals = 0

    # --- S1: Reversal-in-trend sell (76% at T+10, STRONGEST) ---
    # Rally in a confirmed downtrend → high-probability sell
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
    has_oversold = rsi_14 is not None and rsi_14 < 30
    has_deep_dd = (mdd_60 or 0) > 0.15
    has_buy_confirm = has_vol_confirm or has_oversold or has_deep_dd

    if score >= 30 and has_buy_confirm and bullish_factors >= 3:
        direction = SignalDirection.STRONG_BUY
    elif score >= 20 and has_buy_confirm and bullish_factors >= 3:
        direction = SignalDirection.BUY
    elif sell_signals >= 2 and rit is not None and rit < -0.5:
        # SELL only when reversal_in_trend (76%) + another signal confirm
        direction = SignalDirection.STRONG_SELL
    elif sell_signals >= 1 and rit is not None and rit < -0.5:
        # Single reversal_in_trend alone = SELL (60% at T+5, 76% at T+10)
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
        aggressive: If True, reduce bear-market penalty (0.4 → 0.1) to show
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

    # ── Build factor dict for response ──
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

    # ── Generate reasons from factor values ──
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

    # ── Price targets ──
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

    # ── Position sizing ──
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
    # Buy: T+3~T+5 optimal (64.2% accuracy), T+10 drops to 55.7%
    # Sell: T+10 optimal (reversal_in_trend 76%)
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
