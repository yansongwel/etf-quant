"""Real-time ETF data collector via free public APIs.

Data sources:
    - Tencent Finance (qt.gtimg.cn): Real-time OHLCV quotes
    - Tiantian Fund (fundgz.1234567.com.cn): Real-time fund valuation
    - East Money (fundf10.eastmoney.com): Historical net values

These are the same APIs used by browser-based financial tools.
No API key required, no rate limit issues from overseas servers.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://finance.qq.com/",
    }
)

# Min delay between requests (seconds)
_MIN_DELAY = 0.3
_last_request_time = 0.0


def _rate_limit() -> None:
    """Enforce minimum delay between requests."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_DELAY:
        time.sleep(_MIN_DELAY - elapsed)
    _last_request_time = time.monotonic()


def _tencent_prefix(symbol: str) -> str:
    """Convert 6-digit ETF code to Tencent format (sh/sz prefix)."""
    if symbol.startswith(("5", "6")):
        return f"sh{symbol}"
    return f"sz{symbol}"


def fetch_realtime_quotes(symbols: list[str]) -> pd.DataFrame:
    """Fetch real-time quotes from Tencent Finance for multiple ETFs.

    Args:
        symbols: List of 6-digit ETF codes.

    Returns:
        DataFrame with columns: symbol, name, open, high, low, close,
        volume, amount, pct_change, date.
    """
    if not symbols:
        return pd.DataFrame()

    # Tencent API supports batch query (comma-separated)
    codes = ",".join(_tencent_prefix(s) for s in symbols)
    _rate_limit()

    try:
        resp = _SESSION.get(f"https://qt.gtimg.cn/q={codes}", timeout=15)
        resp.raise_for_status()
    except Exception:
        logger.exception("Tencent realtime API failed")
        return pd.DataFrame()

    rows = []
    for line in resp.text.strip().split(";"):
        line = line.strip()
        if not line or '"' not in line:
            continue
        try:
            raw = line.split('"')[1]
            parts = raw.split("~")
            if len(parts) < 50:
                continue

            symbol = parts[2]
            name = parts[1]
            current_price = float(parts[3])
            float(parts[4])
            open_price = float(parts[5])
            volume = int(parts[6])
            # parts[36] = today's date+time, e.g. "20260331153237"
            parts[30] if len(parts[30]) >= 8 else ""
            high = float(parts[33]) if parts[33] else current_price
            low = float(parts[34]) if parts[34] else current_price
            # Amount in CNY (parts[37] is in 万元)
            amount_wan = float(parts[37]) if parts[37] else 0
            amount = amount_wan * 10000
            pct = float(parts[32]) if parts[32] else 0.0
            turnover = float(parts[38]) if parts[38] else 0.0

            # Parse date from timestamp field
            ts_str = parts[30]  # "20260331153237"
            if len(ts_str) >= 8:
                trade_date_str = f"{ts_str[:4]}-{ts_str[4:6]}-{ts_str[6:8]}"
            else:
                trade_date_str = str(date.today())

            rows.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "date": trade_date_str,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": current_price,
                    "volume": volume,
                    "amount": amount,
                    "pct_change": pct,
                    "turnover": turnover,
                }
            )
        except (IndexError, ValueError) as e:
            logger.warning("Failed to parse Tencent quote line: %s", e)
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    logger.info("Fetched realtime quotes for %d ETFs via Tencent", len(df))
    return df


def fetch_fund_valuation(symbol: str) -> dict | None:
    """Fetch real-time fund valuation from Tiantian Fund (天天基金).

    Returns dict with: fundcode, name, nav_date, nav, estimated_nav,
    estimated_change_pct, estimate_time. Or None on failure.
    """
    _rate_limit()
    try:
        resp = _SESSION.get(
            f"https://fundgz.1234567.com.cn/js/{symbol}.js",
            timeout=10,
        )
        match = re.search(r"jsonpgz\((.+)\)", resp.text)
        if not match:
            return None

        d = json.loads(match.group(1))
        return {
            "fundcode": d.get("fundcode", symbol),
            "name": d.get("name", ""),
            "nav_date": d.get("jzrq", ""),
            "nav": float(d.get("dwjz", 0)),
            "estimated_nav": float(d.get("gsz", 0)),
            "estimated_change_pct": float(d.get("gszzl", 0)),
            "estimate_time": d.get("gztime", ""),
        }
    except Exception:
        logger.exception("Tiantian fund valuation failed for %s", symbol)
        return None


