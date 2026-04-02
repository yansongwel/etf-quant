"""Sector rotation analysis API endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from engine.sector import analyze_all_sectors, generate_portfolio_plan

router = APIRouter()


@router.get("/rotation")
def get_sector_rotation() -> dict:
    """Get current sector rotation analysis for all industry groups."""
    sectors = analyze_all_sectors()
    cst = timezone(timedelta(hours=8))
    return {
        "count": len(sectors),
        "sectors": [s.to_dict() for s in sectors],
        "generated_at": datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/groups")
def get_sector_groups() -> dict:
    """Get sector → ETF mapping with names for the explorer UI."""
    from config.constants import DEFAULT_ETF_LIST

    name_map = {e["symbol"]: e["name"] for e in DEFAULT_ETF_LIST}
    sectors = analyze_all_sectors()

    groups = []
    for s in sectors:
        sd = s.to_dict()
        etfs = []
        for sym in sd["etf_symbols"]:
            etfs.append({"symbol": sym, "name": name_map.get(sym, sym)})
        groups.append(
            {
                "sector": sd["sector_name"],
                "phase": sd["phase"],
                "phase_label": sd["phase_label"],
                "etfs": etfs,
                "best_etf": sd["best_etf"],
            }
        )

    return {"count": len(groups), "groups": groups}


class PortfolioPlanRequest(BaseModel):
    capital: float = Field(default=500000, ge=1000, description="投资资金(CNY)")
    max_sectors: int = Field(default=5, ge=1, le=9)
    risk_appetite: Literal["conservative", "moderate", "aggressive"] = Field(default="aggressive")


@router.post("/plan")
def get_portfolio_plan(req: PortfolioPlanRequest) -> dict:
    """Generate a complete portfolio plan based on sector rotation.

    Returns specific ETF buy recommendations with amounts.
    """
    result = generate_portfolio_plan(
        capital=req.capital,
        max_sectors=req.max_sectors,
        risk_appetite=req.risk_appetite,
    )
    cst = timezone(timedelta(hours=8))
    result["generated_at"] = datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S")
    return result
