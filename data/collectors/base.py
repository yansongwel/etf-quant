"""Base collector with rate limiting and retry logic."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

import pandas as pd

from config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RateLimiter:
    """Enforces minimum delay between consecutive calls."""

    def __init__(self, delay: float = settings.data.request_delay) -> None:
        self._delay = delay
        self._last_call: float = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        self._last_call = time.monotonic()


# Module-level rate limiter shared by all collectors
_rate_limiter = RateLimiter()


def fetch_with_retry(
    fn: Callable[..., pd.DataFrame],
    *args: object,
    max_retries: int = settings.data.max_retries,
    **kwargs: object,
) -> pd.DataFrame:
    """Call an AkShare function with rate limiting and exponential backoff.

    Returns an empty DataFrame on exhausted retries instead of raising,
    so callers can decide how to handle missing data.
    """
    fn_name = getattr(fn, "__name__", repr(fn))

    for attempt in range(1, max_retries + 1):
        _rate_limiter.wait()
        try:
            df = fn(*args, **kwargs)
            if df is not None and not df.empty:
                return df
            logger.warning("Empty result from %s (attempt %d/%d)", fn_name, attempt, max_retries)
        except Exception:
            logger.exception("Error calling %s (attempt %d/%d)", fn_name, attempt, max_retries)
            if attempt < max_retries:
                backoff = 2 ** (attempt - 1)
                logger.info("Retrying in %ds...", backoff)
                time.sleep(backoff)

    logger.error("All %d retries exhausted for %s", max_retries, fn_name)
    return pd.DataFrame()


def normalize_columns(df: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    """Rename Chinese columns to English using a mapping dict.

    Only renames columns that exist in both the DataFrame and the mapping.
    Returns a new DataFrame (no mutation).
    """
    rename = {k: v for k, v in column_map.items() if k in df.columns}
    return df.rename(columns=rename)
