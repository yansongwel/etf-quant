"""Optimal strategy parameters — derived from exhaustive backtesting.

Last updated: 2026-03-31
Data range: 2021-03 to 2026-03 (5 years)
Capital: ¥500,000
Sweep: 175 rotation + 288 multifactor + 120 balance + 225 grid combos

These are the strategies that actually make money.
"""

from __future__ import annotations

# ── Strategy 1: 最稳策略 — 多因子均衡配置 ────────────────
# Sharpe 1.08, 回撤 26.9%, 年化 27.6% — WF 100% 窗口盈利
# 2026-03-31 sweep: 288 combos → top by Sharpe after weight filter
BEST_BALANCED = {
    "name": "多因子短期动量配置",
    "strategy": "multifactor",
    "symbols": [
        "510300",
        "518880",
        "511010",
        "512480",
        "513100",
        "510500",
        "159915",
        "515220",
        "512880",
        "562800",
        "159819",
        "515030",
    ],
    "symbol_names": [
        "沪深300ETF",
        "黄金ETF",
        "国债ETF",
        "半导体ETF",
        "纳指ETF",
        "中证500ETF",
        "创业板ETF",
        "煤炭ETF",
        "证券ETF",
        "芯片ETF",
        "人工智能ETF",
        "新能源ETF",
    ],
    "params": {
        "lookback": 10,
        "top_k": 1,
        "rebalance_days": 15,
        "momentum_weight": 0.6,
        "value_weight": 0.1,
        "volatility_weight": 0.3,
    },
    "backtest": {
        "total_return": 2.376,
        "annualized_return": 0.276,
        "sharpe_ratio": 1.08,
        "max_drawdown": 0.269,
    },
    "walk_forward": {
        "windows": 5,
        "win_rate": 1.0,
        "avg_test_return": 0.5392,
        "verdict": "通过",
    },
    "previous": {
        "sharpe_ratio": 1.11,
        "annualized_return": 0.178,
        "max_drawdown": 0.153,
        "note": "2026-03-30 旧参数 lookback=20/top_k=2/rebalance=20",
    },
}

# ── Strategy 2: 最高收益策略 — 短期动量轮动 ──────────────
# Sharpe 0.80, 年化 24.8%, 回撤 35.6% — WF 60% 窗口盈利
# 2026-03-31 sweep: 175 combos → lookback=10 + 月度调仓最优
BEST_RETURN = {
    "name": "短期动量轮动",
    "strategy": "rotation",
    "symbols": [
        "510300",
        "518880",
        "511010",
        "512480",
        "513100",
        "510500",
        "159915",
        "515220",
        "512880",
        "562800",
        "159819",
        "515030",
    ],
    "symbol_names": [
        "沪深300ETF",
        "黄金ETF",
        "国债ETF",
        "半导体ETF",
        "纳指ETF",
        "中证500ETF",
        "创业板ETF",
        "煤炭ETF",
        "证券ETF",
        "芯片ETF",
        "人工智能ETF",
        "新能源ETF",
    ],
    "params": {
        "lookback": 10,
        "top_k": 1,
        "rebalance_days": 30,
    },
    "backtest": {
        "total_return": 2.248,
        "annualized_return": 0.248,
        "sharpe_ratio": 0.80,
        "max_drawdown": 0.356,
    },
    "walk_forward": {
        "windows": 5,
        "win_rate": 0.6,
        "avg_test_return": 0.1321,
        "verdict": "通过",
    },
}

# ── Strategy 3: 高成长策略 — 科技板块轮动 ────────────────
# 年化 24.4%, 偏科技，波动大
BEST_GROWTH = {
    "name": "高成长科技轮动",
    "strategy": "rotation",
    "symbols": ["512480", "562800", "159819", "515030", "513100", "518880"],
    "symbol_names": ["半导体ETF", "芯片ETF", "人工智能ETF", "新能源ETF", "纳指ETF", "黄金ETF"],
    "params": {
        "lookback": 20,
        "top_k": 1,
        "rebalance_days": 20,
    },
    "backtest": {
        "total_return": 1.971,
        "annualized_return": 0.244,
        "sharpe_ratio": 0.79,
        "max_drawdown": 0.317,
    },
}

