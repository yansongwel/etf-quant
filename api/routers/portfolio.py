"""Portfolio management and advisory API endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import require_api_key
from engine.portfolio_advisor import (
    Holding,
    analyze_portfolio,
    analyze_position,
    load_portfolio,
    save_portfolio,
)

router = APIRouter()

_CST = timezone(timedelta(hours=8))


def _now_cst() -> str:
    return datetime.now(_CST).strftime("%Y-%m-%d %H:%M:%S")


# ─── Models ───────────────────────────────────────────


class HoldingInput(BaseModel):
    symbol: str = Field(description="ETF 6-digit code")
    buy_price: float = Field(ge=0.001, description="Buy price per share")
    shares: int = Field(ge=100, description="Number of shares (must be multiple of 100)")
    buy_date: str = Field(default="", description="Buy date YYYY-MM-DD")
    note: str = Field(default="", description="User note")


class PortfolioInput(BaseModel):
    holdings: list[HoldingInput]
    portfolio_id: str = Field(default="default", description="Portfolio identifier")


class AddHoldingInput(BaseModel):
    symbol: str = Field(description="ETF 6-digit code")
    buy_price: float = Field(ge=0.001)
    shares: int = Field(ge=100)
    buy_date: str = Field(default="")
    note: str = Field(default="")
    portfolio_id: str = Field(default="default")


class RemoveHoldingInput(BaseModel):
    symbol: str
    portfolio_id: str = Field(default="default")


# ─── CRUD Endpoints ──────────────────────────────────


@router.get("/list")
def get_portfolio(portfolio_id: str = "default") -> dict:
    """Get all holdings in a portfolio."""
    holdings = load_portfolio(portfolio_id)
    return {
        "portfolio_id": portfolio_id,
        "count": len(holdings),
        "holdings": [
            {
                "symbol": h.symbol,
                "buy_price": h.buy_price,
                "shares": h.shares,
                "cost": round(h.cost, 2),
                "buy_date": h.buy_date,
                "note": h.note,
            }
            for h in holdings
        ],
        "generated_at": _now_cst(),
    }


@router.post("/save", dependencies=[Depends(require_api_key)])
def save_full_portfolio(req: PortfolioInput) -> dict:
    """Save or replace an entire portfolio."""
    holdings = [
        Holding(
            symbol=h.symbol,
            buy_price=h.buy_price,
            shares=h.shares,
            buy_date=h.buy_date,
            note=h.note,
        )
        for h in req.holdings
    ]
    save_portfolio(holdings, req.portfolio_id)
    return {"saved": len(holdings), "portfolio_id": req.portfolio_id}


@router.post("/add", dependencies=[Depends(require_api_key)])
def add_holding(req: AddHoldingInput) -> dict:
    """Add a single holding to an existing portfolio."""
    if len(req.symbol) != 6 or not req.symbol.isdigit():
        raise HTTPException(status_code=400, detail="Invalid ETF symbol")

    existing = load_portfolio(req.portfolio_id)

    # Check if already exists — merge if so (immutable: build new list)
    updated = False
    holdings = []
    for h in existing:
        if h.symbol == req.symbol:
            total_shares = h.shares + req.shares
            avg_price = (h.cost + req.buy_price * req.shares) / total_shares
            holdings.append(
                Holding(
                    symbol=h.symbol,
                    buy_price=round(avg_price, 4),
                    shares=total_shares,
                    buy_date=h.buy_date,
                    note=req.note if req.note else h.note,
                )
            )
            updated = True
        else:
            holdings.append(h)

    if not updated:
        holdings.append(
            Holding(
                symbol=req.symbol,
                buy_price=req.buy_price,
                shares=req.shares,
                buy_date=req.buy_date,
                note=req.note,
            )
        )

    save_portfolio(holdings, req.portfolio_id)
    _analyze_cache.pop(req.portfolio_id, None)  # Invalidate cache
    action = "updated" if updated else "added"
    return {"action": action, "symbol": req.symbol, "total_positions": len(holdings)}


@router.post("/remove", dependencies=[Depends(require_api_key)])
def remove_holding(req: RemoveHoldingInput) -> dict:
    """Remove a holding from the portfolio."""
    holdings = load_portfolio(req.portfolio_id)
    before = len(holdings)
    holdings = [h for h in holdings if h.symbol != req.symbol]
    after = len(holdings)

    if before == after:
        raise HTTPException(status_code=404, detail=f"{req.symbol} not in portfolio")

    save_portfolio(holdings, req.portfolio_id)
    _analyze_cache.pop(req.portfolio_id, None)  # Invalidate cache
    return {"removed": req.symbol, "remaining": after}


# ─── Advisory Endpoints ──────────────────────────────


_analyze_cache: dict[str, tuple[float, dict]] = {}
_ANALYZE_TTL = 60.0  # 1 minute — short because holdings can change


@router.get("/analyze")
def analyze_user_portfolio(portfolio_id: str = "default") -> dict:
    """Analyze portfolio and get per-position advice.

    This is the core advisory endpoint. Returns:
    - Overall portfolio health score
    - P&L summary
    - Per-position action recommendations (加仓/持有/减仓/清仓)
    - Urgency rankings
    """
    now = time.monotonic()
    if portfolio_id in _analyze_cache:
        ts, cached = _analyze_cache[portfolio_id]
        if now - ts < _ANALYZE_TTL:
            return cached

    holdings = load_portfolio(portfolio_id)
    if not holdings:
        raise HTTPException(
            status_code=404,
            detail="Portfolio is empty. Add holdings first via POST /api/portfolio/add",
        )

    result = analyze_portfolio(holdings)
    result["generated_at"] = _now_cst()
    _analyze_cache[portfolio_id] = (now, result)
    return result


@router.get("/analyze/{symbol}")
def analyze_single_position(
    symbol: str,
    buy_price: float = 0,
    shares: int = 100,
) -> dict:
    """Quick analysis for a single ETF position without saving to portfolio."""
    if len(symbol) != 6 or not symbol.isdigit():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    if buy_price <= 0:
        # Use current price as buy price
        from data.storage.parquet_store import load_hist

        df = load_hist(symbol)
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")
        buy_price = float(df["close"].iloc[-1])

    holding = Holding(symbol=symbol, buy_price=buy_price, shares=shares)
    advice = analyze_position(holding)
    if advice is None:
        raise HTTPException(status_code=422, detail="Insufficient data for analysis")

    return {**advice.to_dict(), "generated_at": _now_cst()}


@router.get("/equity-curve")
def get_portfolio_equity_curve(
    portfolio_id: str = "default",
    days: int = 60,
) -> dict:
    """Calculate portfolio value over time using historical prices.

    Returns daily total_value and total_pnl for charting.
    """
    from data.storage.parquet_store import load_hist

    holdings = load_portfolio(portfolio_id)
    if not holdings:
        raise HTTPException(status_code=404, detail="Portfolio is empty")

    # Load price data for all held symbols
    price_data: dict[str, dict[str, float]] = {}  # symbol -> {date_str: close}
    all_dates: set[str] = set()
    for h in holdings:
        df = load_hist(h.symbol)
        if df.empty:
            continue
        tail = df.tail(days)
        for date, row in tail.iterrows():
            ds = str(date.date())
            all_dates.add(ds)
            if h.symbol not in price_data:
                price_data[h.symbol] = {}
            price_data[h.symbol][ds] = float(row["close"])

    if not all_dates:
        return {"curve": [], "generated_at": _now_cst()}

    total_cost = sum(h.cost for h in holdings)
    curve = []
    for ds in sorted(all_dates):
        total_value = 0.0
        for h in holdings:
            price = price_data.get(h.symbol, {}).get(ds)
            if price is not None:
                total_value += h.shares * price
            else:
                total_value += h.cost  # fallback to cost if no price
        curve.append(
            {
                "date": ds,
                "value": round(total_value, 2),
                "pnl": round(total_value - total_cost, 2),
                "pnl_pct": round((total_value - total_cost) / total_cost * 100, 2)
                if total_cost > 0
                else 0,
            }
        )

    return {
        "total_cost": round(total_cost, 2),
        "count": len(curve),
        "curve": curve,
        "generated_at": _now_cst(),
    }
