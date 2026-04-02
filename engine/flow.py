"""Institutional flow detector — detect large order activity via volume/amount anomalies.

Since free data sources (AkShare) don't provide Level2 order-by-order data,
we infer institutional activity through:
1. Volume spike ratio: today_vol / MA(20) — ratio > 2 = abnormal
2. Amount concentration: today_amount / MA(20) — large money flow
3. Volume-price divergence: high volume + small price move = accumulation/distribution
4. Turnover anomaly: sudden turnover increase = position rotation

IMPORTANT: These are probabilistic signals, not proof of institutional activity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FlowType(StrEnum):
    """Detected flow pattern."""

    ACCUMULATION = "accumulation"  # 机构吸筹: 放量不涨
    DISTRIBUTION = "distribution"  # 机构出货: 放量不跌(滞涨)
    BREAKOUT_BUY = "breakout_buy"  # 放量突破: 量价齐升
    PANIC_SELL = "panic_sell"  # 恐慌抛售: 放量大跌
    NORMAL = "normal"  # 无明显异常


FLOW_LABELS: dict[FlowType, str] = {
    FlowType.ACCUMULATION: "🟢 疑似机构吸筹",
    FlowType.DISTRIBUTION: "🔴 疑似机构出货",
    FlowType.BREAKOUT_BUY: "🔵 放量突破买入",
    FlowType.PANIC_SELL: "⚠️ 恐慌性抛售",
    FlowType.NORMAL: "⚪ 正常交易",
}

FLOW_ADVICE: dict[FlowType, str] = {
    FlowType.ACCUMULATION: "价格低位放量可能是机构建仓，可分批布局，设好止损",
    FlowType.DISTRIBUTION: "高位放量滞涨需警惕出货风险，建议减仓或设紧止盈",
    FlowType.BREAKOUT_BUY: "量价齐升趋势明确，可顺势跟入，注意回踩确认",
    FlowType.PANIC_SELL: "恐慌下跌不宜抄底，等待企稳信号再考虑入场",
    FlowType.NORMAL: "成交量正常，按既有策略操作",
}


@dataclass(frozen=True)
class FlowSignal:
    """Flow detection result for a single ETF."""

    symbol: str
    flow_type: FlowType
    volume_ratio: float  # today_vol / MA20_vol
    amount_ratio: float  # today_amount / MA20_amount
    price_change: float  # 当日涨跌幅
    turnover: float  # 换手率 (if available)
    volume_trend_5d: float  # 5日成交量变化趋势
    confidence: float  # 0-100, 检测置信度
    label: str
    advice: str
    details: list[str]  # 具体观察要点

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "flow_type": self.flow_type.value,
            "volume_ratio": round(self.volume_ratio, 2),
            "amount_ratio": round(self.amount_ratio, 2),
            "price_change": round(self.price_change * 100, 2),
            "turnover": round(self.turnover, 2),
            "volume_trend_5d": round(self.volume_trend_5d, 2),
            "confidence": round(self.confidence, 1),
            "label": self.label,
            "advice": self.advice,
            "details": self.details,
        }


def detect_flow(df: pd.DataFrame, symbol: str = "") -> FlowSignal | None:
    """Detect institutional flow patterns for a single ETF.

    Args:
        df: OHLCV DataFrame with columns: open, high, low, close, volume.
            Optional: amount, turnover.
        symbol: ETF code for labeling.

    Returns:
        FlowSignal or None if insufficient data.
    """
    required = {"open", "high", "low", "close", "volume"}
    if df.empty or len(df) < 25 or not required.issubset(df.columns):
        return None

    close = df["close"]
    volume = df["volume"]
    has_amount = "amount" in df.columns
    has_turnover = "turnover" in df.columns

    current_vol = float(volume.iloc[-1])
    current_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])

    # ── Volume ratio (vs 20-day MA) ──
    vol_ma20 = float(volume.iloc[-21:-1].mean())
    vol_ratio = current_vol / vol_ma20 if vol_ma20 > 0 else 1.0

    # ── Amount ratio ──
    if has_amount:
        amount = df["amount"]
        current_amount = float(amount.iloc[-1])
        amt_ma20 = float(amount.iloc[-21:-1].mean())
        amt_ratio = current_amount / amt_ma20 if amt_ma20 > 0 else 1.0
    else:
        amt_ratio = vol_ratio  # Fallback to volume ratio

    # ── Price change ──
    price_change = (current_close - prev_close) / prev_close if prev_close > 0 else 0.0

    # ── Turnover ──
    turnover_val = 0.0
    if has_turnover:
        turnover_val = float(df["turnover"].iloc[-1])

    # ── Volume trend (5-day) ──
    if len(volume) >= 10:
        vol_5d_recent = float(volume.iloc[-5:].mean())
        vol_5d_prev = float(volume.iloc[-10:-5].mean())
        vol_trend_5d = (vol_5d_recent / vol_5d_prev - 1) if vol_5d_prev > 0 else 0.0
    else:
        vol_trend_5d = 0.0

    # ── Pattern detection ──
    details: list[str] = []
    confidence = 0.0

    # Volume spike check
    is_vol_spike = vol_ratio >= 2.0
    is_moderate_spike = vol_ratio >= 1.5

    if is_vol_spike:
        details.append(f"成交量是20日均量的 {vol_ratio:.1f} 倍，明显放量")
        confidence += 30
    elif is_moderate_spike:
        details.append(f"成交量是20日均量的 {vol_ratio:.1f} 倍，温和放量")
        confidence += 15

    if amt_ratio >= 2.0 and has_amount:
        details.append(f"成交额是20日均额的 {amt_ratio:.1f} 倍，大资金活跃")
        confidence += 20

    # Price-volume divergence check
    small_move = abs(price_change) < 0.01  # < 1% move
    big_move_up = price_change > 0.02  # > 2% up
    big_move_down = price_change < -0.02  # > 2% down

    # ── Determine flow type ──
    if is_vol_spike and small_move and price_change >= 0:
        # High volume, price barely moved upward = accumulation
        flow_type = FlowType.ACCUMULATION
        details.append("放量但价格波动小，疑似机构吸筹建仓")
        confidence += 25
    elif is_vol_spike and small_move and price_change < 0:
        # High volume, price barely moved down = could also be accumulation at support
        # or distribution depending on price level
        pctile = _price_percentile(close, 60)
        if pctile is not None and pctile < 0.3:
            flow_type = FlowType.ACCUMULATION
            details.append(f"低位放量(P{pctile:.0%})，可能是承接盘吸筹")
            confidence += 20
        else:
            flow_type = FlowType.DISTRIBUTION
            details.append("放量微跌，可能有大单出货")
            confidence += 20
    elif is_moderate_spike and big_move_up:
        flow_type = FlowType.BREAKOUT_BUY
        details.append(f"放量上涨 {price_change:+.1%}，量价配合良好")
        confidence += 25
    elif is_vol_spike and big_move_down:
        flow_type = FlowType.PANIC_SELL
        details.append(f"放量下跌 {price_change:+.1%}，可能是恐慌性抛售")
        confidence += 30
    elif is_moderate_spike and big_move_down:
        flow_type = FlowType.PANIC_SELL
        details.append(f"温和放量下跌 {price_change:+.1%}")
        confidence += 15
    else:
        flow_type = FlowType.NORMAL
        if vol_ratio < 0.5:
            details.append("缩量交易，市场关注度低")
        else:
            details.append("成交量正常范围")

    # Volume trend context
    if vol_trend_5d > 0.5:
        details.append(f"近5日成交量持续放大 (+{vol_trend_5d:.0%})，趋势性资金流入")
        confidence += 10
    elif vol_trend_5d < -0.3:
        details.append(f"近5日成交量持续萎缩 ({vol_trend_5d:+.0%})")

    # Turnover context
    if turnover_val > 5:
        details.append(f"换手率 {turnover_val:.1f}% 偏高，筹码快速换手")
        confidence += 10
    elif turnover_val > 3:
        details.append(f"换手率 {turnover_val:.1f}% 中等活跃")

    confidence = min(confidence, 95)

    return FlowSignal(
        symbol=symbol,
        flow_type=flow_type,
        volume_ratio=vol_ratio,
        amount_ratio=amt_ratio,
        price_change=price_change,
        turnover=turnover_val,
        volume_trend_5d=vol_trend_5d,
        confidence=confidence,
        label=FLOW_LABELS[flow_type],
        advice=FLOW_ADVICE[flow_type],
        details=details,
    )


def _price_percentile(close: pd.Series, window: int) -> float | None:
    """Get price percentile within recent window."""
    if len(close) < window:
        return None
    recent = close.iloc[-window:]
    current = float(close.iloc[-1])
    return float(np.sum(recent <= current) / len(recent))


def detect_flow_batch(data: dict[str, pd.DataFrame]) -> list[FlowSignal]:
    """Detect flow for multiple ETFs, sorted by confidence (most notable first)."""
    signals = []
    for symbol, df in data.items():
        sig = detect_flow(df, symbol)
        if sig is not None:
            signals.append(sig)

    # Sort: abnormal flows first (by confidence), then normal
    signals.sort(key=lambda s: (s.flow_type != FlowType.NORMAL, s.confidence), reverse=True)
    return signals
