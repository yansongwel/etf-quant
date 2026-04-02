"""One-line market verdict — "今天该买还是该卖" in plain Chinese.

Combines market regime, signal distribution, and sector rotation status
into a single actionable sentence that anyone can understand.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config.constants import DEFAULT_ETF_LIST
from data.storage.parquet_store import load_hist
from engine.alerts import check_alerts
from engine.regime import detect_regime
from engine.signals import SignalDirection, generate_signals_batch


def generate_verdict(capital: float = 500_000) -> dict:
    """Generate a one-line actionable verdict.

    Returns:
        Dict with verdict, action, risk_level, and details.
    """
    # 1. Market regime
    regime = detect_regime()
    regime_type = regime["regime"]

    # 2. Signal distribution
    data = {}
    for etf in DEFAULT_ETF_LIST:
        df = load_hist(etf["symbol"])
        if not df.empty and len(df) >= 60:
            data[etf["symbol"]] = df

    signals = generate_signals_batch(data)
    n_buy = sum(
        1 for s in signals if s.direction in (SignalDirection.STRONG_BUY, SignalDirection.BUY)
    )
    n_sell = sum(
        1 for s in signals if s.direction in (SignalDirection.STRONG_SELL, SignalDirection.SELL)
    )
    n_hold = sum(1 for s in signals if s.direction == SignalDirection.HOLD)
    total = len(signals)

    buy_pct = n_buy / total * 100 if total > 0 else 0
    sell_pct = n_sell / total * 100 if total > 0 else 0

    # 3. Alerts
    alerts = check_alerts()
    stop_loss_alerts = [a for a in alerts if a.alert_type.value == "stop_loss"]

    # 4. Build verdict
    if stop_loss_alerts:
        verdict = f"⚠️ 紧急：{len(stop_loss_alerts)}个持仓触发止损，请立即处理！"
        action = "止损"
        risk = "极高"
        color = "#ef4444"
    elif regime_type == "bear" and sell_pct > 50:
        verdict = f"📉 今日建议观望。市场处于下跌趋势，{n_sell}只ETF发出卖出信号，不宜追加。"
        action = "观望"
        risk = "高"
        color = "#f87171"
    elif regime_type == "bear" and buy_pct > 20:
        verdict = f"🔍 市场下跌但有{n_buy}只ETF出现买入信号，可小仓位试探性布局。"
        action = "轻仓试探"
        risk = "中高"
        color = "#eab308"
    elif regime_type == "bull" and buy_pct > 30:
        verdict = f"🚀 市场上涨趋势中，{n_buy}只ETF买入信号！建议顺势加仓。"
        action = "加仓"
        risk = "中低"
        color = "#22c55e"
    elif regime_type == "bull":
        verdict = "📈 市场趋势向好，持有为主，关注调仓信号。"
        action = "持有"
        risk = "中"
        color = "#4ade80"
    elif buy_pct > sell_pct and buy_pct > 15:
        verdict = f"💡 震荡市中有{n_buy}只ETF出现买入机会，可选择性布局强势板块。"
        action = "精选买入"
        risk = "中"
        color = "#3b82f6"
    elif sell_pct > 60:
        verdict = f"🛑 多数ETF发出卖出信号（{n_sell}/{total}），建议减仓或观望。"
        action = "减仓"
        risk = "高"
        color = "#f87171"
    else:
        verdict = f"⏸️ 市场方向不明（{n_buy}买/{n_hold}持/{n_sell}卖），建议等待明确信号。"
        action = "等待"
        risk = "中"
        color = "#94a3b8"

    # Top recommendation
    top_buy = None
    if n_buy > 0:
        best = [
            s for s in signals if s.direction in (SignalDirection.STRONG_BUY, SignalDirection.BUY)
        ]
        if best:
            name_map = {e["symbol"]: e["name"] for e in DEFAULT_ETF_LIST}
            b = best[0]
            top_buy = {
                "symbol": b.symbol,
                "name": name_map.get(b.symbol, b.symbol),
                "score": round(b.score, 0),
                "price": round(b.current_price, 3),
            }

    cst = timezone(timedelta(hours=8))
    return {
        "verdict": verdict,
        "action": action,
        "risk_level": risk,
        "color": color,
        "regime": regime["label"],
        "signal_summary": f"{n_buy}买 / {n_hold}持 / {n_sell}卖",
        "top_buy": top_buy,
        "alert_count": len(alerts),
        "generated_at": datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S"),
    }
