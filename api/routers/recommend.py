"""Proven strategy recommendation API — uses backtested optimal parameters."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config.optimal_params import ALL_OPTIMAL
from data.storage.parquet_store import load_hist
from engine.backtest import run_backtest
from engine.metrics import summary
from engine.types import BacktestConfig
from strategies.multifactor import MultiFactorStrategy
from strategies.rotation import RotationStrategy

router = APIRouter()


class RecommendRequest(BaseModel):
    capital: float = Field(default=500000, ge=1000, description="投资资金(CNY)")


_proven_cache: dict[float, tuple[float, dict]] = {}
_PROVEN_CACHE_TTL = 600  # 10 minutes


@router.post("/proven")
def get_proven_strategies(req: RecommendRequest) -> dict:
    """Get proven profitable strategies with specific ETF codes and amounts.

    These strategies are backtested to be profitable over 5 years.
    Returns specific buy recommendations with amounts.
    Results cached for 10 minutes since backtests are expensive.
    """
    now = time.monotonic()
    if req.capital in _proven_cache:
        ts, cached = _proven_cache[req.capital]
        if now - ts < _PROVEN_CACHE_TTL:
            return cached

    results = []

    for i, strat_config in enumerate(ALL_OPTIMAL, 1):
        # Load data
        data = {}
        for sym in strat_config["symbols"]:
            df = load_hist(sym)
            if not df.empty:
                data[sym] = df

        if len(data) < 2:
            continue

        # Build strategy
        params = strat_config["params"]
        config = BacktestConfig(
            initial_cash=req.capital,
            commission_rate=0.0002,
            slippage=0.001,
        )

        if strat_config["strategy"] == "multifactor":
            strategy = MultiFactorStrategy(**params)
        else:
            strategy = RotationStrategy(
                lookback=params["lookback"],
                top_k=params["top_k"],
                rebalance_days=params["rebalance_days"],
            )

        result = run_backtest(data, strategy, config)
        metrics = summary(result)

        # Get current positions (what to buy NOW)
        current_buys = []
        if result.snapshots:
            last_snap = result.snapshots[-1]
            for pos in last_snap.positions:
                name = ""
                for j, sym in enumerate(strat_config["symbols"]):
                    if sym == pos.symbol:
                        name = strat_config["symbol_names"][j]
                        break
                current_buys.append(
                    {
                        "etf_code": pos.symbol,
                        "etf_name": name,
                        "shares": pos.shares,
                        "avg_cost": round(pos.avg_cost, 4),
                        "current_value": round(
                            pos.shares * float(data[pos.symbol]["close"].iloc[-1]), 2
                        ),
                    }
                )

        # Calculate expected amounts per ETF
        etf_pool = []
        for j, sym in enumerate(strat_config["symbols"]):
            price = float(data[sym]["close"].iloc[-1]) if sym in data else 0
            etf_pool.append(
                {
                    "code": sym,
                    "name": strat_config["symbol_names"][j],
                    "current_price": round(price, 4),
                }
            )

        final_value = result.equity_curve.iloc[-1] if not result.equity_curve.empty else req.capital
        profit = final_value - req.capital

        results.append(
            {
                "rank": i,
                "name": strat_config["name"],
                "strategy_type": strat_config["strategy"],
                "etf_pool": etf_pool,
                "params": params,
                "backtest_result": {
                    "total_return": round(metrics["total_return"] * 100, 1),
                    "annualized_return": round(metrics["annualized_return"] * 100, 1),
                    "sharpe_ratio": round(metrics["sharpe_ratio"], 2),
                    "max_drawdown": round(metrics["max_drawdown"] * 100, 1),
                    "win_rate": round(metrics["win_rate"] * 100, 1),
                    "total_trades": metrics["total_trades"],
                    "final_value": round(final_value, 0),
                    "total_profit": round(profit, 0),
                },
                "current_holding": current_buys,
                "rebalance_note": f"每{params.get('rebalance_days', 20)}个交易日调仓一次",
            }
        )

    cst = timezone(timedelta(hours=8))
    response = {
        "capital": req.capital,
        "strategies": results,
        "disclaimer": "基于2021-2026年历史回测数据，不代表未来收益。仅供研究参考，不构成投资建议。",
        "generated_at": datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S"),
    }

    _proven_cache[req.capital] = (now, response)
    return response
