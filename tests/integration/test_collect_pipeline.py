"""Integration test: collect → normalize → save → load roundtrip.

Hits real AkShare API — marked as slow so `pytest -m "not slow"` can skip.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from config.settings import DataSettings, Settings
from config.settings import settings as orig
from data.collectors.etf_hist import collect_etf_hist
from data.collectors.etf_spot import collect_etf_spot
from data.storage.parquet_store import load_hist, save_hist


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    new_data = DataSettings.__new__(DataSettings)
    object.__setattr__(new_data, "request_delay", 0.5)
    object.__setattr__(new_data, "max_retries", 2)
    object.__setattr__(new_data, "data_dir", tmp_path)

    new_settings = Settings.__new__(Settings)
    object.__setattr__(new_settings, "project_root", orig.project_root)
    object.__setattr__(new_settings, "data", new_data)
    object.__setattr__(new_settings, "backtest", orig.backtest)

    monkeypatch.setattr("data.storage.parquet_store.settings", new_settings)
    return tmp_path


@pytest.mark.slow
class TestCollectPipeline:
    """End-to-end test hitting real AkShare API."""

    def test_hist_collect_save_load(self, tmp_store):
        end = date.today()
        start = end - timedelta(days=30)

        try:
            df = collect_etf_hist("510300", start, end)
        except Exception as exc:
            pytest.skip(f"AkShare API unavailable: {exc}")

        if df.empty:
            pytest.skip("AkShare API returned empty data (network issue)")

        assert "close" in df.columns
        assert "symbol" in df.columns
        assert df.index.name == "date"
        assert (df["symbol"] == "510300").all()

        save_hist(df)
        loaded = load_hist("510300")

        assert len(loaded) == len(df)
        pd.testing.assert_frame_equal(loaded, df)

    def test_spot_collect_filtered(self):
        try:
            df = collect_etf_spot(["510300", "510500"])
        except Exception as exc:
            pytest.skip(f"AkShare API unavailable: {exc}")

        if df.empty:
            pytest.skip("AkShare API returned empty data (network issue)")

        assert "symbol" in df.columns
        assert "price" in df.columns
        assert set(df["symbol"]).issubset({"510300", "510500"})
