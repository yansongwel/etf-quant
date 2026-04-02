"""Backtest endpoints — run strategies and return results."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from data.storage.parquet_store import load_hist
from engine.backtest import run_backtest
from engine.metrics import summary
from engine.types import BacktestConfig
from strategies.balance import BalanceStrategy
from strategies.grid import GridStrategy
from strategies.multifactor import MultiFactorStrategy
from strategies.rotation import RotationStrategy

router = APIRouter()


# ── Shared helpers ────────────────────────────────────────


def _load_data(symbols: list[str]) -> tuple[dict, list[str]]:
    """Load historical data for symbols. Returns (data_dict, missing_list)."""
    data: dict = {}
    missing: list[str] = []
    for sym in symbols:
        if len(sym) != 6 or not sym.isdigit():
            raise HTTPException(status_code=400, detail=f"Invalid symbol: {sym}")
        df = load_hist(sym)
        if df.empty:
            missing.append(sym)
        else:
            data[sym] = df
    return data, missing


def _format_result(result, missing: list[str]) -> dict:
    """Format backtest result into API response."""
    metrics = summary(result)
    equity = result.equity_curve
    equity_data = [
        {"date": str(d.date()), "value": round(v, 2)}
        for d, v in zip(equity.index, equity.values, strict=True)
    ]
    trades = [
        {
            "date": str(t.date.date()),
            "signal_date": str(t.signal_date.date()),
            "symbol": t.symbol,
            "side": t.side.value,
            "price": round(t.price, 4),
            "shares": t.shares,
            "commission": round(t.commission, 2),
        }
        for t in result.trades
    ]
    return {
        "metrics": {k: round(v, 6) if isinstance(v, float) else v for k, v in metrics.items()},
        "equity_curve": {"count": len(equity_data), "data": equity_data[-500:]},
        "trades": {"count": len(trades), "data": trades[-100:]},
        "warnings": [f"Missing data for: {sym}" for sym in missing] if missing else [],
    }


# ── Rotation Strategy ────────────────────────────────────


class RotationRequest(BaseModel):
    symbols: list[str] = Field(
        default=["510300", "510500", "510050", "159915", "512010"],
        description="ETF symbols",
    )
    lookback: int = Field(default=20, ge=5, le=120)
    top_k: int = Field(default=3, ge=1, le=10)
    rebalance_days: int = Field(default=20, ge=5, le=60)
    initial_cash: float = Field(default=1_000_000, ge=10_000)
    commission_rate: float = Field(default=0.0002, ge=0, le=0.01)
    slippage: float = Field(default=0.001, ge=0, le=0.01)


@router.post("/rotation")
def run_rotation_backtest(req: RotationRequest) -> dict:
    """Run momentum rotation backtest."""
    data, missing = _load_data(req.symbols)
    if not data:
        raise HTTPException(404, f"No data. Missing: {missing}")

    strategy = RotationStrategy(req.lookback, req.top_k, req.rebalance_days)
    config = BacktestConfig(req.initial_cash, req.commission_rate, req.slippage)
    result = run_backtest(data, strategy, config)
    return _format_result(result, missing)


# ── Balance Strategy ──────────────────────────────────────


class BalanceRequest(BaseModel):
    stock_symbol: str = Field(default="510300", description="Stock ETF")
    bond_symbol: str = Field(default="511010", description="Bond ETF")
    stock_weight: float = Field(default=0.6, ge=0.1, le=0.9, description="Stock allocation")
    drift_threshold: float = Field(default=0.1, ge=0.02, le=0.3)
    min_rebalance_days: int = Field(default=10, ge=1, le=60)
    initial_cash: float = Field(default=1_000_000, ge=10_000)
    commission_rate: float = Field(default=0.0002, ge=0, le=0.01)
    slippage: float = Field(default=0.001, ge=0, le=0.01)


@router.post("/balance")
def run_balance_backtest(req: BalanceRequest) -> dict:
    """Run stock-bond balance backtest."""
    data, missing = _load_data([req.stock_symbol, req.bond_symbol])
    if len(data) < 2:
        raise HTTPException(404, f"Need both stock and bond data. Missing: {missing}")

    strategy = BalanceStrategy(
        req.stock_symbol,
        req.bond_symbol,
        req.stock_weight,
        req.drift_threshold,
        req.min_rebalance_days,
    )
    config = BacktestConfig(req.initial_cash, req.commission_rate, req.slippage)
    result = run_backtest(data, strategy, config)
    return _format_result(result, missing)


# ── Grid Strategy ─────────────────────────────────────────


class GridRequest(BaseModel):
    symbol: str = Field(default="510300", description="ETF to grid-trade")
    grid_count: int = Field(default=10, ge=3, le=30)
    grid_width_pct: float = Field(default=0.02, ge=0.005, le=0.1)
    position_per_grid: float = Field(default=0.08, ge=0.01, le=0.2)
    initial_cash: float = Field(default=1_000_000, ge=10_000)
    commission_rate: float = Field(default=0.0002, ge=0, le=0.01)
    slippage: float = Field(default=0.001, ge=0, le=0.01)


@router.post("/grid")
def run_grid_backtest(req: GridRequest) -> dict:
    """Run grid trading backtest."""
    data, missing = _load_data([req.symbol])
    if not data:
        raise HTTPException(404, f"No data for {req.symbol}")

    strategy = GridStrategy(
        req.symbol,
        req.grid_count,
        req.grid_width_pct,
        req.position_per_grid,
    )
    config = BacktestConfig(req.initial_cash, req.commission_rate, req.slippage)
    result = run_backtest(data, strategy, config)
    return _format_result(result, missing)


# ── Multi-Factor Strategy ────────────────────────────────


class MultiFactorRequest(BaseModel):
    symbols: list[str] = Field(
        default=["510300", "510500", "510050", "159915", "512010"],
        description="ETF universe",
    )
    lookback: int = Field(default=20, ge=5, le=120)
    top_k: int = Field(default=3, ge=1, le=10)
    rebalance_days: int = Field(default=20, ge=5, le=60)
    momentum_weight: float = Field(default=0.5, ge=0, le=1)
    value_weight: float = Field(default=0.3, ge=0, le=1)
    volatility_weight: float = Field(default=0.2, ge=0, le=1)
    initial_cash: float = Field(default=1_000_000, ge=10_000)
    commission_rate: float = Field(default=0.0002, ge=0, le=0.01)
    slippage: float = Field(default=0.001, ge=0, le=0.01)


@router.post("/multifactor")
def run_multifactor_backtest(req: MultiFactorRequest) -> dict:
    """Run multi-factor scoring backtest."""
    data, missing = _load_data(req.symbols)
    if not data:
        raise HTTPException(404, f"No data. Missing: {missing}")

    strategy = MultiFactorStrategy(
        req.lookback,
        req.top_k,
        req.rebalance_days,
        req.momentum_weight,
        req.value_weight,
        req.volatility_weight,
    )
    config = BacktestConfig(req.initial_cash, req.commission_rate, req.slippage)
    result = run_backtest(data, strategy, config)
    return _format_result(result, missing)


# ── List available strategies ─────────────────────────────


@router.get("/strategies")
def list_strategies() -> list[dict]:
    """List all available backtest strategies with their parameters."""
    return [
        {
            "id": "rotation",
            "name": "动量轮动",
            "description": "按动量排名在 ETF 间定期切换",
            "endpoint": "/api/backtest/rotation",
        },
        {
            "id": "balance",
            "name": "股债平衡",
            "description": "股票/债券 ETF 按目标比例再平衡",
            "endpoint": "/api/backtest/balance",
        },
        {
            "id": "grid",
            "name": "网格交易",
            "description": "在价格网格内高抛低吸",
            "endpoint": "/api/backtest/grid",
        },
        {
            "id": "multifactor",
            "name": "多因子打分",
            "description": "综合动量、价值、波动率因子排序选 ETF",
            "endpoint": "/api/backtest/multifactor",
        },
    ]
