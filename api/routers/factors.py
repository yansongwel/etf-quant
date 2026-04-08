"""Factor calculation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from data.cache import cache_json_get, cache_json_set
from data.storage.parquet_store import load_hist
from factors.momentum import compute_momentum_factors
from factors.value import compute_value_factors
from factors.volatility import compute_volatility_factors

router = APIRouter()

FACTOR_COMPUTERS = {
    "momentum": compute_momentum_factors,
    "value": compute_value_factors,
    "volatility": compute_volatility_factors,
}


@router.get("/{symbol}")
def get_factors(
    symbol: str,
    category: str = Query("momentum", description="Factor category: momentum, value, volatility"),
    tail: int = Query(30, ge=1, le=500, description="Number of recent rows to return"),
) -> dict:
    """Compute and return factor values for a symbol."""
    if len(symbol) != 6 or not symbol.isdigit():
        raise HTTPException(status_code=400, detail="Symbol must be a 6-digit string")

    if category not in FACTOR_COMPUTERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown category: {category}. Choose from: {list(FACTOR_COMPUTERS.keys())}",
        )

    cache_key = f"factors:{category}:{symbol}:{tail}"
    cached = cache_json_get(cache_key)
    if cached is not None:
        return cached

    df = load_hist(symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for symbol {symbol}")

    compute_fn = FACTOR_COMPUTERS[category]
    result_df = compute_fn(df)

    # Get only the factor columns (not OHLCV)
    ohlcv_cols = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "amplitude",
        "pct_change",
        "change",
        "turnover",
        "symbol",
    }
    factor_cols = [c for c in result_df.columns if c not in ohlcv_cols]

    if not factor_cols:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data to compute {category} factors (need more history)",
        )

    tail_df = result_df[factor_cols].tail(tail)

    records = []
    for idx, row in tail_df.iterrows():
        record = {"date": str(idx.date()) if hasattr(idx, "date") else str(idx)}
        for col in factor_cols:
            val = row[col]
            record[col] = round(float(val), 6) if val == val else None  # NaN → None
        records.append(record)

    result = {
        "symbol": symbol,
        "category": category,
        "factors": factor_cols,
        "count": len(records),
        "data": records,
    }

    cache_json_set(cache_key, result, ttl=600)  # 10 min cache
    return result


class CompareRequest(BaseModel):
    """Request body for cross-sectional factor comparison."""

    symbols: list[str] = Field(
        default=["510300", "510500", "510050", "159915", "512010"],
        description="ETF symbols to compare",
    )
    category: str = Field(default="momentum", description="Factor category")


@router.post("/compare")
def compare_factors(req: CompareRequest) -> dict:
    """Compute latest factor values for multiple symbols side-by-side.

    Returns a table with symbols as rows and factors as columns.
    Useful for cross-sectional ranking and comparison.
    """
    if req.category not in FACTOR_COMPUTERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown category: {req.category}. "
            f"Choose from: {list(FACTOR_COMPUTERS.keys())}",
        )

    compute_fn = FACTOR_COMPUTERS[req.category]
    ohlcv_cols = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "amplitude",
        "pct_change",
        "change",
        "turnover",
        "symbol",
    }

    rows = []
    missing: list[str] = []

    for symbol in req.symbols:
        if len(symbol) != 6 or not symbol.isdigit():
            raise HTTPException(status_code=400, detail=f"Invalid symbol: {symbol}")

        df = load_hist(symbol)
        if df.empty:
            missing.append(symbol)
            continue

        result_df = compute_fn(df)
        factor_cols = [c for c in result_df.columns if c not in ohlcv_cols]
        if not factor_cols:
            missing.append(symbol)
            continue

        last_row = result_df[factor_cols].iloc[-1]
        row: dict = {"symbol": symbol}
        for col in factor_cols:
            val = last_row[col]
            row[col] = round(float(val), 6) if val == val else None
        rows.append(row)

    factor_names = list(rows[0].keys())[1:] if rows else []

    return {
        "category": req.category,
        "factors": factor_names,
        "count": len(rows),
        "data": rows,
        "missing": missing,
    }


@router.get("/correlation/{symbol}")
def get_factor_correlation(
    symbol: str,
    tail: int = Query(120, ge=30, le=500, description="Trading days to compute over"),
) -> dict:
    """Compute correlation matrix across all factor categories for a single ETF.

    Returns a symmetric matrix of Pearson correlations between factors.
    """
    if len(symbol) != 6 or not symbol.isdigit():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    cache_key = f"corr:{symbol}:{tail}"
    cached = cache_json_get(cache_key)
    if cached is not None:
        return cached

    import pandas as pd

    df = load_hist(symbol)
    if df.empty or len(df) < tail:
        raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")

    ohlcv_cols = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "amplitude",
        "pct_change",
        "change",
        "turnover",
        "symbol",
    }

    # Compute all factor categories
    all_factors = pd.DataFrame(index=df.index)
    for compute_fn in FACTOR_COMPUTERS.values():
        result_df = compute_fn(df)
        factor_cols = [c for c in result_df.columns if c not in ohlcv_cols]
        for c in factor_cols:
            all_factors[c] = result_df[c]

    # Use tail rows, drop NaN-heavy columns
    all_factors = all_factors.tail(tail).dropna(axis=1, thresh=int(tail * 0.7))
    if all_factors.shape[1] < 2:
        raise HTTPException(status_code=422, detail="Not enough factors with valid data")

    corr = all_factors.corr()
    factor_names = list(corr.columns)

    # Convert to list-of-lists for frontend
    matrix = []
    for row_name in factor_names:
        row = []
        for col_name in factor_names:
            val = corr.loc[row_name, col_name]
            row.append(round(float(val), 3) if val == val else 0)
        matrix.append(row)

    result = {
        "symbol": symbol,
        "factors": factor_names,
        "size": len(factor_names),
        "matrix": matrix,
    }
    cache_json_set(cache_key, result, ttl=600)
    return result


@router.get("/ic/latest")
def get_factor_ic() -> dict:
    """Return latest factor IC evaluation results from disk."""
    import json
    from pathlib import Path

    ic_file = Path("data_store/factor_ic_history/latest.json")
    if not ic_file.exists():
        raise HTTPException(
            status_code=404,
            detail="No IC evaluation results found. Run scripts/factor_ic.py first.",
        )

    data = json.loads(ic_file.read_text(encoding="utf-8"))
    return data
