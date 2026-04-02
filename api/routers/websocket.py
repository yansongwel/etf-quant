"""WebSocket endpoint for real-time market data push.

During trading hours (09:30-15:00 CST weekdays), pushes:
- Real-time ETF quotes (from Tencent API)
- Signal summary (buy/hold/sell counts)
- Market verdict updates

Clients connect to /ws/market and receive JSON messages every ~10 seconds.
Outside trading hours, sends a single status message then reduces to 60s interval.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))


def _is_market_open() -> bool:
    """Check if A-share market is in trading hours."""
    now = datetime.now(_CST)
    if now.weekday() >= 5:
        return False
    hm = now.hour * 100 + now.minute
    return 930 <= hm <= 1500


def _get_realtime_snapshot() -> dict:
    """Build a lightweight snapshot for WebSocket push."""
    from config.constants import DEFAULT_ETF_LIST
    from data.collectors.realtime import fetch_realtime_quotes

    symbols = [e["symbol"] for e in DEFAULT_ETF_LIST]
    name_map = {e["symbol"]: e["name"] for e in DEFAULT_ETF_LIST}

    df = fetch_realtime_quotes(symbols)
    if df.empty:
        return {"type": "error", "message": "行情数据暂不可用"}

    # Top movers (by absolute change)
    quotes = []
    for _, row in df.iterrows():
        quotes.append(
            {
                "symbol": row["symbol"],
                "name": name_map.get(row["symbol"], ""),
                "price": round(row["close"], 3),
                "change_pct": round(row["pct_change"], 2),
            }
        )
    quotes.sort(key=lambda q: abs(q["change_pct"]), reverse=True)

    # Quick signal summary from cached signals
    signal_summary = {"buy": 0, "hold": 0, "sell": 0}
    try:
        from api.routers.signals import _get_cached_signals

        cached = _get_cached_signals(",".join(sorted(symbols)))
        if cached is not None:
            signals, _ = cached
            for s in signals:
                d = s.direction.value
                if d in ("strong_buy", "buy"):
                    signal_summary["buy"] += 1
                elif d in ("strong_sell", "sell"):
                    signal_summary["sell"] += 1
                else:
                    signal_summary["hold"] += 1
    except Exception:
        pass

    now_cst = datetime.now(_CST)
    return {
        "type": "market_update",
        "market_open": _is_market_open(),
        "timestamp": now_cst.strftime("%Y-%m-%d %H:%M:%S"),
        "quotes": quotes[:15],  # Top 15 movers
        "total_etfs": len(quotes),
        "signal_summary": signal_summary,
    }


@router.websocket("/ws/market")
async def market_websocket(websocket: WebSocket) -> None:
    """Real-time market data WebSocket.

    Sends JSON updates:
    - During trading: every 10 seconds
    - After hours: every 60 seconds (just timestamp updates)

    Message format:
    {
        "type": "market_update",
        "market_open": true/false,
        "timestamp": "2026-03-31 14:30:05",
        "quotes": [...top 15 movers...],
        "signal_summary": {"buy": 2, "hold": 10, "sell": 26}
    }
    """
    await websocket.accept()
    logger.info("WebSocket client connected")

    try:
        while True:
            market_open = _is_market_open()
            interval = 10 if market_open else 60

            try:
                snapshot = await asyncio.to_thread(_get_realtime_snapshot)
                await websocket.send_text(json.dumps(snapshot, ensure_ascii=False))
            except Exception as e:
                error_msg = json.dumps(
                    {
                        "type": "error",
                        "message": str(e),
                        "timestamp": datetime.now(_CST).strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
                await websocket.send_text(error_msg)

            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        logger.exception("WebSocket error")
