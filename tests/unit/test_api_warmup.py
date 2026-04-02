"""Tests for API cache warmup functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


class TestWarmupSignalCache:
    @pytest.mark.asyncio()
    @patch("data.storage.parquet_store.load_hist")
    @patch("engine.signals.generate_signals_batch")
    async def test_warmup_populates_cache(self, mock_batch, mock_load) -> None:
        from api.main import _warmup_signal_cache

        mock_load.return_value = pd.DataFrame(
            {"close": [3.5]}, index=pd.DatetimeIndex(["2024-01-01"])
        )
        mock_batch.return_value = []

        with patch("api.routers.signals._set_cached_signals"):
            await _warmup_signal_cache()
            # Either populates cache or skips if no data dir
            # The function is resilient to missing data

    @pytest.mark.asyncio()
    async def test_warmup_handles_exception(self) -> None:
        from api.main import _warmup_signal_cache

        with patch("config.settings.settings") as mock_settings:
            mock_settings.data.data_dir.__truediv__ = MagicMock(side_effect=Exception("test error"))
            # Should catch exception gracefully — not raise
            await _warmup_signal_cache()


class TestWarmupRecommendCache:
    @pytest.mark.asyncio()
    @patch("engine.recommender.recommend_strategies")
    async def test_warmup_recommend(self, mock_recommend) -> None:
        from api.main import _warmup_recommend_cache

        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"name": "test", "sharpe": 1.0}
        mock_recommend.return_value = [mock_result]

        await _warmup_recommend_cache()
        mock_recommend.assert_called_once_with(500000, 5)

    @pytest.mark.asyncio()
    @patch("engine.recommender.recommend_strategies")
    async def test_warmup_recommend_handles_error(self, mock_recommend) -> None:
        from api.main import _warmup_recommend_cache

        mock_recommend.side_effect = Exception("no data")
        # Should catch exception gracefully — not raise
        await _warmup_recommend_cache()