def fetch_hist_from_eastmoney(
    symbol: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Fetch historical daily OHLCV from East Money push API.

    This is a backup when AkShare fails. Uses the same underlying
    East Money data but via a different HTTP endpoint.

    Args:
        symbol: 6-digit ETF code.
        start_date: Start date.
        end_date: End date.

    Returns:
        DataFrame with standardized columns and DatetimeIndex.
    """
    # Determine market: 1=Shanghai(5xx,6xx), 0=Shenzhen(others)
    market = "1" if symbol.startswith(("5", "6")) else "0"
    secid = f"{market}.{symbol}"

    _rate_limit()
    try:
        resp = _SESSION.get(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101",  # daily
                "fqt": "1",  # forward-adjusted
                "beg": start_date.strftime("%Y%m%d"),
                "end": end_date.strftime("%Y%m%d"),
            },
            timeout=15,
        )
        data = resp.json()
    except Exception:
        logger.exception("East Money hist API failed for %s", symbol)
        return pd.DataFrame()

    klines = data.get("data", {}).get("klines", [])
    if not klines:
        logger.warning("No kline data from East Money for %s", symbol)
        return pd.DataFrame()

    # Parse: "2026-03-27,4.450,4.508,4.530,4.445,5626908,2530647936,1.89,-0.80,-0.036,1.25"
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 7:
            continue
        rows.append(
            {
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": int(parts[5]),
                "amount": float(parts[6]),
                "amplitude": float(parts[7]) if len(parts) > 7 else 0,
                "pct_change": float(parts[8]) if len(parts) > 8 else 0,
                "change": float(parts[9]) if len(parts) > 9 else 0,
                "turnover": float(parts[10]) if len(parts) > 10 else 0,
                "symbol": symbol,
            }
        )

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    logger.info(
        "Collected %d rows for %s from East Money (%s ~ %s)",
        len(df),
        symbol,
        start_date,
        end_date,
    )
    return df


def fetch_hist_from_tencent(
    symbol: str,
    start_date: date,
    count: int = 30,
) -> pd.DataFrame:
    """Fetch historical daily OHLCV from Tencent kline API.

    This works when East Money push API is blocked.

    Args:
        symbol: 6-digit ETF code.
        start_date: Start date for kline data.
        count: Number of bars to fetch.

    Returns:
        DataFrame with standardized columns and DatetimeIndex.
    """
    prefix = _tencent_prefix(symbol)
    _rate_limit()
    try:
        resp = _SESSION.get(
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            params={
                "param": f"{prefix},day,{start_date.isoformat()},,{count},qfq",
            },
            timeout=15,
        )
        data = resp.json()
    except Exception:
        logger.exception("Tencent kline API failed for %s", symbol)
        return pd.DataFrame()

    klines = data.get("data", {}).get(prefix, {}).get("qfqday", []) or data.get("data", {}).get(
        prefix, {}
    ).get("day", [])
    if not klines:
        logger.warning("No kline data from Tencent for %s", symbol)
        return pd.DataFrame()

    rows = []
    for k in klines:
        if len(k) < 6:
            continue
        rows.append(
            {
                "date": k[0],
                "open": float(k[1]),
                "close": float(k[2]),
                "high": float(k[3]),
                "low": float(k[4]),
                "volume": int(float(k[5])),
                "symbol": symbol,
            }
        )

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    logger.info("Collected %d klines for %s from Tencent", len(df), symbol)
    return df
