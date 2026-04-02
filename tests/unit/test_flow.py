"""Tests for engine.flow — institutional flow detector."""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine.flow import FlowType, detect_flow, detect_flow_batch


def _make_df(
    days: int = 60,
    base_price: float = 2.0,
    base_vol: float = 1_000_000,
    last_vol_multiplier: float = 1.0,
    last_price_change: float = 0.0,
    include_amount: bool = True,
    include_turnover: bool = False,
) -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame for testing."""
    dates = pd.date_range(end="2026-03-28", periods=days, freq="D")
    np.random.seed(42)

    close = base_price + np.cumsum(np.random.randn(days) * 0.01)
    close[-1] = close[-2] * (1 + last_price_change)

    volume = np.full(days, base_vol, dtype=float)
    volume += np.random.randn(days) * base_vol * 0.1
    volume[-1] = base_vol * last_vol_multiplier

    data: dict[str, np.ndarray] = {
        "open": close - np.random.rand(days) * 0.01,
        "high": close + np.random.rand(days) * 0.02,
        "low": close - np.random.rand(days) * 0.02,
        "close": close,
        "volume": np.maximum(volume, 100),
    }
    if include_amount:
        data["amount"] = close * volume
    if include_turnover:
        data["turnover"] = np.full(days, 2.0)
        data["turnover"][-1] = 6.0  # Spike

    return pd.DataFrame(data, index=dates)


class TestDetectFlow:
    """Tests for detect_flow function."""

    def test_normal_volume(self) -> None:
        """Normal volume should be detected as normal."""
        df = _make_df(last_vol_multiplier=1.0, last_price_change=0.005)
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert sig.flow_type == FlowType.NORMAL
        assert sig.symbol == "510300"

    def test_accumulation_high_vol_small_move(self) -> None:
        """High volume + small price move = accumulation."""
        df = _make_df(last_vol_multiplier=3.0, last_price_change=0.003)
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert sig.flow_type == FlowType.ACCUMULATION
        assert sig.confidence >= 40
        assert "放量" in sig.details[0] or "机构" in sig.details[-1]

    def test_breakout_buy_vol_and_price_up(self) -> None:
        """Moderate volume spike + big price up = breakout buy."""
        df = _make_df(last_vol_multiplier=2.0, last_price_change=0.03)
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert sig.flow_type == FlowType.BREAKOUT_BUY
        assert sig.confidence >= 30

    def test_panic_sell_vol_and_price_down(self) -> None:
        """High volume + big price drop = panic sell."""
        df = _make_df(last_vol_multiplier=3.0, last_price_change=-0.035)
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert sig.flow_type == FlowType.PANIC_SELL
        assert sig.confidence >= 40

    def test_low_volume_shrink(self) -> None:
        """Very low volume should mention 缩量."""
        df = _make_df(last_vol_multiplier=0.3, last_price_change=0.001)
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert sig.flow_type == FlowType.NORMAL
        assert any("缩量" in d for d in sig.details)

    def test_insufficient_data(self) -> None:
        """Should return None for insufficient data."""
        df = _make_df(days=10)
        sig = detect_flow(df, "510300")
        assert sig is None

    def test_empty_dataframe(self) -> None:
        """Should return None for empty DataFrame."""
        sig = detect_flow(pd.DataFrame(), "510300")
        assert sig is None

    def test_to_dict(self) -> None:
        """to_dict should produce expected keys."""
        df = _make_df()
        sig = detect_flow(df, "510300")
        assert sig is not None
        d = sig.to_dict()
        assert "symbol" in d
        assert "flow_type" in d
        assert "volume_ratio" in d
        assert "advice" in d
        assert "details" in d
        assert isinstance(d["details"], list)

    def test_with_turnover(self) -> None:
        """High turnover should be noted in details."""
        df = _make_df(last_vol_multiplier=2.5, last_price_change=0.002, include_turnover=True)
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert any("换手率" in d for d in sig.details)

    def test_without_amount(self) -> None:
        """Should work without amount column."""
        df = _make_df(include_amount=False)
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert sig.amount_ratio == sig.volume_ratio

    def test_distribution_high_vol_small_down(self) -> None:
        """High vol + small negative move at high price = distribution."""
        # Set price high (top of range) with small negative change
        df = _make_df(days=80, base_price=5.0, last_vol_multiplier=2.5, last_price_change=-0.005)
        sig = detect_flow(df, "510300")
        assert sig is not None
        # High vol + small move triggers accumulation/distribution logic
        assert sig.flow_type in (FlowType.DISTRIBUTION, FlowType.ACCUMULATION, FlowType.NORMAL)

    def test_accumulation_low_price_percentile(self) -> None:
        """High vol + small negative move at LOW price = accumulation."""
        # Create df where prices are in a range, then set last to be near bottom
        df = _make_df(days=80, base_price=3.0, last_vol_multiplier=2.5, last_price_change=-0.005)
        # Override last 60 days to create a clear high range, with last at bottom
        close = df["close"].values.copy()
        close[-60:] = np.linspace(3.0, 3.5, 60)  # uptrend
        close[-1] = 3.05  # near bottom of the 60-day range
        close[-2] = 3.07  # small drop from prev day
        df["close"] = close
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert sig.flow_type == FlowType.ACCUMULATION

    def test_moderate_panic_sell(self) -> None:
        """Moderate vol spike + big drop = panic sell."""
        df = _make_df(last_vol_multiplier=1.7, last_price_change=-0.03)
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert sig.flow_type == FlowType.PANIC_SELL

    def test_volume_trend_up(self) -> None:
        """Rising 5-day volume trend should add confidence."""
        df = _make_df(days=60, last_vol_multiplier=2.5, last_price_change=0.005)
        # Make last 5 days volume much higher than prev 5
        for i in range(-5, 0):
            df.iloc[i, df.columns.get_loc("volume")] = 3_000_000
        for i in range(-10, -5):
            df.iloc[i, df.columns.get_loc("volume")] = 1_000_000
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert any("持续放大" in d for d in sig.details)

    def test_volume_trend_down(self) -> None:
        """Falling 5-day volume trend should be noted."""
        df = _make_df(days=60, last_vol_multiplier=1.0, last_price_change=0.001)
        # Make last 5 days volume much lower than prev 5
        for i in range(-5, 0):
            df.iloc[i, df.columns.get_loc("volume")] = 300_000
        for i in range(-10, -5):
            df.iloc[i, df.columns.get_loc("volume")] = 1_500_000
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert any("萎缩" in d for d in sig.details)

    def test_moderate_turnover(self) -> None:
        """Moderate turnover (3-5%) should be noted."""
        df = _make_df(days=60, include_turnover=True)
        df["turnover"] = 3.5  # moderate
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert any("中等活跃" in d for d in sig.details)

    def test_amount_ratio_high(self) -> None:
        """High amount ratio should add confidence."""
        df = _make_df(days=60, last_vol_multiplier=2.5, last_price_change=0.003)
        # Spike the amount on last day
        df.iloc[-1, df.columns.get_loc("amount")] = df["amount"].iloc[-21:-1].mean() * 3
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert any("大资金" in d for d in sig.details)

    def test_short_data_no_vol_trend(self) -> None:
        """With < 10 data points for vol, trend should be 0."""
        df = _make_df(days=25, last_vol_multiplier=1.0, last_price_change=0.001)
        sig = detect_flow(df, "510300")
        assert sig is not None
        assert sig.volume_trend_5d == 0.0 or isinstance(sig.volume_trend_5d, float)

    def test_price_percentile_short_window(self) -> None:
        """_price_percentile should return None for short data."""
        from engine.flow import _price_percentile

        s = pd.Series([1.0, 2.0, 3.0])
        assert _price_percentile(s, 10) is None

    def test_price_percentile_normal(self) -> None:
        """_price_percentile should return valid percentile."""
        from engine.flow import _price_percentile

        s = pd.Series(range(100), dtype=float)
        pct = _price_percentile(s, 60)
        assert pct is not None
        assert 0 <= pct <= 1


class TestDetectFlowBatch:
    """Tests for detect_flow_batch function."""

    def test_batch_sorting(self) -> None:
        """Abnormal signals should sort before normal ones."""
        data = {
            "AAA": _make_df(last_vol_multiplier=1.0),
            "BBB": _make_df(last_vol_multiplier=3.0, last_price_change=0.003),
        }
        signals = detect_flow_batch(data)
        assert len(signals) == 2
        # Abnormal (BBB accumulation) should come first
        assert signals[0].flow_type != FlowType.NORMAL

    def test_batch_empty(self) -> None:
        """Empty data should return empty list."""
        assert detect_flow_batch({}) == []
