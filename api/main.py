"""FastAPI application — ETF Quant Platform API."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    backtest_router,
    data_router,
    factor_router,
    flow_router,
    portfolio_router,
    recommend_router,
    sector_router,
    sentiment_router,
    signal_router,
    system_router,
    ws_router,
)
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


async def _warmup_signal_cache() -> None:
    """Pre-compute signals so first dashboard load is fast."""
    try:
        from data.storage.parquet_store import load_hist
        from engine.signals import generate_signals_batch

        data_dir = settings.data.data_dir / "etf_hist"
        if not data_dir.exists():
            return

        sym_list = sorted(f.stem for f in data_dir.glob("*.parquet"))
        data = {}
        for sym in sym_list:
            df = load_hist(sym)
            if not df.empty:
                data[sym] = df

        if data:
            signals = generate_signals_batch(data)
            # Store in signal router cache
            from api.routers.signals import _set_cached_signals

            cache_key = ",".join(sorted(data.keys()))
            _set_cached_signals(cache_key, signals, {})
            logger.info("Signal cache warmed: %d signals for %d ETFs", len(signals), len(data))
    except Exception as e:
        logger.warning("Signal cache warmup failed (non-critical): %s", e)


async def _warmup_recommend_cache() -> None:
    """Pre-compute strategy recommendations (runs ~2-3 min, non-blocking)."""
    try:
        from engine.recommender import recommend_strategies

        results = recommend_strategies(500000, 5)
        from datetime import datetime, timedelta, timezone

        from api.routers.signals import _recommend_cache

        cst = timezone(timedelta(hours=8))
        response = {
            "capital": 500000,
            "count": len(results),
            "recommendations": [r.to_dict() for r in results],
            "disclaimer": "基于历史回测数据，不代表未来收益。仅供研究参考。",
            "generated_at": datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S"),
        }
        _recommend_cache["500000.0:5"] = (time.monotonic(), response)
        logger.info("Recommend cache warmed: %d strategies", len(results))
    except Exception as e:
        logger.warning("Recommend cache warmup failed (non-critical): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: run startup/shutdown tasks."""
    # Startup: warm caches in background so startup isn't blocked
    asyncio.create_task(_warmup_signal_cache())
    asyncio.create_task(_warmup_recommend_cache())
    yield
    # Shutdown: nothing to clean up currently


app = FastAPI(
    title="ETF Quant Platform",
    description="中国 ETF 量化投研平台 API",
    version="3.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        f"http://127.0.0.1:{settings.api.port}",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)


app.include_router(system_router, tags=["system"])
app.include_router(data_router, prefix="/api/data", tags=["data"])
app.include_router(factor_router, prefix="/api/factors", tags=["factors"])
app.include_router(backtest_router, prefix="/api/backtest", tags=["backtest"])
app.include_router(signal_router, prefix="/api/signals", tags=["signals"])
app.include_router(sector_router, prefix="/api/sector", tags=["sector"])
app.include_router(recommend_router, prefix="/api/recommend", tags=["recommend"])
app.include_router(flow_router, prefix="/api", tags=["flow", "risk"])
app.include_router(portfolio_router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(sentiment_router, prefix="/api/sentiment", tags=["sentiment"])
app.include_router(ws_router, tags=["websocket"])


def main() -> None:
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        workers=1,
        timeout_keep_alive=300,
    )
