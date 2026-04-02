"""Signal and recommendation API endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import require_api_key
from data.storage.parquet_store import load_hist
from engine.alerts import check_alerts
from engine.recommender import recommend_strategies
from engine.signals import (
    calculate_positions,
    generate_signal,
    generate_signals_batch,
)
from engine.tracker import get_overall_accuracy, record_signals

router = APIRouter()

_CST = timezone(timedelta(hours=8))


def _now_cst() -> str:
    """Current Beijing time as string."""
    return datetime.now(_CST).strftime("%Y-%m-%d %H:%M:%S")


# ─── Signal cache (TTL = 60s) ───────────────────────
# Signal computation is expensive (~35s for 38 ETFs). Cache results since
# market data only changes once per day. 60s TTL is conservative.
_signal_cache: dict[str, tuple[float, list, dict[str, object]]] = {}
_SIGNAL_CACHE_TTL = 60.0  # seconds


def _get_cached_signals(
    cache_key: str, ttl: float = _SIGNAL_CACHE_TTL
) -> tuple[list, dict[str, object]] | None:
    if cache_key in _signal_cache:
        ts, signals, data_map = _signal_cache[cache_key]
        if time.monotonic() - ts < ttl:
            return signals, data_map
        del _signal_cache[cache_key]
    return None


def _set_cached_signals(cache_key: str, signals: list, data_map: dict[str, object]) -> None:
    _signal_cache[cache_key] = (time.monotonic(), signals, data_map)


def _is_market_open() -> bool:
    """Check if A-share market is in trading session (including lunch break).

    Returns True from 9:30 to 15:00 on weekdays, including 11:30-13:00 lunch
    break — during lunch the morning session data is still today's valid data,
    so realtime injection should remain active.
    """
    now = datetime.now(_CST)
    if now.weekday() >= 5:
        return False
    hm = now.hour * 100 + now.minute
    return 930 <= hm <= 1500


def _inject_realtime_prices(data: dict) -> dict:
    """During trading hours, append real-time prices as an intraday row.

    This makes signal factors (momentum, RSI, etc.) reflect current market
    prices instead of yesterday's close. The injected row is NOT persisted.
    """
    import pandas as pd

    from data.collectors.realtime import fetch_realtime_quotes

    symbols = list(data.keys())
    rt = fetch_realtime_quotes(symbols)
    if rt.empty:
        return data

    enhanced = {}
    for sym, df in data.items():
        row = rt[rt["symbol"] == sym]
        if row.empty:
            enhanced[sym] = df
            continue
        r = row.iloc[0]
        trade_date = pd.Timestamp(r["date"])
        # Only inject if realtime date is newer than last bar
        if trade_date <= df.index.max():
            enhanced[sym] = df
            continue
        new_row = pd.DataFrame(
            [
                {
                    "open": r["open"],
                    "close": r["close"],
                    "high": r["high"],
                    "low": r["low"],
                    "volume": r["volume"],
                    "amount": r.get("amount", 0),
                    "symbol": sym,
                }
            ],
            index=pd.DatetimeIndex([trade_date], name="date"),
        )
        enhanced[sym] = pd.concat([df, new_row]).sort_index()

    return enhanced


def _load_all_data(symbols: str = "") -> tuple[str, list | None, dict]:
    """Load data for signal generation.

    Returns (cache_key, cached_signals_or_None, data_dict).
    When cached_signals is not None, data_dict is empty — use the cached signals directly.
    During trading hours, appends real-time prices so signals reflect the live market.
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

    # During market hours, use shorter cache TTL (30s) for fresher signals
    market_open = _is_market_open()
    ttl = 30.0 if market_open else _SIGNAL_CACHE_TTL
    cache_key = ",".join(sym_list)

    cached = _get_cached_signals(cache_key, ttl=ttl)
    if cached is not None:
        signals, _ = cached
        return cache_key, signals, {}

    data = {}
    for sym in sym_list:
        df = load_hist(sym)
        if not df.empty:
            data[sym] = df

    # Inject live prices during trading hours
    if market_open and data:
        data = _inject_realtime_prices(data)

    return cache_key, None, data


