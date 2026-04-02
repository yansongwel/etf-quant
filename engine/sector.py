"""Sector rotation analyzer — identifies which sectors are leading/lagging.

Analyzes momentum, relative strength, and mean-reversion signals across
sector groups to determine rotation direction and early-entry opportunities.

Key concepts:
- Leading sectors: strong momentum + accelerating
- Lagging sectors: weak momentum but improving (potential early entry)
- Overheated sectors: strong momentum + decelerating (risk of reversal)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd

from config.constants import DEFAULT_ETF_LIST, SECTOR_GROUPS
from data.storage.parquet_store import load_hist
from factors.momentum import momentum, moving_average_ratio, rsi
from factors.volatility import historical_volatility

logger = logging.getLogger(__name__)


class SectorPhase(StrEnum):
    """Sector rotation phase (clock model)."""

    LEADING = "leading"  # 领涨 — 动量强 + 加速中
    WEAKENING = "weakening"  # 走弱 — 动量强但减速
    LAGGING = "lagging"  # 落后 — 动量弱
    RECOVERING = "recovering"  # 复苏 — 动量弱但改善中（提前布局机会）


PHASE_LABELS = {
    SectorPhase.LEADING: "🔴 领涨板块",
    SectorPhase.WEAKENING: "🟡 高位走弱",
    SectorPhase.LAGGING: "🔵 底部板块",
    SectorPhase.RECOVERING: "🟢 复苏机会",
}

PHASE_RISK = {
    SectorPhase.LEADING: "中风险 — 趋势延续但追高需谨慎",
    SectorPhase.WEAKENING: "高风险 — 可能见顶回落",
    SectorPhase.LAGGING: "低风险 — 可少量左侧布局",
    SectorPhase.RECOVERING: "中低风险 — 提前布局良机",
}


@dataclass(frozen=True)
class SectorAnalysis:
    """Analysis result for a single sector group."""

    sector_name: str
    phase: SectorPhase
    etf_symbols: list[str]
    best_etf: str
    best_etf_name: str
    momentum_20d: float
    momentum_5d: float
    momentum_acceleration: float  # 5d_mom - 20d_mom (positive = accelerating)
    rsi: float
    ma_ratio: float
    volatility: float
    score: float  # Composite ranking score
    risk_level: str
    action: str  # 具体操作建议
    allocation_pct: float  # Suggested allocation percentage

    def to_dict(self) -> dict:
        return {
            "sector_name": self.sector_name,
            "phase": self.phase.value,
            "phase_label": PHASE_LABELS[self.phase],
            "etf_symbols": self.etf_symbols,
            "best_etf": self.best_etf,
            "best_etf_name": self.best_etf_name,
            "momentum_20d": round(self.momentum_20d * 100, 2),
            "momentum_5d": round(self.momentum_5d * 100, 2),
            "momentum_acceleration": round(self.momentum_acceleration * 100, 2),
            "rsi": round(self.rsi, 1),
            "ma_ratio": round(self.ma_ratio, 4),
            "volatility": round(self.volatility * 100, 1),
            "score": round(self.score, 2),
            "risk_level": self.risk_level,
            "action": self.action,
            "allocation_pct": round(self.allocation_pct, 1),
        }


def _get_name(symbol: str) -> str:
    for etf in DEFAULT_ETF_LIST:
        if etf["symbol"] == symbol:
            return etf["name"]
    return symbol


def analyze_sector(sector_name: str, symbols: list[str]) -> SectorAnalysis | None:
    """Analyze a single sector group."""
    best_score = -999.0
    best_sym = ""
    sector_moms_20: list[float] = []
    sector_moms_5: list[float] = []
    sector_rsis: list[float] = []
    sector_ma_ratios: list[float] = []
    sector_vols: list[float] = []

    for sym in symbols:
        df = load_hist(sym)
        if df.empty or len(df) < 60 or "close" not in df.columns:
            continue

        close = df["close"]
        m20 = momentum(close, 20).iloc[-1]
        m5 = momentum(close, 5).iloc[-1]
        r = rsi(close, 14).iloc[-1]
        mar = moving_average_ratio(close, 5, 20).iloc[-1]
        vol = historical_volatility(close, 20).iloc[-1]

        if any(pd.isna(x) for x in [m20, m5, r, mar, vol]):
            continue

        sector_moms_20.append(float(m20))
        sector_moms_5.append(float(m5))
        sector_rsis.append(float(r))
        sector_ma_ratios.append(float(mar))
        sector_vols.append(float(vol))

        # Score individual ETF: momentum + value (RSI mean-reversion)
        etf_score = float(m20) * 40 + (50 - float(r)) * 0.3 + float(mar - 1) * 100
        if etf_score > best_score:
            best_score = etf_score
            best_sym = sym

    if not sector_moms_20 or not best_sym:
        return None

    # Sector averages
    avg_m20 = np.mean(sector_moms_20)
    avg_m5 = np.mean(sector_moms_5)
    avg_rsi = np.mean(sector_rsis)
    avg_mar = np.mean(sector_ma_ratios)
    avg_vol = np.mean(sector_vols)
    accel = avg_m5 - avg_m20  # Momentum acceleration

    # Determine phase
    if avg_m20 > 0.02 and accel > 0:
        phase = SectorPhase.LEADING
    elif avg_m20 > 0.02 and accel <= 0:
        phase = SectorPhase.WEAKENING
    elif avg_m20 <= -0.02 and accel >= 0:
        phase = SectorPhase.RECOVERING
    else:
        phase = SectorPhase.LAGGING

    # Action suggestion
    if phase == SectorPhase.RECOVERING:
        action = f"🟢 提前布局 — 买入 {_get_name(best_sym)}({best_sym})"
        alloc = 20.0
    elif phase == SectorPhase.LEADING:
        action = f"🔴 顺势持有 — 持有/加仓 {_get_name(best_sym)}({best_sym})"
        alloc = 15.0
    elif phase == SectorPhase.WEAKENING:
        action = f"🟡 逐步减仓 — 设止盈 {_get_name(best_sym)}({best_sym})"
        alloc = 5.0
    else:
        action = f"🔵 观望 — {_get_name(best_sym)}({best_sym}) 待底部信号"
        alloc = 3.0

    # Composite score for ranking
    score = avg_m20 * 50 + accel * 100 + (50 - avg_rsi) * 0.2 - avg_vol * 10

    return SectorAnalysis(
        sector_name=sector_name,
        phase=phase,
        etf_symbols=symbols,
        best_etf=best_sym,
        best_etf_name=_get_name(best_sym),
        momentum_20d=avg_m20,
        momentum_5d=avg_m5,
        momentum_acceleration=accel,
        rsi=avg_rsi,
        ma_ratio=avg_mar,
        volatility=avg_vol,
        score=score,
        risk_level=PHASE_RISK[phase],
        action=action,
        allocation_pct=alloc,
    )


def analyze_all_sectors() -> list[SectorAnalysis]:
    """Analyze all sector groups and return sorted by opportunity score."""
    results = []
    for sector_name, symbols in SECTOR_GROUPS.items():
        analysis = analyze_sector(sector_name, symbols)
        if analysis:
            results.append(analysis)

    results.sort(key=lambda x: x.score, reverse=True)
    return results


def generate_portfolio_plan(
    capital: float,
    max_sectors: int = 5,
    risk_appetite: str = "aggressive",
) -> dict:
    """Generate a complete portfolio plan based on sector rotation.

    Args:
        capital: Total investable capital in CNY.
        max_sectors: Maximum number of sectors to hold.
        risk_appetite: "conservative", "moderate", or "aggressive".

    Returns:
        Portfolio plan with specific buy recommendations.
    """
    sectors = analyze_all_sectors()

    # Risk-based filtering
    if risk_appetite == "conservative":
        eligible = [s for s in sectors if s.phase != SectorPhase.WEAKENING]
        max_position_pct = 0.20
    elif risk_appetite == "aggressive":
        eligible = sectors  # All phases eligible
        max_position_pct = 0.35
    else:
        eligible = [s for s in sectors if s.phase != SectorPhase.WEAKENING]
        max_position_pct = 0.25

    # Build positions
    positions = []
    remaining = capital
    total_alloc = sum(s.allocation_pct for s in eligible[:max_sectors])

    for sector in eligible[:max_sectors]:
        if remaining <= 500:
            break

        # Normalize allocation to use full capital
        normalized_pct = (sector.allocation_pct / total_alloc) if total_alloc > 0 else 0.2
        normalized_pct = min(normalized_pct, max_position_pct)

        amount = capital * normalized_pct

        # Calculate shares (ETF lots of 100)
        df = load_hist(sector.best_etf)
        if df.empty:
            continue
        price = float(df["close"].iloc[-1])
        shares = int(amount / price / 100) * 100
        if shares <= 0:
            shares = 100
        actual_amount = shares * price

        if actual_amount > remaining:
            shares = int(remaining / price / 100) * 100
            if shares <= 0:
                continue
            actual_amount = shares * price

        remaining -= actual_amount

        positions.append(
            {
                "sector": sector.sector_name,
                "phase": sector.phase.value,
                "phase_label": PHASE_LABELS[sector.phase],
                "etf_code": sector.best_etf,
                "etf_name": sector.best_etf_name,
                "price": round(price, 4),
                "shares": shares,
                "amount": round(actual_amount, 2),
                "pct_of_portfolio": round(actual_amount / capital * 100, 1),
                "risk_level": sector.risk_level,
                "action": sector.action,
                "momentum": round(sector.momentum_20d * 100, 2),
                "rsi": round(sector.rsi, 1),
            }
        )

    # Weekly profit estimate (very rough, based on average sector momentum)
    avg_weekly_mom = np.mean([s.momentum_5d for s in eligible[:max_sectors]]) if eligible else 0
    estimated_weekly = capital * avg_weekly_mom

    # Risk warning
    weekly_target_pct = 10000 / capital * 100 if capital > 0 else 0
    risk_warning = ""
    if weekly_target_pct > 3:
        risk_warning = (
            f"⚠️ 每周盈利1万 = 周收益{weekly_target_pct:.1f}%，年化约{weekly_target_pct * 52:.0f}%。"
            "这一目标极为激进，即使最优秀的基金经理也难以持续达到。"
            "建议：1) 降低预期到每月2-3% 2) 严格止损 3) 分散投资 4) 做好亏损准备"
        )
    elif weekly_target_pct > 1:
        risk_warning = (
            f"⚠️ 每周{weekly_target_pct:.1f}%的目标需要精准择时，存在较大风险。"
            "建议设置严格止损（每笔亏损不超过本金2%）"
        )

    return {
        "capital": capital,
        "risk_appetite": risk_appetite,
        "invested": round(capital - remaining, 2),
        "remaining": round(remaining, 2),
        "positions": positions,
        "sector_count": len(positions),
        "estimated_weekly_return": round(estimated_weekly, 2),
        "risk_warning": risk_warning,
        "sectors_analysis": [s.to_dict() for s in sectors],
        "disclaimer": "仅供研究参考，不构成投资建议。历史表现不代表未来收益。",
    }
