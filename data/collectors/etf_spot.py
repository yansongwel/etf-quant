"""ETF real-time spot data collector via AkShare."""

from __future__ import annotations

import logging

import akshare as ak
import pandas as pd

from config.constants import ETF_SPOT_COLUMNS
from data.collectors.base import fetch_with_retry, normalize_columns

logger = logging.getLogger(__name__)


def collect_etf_spot(symbols: list[str] | None = None) -> pd.DataFrame:
    """Fetch current ETF spot snapshot from East Money.

    Args:
        symbols: Optional list of 6-digit ETF codes to filter.
                 If None, returns all ETFs.

    Returns:
        DataFrame with standardized English columns.
    """
    raw = fetch_with_retry(ak.fund_etf_spot_em)

    if raw.empty:
        return raw

    df = normalize_columns(raw, ETF_SPOT_COLUMNS)

    if symbols is not None:
        df = df[df["symbol"].isin(symbols)]
        missing = set(symbols) - set(df["symbol"])
        if missing:
            logger.warning("Symbols not found in spot data: %s", missing)

    logger.info("Spot snapshot: %d ETFs", len(df))
    return df.reset_index(drop=True)