@router.get("/current")
def get_current_signals(
    symbols: str = Query(
        default="",
        description="Comma-separated ETF symbols. Empty = all available.",
    ),
    tier: str = Query(
        default="",
        description="Filter by tier: action, watch, reference. Empty = all.",
    ),
) -> dict:
    """Get real-time trading signals for ETFs.

    Returns signals sorted by score (best buy opportunities first).
    Results are cached for 60s since signal computation is expensive (~35s).

    V5.0 tier system:
    - action: score>=50 buy or 3+ sell signals (80% accuracy, ~every 12 days)
    - watch: score 30-49 buy or 2 sell signals (58% accuracy)
    - reference: score 20-29 buy (marginal edge)
    """
    from config.constants import DEFAULT_ETF_LIST

    cache_key, cached_signals, data = _load_all_data(symbols)

    if cached_signals is not None:
        signals = cached_signals
    else:
        if not data:
            raise HTTPException(status_code=404, detail="No data available")
        signals = generate_signals_batch(data)
        _set_cached_signals(cache_key, signals, {})

    # Filter by tier if requested
    if tier:
        signals = [s for s in signals if s.tier.value == tier]

    # Enrich with ETF names
    name_map = {e["symbol"]: e["name"] for e in DEFAULT_ETF_LIST}

    # Tier summary
    tier_counts = {
        "action": sum(1 for s in signals if s.tier.value == "action"),
        "watch": sum(1 for s in signals if s.tier.value == "watch"),
        "reference": sum(1 for s in signals if s.tier.value == "reference"),
    }

    return {
        "count": len(signals),
        "signals": [{**s.to_dict(), "name": name_map.get(s.symbol, s.symbol)} for s in signals],
        "summary": {
            "strong_buy": sum(1 for s in signals if s.direction.value == "strong_buy"),
            "buy": sum(1 for s in signals if s.direction.value == "buy"),
            "hold": sum(1 for s in signals if s.direction.value == "hold"),
            "sell": sum(1 for s in signals if s.direction.value == "sell"),
            "strong_sell": sum(1 for s in signals if s.direction.value == "strong_sell"),
        },
        "tiers": tier_counts,
        "generated_at": _now_cst(),
    }


