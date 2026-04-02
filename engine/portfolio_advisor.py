"""Portfolio advisor — analyze user holdings and give per-position advice.

Given a user's actual portfolio (ETF code, buy price, quantity),
analyze each position against current market data and provide:
1. Real-time P&L
2. Per-position action: 加仓 / 持有 / 减仓 / 清仓
3. Risk warnings per position
4. Overall portfolio health score
5. Rebalancing suggestions
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from config.constants import DEFAULT_ETF_LIST
from data.storage.parquet_store import load_hist
from engine.flow import detect_flow
from engine.signals import generate_signal
from factors.momentum import momentum, rsi
from factors.volatility import historical_volatility

logger = logging.getLogger(__name__)

PORTFOLIO_DIR = Path(__file__).resolve().parent.parent / "data_store" / "portfolio"

# ─── Data Model ───────────────────────────────────────


@dataclass
class Holding:
    """A single user holding."""

    symbol: str
    buy_price: float
    shares: int
    buy_date: str = ""  # YYYY-MM-DD
    note: str = ""

    @property
    def cost(self) -> float:
        return self.buy_price * self.shares


@dataclass
class PositionAdvice:
    """Advisory output for a single holding."""

    symbol: str
    name: str
    # Holding info
    buy_price: float
    shares: int
    cost: float
    # Current market
    current_price: float
    market_value: float
    # P&L
    pnl: float
    pnl_pct: float
    # Action
    action: str  # 加仓 / 持有 / 减仓 / 清仓
    action_color: str  # green / yellow / orange / red
    urgency: int  # 1-5, higher = more urgent
    reasons: list[str]
    # Key factors
    rsi_14: float
    momentum_20d: float
    flow_type: str
    signal_direction: str
    # Specific guidance
    target_price: float
    stop_loss: float
    suggested_action: str  # Concrete next step

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "buy_price": round(self.buy_price, 4),
            "shares": self.shares,
            "cost": round(self.cost, 2),
            "current_price": round(self.current_price, 4),
            "market_value": round(self.market_value, 2),
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct, 2),
            "action": self.action,
            "action_color": self.action_color,
            "urgency": self.urgency,
            "reasons": self.reasons,
            "rsi_14": round(self.rsi_14, 1),
            "momentum_20d": round(self.momentum_20d, 2),
            "flow_type": self.flow_type,
            "signal_direction": self.signal_direction,
            "target_price": round(self.target_price, 4),
            "stop_loss": round(self.stop_loss, 4),
            "suggested_action": self.suggested_action,
        }


def _get_name(symbol: str) -> str:
    for etf in DEFAULT_ETF_LIST:
        if etf["symbol"] == symbol:
            return etf["name"]
    return symbol


def _safe_last(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    val = series.iloc[-1]
    return 0.0 if pd.isna(val) else float(val)


# ─── Portfolio Persistence ────────────────────────────


def _ensure_dir() -> Path:
    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    return PORTFOLIO_DIR


def _validate_portfolio_id(portfolio_id: str) -> None:
    """Validate portfolio_id to prevent path traversal attacks."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", portfolio_id):
        raise ValueError(f"Invalid portfolio_id: {portfolio_id!r}")


def save_portfolio(holdings: list[Holding], portfolio_id: str = "default") -> Path:
    """Save portfolio to JSON file."""
    _validate_portfolio_id(portfolio_id)
    path = _ensure_dir() / f"{portfolio_id}.json"
    data = [asdict(h) for h in holdings]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return path


def load_portfolio(portfolio_id: str = "default") -> list[Holding]:
    """Load portfolio from JSON file."""
    _validate_portfolio_id(portfolio_id)
    path = PORTFOLIO_DIR / f"{portfolio_id}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [Holding(**h) for h in data]


# ─── Per-Position Analysis ────────────────────────────


