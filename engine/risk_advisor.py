"""Risk advisor — multi-dimensional risk assessment and positioning suggestions.

Provides:
1. Overall portfolio risk score
2. Per-ETF risk breakdown
3. Early positioning (提前布局) suggestions based on sector rotation + flow
4. Multi-strategy recommendations with risk levels
5. Stop-loss and position sizing guidance
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd

from config.constants import DEFAULT_ETF_LIST
from data.storage.parquet_store import load_hist
from engine.flow import FlowType, detect_flow
from engine.sector import SectorPhase, analyze_all_sectors
from factors.momentum import momentum, rsi
from factors.volatility import historical_volatility, max_drawdown

logger = logging.getLogger(__name__)


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


RISK_LABELS: dict[RiskLevel, str] = {
    RiskLevel.LOW: "🟢 低风险",
    RiskLevel.MEDIUM: "🟡 中风险",
    RiskLevel.HIGH: "🔴 高风险",
    RiskLevel.EXTREME: "⛔ 极高风险",
}


@dataclass(frozen=True)
class ETFRiskProfile:
    """Risk profile for a single ETF."""

    symbol: str
    name: str
    risk_level: RiskLevel
    risk_score: float  # 0-100, higher = riskier
    volatility_20d: float
    max_drawdown_60d: float
    rsi_14: float
    momentum_20d: float
    volume_ratio: float  # vs 20d avg
    flow_type: str  # from flow detector
    warnings: list[str]
    suggestions: list[str]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "risk_level": self.risk_level.value,
            "risk_label": RISK_LABELS[self.risk_level],
            "risk_score": round(self.risk_score, 1),
            "volatility_20d": round(self.volatility_20d * 100, 1),
            "max_drawdown_60d": round(self.max_drawdown_60d * 100, 1),
            "rsi_14": round(self.rsi_14, 1),
            "momentum_20d": round(self.momentum_20d * 100, 2),
            "volume_ratio": round(self.volume_ratio, 2),
            "flow_type": self.flow_type,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
        }


@dataclass(frozen=True)
class LayoutSuggestion:
    """A positioning / early-entry suggestion."""

    symbol: str
    name: str
    action: str  # "提前布局", "逢低建仓", "观望", "减仓"
    reason: str
    entry_strategy: str  # 具体入场策略
    position_pct: float  # 建议仓位 %
    stop_loss_pct: float  # 止损比例
    risk_level: RiskLevel
    confidence: float  # 0-100
    timeframe: str  # "短期1-2周", "中期1-3月"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "action": self.action,
            "reason": self.reason,
            "entry_strategy": self.entry_strategy,
            "position_pct": round(self.position_pct, 1),
            "stop_loss_pct": round(self.stop_loss_pct, 1),
            "risk_level": self.risk_level.value,
            "risk_label": RISK_LABELS[self.risk_level],
            "confidence": round(self.confidence, 1),
            "timeframe": self.timeframe,
        }


def _safe_last(series: pd.Series) -> float:
    """Get last non-NaN value, default 0."""
    if series.empty:
        return 0.0
    val = series.iloc[-1]
    return 0.0 if pd.isna(val) else float(val)


def _get_name(symbol: str) -> str:
    for etf in DEFAULT_ETF_LIST:
        if etf["symbol"] == symbol:
            return etf["name"]
    return symbol


def assess_etf_risk(df: pd.DataFrame, symbol: str) -> ETFRiskProfile | None:
    """Assess risk for a single ETF."""
    if df.empty or len(df) < 60 or "close" not in df.columns:
        return None

    close = df["close"]
    volume = df["volume"]

    vol_20 = _safe_last(historical_volatility(close, 20))
    mdd_60 = _safe_last(max_drawdown(close, 60))
    rsi_val = _safe_last(rsi(close, 14))
    mom_20 = _safe_last(momentum(close, 20))

    # Volume ratio
    current_vol = float(volume.iloc[-1])
    vol_ma20 = float(volume.iloc[-21:-1].mean()) if len(volume) > 20 else current_vol
    vol_ratio = current_vol / vol_ma20 if vol_ma20 > 0 else 1.0

    # Flow detection
    flow_sig = detect_flow(df, symbol)
    flow_type_str = flow_sig.flow_type.value if flow_sig else "normal"

    # ── Risk scoring ──
    risk_score = 0.0
    warnings: list[str] = []
    suggestions: list[str] = []

    # Volatility risk (0-30 points)
    if vol_20 > 0.5:
        risk_score += 30
        warnings.append(f"波动率极高({vol_20:.0%})，价格波动剧烈")
    elif vol_20 > 0.35:
        risk_score += 20
        warnings.append(f"波动率偏高({vol_20:.0%})")
    elif vol_20 > 0.2:
        risk_score += 10

    # Drawdown risk (0-25 points)
    if mdd_60 > 0.2:
        risk_score += 25
        warnings.append(f"近60日最大回撤 {mdd_60:.0%}，下行风险大")
    elif mdd_60 > 0.1:
        risk_score += 15
        warnings.append(f"近60日回撤 {mdd_60:.0%}")
    elif mdd_60 > 0.05:
        risk_score += 5

    # RSI extreme risk (0-20 points)
    if rsi_val > 80:
        risk_score += 20
        warnings.append(f"RSI {rsi_val:.0f} 严重超买，回调风险极高")
        suggestions.append("建议减仓或设置紧止盈")
    elif rsi_val > 70:
        risk_score += 12
        warnings.append(f"RSI {rsi_val:.0f} 超买区域")
        suggestions.append("注意止盈，不宜追高")
    elif rsi_val < 20:
        risk_score += 10
        warnings.append(f"RSI {rsi_val:.0f} 严重超卖，可能继续下跌")
        suggestions.append("等待企稳信号再考虑入场")
    elif rsi_val < 30:
        risk_score += 5
        suggestions.append("超卖区域可考虑分批建仓")

    # Momentum risk (0-15 points)
    if mom_20 < -0.1:
        risk_score += 15
        warnings.append(f"20日下跌 {mom_20:.0%}，趋势性下行")
    elif mom_20 < -0.05:
        risk_score += 8

    # Flow risk (0-10 points)
    if flow_sig and flow_sig.flow_type == FlowType.DISTRIBUTION:
        risk_score += 10
        warnings.append("检测到疑似机构出货信号")
        suggestions.append("关注后续成交量变化，出货确认则离场")
    elif flow_sig and flow_sig.flow_type == FlowType.PANIC_SELL:
        risk_score += 8
        warnings.append("出现恐慌性抛售")
        suggestions.append("不宜抄底，等待恐慌情绪消退")
    elif flow_sig and flow_sig.flow_type == FlowType.ACCUMULATION:
        suggestions.append("检测到疑似机构吸筹，可关注后续走势")
    elif flow_sig and flow_sig.flow_type == FlowType.BREAKOUT_BUY:
        suggestions.append("放量突破信号，可顺势跟入并设好止损")

    # General suggestions
    if not suggestions:
        if risk_score < 20:
            suggestions.append("风险较低，可按策略正常操作")
        elif risk_score < 50:
            suggestions.append("风险适中，建议控制仓位不超过20%")
        else:
            suggestions.append("风险较高，建议降低仓位或观望")

    risk_score = min(risk_score, 100)

    if risk_score >= 70:
        risk_level = RiskLevel.EXTREME
    elif risk_score >= 45:
        risk_level = RiskLevel.HIGH
    elif risk_score >= 20:
        risk_level = RiskLevel.MEDIUM
    else:
        risk_level = RiskLevel.LOW

    return ETFRiskProfile(
        symbol=symbol,
        name=_get_name(symbol),
        risk_level=risk_level,
        risk_score=risk_score,
        volatility_20d=vol_20,
        max_drawdown_60d=mdd_60,
        rsi_14=rsi_val,
        momentum_20d=mom_20,
        volume_ratio=vol_ratio,
        flow_type=flow_type_str,
        warnings=warnings,
        suggestions=suggestions,
    )


def generate_layout_suggestions(capital: float = 500000) -> list[LayoutSuggestion]:
    """Generate early-positioning (提前布局) suggestions.

    Combines sector rotation phase, flow signals, and risk assessment
    to recommend where to position ahead of the market.
    """
    sectors = analyze_all_sectors()
    suggestions: list[LayoutSuggestion] = []

    for sector in sectors:
        df = load_hist(sector.best_etf)
        if df.empty:
            continue

        risk_profile = assess_etf_risk(df, sector.best_etf)
        flow_sig = detect_flow(df, sector.best_etf)

        if risk_profile is None:
            continue

        # ── Determine action based on combined signals ──

        if sector.phase == SectorPhase.RECOVERING:
            # Best opportunity: sector is recovering from bottom
            confidence = 60.0
            action = "🟢 提前布局"
            accel = sector.momentum_acceleration * 100
            reason = f"{sector.sector_name}板块从底部复苏，动量加速度 +{accel:.1f}%"
            entry_strategy = "分2-3批建仓，每批间隔3-5天，首批不超过总仓位40%"
            position_pct = 15.0
            stop_loss_pct = 5.0
            timeframe = "中期1-3月"

            # Boost confidence if flow confirms
            if flow_sig and flow_sig.flow_type == FlowType.ACCUMULATION:
                confidence += 15
                reason += " + 检测到机构吸筹信号"
                position_pct = 20.0
            elif flow_sig and flow_sig.flow_type == FlowType.BREAKOUT_BUY:
                confidence += 10
                reason += " + 放量突破确认"

            # Reduce if risk is high
            if risk_profile.risk_score > 50:
                confidence -= 15
                position_pct = 10.0
                stop_loss_pct = 3.0

            risk_level = RiskLevel.MEDIUM

        elif sector.phase == SectorPhase.LEADING:
            action = "🔵 顺势加仓"
            reason = f"{sector.sector_name}板块领涨，动量 +{sector.momentum_20d * 100:.1f}%"
            entry_strategy = "回踩5日均线时加仓，不追高"
            position_pct = 10.0
            stop_loss_pct = 4.0
            confidence = 50.0
            timeframe = "短期1-2周"
            risk_level = RiskLevel.MEDIUM

            if flow_sig and flow_sig.flow_type == FlowType.DISTRIBUTION:
                confidence -= 20
                action = "⚠️ 谨慎持有"
                reason += " ⚠️ 但检测到出货信号"
                risk_level = RiskLevel.HIGH

        elif sector.phase == SectorPhase.WEAKENING:
            action = "🔴 逐步减仓"
            reason = f"{sector.sector_name}板块高位走弱，动量减速中"
            entry_strategy = "不建议新建仓位，已有仓位设止盈逐步退出"
            position_pct = 0.0
            stop_loss_pct = 3.0
            confidence = 65.0
            timeframe = "立即"
            risk_level = RiskLevel.HIGH

        else:  # LAGGING
            action = "⚪ 观望等待"
            reason = f"{sector.sector_name}板块仍在底部，等待右侧信号"
            entry_strategy = "仅用极小仓位(5%)试探性布局，等待动量转正"
            position_pct = 5.0
            stop_loss_pct = 3.0
            confidence = 35.0
            timeframe = "长期3月+"
            risk_level = RiskLevel.LOW

            if flow_sig and flow_sig.flow_type == FlowType.ACCUMULATION:
                confidence += 20
                action = "🟢 底部吸筹信号"
                reason += " + 检测到机构资金流入"
                position_pct = 10.0

        suggestions.append(
            LayoutSuggestion(
                symbol=sector.best_etf,
                name=sector.best_etf_name,
                action=action,
                reason=reason,
                entry_strategy=entry_strategy,
                position_pct=position_pct,
                stop_loss_pct=stop_loss_pct,
                risk_level=risk_level,
                confidence=min(confidence, 95),
                timeframe=timeframe,
            )
        )

    # Sort by confidence (best opportunities first)
    suggestions.sort(key=lambda s: s.confidence, reverse=True)
    return suggestions


def full_risk_report(capital: float = 500000) -> dict:
    """Generate a comprehensive risk report with all dimensions.

    Returns:
        Dict with risk_profiles, layout_suggestions, portfolio_risk, and risk_rules.
    """
    from config.settings import settings

    # Load all available data
    data_dir = settings.data.data_dir / "etf_hist"
    sym_list = sorted(f.stem for f in data_dir.glob("*.parquet")) if data_dir.exists() else []

    # Assess risk for each ETF
    profiles: list[ETFRiskProfile] = []
    for sym in sym_list:
        df = load_hist(sym)
        if not df.empty:
            profile = assess_etf_risk(df, sym)
            if profile:
                profiles.append(profile)

    # Sort by risk score (highest risk first)
    profiles.sort(key=lambda p: p.risk_score, reverse=True)

    # Overall portfolio risk
    avg_risk = np.mean([p.risk_score for p in profiles]) if profiles else 0
    high_risk_count = sum(
        1 for p in profiles if p.risk_level in (RiskLevel.HIGH, RiskLevel.EXTREME)
    )

    if avg_risk >= 50:
        portfolio_risk = RiskLevel.HIGH
    elif avg_risk >= 30:
        portfolio_risk = RiskLevel.MEDIUM
    else:
        portfolio_risk = RiskLevel.LOW

    # Layout suggestions
    layout = generate_layout_suggestions(capital)

    # Risk management rules
    risk_rules = [
        {
            "rule": "单笔止损",
            "value": f"不超过总资金 2%（¥{capital * 0.02:,.0f}）",
            "priority": "必须执行",
        },
        {
            "rule": "单只 ETF 仓位",
            "value": "不超过总资金 30%",
            "priority": "必须执行",
        },
        {
            "rule": "同板块仓位",
            "value": "不超过总资金 40%",
            "priority": "建议执行",
        },
        {
            "rule": "现金保留",
            "value": f"始终保留 10-20%（¥{capital * 0.1:,.0f}~¥{capital * 0.2:,.0f}）",
            "priority": "必须执行",
        },
        {
            "rule": "亏损熔断",
            "value": f"总亏损达 5%（¥{capital * 0.05:,.0f}）时全部清仓观望",
            "priority": "必须执行",
        },
        {
            "rule": "盈利保护",
            "value": "盈利超过 3% 后设移动止盈（回撤 1.5% 离场）",
            "priority": "建议执行",
        },
    ]

    return {
        "capital": capital,
        "portfolio_risk": portfolio_risk.value,
        "portfolio_risk_label": RISK_LABELS[portfolio_risk],
        "avg_risk_score": round(avg_risk, 1),
        "high_risk_count": high_risk_count,
        "total_etfs": len(profiles),
        "risk_profiles": [p.to_dict() for p in profiles],
        "layout_suggestions": [s.to_dict() for s in layout],
        "risk_rules": risk_rules,
        "disclaimer": "风险评估基于历史数据，不代表未来表现。仅供参考，不构成投资建议。",
    }
