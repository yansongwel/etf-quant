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


# ── Signal Engine V3.5: IC-Calibrated Parameters ────────
# Calibrated by factor IC analysis on 27 factors × 16 ETFs (2026-03-31)
# Key change: added ret_5d reversal factor (IC=-0.022), reversed hvol/mdd
SIGNAL_V3_5 = {
    "version": "3.5",
    "date": "2026-03-31",
    "accuracy": 55.0,
    "changes_from_v3_2": [
        "Added ret_5d contrarian reversal factor (IC=-0.022, strongest)",
        "Reversed hvol direction: high vol → buy signal (IC=+0.015)",
        "Reversed mdd direction: deep drawdown → buy signal (IC=+0.017)",
        "Reduced momentum_20d weight: ±12 → ±6 (IC=-0.005, WEAK)",
        "Reduced RSI weight: ±12/6 → ±8/4 (IC=-0.004, WEAK)",
        "Reduced MA ratio weight: ±8 → ±4 (IC=-0.001, WEAK)",
        "Reduced MFI weight: ±8 → ±3 (IC=-0.002, WEAK)",
        "Reduced OBV weight: ±5 → ±2 (IC=-0.003, WEAK)",
        "Lowered buy threshold: 18 → 12, strong_buy: 35 → 25",
        "Relaxed buy gate: bear 4→3, non-bear 3→2",
        "Reduced bear suppression: 0.6 → 0.4",
    ],
    "bear_market": {
        "regime_penalty": 0.4,
        "sell_threshold": -10,
        "strong_sell_threshold": -25,
        "buy_confirmation_min_factors": 3,
    },
    "bull_market": {
        "regime_penalty": 0.2,
        "sell_threshold": -15,
        "strong_sell_threshold": -35,
        "buy_confirmation_min_factors": 2,
    },
    "ic_analysis": {
        "strong_factors": ["ret_5d (-0.022)", "pct_change (-0.025)"],
        "useful_factors": ["mdd_60d (+0.017)", "vol_price_div (+0.017)", "hvol_20d (+0.015)"],
        "weak_factors_removed": [
            "atr_14",
            "ma_ratio_5_20",
            "rsi_14",
            "momentum_20d",
            "mfi_14",
            "obv_trend_20d",
            "price_pctile_120d",
        ],
    },
}
