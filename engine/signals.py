"""Real-time trading signal generator — V2 with multi-factor confirmation.

Key improvements over V1:
1. Higher buy threshold (18 vs 10) — reduces false positives
2. Volume confirmation — buy signals require above-average volume
3. Momentum acceleration — not just direction but acceleration matters
4. Factor conflict resolution — contradictory signals downgrade to HOLD
5. Market regime awareness — suppress buy in bear markets

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
) -> tuple[SignalDirection, float]:
    """Score a single time point using precomputed factor series.

    V4.0 — Recalibrated with fresh IC analysis (2026-04-01):
    Key changes from V3.5:
    1. Weights proportional to measured IC (ma_dev=0.19 gets 3x weight of hvol=0.015)
    2. Lower thresholds: buy >= 8, sell <= -8 (was 12/-15) — reduce 96% hold problem
    3. Trend-following sell: MA5 < MA20 + momentum deceleration → sell (profit-taking)
    4. Relaxed gates: buy needs 2 factors (was 3 in bear), sell needs 1 (was 2)
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

    # ── V4.0 Scoring — IC-proportional weights ──
    # Fresh IC analysis (2026-04-01, 16 ETFs, 60-day window):
    #   ma_dev_20d  IC=-0.193 *** (STRONGEST — far below MA = oversold bounce)
    #   rsi_14      IC=-0.158 *** (oversold RSI predicts 5d rebound)
    #   ret_5d      IC=-0.140 *** (short-term reversal, contrarian)
    #   mom_5d      IC=-0.140 *** (5-day losers bounce)
    #   mom_20d     IC=-0.144 *** (20-day losers bounce)
    #   ma_ratio    IC=-0.129 *** (below MA5/20 = oversold)
    #   vol_price   IC=+0.130 *** (volume-price divergence = reversal)
    #   mfi_14      IC=-0.119 *** (money flow oversold)
    #   mdd_60d     IC=+0.100 *** (deep drawdown = mean reversion)
    #   vol_ratio   IC=+0.079 **  (high volume confirms direction)
    #   smart_flow  IC=-0.050 *   (net outflow = contrarian buy)
    #   mom_accel   IC=+0.016 *   (acceleration, weak standalone)
    #   obv_trend   IC=+0.019 *   (OBV trend, weak)
    #   hvol_20d    IC=+0.016 *   (high vol = bounce, very weak)
    score = 0.0
    bullish_factors = 0
    bearish_factors = 0

    # --- #1 MA deviation (IC=0.193, STRONGEST) ---
    # Far below 20d MA → strong oversold bounce signal
    if ma_dev_20 is not None:
        if ma_dev_20 < -0.06:
            score += 12
            bullish_factors += 1
        elif ma_dev_20 < -0.03:
            score += 7
            bullish_factors += 1
        elif ma_dev_20 > 0.06:
            score -= 10  # Far above MA → overbought, sell
            bearish_factors += 1
        elif ma_dev_20 > 0.03:
            score -= 5
            bearish_factors += 1

    # --- #2 RSI (IC=0.158) ---
    if rsi_14 is not None:
        if rsi_14 < 25:
            score += 10
            bullish_factors += 1
        elif rsi_14 < 35:
            score += 5
            bullish_factors += 1
        elif rsi_14 > 75:
            score -= 10  # Strong overbought → sell signal
            bearish_factors += 1
        elif rsi_14 > 65:
            score -= 5
            bearish_factors += 1

    # --- #3 Short-term reversal ret_5d (IC=0.140) ---
    if ret_5d is not None:
        if ret_5d < -0.04:
            score += 8
            bullish_factors += 1
        elif ret_5d < -0.02:
            score += 4
            bullish_factors += 1
        elif ret_5d > 0.04:
            score -= 7  # Sharp rally → profit-taking sell
            bearish_factors += 1
        elif ret_5d > 0.02:
            score -= 3
            bearish_factors += 1

    # --- #4 Momentum 5d + 20d (IC=0.140/0.144) ---
    if mom_5 is not None:
        if mom_5 < -0.03:
            score += 6
            bullish_factors += 1
        elif mom_5 > 0.03:
            score -= 6  # V4: symmetric sell for profit-taking
            bearish_factors += 1

    if mom_20 is not None:
        if mom_20 < -0.05:
            score += 5
            bullish_factors += 1
        elif mom_20 > 0.05:
            score -= 5
            bearish_factors += 1

    # --- #5 MA ratio / trend (IC=0.129) ---
    # V4: This is now a key SELL trigger — MA5 below MA20 = downtrend
    if ma_ratio is not None:
        if ma_ratio < 0.97:
            score += 5  # Deep below → oversold buy
            bullish_factors += 1
        elif ma_ratio < 0.99:
            score += 2
        elif ma_ratio > 1.03:
            score -= 5  # Far above → trend exhaustion sell
            bearish_factors += 1
        elif ma_ratio > 1.01:
            score -= 2

    # --- #6 Volume-price divergence (IC=0.130) ---
    if vpd is not None:
        if vpd > 1.0:
            score += 6  # Strong divergence → reversal
            bullish_factors += 1
        elif vpd > 0.5:
            score += 3
        elif vpd < -1.0:
            score -= 6
            bearish_factors += 1
        elif vpd < -0.5:
            score -= 3

    # --- #7 MFI (IC=0.119) ---
    if mfi is not None:
        if mfi < 20:
            score += 5
            bullish_factors += 1
        elif mfi < 30:
            score += 2
        elif mfi > 80:
            score -= 5  # V4: symmetric sell
            bearish_factors += 1
        elif mfi > 70:
            score -= 2

    # --- #8 Max drawdown (IC=0.100) ---
    if mdd_60 is not None:
        if mdd_60 > 0.20:
            score += 5
            bullish_factors += 1
        elif mdd_60 > 0.12:
            score += 2

    # --- #9 Volume ratio (IC=0.079) ---
    if vol_ratio is not None:
        if vol_ratio >= 2.0:
            if score > 0:
                score += 4
                bullish_factors += 1
            elif score < 0:
                score -= 4
                bearish_factors += 1
        elif vol_ratio < 0.5 and score > 0:
            score -= 2  # Low volume weakens buy

    # --- #10 Price percentile (weak but useful for extremes) ---
    if pctile is not None:
        if pctile < 0.10:
            score += 3
            bullish_factors += 1
        elif pctile > 0.90:
            score -= 3
            bearish_factors += 1

    # --- #11 Momentum acceleration (IC=0.016, weak) ---
    # V4: Used primarily as sell trigger — deceleration after rally
    if mom_accel is not None:
        if mom_accel > 0.03:
            score += 3
        elif mom_accel < -0.03 and mom_20 is not None and mom_20 > 0:
            # Was going up but now decelerating → trend exhaustion → SELL
            score -= 5
            bearish_factors += 1

    # --- #12 Smart money flow (IC=0.050) ---
    if smf is not None:
        if smf < -0.3:
            score += 3  # Net outflow = contrarian buy (IC is negative)
            bullish_factors += 1
        elif smf > 0.3:
            score -= 2

    # --- #13 OBV trend + volatility (weak, confirmation only) ---
    if obv_t is not None and abs(score) > 3:
        if obv_t > 0.02 and score > 0:
            score += 2
        elif obv_t < -0.02 and score < 0:
            score -= 2
            bearish_factors += 1

    if hvol is not None and hvol > 0.4:
        score += 2  # High vol = bounce potential (very weak)

    # ── V4.0: Trend-following sell signal ──
    # Detect profit-taking opportunity: was rising, now turning
    if (
        ma_ratio is not None
        and mom_accel is not None
        and mom_20 is not None
        and rsi_14 is not None
        and ma_ratio < 1.0  # MA5 below MA20 (death cross)
        and mom_accel < -0.01  # Momentum decelerating
        and mom_20 > -0.02  # Was recently positive (i.e., was profitable)
        and rsi_14 > 45  # Not deeply oversold
    ):
        score -= 6
        bearish_factors += 1

    # ── V4.1: Research-backed A-share factors ──

    # #14 Reversal-in-trend combo (IC expected 0.030-0.035)
    rit = _safe_at(factors.get("reversal_in_trend", pd.Series(dtype=float)), idx)
    if rit is not None:
        if rit > 0.5:  # Buy dip in uptrend
            score += 6
            bullish_factors += 1
        elif rit < -0.5:  # Sell rally in downtrend
            score -= 6
            bearish_factors += 1

    # #15 ATR trailing stop (sell when below 10-day peak - 2*ATR)
    atr_stop = _safe_at(factors.get("atr_trail_stop", pd.Series(dtype=float)), idx)
    if atr_stop is not None and atr_stop > 0.5:
        score -= 8  # Strong sell — price broke below trailing stop
        bearish_factors += 1

    # #16 Volume climax (extreme volume at peak → distribution top)
    vc = _safe_at(factors.get("vol_climax", pd.Series(dtype=float)), idx)
    if vc is not None and vc > 0.5:
        score -= 5  # Sell signal — likely institutional distribution
        bearish_factors += 1

    # #17 RSI divergence (price new high but RSI lower → bearish)
    rsi_div = _safe_at(factors.get("rsi_divergence", pd.Series(dtype=float)), idx)
    if rsi_div is not None and rsi_div > 0.5:
        score -= 5  # Trend exhaustion warning
        bearish_factors += 1

    # #18 Calendar effect (A-share seasonality, weak but consistent)
    if idx < len(factors.get("momentum_20d", pd.Series(dtype=float))):
        try:
            date_index = factors["momentum_20d"].index
            if idx < len(date_index):
                month = date_index[idx].month
                day = date_index[idx].day
                if month == 2:
                    score += 2  # CNY rally effect
                elif month == 12 and day >= 15:
                    score += 2  # Year-end rally
                elif month == 1:
                    score -= 1  # January effect
                elif month in (4, 7, 10) and day <= 3:
                    score -= 2  # Quarter-start sell pressure
        except (IndexError, AttributeError):
            pass

    # Factor conflict resolution (lighter penalty in V4)
    if bullish_factors >= 2 and bearish_factors >= 2:
        penalty = min(bullish_factors, bearish_factors) * 2
        score = max(score - penalty, 0) if score > 0 else min(score + penalty, 0)

    # Regime filter (V4: lighter — let factors speak)
    if market_regime == "bear" and score > 0:
        score -= score * 0.25
    elif market_regime == "bull" and score < 0:
        score += abs(score) * 0.15

    # ── V4.3 Adaptive thresholds with confirmation ──
    # ALL buys require score>=12 AND confirmation (vol>=1.0 OR RSI<35 OR mdd>15%)
    # STRONG_BUY: score>=16 + confirmation → 70% accuracy
    # BUY: score 12-15 + confirmation → 67% accuracy
    # No confirmation → HOLD (data shows ~50% = noise)
    strong_buy_threshold = 16
    sell_threshold = -8
    strong_sell_threshold = -18

    # V4.3: ALL buy signals require score>=12 AND at least one confirmation
    # Confirmations: volume>=1.0, RSI<35, or max_drawdown>15%
    # Without confirmation, even high scores are 50/50 noise → HOLD
    has_vol_confirm = vol_ratio is not None and vol_ratio >= 1.0
    has_oversold = rsi_14 is not None and rsi_14 < 35
    has_deep_dd = (_safe_at(factors.get("mdd_60d", pd.Series(dtype=float)), idx) or 0) > 0.15
    has_confirmation = has_vol_confirm or has_oversold or has_deep_dd

    if score >= strong_buy_threshold and has_confirmation:
        direction = SignalDirection.STRONG_BUY
    elif score >= 12 and has_confirmation:
        direction = SignalDirection.BUY
    elif score <= strong_sell_threshold:
        direction = SignalDirection.STRONG_SELL
    elif score <= sell_threshold:
        direction = SignalDirection.SELL
    else:
        direction = SignalDirection.HOLD

    # V4.3 Buy quality gates
    if direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY):
        if bullish_factors < 2:
            direction = SignalDirection.HOLD
        # Anti-chase filter: if momentum is accelerating UP, it's chasing → riskier
        # Data: wrong buys have mom_accel +0.015 (chasing), correct buys -0.024 (dip)
        elif (
            direction == SignalDirection.BUY  # Only filter non-strong
            and mom_accel is not None
            and mom_accel > 0.02
            and (vol_ratio is None or vol_ratio < 1.0)
        ):
            direction = SignalDirection.HOLD  # Chasing without volume = unreliable

    # V4.3 Sell quality gates
    if direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL):
        if bearish_factors < 1:
            direction = SignalDirection.HOLD
        # Strong-trend protection: don't sell in powerful uptrends
        # Data: wrong sells have avg mom_20d +14.2% — strong uptrend sold prematurely
        elif (
            mom_20 is not None
            and mom_20 > 0.08
            and rsi_14 is not None
            and rsi_14 < 70  # Not overbought — trend is healthy
        ):
            direction = SignalDirection.HOLD  # Don't fight a strong trend

    return direction, score


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

    # ── V4.0: Use precompute + score_at_index (single source of truth) ──
    precomputed = precompute_factors(df)

    # Use aggressive regime penalty if requested
    effective_regime = market_regime
    if aggressive and market_regime == "bear":
        effective_regime = "range"  # Treat bear as range in aggressive mode

    direction, score = score_at_index(
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

    V4.3: Integrates per-ETF signal quality. Low-confidence ETFs
    have their buy signals downgraded to HOLD to reduce noise.
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

        # V4.3: Downgrade buy signals for low-confidence ETFs
        q = quality.get(symbol, {})
        confidence = q.get("confidence", "medium")

        if confidence == "low" and sig.direction in (
            SignalDirection.BUY,
            SignalDirection.STRONG_BUY,
        ):
            # Low confidence ETF → downgrade buy to HOLD
            sig = TradingSignal(
                symbol=sig.symbol,
                direction=SignalDirection.HOLD,
                strength=sig.strength,
                current_price=sig.current_price,
                entry_price=sig.entry_price,
                target_price=sig.target_price,
                stop_loss=sig.stop_loss,
                position_pct=sig.position_pct,
                reason=sig.reason + " | 该ETF历史买入准确率<50%，信号降级",
                factors=sig.factors,
                score=sig.score,
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