def analyze_position(holding: Holding) -> PositionAdvice | None:
    """Analyze a single holding and generate advice."""
    df = load_hist(holding.symbol)
    if df.empty or len(df) < 60 or "close" not in df.columns:
        return None

    close = df["close"]
    current_price = float(close.iloc[-1])
    market_value = current_price * holding.shares
    pnl = market_value - holding.cost
    pnl_pct = (current_price / holding.buy_price - 1) * 100 if holding.buy_price > 0 else 0

    # Compute factors
    rsi_val = _safe_last(rsi(close, 14))
    mom_20 = _safe_last(momentum(close, 20))
    hvol = _safe_last(historical_volatility(close, 20))
    # Flow detection
    flow_sig = detect_flow(df, holding.symbol)
    flow_type = flow_sig.flow_type.value if flow_sig else "normal"

    # Signal
    sig = generate_signal(df, holding.symbol)
    signal_dir = sig.direction.value if sig else "hold"
    target_price = sig.target_price if sig else current_price * 1.05
    stop_loss = sig.stop_loss if sig else current_price * 0.95

    # ── Decision Logic ──
    reasons: list[str] = []
    urgency = 1

    # === P&L assessment ===
    if pnl_pct <= -8:
        reasons.append(f"亏损 {pnl_pct:.1f}%，已触及深度止损线")
        urgency = max(urgency, 5)
    elif pnl_pct <= -5:
        reasons.append(f"亏损 {pnl_pct:.1f}%，接近止损线")
        urgency = max(urgency, 4)
    elif pnl_pct <= -2:
        reasons.append(f"小幅亏损 {pnl_pct:.1f}%")
        urgency = max(urgency, 2)
    elif pnl_pct >= 10:
        reasons.append(f"盈利丰厚 +{pnl_pct:.1f}%，建议设移动止盈")
        urgency = max(urgency, 3)
    elif pnl_pct >= 5:
        reasons.append(f"盈利 +{pnl_pct:.1f}%，注意止盈保护")
        urgency = max(urgency, 2)

    # === Technical signals ===
    if rsi_val > 75:
        reasons.append(f"RSI {rsi_val:.0f} 严重超买")
        urgency = max(urgency, 4)
    elif rsi_val > 65:
        reasons.append(f"RSI {rsi_val:.0f} 偏高")
    elif rsi_val < 25:
        reasons.append(f"RSI {rsi_val:.0f} 深度超卖，可能反弹")
    elif rsi_val < 35:
        reasons.append(f"RSI {rsi_val:.0f} 超卖区")

    if mom_20 < -0.08:
        reasons.append(f"20日跌幅 {mom_20 * 100:.1f}%，趋势性下行")
        urgency = max(urgency, 4)
    elif mom_20 < -0.03:
        reasons.append(f"20日跌 {mom_20 * 100:.1f}%")
    elif mom_20 > 0.05:
        reasons.append(f"20日涨 +{mom_20 * 100:.1f}%，趋势良好")

    if hvol > 0.4:
        reasons.append(f"波动率 {hvol * 100:.0f}% 极高")
        urgency = max(urgency, 3)

    # === Flow signals ===
    if flow_type == "distribution":
        reasons.append("检测到机构出货信号")
        urgency = max(urgency, 4)
    elif flow_type == "accumulation":
        reasons.append("检测到机构吸筹信号")
    elif flow_type == "panic_sell":
        reasons.append("市场恐慌抛售")
        urgency = max(urgency, 5)
    elif flow_type == "breakout_buy":
        reasons.append("放量突破，趋势确认")

    # === Signal direction ===
    if signal_dir in ("sell", "strong_sell"):
        reasons.append(f"量化信号: {signal_dir}")
        urgency = max(urgency, 3)
    elif signal_dir in ("buy", "strong_buy"):
        reasons.append(f"量化信号: {signal_dir}")

    # ── Determine action ──
    action, action_color, suggested = _determine_action(
        pnl_pct, rsi_val, mom_20, flow_type, signal_dir, urgency, current_price, stop_loss
    )

    if not reasons:
        reasons.append("暂无明显信号")

    return PositionAdvice(
        symbol=holding.symbol,
        name=_get_name(holding.symbol),
        buy_price=holding.buy_price,
        shares=holding.shares,
        cost=holding.cost,
        current_price=current_price,
        market_value=market_value,
        pnl=pnl,
        pnl_pct=pnl_pct,
        action=action,
        action_color=action_color,
        urgency=urgency,
        reasons=reasons,
        rsi_14=rsi_val,
        momentum_20d=mom_20 * 100,
        flow_type=flow_type,
        signal_direction=signal_dir,
        target_price=target_price,
        stop_loss=stop_loss,
        suggested_action=suggested,
    )