@router.get("/detail/{symbol}")
def get_signal_detail(symbol: str) -> dict:
    """Get detailed trading signal for a single ETF."""
    if len(symbol) != 6 or not symbol.isdigit():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    df = load_hist(symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    signal = generate_signal(df, symbol)
    if signal is None:
        raise HTTPException(status_code=422, detail="Insufficient data for signal generation")

    return {**signal.to_dict(), "generated_at": _now_cst()}


class PositionRequest(BaseModel):
    capital: float = Field(default=5000, ge=100, description="Available capital in CNY")
    symbols: str = Field(default="", description="Comma-separated symbols. Empty = all.")
    max_positions: int = Field(default=5, ge=1, le=10)


@router.post("/positions")
def calculate_trading_positions(req: PositionRequest) -> dict:
    """Calculate specific buy positions based on available capital.

    Returns: which ETFs to buy, how many shares, exact amounts.
    Uses cached signals when available (same 60s TTL).
    """
    from config.constants import DEFAULT_ETF_LIST

    cache_key, cached_signals, data = _load_all_data(req.symbols)

    if cached_signals is not None:
        signals = cached_signals
    else:
        if not data:
            raise HTTPException(status_code=404, detail="No data available")
        signals = generate_signals_batch(data)
        _set_cached_signals(cache_key, signals, {})

    positions = calculate_positions(signals, req.capital, req.max_positions)

    total_invested = sum(p["buy_amount"] for p in positions)
    name_map = {e["symbol"]: e["name"] for e in DEFAULT_ETF_LIST}

    return {
        "capital": req.capital,
        "invested": round(total_invested, 2),
        "remaining": round(req.capital - total_invested, 2),
        "positions": [{**p, "name": name_map.get(p["symbol"], p["symbol"])} for p in positions],
        "disclaimer": "仅供研究参考，不构成投资建议。ETF 交易遵循 T+1 规则。",
        "generated_at": _now_cst(),
    }


class RecommendRequest(BaseModel):
    capital: float = Field(default=5000, ge=100, description="Available capital in CNY")
    max_results: int = Field(default=5, ge=1, le=10)


_recommend_cache: dict[str, tuple[float, dict]] = {}
_RECOMMEND_CACHE_TTL = 600  # 10 minutes — recommendations don't change quickly


@router.post("/recommend")
def get_recommendations(req: RecommendRequest) -> dict:
    """Get strategy recommendations ranked by risk-adjusted performance.

    Evaluates multiple strategies with different parameters against all
    available ETF data and returns the best combinations.
    Results are cached for 10 minutes since backtests are expensive (~30s).
    """
    cache_key = f"{req.capital}:{req.max_results}"
    now = time.monotonic()

    if cache_key in _recommend_cache:
        ts, cached_result = _recommend_cache[cache_key]
        if now - ts < _RECOMMEND_CACHE_TTL:
            return cached_result

    results = recommend_strategies(req.capital, req.max_results)

    response = {
        "capital": req.capital,
        "count": len(results),
        "recommendations": [r.to_dict() for r in results],
        "disclaimer": "基于历史回测数据，不代表未来收益。仅供研究参考。",
        "generated_at": _now_cst(),
    }

    _recommend_cache[cache_key] = (now, response)
    return response


@router.post("/record", dependencies=[Depends(require_api_key)])
def record_current_signals() -> dict:
    """Record today's signals for later accuracy validation."""
    cache_key, cached_signals, data = _load_all_data()

    if cached_signals is not None:
        signals = cached_signals
    else:
        if not data:
            raise HTTPException(status_code=404, detail="No data")
        signals = generate_signals_batch(data)
        _set_cached_signals(cache_key, signals, {})

    record_signals(signals)
    return {"recorded": len(signals)}


_accuracy_cache: dict[str, tuple[float, dict]] = {}


@router.get("/accuracy")
def get_signal_accuracy(days: int = Query(30, ge=7, le=180)) -> dict:
    """Get signal accuracy stats over recent history. Cached for 5 min."""
    from datetime import date

    cache_key = f"{date.today().isoformat()}_{days}"
    if cache_key in _accuracy_cache:
        ts, result = _accuracy_cache[cache_key]
        if time.monotonic() - ts < 300:  # 5 min TTL
            return result

    result = get_overall_accuracy(days)
    _accuracy_cache[cache_key] = (time.monotonic(), result)
    return result


@router.get("/alerts")
def get_price_alerts() -> dict:
    """Check if any positions have hit stop-loss or take-profit levels."""
    alerts = check_alerts()
    return {
        "count": len(alerts),
        "alerts": [a.to_dict() for a in alerts],
        "generated_at": _now_cst(),
    }


# ─── Signal Trend (per-ETF historical scores) ──────────────
_trend_cache: dict[str, tuple[float, dict]] = {}
_TREND_CACHE_TTL = 300  # 5 min — historical trend changes only when daily data updates


@router.get("/trend/{symbol}")
def get_signal_trend(
    symbol: str,
    days: int = Query(60, ge=10, le=250, description="Number of trading days (max 250 = ~1 year)"),
) -> dict:
    """Get daily signal score trend for a single ETF.

    Returns an array of {date, score, direction} for the last N trading days.
    Uses precomputed factors + score_at_index for fast replay (~30ms per ETF).
    """
    if len(symbol) != 6 or not symbol.isdigit():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    cache_key = f"{symbol}_{days}"
    now = time.monotonic()
    if cache_key in _trend_cache:
        ts, cached = _trend_cache[cache_key]
        if now - ts < _TREND_CACHE_TTL:
            return cached

    from engine.signals import _detect_market_regime, precompute_factors, score_at_index

    df = load_hist(symbol)
    if df.empty or len(df) < days + 20:
        raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")

    factors = precompute_factors(df)
    regime = _detect_market_regime()

    total = len(df)
    start_idx = max(total - days, 60)
    trend = []
    for i in range(start_idx, total):
        price = float(df["close"].iloc[i])
        direction, score, _ = score_at_index(factors, i, price, market_regime=regime)
        trend.append(
            {
                "date": str(df.index[i].date()),
                "score": round(float(score), 1),
                "direction": direction.value,
                "close": round(price, 4),
            }
        )

    result = {
        "symbol": symbol,
        "count": len(trend),
        "trend": trend,
        "generated_at": _now_cst(),
    }
    _trend_cache[cache_key] = (now, result)
    return result


_backtest_cache: dict[str, dict] = {}


@router.get("/backtest-accuracy")
async def backtest_signal_accuracy(
    days: int = Query(30, ge=10, le=90, description="Days to test over"),
) -> dict:
    """Backtest signal accuracy over historical data.

    Replays the V5.1 signal engine over the last N days and reports
    accuracy by direction and score bucket. Cached per-day since
    results only change when market data updates.
    """
    import asyncio
    from datetime import date

    from config.constants import DEFAULT_ETF_LIST
    from config.settings import settings
    from engine.signal_backtest import backtest_signals

    cache_key = f"{date.today().isoformat()}_{days}"
    if cache_key in _backtest_cache:
        return _backtest_cache[cache_key]

    data_dir = settings.data.data_dir / "etf_hist"
    if data_dir.exists():
        sym_list = sorted(f.stem for f in data_dir.glob("*.parquet"))
    else:
        sym_list = [e["symbol"] for e in DEFAULT_ETF_LIST]

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: backtest_signals(sym_list, lookback_days=60, test_days=days)
    )
    _backtest_cache[cache_key] = result
    return result
