"""Flow detection and risk advisory API endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from data.storage.parquet_store import load_hist
from engine.flow import detect_flow, detect_flow_batch
from engine.risk_advisor import assess_etf_risk, full_risk_report, generate_layout_suggestions

router = APIRouter()


# ─── Flow Detection ───────────────────────────────────────


@router.get("/flow/scan")
def scan_flow(
    symbols: str = Query(
        default="",
        description="Comma-separated ETF symbols. Empty = all available.",
    ),
) -> dict:
    """Scan for institutional flow patterns across all ETFs.

    Detects volume anomalies that may indicate institutional activity:
    accumulation (吸筹), distribution (出货), breakout buying, or panic selling.
    """
    from config.constants import DEFAULT_ETF_LIST
    from config.settings import settings

    max_symbols = 50
    if symbols:
        sym_list = [
            s.strip() for s in symbols.split(",") if len(s.strip()) == 6 and s.strip().isdigit()
        ]
        if len(sym_list) > max_symbols:
            sym_list = sym_list[:max_symbols]
    else:
        data_dir = settings.data.data_dir / "etf_hist"
        if data_dir.exists():
            sym_list = sorted(f.stem for f in data_dir.glob("*.parquet"))
        else:
            sym_list = [e["symbol"] for e in DEFAULT_ETF_LIST]

    data = {}
    for sym in sym_list:
        df = load_hist(sym)
        if not df.empty:
            data[sym] = df

    if not data:
        raise HTTPException(status_code=404, detail="No data available")

    signals = detect_flow_batch(data)

    name_map = {e["symbol"]: e["name"] for e in DEFAULT_ETF_LIST}
    abnormal = [s for s in signals if s.flow_type.value != "normal"]

    cst = timezone(timedelta(hours=8))
    return {
        "total_scanned": len(signals),
        "abnormal_count": len(abnormal),
        "signals": [{**s.to_dict(), "name": name_map.get(s.symbol, s.symbol)} for s in signals],
        "generated_at": datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/flow/detail/{symbol}")
def get_flow_detail(symbol: str) -> dict:
    """Get detailed flow analysis for a single ETF."""
    if len(symbol) != 6 or not symbol.isdigit():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    df = load_hist(symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    signal = detect_flow(df, symbol)
    if signal is None:
        raise HTTPException(status_code=422, detail="Insufficient data")

    from config.constants import DEFAULT_ETF_LIST

    name_map = {e["symbol"]: e["name"] for e in DEFAULT_ETF_LIST}
    return {**signal.to_dict(), "name": name_map.get(symbol, symbol)}


# ─── Risk Advisory ────────────────────────────────────────


class RiskReportRequest(BaseModel):
    capital: float = Field(default=500000, ge=10000, description="Total capital in CNY")


@router.post("/risk/report")
def get_risk_report(req: RiskReportRequest) -> dict:
    """Get comprehensive risk report with risk profiles, layout suggestions, and rules."""
    return full_risk_report(req.capital)


@router.get("/risk/etf/{symbol}")
def get_etf_risk(symbol: str) -> dict:
    """Get risk assessment for a single ETF."""
    if len(symbol) != 6 or not symbol.isdigit():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    df = load_hist(symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    profile = assess_etf_risk(df, symbol)
    if profile is None:
        raise HTTPException(status_code=422, detail="Insufficient data")

    return profile.to_dict()


class LayoutRequest(BaseModel):
    capital: float = Field(default=500000, ge=10000, description="Total capital in CNY")


@router.post("/risk/layout")
def get_layout_suggestions(req: LayoutRequest) -> dict:
    """Get early-positioning (提前布局) suggestions.

    Combines sector rotation, institutional flow, and risk assessment
    to recommend where to position ahead of the market.
    """
    suggestions = generate_layout_suggestions(req.capital)

    buy_suggestions = [s for s in suggestions if s.position_pct > 0]
    avoid_suggestions = [s for s in suggestions if s.position_pct == 0]

    return {
        "capital": req.capital,
        "total_suggestions": len(suggestions),
        "buy_opportunities": len(buy_suggestions),
        "avoid_count": len(avoid_suggestions),
        "suggestions": [s.to_dict() for s in suggestions],
        "disclaimer": "布局建议基于量化分析，仅供参考。请结合自身风险承受能力决策。",
    }