def _determine_action(
    pnl_pct: float,
    rsi_val: float,
    mom_20: float,
    flow_type: str,
    signal_dir: str,
    urgency: int,
    current_price: float,
    stop_loss: float,
) -> tuple[str, str, str]:
    """Determine the recommended action based on multi-dimensional analysis."""

    # === CLEAR EXIT signals ===
    if pnl_pct <= -8:
        return (
            "🔴 清仓止损",
            "red",
            f"亏损超过8%，建议明日开盘清仓，止损价 ¥{stop_loss:.3f}",
        )

    if flow_type == "distribution" and pnl_pct < 0:
        return (
            "🔴 清仓",
            "red",
            "机构出货+已亏损，不宜继续持有，建议清仓止损",
        )

    if flow_type == "panic_sell":
        return (
            "🟠 减仓观望",
            "orange",
            "恐慌抛售期间先减仓50%，等待企稳再决定",
        )

    # === REDUCE signals ===
    if pnl_pct <= -5:
        if mom_20 < -0.05:
            return (
                "🔴 清仓止损",
                "red",
                f"亏5%+趋势下行，建议止损，目标止损价 ¥{stop_loss:.3f}",
            )
        return (
            "🟠 减仓一半",
            "orange",
            "亏损接近5%，建议减仓50%，降低风险敞口",
        )

    if rsi_val > 75 and pnl_pct > 0:
        return (
            "🟠 止盈减仓",
            "orange",
            "RSI超买+盈利中，建议卖出50-70%锁定利润",
        )

    if signal_dir == "strong_sell":
        return (
            "🟠 减仓",
            "orange",
            "强烈卖出信号，建议减仓50%",
        )

    if pnl_pct > 10 and mom_20 < 0:
        return (
            "🟠 止盈",
            "orange",
            f"盈利 +{pnl_pct:.1f}% 但动量转弱，建议逐步止盈",
        )

    # === ADD signals ===
    if flow_type == "accumulation" and signal_dir in ("buy", "strong_buy"):
        return (
            "🟢 加仓",
            "green",
            "机构吸筹+买入信号确认，可加仓20%摊低成本",
        )

    if rsi_val < 30 and mom_20 > -0.03 and pnl_pct > -5:
        return (
            "🟢 逢低加仓",
            "green",
            "超卖反弹预期，可小幅加仓10-15%",
        )

    if signal_dir in ("buy", "strong_buy") and pnl_pct > -3:
        return (
            "🟢 可加仓",
            "green",
            "买入信号确认，可适当加仓",
        )

    # === HOLD signals ===
    if pnl_pct > 3 and mom_20 > 0:
        return (
            "🟡 持有",
            "yellow",
            f"趋势向好+盈利中，继续持有，止盈位 ¥{current_price * 1.05:.3f}",
        )

    if abs(pnl_pct) < 3 and signal_dir == "hold":
        return (
            "🟡 观望",
            "yellow",
            "无明显方向信号，继续观望，关注后续量价变化",
        )

    if pnl_pct < -3 and rsi_val < 40 and flow_type != "distribution":
        return (
            "🟡 持仓等待",
            "yellow",
            f"亏损但超卖区，耐心等待反弹，止损位 ¥{stop_loss:.3f}",
        )

    return (
        "🟡 持有观望",
        "yellow",
        "综合信号不明确，保持现有仓位，密切关注",
    )


# ─── Portfolio-Level Analysis ─────────────────────────


def analyze_portfolio(
    holdings: list[Holding],
) -> dict:
    """Analyze entire portfolio and return comprehensive advice."""
    advices: list[PositionAdvice] = []
    for h in holdings:
        advice = analyze_position(h)
        if advice is not None:
            advices.append(advice)

    # Sort by urgency (most urgent first)
    advices.sort(key=lambda a: (-a.urgency, a.pnl_pct))

    # Portfolio-level metrics
    total_cost = sum(a.cost for a in advices)
    total_value = sum(a.market_value for a in advices)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_value / total_cost - 1) * 100 if total_cost > 0 else 0

    # Action distribution
    action_counts = {}
    for a in advices:
        key = a.action.split(" ", 1)[-1] if " " in a.action else a.action
        action_counts[key] = action_counts.get(key, 0) + 1

    # Urgent items
    urgent = [a for a in advices if a.urgency >= 4]

    # Winners and losers
    winners = [a for a in advices if a.pnl_pct > 0]
    losers = [a for a in advices if a.pnl_pct < 0]

    # Overall health score (0-100)
    health = 50.0
    if total_pnl_pct > 5:
        health += 20
    elif total_pnl_pct > 0:
        health += 10
    elif total_pnl_pct < -5:
        health -= 20
    elif total_pnl_pct < 0:
        health -= 10

    if len(urgent) == 0:
        health += 15
    elif len(urgent) <= 2:
        health -= 5
    else:
        health -= 15

    win_ratio = len(winners) / len(advices) if advices else 0
    health += (win_ratio - 0.5) * 30
    health = max(0, min(100, health))

    # Overall strategy
    if total_pnl_pct < -5 and len(urgent) > 3:
        overall_strategy = "⚠️ 组合亏损较大，建议优先处理止损单，降低风险敞口"
    elif total_pnl_pct < -2:
        overall_strategy = "📊 组合小幅亏损，关注止损位，减持弱势标的，保留强势标的"
    elif total_pnl_pct > 5:
        overall_strategy = "✅ 组合盈利良好，注意止盈保护，适当锁定部分利润"
    elif len(urgent) > 0:
        overall_strategy = f"⚠️ 有 {len(urgent)} 个持仓需要紧急处理，请优先操作"
    else:
        overall_strategy = "📊 组合状态正常，按各持仓建议分别操作"

    return {
        "total_positions": len(advices),
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "health_score": round(health, 1),
        "winners": len(winners),
        "losers": len(losers),
        "urgent_count": len(urgent),
        "action_summary": action_counts,
        "overall_strategy": overall_strategy,
        "positions": [a.to_dict() for a in advices],
        "disclaimer": "持仓建议基于量化分析，仅供参考。请结合自身情况做出投资决策。",
    }
