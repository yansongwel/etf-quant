"""Data endpoints — historical prices, spot snapshots."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from data.cache import cache_json_get, cache_json_set
from data.storage.parquet_store import load_hist
from data.validators import validate_symbol

_CST = timezone(timedelta(hours=8))


def _now_cst() -> str:
    return datetime.now(_CST).strftime("%Y-%m-%d %H:%M:%S")


router = APIRouter()

# In-memory cache for data quality (expensive: reads all 38 parquets)
_quality_cache: tuple[float, dict] | None = None
_QUALITY_TTL = 300.0  # 5 minutes


@router.get("/hist/{symbol}")
def get_historical(
    symbol: str,
    start: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(500, ge=1, le=5000, description="Max rows to return"),
) -> dict:
    """Get historical OHLCV data for a single ETF."""
    if len(symbol) != 6 or not symbol.isdigit():
        raise HTTPException(status_code=400, detail="Symbol must be a 6-digit string")

    # Try cache first
    cache_key = f"hist:{symbol}:{start}:{end}:{limit}"
    cached = cache_json_get(cache_key)
    if cached is not None:
        return cached

    df = load_hist(symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for symbol {symbol}")

    # Filter by date range
    if start:
        df = df[df.index >= str(start)]
    if end:
        df = df[df.index <= str(end)]

    df = df.tail(limit)

    # Convert to response format
    records = []
    for idx, row in df.iterrows():
        records.append(
            {
                "date": str(idx.date()) if hasattr(idx, "date") else str(idx),
                "open": round(float(row.get("open", 0)), 4),
                "high": round(float(row.get("high", 0)), 4),
                "low": round(float(row.get("low", 0)), 4),
                "close": round(float(row.get("close", 0)), 4),
                "volume": int(row.get("volume", 0)),
            }
        )

    result = {
        "symbol": symbol,
        "count": len(records),
        "data": records,
    }

    cache_json_set(cache_key, result, ttl=300)  # 5 min cache
    return result


@router.get("/symbols")
def list_available_symbols() -> dict:
    """List all symbols that have stored historical data."""
    from config.settings import settings

    data_dir = settings.data.data_dir / "etf_hist"
    if not data_dir.exists():
        return {"symbols": [], "count": 0}

    symbols = sorted(f.stem for f in data_dir.glob("*.parquet"))
    return {"symbols": symbols, "count": len(symbols)}


@router.get("/quality/{symbol}")
def get_data_quality(symbol: str) -> dict:
    """Run data quality checks for a single ETF."""
    if len(symbol) != 6 or not symbol.isdigit():
        raise HTTPException(status_code=400, detail="Symbol must be a 6-digit string")

    df = load_hist(symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for symbol {symbol}")

    report = validate_symbol(df, symbol)
    return report.to_dict()


@router.get("/quality")
def get_all_data_quality() -> dict:
    """Run data quality checks for all available symbols. Cached for 5 min."""
    global _quality_cache
    now = time.monotonic()
    if _quality_cache is not None:
        ts, result = _quality_cache
        if now - ts < _QUALITY_TTL:
            return result

    from config.settings import settings

    data_dir = settings.data.data_dir / "etf_hist"
    if not data_dir.exists():
        return {"reports": [], "count": 0}

    reports = []
    for f in sorted(data_dir.glob("*.parquet")):
        df = load_hist(f.stem)
        if not df.empty:
            report = validate_symbol(df, f.stem)
            reports.append(report.to_dict())

    avg_score = sum(r["quality_score"] for r in reports) / len(reports) if reports else 0
    result = {
        "count": len(reports),
        "average_score": round(avg_score, 1),
        "reports": reports,
        "generated_at": _now_cst(),
    }
    _quality_cache = (now, result)
    return result
