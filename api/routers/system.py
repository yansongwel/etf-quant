"""System endpoints — health check, ETF list, status."""

from __future__ import annotations

import contextlib
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from config.constants import DEFAULT_ETF_LIST
from data.cache import get_client
from engine.regime import detect_regime
from engine.verdict import generate_verdict

router = APIRouter()

# Verdict cache: (timestamp, result) with 120s TTL
_verdict_cache: tuple[float, dict] | None = None
_VERDICT_TTL = 120.0

# Data stats cache: (timestamp, data_date, etf_count) with 60s TTL
_data_stats_cache: tuple[float, str | None, int] | None = None
_DATA_STATS_TTL = 60.0


def _get_data_stats() -> tuple[str | None, int]:
    """Get data date and ETF count with 60s cache."""
    global _data_stats_cache
    now = time.monotonic()
    if _data_stats_cache is not None:
        ts, date_val, count_val = _data_stats_cache
        if now - ts < _DATA_STATS_TTL:
            return date_val, count_val

    last_data_date = None
    etf_count = 0
    with contextlib.suppress(Exception):
        from config.settings import settings
        from data.storage.parquet_store import load_hist

        data_dir = settings.data.data_dir / "etf_hist"
        if data_dir.exists():
            etf_count = len(list(data_dir.glob("*.parquet")))

        df = load_hist("510300")
        if not df.empty:
            last_data_date = str(df.index.max().date())

    _data_stats_cache = (now, last_data_date, etf_count)
    return last_data_date, etf_count


_redis_cache: tuple[float, bool] | None = None
_REDIS_TTL = 30.0


@router.get("/health")
def health_check() -> dict:
    global _redis_cache
    now = time.monotonic()
    if _redis_cache is not None and now - _redis_cache[0] < _REDIS_TTL:
        redis_ok = _redis_cache[1]
    else:
        redis_ok = False
        client = get_client()
        if client:
            with contextlib.suppress(Exception):
                redis_ok = client.ping()
        _redis_cache = (now, redis_ok)

    # Data freshness: cached for 60s to avoid repeated parquet reads
    last_data_date, etf_count = _get_data_stats()

    # Current Beijing time (CST = UTC+8), A-stock market timezone
    cst = timezone(timedelta(hours=8))
    now_cst = datetime.now(cst)

    # A-share market status: trading / lunch / closed
    weekday = now_cst.weekday()
    hour_min = now_cst.hour * 100 + now_cst.minute
    is_trading = weekday < 5 and ((930 <= hour_min <= 1130) or (1300 <= hour_min <= 1500))
    is_lunch = weekday < 5 and (1130 < hour_min < 1300)
    market_open = is_trading or is_lunch  # data injection stays active for both
    market_status = "trading" if is_trading else "lunch" if is_lunch else "closed"

    from config.constants import PLATFORM_VERSION, SIGNAL_ENGINE_VERSION

    return {
        "status": "ok",
        "services": {
            "redis": "connected" if redis_ok else "unavailable",
        },
        "platform_version": PLATFORM_VERSION,
        "signal_version": SIGNAL_ENGINE_VERSION,
        "data_date": last_data_date,
        "etf_count": etf_count,
        "server_time_cst": now_cst.strftime("%Y-%m-%d %H:%M:%S"),
        "market_open": market_open,
        "market_status": market_status,
    }


@router.get("/etf/list")
def get_etf_list() -> list[dict[str, str]]:
    """Return the default ETF watchlist."""
    return DEFAULT_ETF_LIST


# Realtime quotes cache: 30s TTL (trading hours), longer outside
_realtime_cache: tuple[float, dict] | None = None
_REALTIME_TTL = 30.0


@router.get("/market/realtime")
def get_realtime_quotes() -> dict:
    """Get real-time quotes for all ETFs via Tencent Finance API."""
    global _realtime_cache
    now = time.monotonic()
    if _realtime_cache is not None:
        ts, result = _realtime_cache
        if now - ts < _REALTIME_TTL:
            return result

    from data.collectors.realtime import fetch_realtime_quotes

    symbols = [e["symbol"] for e in DEFAULT_ETF_LIST]
    name_map = {e["symbol"]: e["name"] for e in DEFAULT_ETF_LIST}
    df = fetch_realtime_quotes(symbols)

    if df.empty:
        return {"count": 0, "quotes": [], "source": "tencent"}

    quotes = []
    for _, row in df.iterrows():
        quotes.append(
            {
                "symbol": row["symbol"],
                "name": name_map.get(row["symbol"], row.get("name", "")),
                "price": row["close"],
                "change_pct": row["pct_change"],
                "volume": int(row["volume"]),
                "high": row["high"],
                "low": row["low"],
                "open": row["open"],
            }
        )

    # Sort by absolute change (most volatile first)
    quotes.sort(key=lambda q: abs(q["change_pct"]), reverse=True)
    cst = timezone(timedelta(hours=8))
    result = {
        "count": len(quotes),
        "quotes": quotes,
        "source": "tencent",
        "generated_at": datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S"),
    }
    _realtime_cache = (now, result)
    return result


@router.get("/market/regime")
def get_market_regime() -> dict:
    """Detect current market regime (bull/bear/range) and adaptive weights."""
    return detect_regime()


@router.get("/market/verdict")
def get_market_verdict() -> dict:
    """Get one-line actionable verdict: should I buy, sell, or wait today?"""
    global _verdict_cache
    now = time.monotonic()
    if _verdict_cache is not None:
        ts, result = _verdict_cache
        if now - ts < _VERDICT_TTL:
            return result

    result = generate_verdict()
    _verdict_cache = (now, result)
    return result