# ── Strategy 4: 避险宽基轮动 ─────────────────────────────
# 夏普 0.90, 回撤 25.5%, 最稳定的轮动策略
BEST_DEFENSIVE = {
    "name": "避险宽基轮动",
    "strategy": "rotation",
    "symbols": ["518880", "511010", "510300", "510500", "159915"],
    "symbol_names": ["黄金ETF", "国债ETF", "沪深300ETF", "中证500ETF", "创业板ETF"],
    "params": {
        "lookback": 20,
        "top_k": 1,
        "rebalance_days": 15,
    },
    "backtest": {
        "total_return": 1.849,
        "annualized_return": 0.233,
        "sharpe_ratio": 0.90,
        "max_drawdown": 0.255,
    },
}

# ── Balance / Grid: NOT recommended ─────────────────────
# 2026-03-31 sweep: balance Sharpe=0.03, grid Sharpe≤0
# These strategies underperform rotation/multifactor by 10-30x on Sharpe.
# Kept in codebase for completeness but not included in ALL_OPTIMAL.
BALANCE_NOTE = {
    "strategy": "balance",
    "best_sharpe": 0.03,
    "best_params": {"stock_weight": 0.3, "drift_threshold": 0.1},
    "verdict": "不推荐 — 近似零收益",
}
GRID_NOTE = {
    "strategy": "grid",
    "best_sharpe": -0.004,
    "best_params": {"grid_count": 5, "grid_width_pct": 0.05, "symbol": "159915"},
    "verdict": "不推荐 — 负夏普比",
}

# ── All strategies sorted by Sharpe ──────────────────────
ALL_OPTIMAL = [BEST_BALANCED, BEST_DEFENSIVE, BEST_GROWTH, BEST_RETURN]


# ── Signal Engine V5.0: Asymmetric Buy/Sell Redesign ────────
# Backtested 2026-04-02: V4.3 sell accuracy was 48.7% (worse than random)
# Root cause: "overbought = sell" is wrong for A-share ETFs (momentum persists)
SIGNAL_V5_0 = {
    "version": "5.0",
    "date": "2026-04-02",
    "buy_accuracy_1d": 55.4,
    "buy_accuracy_5d": 58.2,
    "sell_avg_return_5d": -0.03,  # Now correctly negative (was +0.19% in V4.3)
    "changes_from_v4_3": [
        "Asymmetric design: buy uses IC-weighted mean-reversion, sell uses structural-only",
        "Removed all individual-factor sell scoring (RSI overbought, MFI>80, etc.)",
        "Sell now requires 2+ structural signals: ATR stop + MA death cross + RSI div + vol climax",
        "Buy threshold raised: 12 → 20 (cut 52% accuracy noise signals)",
        "Buy gate: 3+ bullish factors required (was 2)",
        "Strong sell: 3+ structural signals (very selective, 26 vs 362 in V4.3)",
        "Eval window: 5-day return as primary metric (ETF rotation cycle)",
        "Score 50+ signals: 80% accuracy at T+5, avg return +2.81%",
    ],
    "buy_thresholds": {
        "buy": 20,
        "strong_buy": 30,
        "min_bullish_factors": 3,
        "confirmation": "vol>=1.0 OR RSI<35 OR mdd>15%",
    },
    "sell_thresholds": {
        "sell": "2+ structural signals",
        "strong_sell": "3+ structural signals",
        "structural_signals": [
            "ATR trailing stop break",
            "MA death cross + volume decline",
            "RSI divergence",
            "Volume climax at peak",
            "Reversal-in-trend sell",
            "Volume-price bearish divergence",
            "Momentum deceleration after rally",
        ],
    },
}
