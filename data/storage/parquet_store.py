"""Parquet-based local storage for ETF data."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from config.settings import settings

logger = logging.getLogger(__name__)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_hist(df: pd.DataFrame, category: str = "etf_hist") -> list[Path]:
    """Save historical DataFrame partitioned by symbol as Parquet files.

    Each symbol gets its own file: data_store/etf_hist/{symbol}.parquet
    If a file already exists, new data is appended (duplicates dropped by date).

    Returns list of written file paths.
    """
    if df.empty:
        logger.warning("Empty DataFrame, nothing to save")
        return []

    base_dir = _ensure_dir(settings.data.data_dir / category)
    written: list[Path] = []

    for symbol, group in df.groupby("symbol"):
        file_path = base_dir / f"{symbol}.parquet"

        if file_path.exists():
            existing = pd.read_parquet(file_path)
            merged = pd.concat([existing, group])
            merged = merged[~merged.index.duplicated(keep="last")]
            merged = merged.sort_index()
        else:
            merged = group.sort_index()

        merged.to_parquet(file_path, engine="pyarrow")
        written.append(file_path)
        logger.info("Saved %d rows → %s", len(merged), file_path)

    return written


def load_hist(symbol: str, category: str = "etf_hist") -> pd.DataFrame:
    """Load historical data for a single symbol from Parquet.

    Returns empty DataFrame if file does not exist.
    """
    file_path = settings.data.data_dir / category / f"{symbol}.parquet"

    if not file_path.exists():
        logger.warning("No data file for %s at %s", symbol, file_path)
        return pd.DataFrame()

    df = pd.read_parquet(file_path)
    logger.info("Loaded %d rows for %s", len(df), symbol)
    return df


def load_hist_multi(symbols: list[str], category: str = "etf_hist") -> pd.DataFrame:
    """Load and concatenate historical data for multiple symbols."""
    frames = [load_hist(s, category) for s in symbols]
    frames = [f for f in frames if not f.empty]

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames)


def save_snapshot(df: pd.DataFrame, name: str = "etf_spot") -> Path:
    """Save a spot snapshot as a single Parquet file with timestamp in name."""
    base_dir = _ensure_dir(settings.data.data_dir / "snapshots")
    timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    file_path = base_dir / f"{name}_{timestamp}.parquet"

    df.to_parquet(file_path, engine="pyarrow")
    logger.info("Snapshot saved: %d rows → %s", len(df), file_path)
    return file_path
