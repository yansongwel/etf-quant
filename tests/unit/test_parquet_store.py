"""Tests for Parquet storage layer."""

from __future__ import annotations

import pandas as pd
import pytest

from data.storage.parquet_store import load_hist, load_hist_multi, save_hist, save_snapshot


@pytest.fixture
def sample_hist_df() -> pd.DataFrame:
    """Create a sample historical DataFrame matching collector output format."""
    df = pd.DataFrame(
        {
            "open": [3.8, 3.7],
            "close": [3.7, 3.65],
            "high": [3.81, 3.71],
            "low": [3.67, 3.64],
            "volume": [21000000, 15000000],
            "amount": [8.5e9, 6.1e9],
            "symbol": ["510300", "510300"],
        },
        index=pd.to_datetime(["2025-01-02", "2025-01-03"]),
    )
    df.index.name = "date"
    return df


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Override settings.data.data_dir to use a temp directory."""
    from config.settings import DataSettings, Settings
    from config.settings import settings as orig

    new_data = DataSettings.__new__(DataSettings)
    object.__setattr__(new_data, "request_delay", 0.2)
    object.__setattr__(new_data, "max_retries", 3)
    object.__setattr__(new_data, "data_dir", tmp_path)

    new_settings = Settings.__new__(Settings)
    object.__setattr__(new_settings, "project_root", orig.project_root)
    object.__setattr__(new_settings, "data", new_data)
    object.__setattr__(new_settings, "backtest", orig.backtest)

    monkeypatch.setattr("data.storage.parquet_store.settings", new_settings)
    return tmp_path


class TestSaveAndLoadHist:
    def test_save_creates_parquet_file(self, sample_hist_df, tmp_data_dir):
        paths = save_hist(sample_hist_df)

        assert len(paths) == 1
        assert paths[0].name == "510300.parquet"
        assert paths[0].exists()

    def test_load_roundtrip(self, sample_hist_df, tmp_data_dir):
        save_hist(sample_hist_df)
        loaded = load_hist("510300")

        assert len(loaded) == 2
        assert loaded.index.name == "date"
        assert "close" in loaded.columns

    def test_incremental_append_deduplicates(self, sample_hist_df, tmp_data_dir):
        save_hist(sample_hist_df)

        # New data overlaps on 2025-01-03, adds 2025-01-06
        new_df = pd.DataFrame(
            {
                "open": [3.65, 3.64],
                "close": [3.64, 3.60],
                "high": [3.66, 3.65],
                "low": [3.62, 3.58],
                "volume": [12000000, 10000000],
                "amount": [5.0e9, 4.2e9],
                "symbol": ["510300", "510300"],
            },
            index=pd.to_datetime(["2025-01-03", "2025-01-06"]),
        )
        new_df.index.name = "date"

        save_hist(new_df)
        loaded = load_hist("510300")

        assert len(loaded) == 3  # 01-02, 01-03(updated), 01-06
        # The overlapping row should use the latest value
        jan3_close = loaded.loc["2025-01-03", "close"]
        assert jan3_close == 3.64  # from new data

    def test_load_nonexistent_returns_empty(self, tmp_data_dir):
        result = load_hist("999999")
        assert result.empty

    def test_save_empty_returns_empty_list(self, tmp_data_dir):
        result = save_hist(pd.DataFrame())
        assert result == []


class TestLoadHistMulti:
    def test_load_multiple_symbols(self, tmp_data_dir):
        """Load data for multiple symbols that exist."""
        for symbol, close in [("510300", 3.7), ("510500", 5.2)]:
            df = pd.DataFrame(
                {
                    "open": [close + 0.1],
                    "close": [close],
                    "high": [close + 0.2],
                    "low": [close - 0.1],
                    "volume": [10000000],
                    "amount": [5.0e9],
                    "symbol": [symbol],
                },
                index=pd.to_datetime(["2025-01-02"]),
            )
            df.index.name = "date"
            save_hist(df)

        result = load_hist_multi(["510300", "510500"])
        assert len(result) == 2
        assert not result.empty

    def test_load_multi_all_missing_returns_empty(self, tmp_data_dir):
        """All symbols missing returns empty DataFrame."""
        result = load_hist_multi(["999999", "888888"])
        assert result.empty

    def test_load_multi_partial_missing(self, tmp_data_dir):
        """Only existing symbols are returned, missing ones are skipped."""
        df = pd.DataFrame(
            {
                "open": [3.8],
                "close": [3.7],
                "high": [3.81],
                "low": [3.67],
                "volume": [21000000],
                "amount": [8.5e9],
                "symbol": ["510300"],
            },
            index=pd.to_datetime(["2025-01-02"]),
        )
        df.index.name = "date"
        save_hist(df)

        result = load_hist_multi(["510300", "999999"])
        assert len(result) == 1

    def test_load_multi_empty_list(self, tmp_data_dir):
        """Empty symbol list returns empty DataFrame."""
        result = load_hist_multi([])
        assert result.empty


class TestSaveSnapshot:
    def test_save_snapshot_creates_file(self, tmp_data_dir):
        """Snapshot saves a parquet file with timestamp in name."""
        df = pd.DataFrame(
            {
                "symbol": ["510300", "510500"],
                "price": [3.7, 5.2],
                "volume": [10000000, 8000000],
            }
        )
        path = save_snapshot(df)

        assert path.exists()
        assert path.suffix == ".parquet"
        assert "etf_spot_" in path.name
        assert path.parent.name == "snapshots"

    def test_save_snapshot_custom_name(self, tmp_data_dir):
        """Snapshot with custom name prefix."""
        df = pd.DataFrame({"symbol": ["510300"], "price": [3.7]})
        path = save_snapshot(df, name="my_snapshot")

        assert "my_snapshot_" in path.name

    def test_save_snapshot_roundtrip(self, tmp_data_dir):
        """Saved snapshot can be read back."""
        df = pd.DataFrame({"symbol": ["510300", "510500"], "price": [3.7, 5.2]})
        path = save_snapshot(df)
        loaded = pd.read_parquet(path)

        assert len(loaded) == 2
        assert list(loaded.columns) == ["symbol", "price"]
