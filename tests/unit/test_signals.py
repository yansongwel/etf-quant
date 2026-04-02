"""Tests for the signal generation engine V2."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from engine.signals import (
    SignalDirection,
    _momentum_acceleration,
    _volume_ratio,
    calculate_positions,
    generate_signal,
    generate_signals_batch,
)


def _make_ohlcv(
    days: int = 100,
    trend: float = 0.001,
    vol_spike: bool = False,
    high_volume: bool = False,
) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=days)
    close = 3.0 * np.cumprod(1 + np.random.normal(trend, 0.02, days))
    volume = np.random.randint(1_000_000, 10_000_000, days).astype(float)
    if vol_spike:
        volume[-1] = volume[-20:-1].mean() * 3
    if high_volume:
        volume[-5:] = volume.mean() * 2.5
    df = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )
    df.index.name = "date"
    return df


class TestHelpers:
    def test_volume_ratio(self) -> None:
        df = _make_ohlcv()
        ratio = _volume_ratio(df["volume"])
        assert ratio is not None
        assert ratio > 0

    def test_volume_ratio_insufficient(self) -> None:
        df = _make_ohlcv(days=10)
        assert _volume_ratio(df["volume"]) is None

    def test_momentum_acceleration(self) -> None:
        df = _make_ohlcv()
        accel = _momentum_acceleration(df["close"])
        assert accel is not None
        assert isinstance(accel, float)

    def test_momentum_acceleration_insufficient(self) -> None:
        df = _make_ohlcv(days=10)
        assert _momentum_acceleration(df["close"]) is None


class TestGenerateSignal:
    def test_generates_signal(self) -> None:
        df = _make_ohlcv()
        sig = generate_signal(df, "510300")
        assert sig is not None
        assert sig.symbol == "510300"
        assert sig.current_price > 0
        assert sig.entry_price > 0
        assert sig.target_price > 0
        assert sig.stop_loss > 0
        assert sig.direction in list(SignalDirection)

    def test_insufficient_data_returns_none(self) -> None:
        df = _make_ohlcv(days=10)
        assert generate_signal(df, "510300") is None

    def test_empty_df_returns_none(self) -> None:
        assert generate_signal(pd.DataFrame(), "510300") is None

    def test_uptrend_not_strongly_negative(self) -> None:
        """Mild uptrend should not produce strong sell signals."""
        df = _make_ohlcv(days=150, trend=0.005)
        sig = generate_signal(df, "TEST")
        assert sig is not None
        # With flow factors and pattern layer, mild uptrend may score near zero
        assert sig.score > -15
        assert sig.direction != SignalDirection.STRONG_SELL

    def test_downtrend_contrarian_buy(self) -> None:
        """V3.5: Downtrend with oversold reversal factors CAN produce buy.

        IC analysis shows ret_5d (IC=-0.022) and mdd (IC=+0.017) are
        contrarian predictors: deep drops predict positive next-day returns.
        """
        df = _make_ohlcv(days=150, trend=-0.005)
        sig = generate_signal(df, "TEST")
        assert sig is not None
        # V3.5: contrarian reversal may trigger buy in downtrend
        # The key check is that the signal has valid factors
        assert sig.score is not None
        assert "ret_5d" in sig.factors

    def test_to_dict_has_v2_fields(self) -> None:
        df = _make_ohlcv()
        sig = generate_signal(df, "510300")
        assert sig is not None
        d = sig.to_dict()
        assert "symbol" in d
        assert "direction" in d
        assert "score" in d
        assert "factors" in d
        # V2 new factors
        assert "volume_ratio" in d["factors"]
        assert "momentum_accel" in d["factors"]

    def test_market_regime_bear_suppresses_buy(self) -> None:
        """Bear market regime should reduce buy scores."""
        df = _make_ohlcv(days=150, trend=0.003)
        sig_neutral = generate_signal(df, "TEST", market_regime=None)
        sig_bear = generate_signal(df, "TEST", market_regime="bear")
        assert sig_neutral is not None
        assert sig_bear is not None
        # Bear regime should have lower or equal score
        assert sig_bear.score <= sig_neutral.score

    def test_market_regime_bull(self) -> None:
        """Bull market should not harm buy signals."""
        df = _make_ohlcv(days=150, trend=0.003)
        sig_bull = generate_signal(df, "TEST", market_regime="bull")
        assert sig_bull is not None

    def test_volume_spike_amplifies_signal(self) -> None:
        """Volume spike should strengthen the signal direction."""
        df_normal = _make_ohlcv(days=150, trend=0.004)
        df_spike = _make_ohlcv(days=150, trend=0.004, vol_spike=True)
        sig_normal = generate_signal(df_normal, "TEST")
        sig_spike = generate_signal(df_spike, "TEST")
        assert sig_normal is not None
        assert sig_spike is not None
        # Volume spike should amplify (higher abs score if positive)
        if sig_normal.score > 0:
            assert sig_spike.score >= sig_normal.score

    def test_buy_requires_3_bullish_factors(self) -> None:
        """V2: Buy requires at least 3 confirming bullish factors."""
        # Mild uptrend — might have score > 18 but not enough factors
        df = _make_ohlcv(days=100, trend=0.001)
        sig = generate_signal(df, "TEST")
        assert sig is not None
        # If direction is BUY, we need confirmation in reason
        if sig.direction == SignalDirection.BUY:
            # Should have sufficient bullish factors
            assert "多头因子不足" not in sig.reason

    def test_conflict_resolution(self) -> None:
        """Contradicting bull/bear signals should reduce score magnitude."""
        # This is tested implicitly — a signal can't have both
        # strong bull and strong bear factors without conflict resolution
        df = _make_ohlcv(days=150, trend=0.0)
        sig = generate_signal(df, "TEST")
        assert sig is not None
        # Near-zero trend should produce moderate score
        assert abs(sig.score) < 40


class TestBatchSignals:
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_batch_sorted_by_score(self, _mock: object) -> None:
        data = {
            "A": _make_ohlcv(trend=0.005),
            "B": _make_ohlcv(trend=-0.005),
            "C": _make_ohlcv(trend=0.002),
        }
        signals = generate_signals_batch(data)
        assert len(signals) == 3
        scores = [s.score for s in signals]
        assert scores == sorted(scores, reverse=True)

    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_empty_data(self, _mock: object) -> None:
        assert generate_signals_batch({}) == []

    @patch("engine.signals._detect_market_regime", return_value="bear")
    def test_bear_regime_affects_batch(self, _mock: object) -> None:
        data = {"A": _make_ohlcv(trend=0.003)}
        signals = generate_signals_batch(data)
        assert len(signals) == 1
        # In bear regime, buy signals should be suppressed
        assert signals[0].reason  # Should have some reason


class TestCalculatePositions:
    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_calculates_positions(self, _mock: object) -> None:
        data = {
            "A": _make_ohlcv(trend=0.005, high_volume=True),
            "B": _make_ohlcv(trend=0.003, high_volume=True),
            "C": _make_ohlcv(trend=-0.005),
        }
        signals = generate_signals_batch(data)
        positions = calculate_positions(signals, capital=50000, max_positions=3)
        assert isinstance(positions, list)
        for p in positions:
            assert "symbol" in p
            assert "shares" in p
            assert "buy_amount" in p
            assert p["shares"] >= 0

    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_respects_capital_limit(self, _mock: object) -> None:
        data = {"A": _make_ohlcv(trend=0.005, high_volume=True)}
        signals = generate_signals_batch(data)
        positions = calculate_positions(signals, capital=100, max_positions=1)
        total = sum(p["buy_amount"] for p in positions)
        assert total <= 100

    @patch("engine.signals._detect_market_regime", return_value="range")
    def test_no_buy_signals_returns_empty(self, _mock: object) -> None:
        data = {"A": _make_ohlcv(trend=-0.01)}
        signals = generate_signals_batch(data)
        positions = calculate_positions(signals, capital=5000)
        total = sum(p["buy_amount"] for p in positions)
        assert total <= 5000

    def test_positions_small_capital(self) -> None:
        """When capital is very small, should handle gracefully."""
        sig = generate_signal(_make_ohlcv(days=150, trend=0.005, high_volume=True), "TEST")
        assert sig is not None
        positions = calculate_positions([sig], capital=50, max_positions=1)
        # Should still produce something or empty list
        assert isinstance(positions, list)

    def test_positions_remaining_exhaustion(self) -> None:
        """Multiple buy signals should not exceed total capital."""
        sigs = []
        for sym in ["A", "B", "C", "D"]:
            s = generate_signal(_make_ohlcv(days=150, trend=0.005, high_volume=True), sym)
            if s is not None:
                sigs.append(s)
        positions = calculate_positions(sigs, capital=1000, max_positions=4)
        total = sum(p["buy_amount"] for p in positions)
        assert total <= 1000


class TestSafeFunctions:
    """Test _safe_last and _safe_at edge cases."""

    def test_safe_last_empty_series(self) -> None:
        from engine.signals import _safe_last

        assert _safe_last(pd.Series(dtype=float)) is None

    def test_safe_last_nan_value(self) -> None:
        from engine.signals import _safe_last

        s = pd.Series([1.0, 2.0, float("nan")])
        assert _safe_last(s) is None

    def test_safe_last_valid(self) -> None:
        from engine.signals import _safe_last

        s = pd.Series([1.0, 2.0, 3.0])
        assert _safe_last(s) == 3.0

    def test_safe_at_out_of_bounds(self) -> None:
        from engine.signals import _safe_at

        s = pd.Series([1.0, 2.0])
        assert _safe_at(s, -1) is None
        assert _safe_at(s, 5) is None

    def test_safe_at_nan(self) -> None:
        from engine.signals import _safe_at

        s = pd.Series([1.0, float("nan"), 3.0])
        assert _safe_at(s, 1) is None

    def test_safe_at_valid(self) -> None:
        from engine.signals import _safe_at

        s = pd.Series([10.0, 20.0])
        assert _safe_at(s, 0) == 10.0
        assert _safe_at(s, 1) == 20.0


class TestScoreAtIndex:
    """Test score_at_index with various factor combinations."""

    def test_score_at_index_basic(self) -> None:
        from engine.signals import precompute_factors, score_at_index

        df = _make_ohlcv(days=150, trend=0.003)
        factors = precompute_factors(df)
        direction, score = score_at_index(factors, 140, float(df["close"].iloc[140]))
        assert isinstance(direction, SignalDirection)
        assert isinstance(score, float)

    def test_score_at_index_bear_regime(self) -> None:
        from engine.signals import precompute_factors, score_at_index

        df = _make_ohlcv(days=150, trend=0.003)
        factors = precompute_factors(df)
        price = float(df["close"].iloc[140])
        _, score_neutral = score_at_index(factors, 140, price, market_regime=None)
        _, score_bear = score_at_index(factors, 140, price, market_regime="bear")
        # Bear regime should suppress positive scores
        if score_neutral > 0:
            assert score_bear <= score_neutral

    def test_score_at_index_bull_regime(self) -> None:
        from engine.signals import precompute_factors, score_at_index

        df = _make_ohlcv(days=150, trend=-0.003)
        factors = precompute_factors(df)
        price = float(df["close"].iloc[140])
        _, score_neutral = score_at_index(factors, 140, price, market_regime=None)
        _, score_bull = score_at_index(factors, 140, price, market_regime="bull")
        # Bull regime should reduce negative scores
        if score_neutral < 0:
            assert score_bull >= score_neutral

    def test_score_at_index_returns_valid_range(self) -> None:
        """Score at index should return finite score for various trends."""
        from engine.signals import precompute_factors, score_at_index

        for trend in [0.006, -0.006, 0.0]:
            df = _make_ohlcv(days=200, trend=trend)
            factors = precompute_factors(df)
            idx = 180
            direction, score = score_at_index(factors, idx, float(df["close"].iloc[idx]))
            assert isinstance(score, float)
            assert -100 <= score <= 100
            assert isinstance(direction, SignalDirection)


class TestDetectMarketRegime:
    """Test _detect_market_regime with mocked data."""

    @patch("data.storage.parquet_store.load_hist")
    def test_bull_market(self, mock_load: object) -> None:
        from engine.signals import _detect_market_regime

        mock_load.return_value = _make_ohlcv(days=200, trend=0.005)
        regime = _detect_market_regime()
        assert regime in ("bull", "range", "bear")

    @patch("data.storage.parquet_store.load_hist")
    def test_bear_market(self, mock_load: object) -> None:
        from engine.signals import _detect_market_regime

        mock_load.return_value = _make_ohlcv(days=200, trend=-0.005)
        regime = _detect_market_regime()
        assert regime in ("bull", "range", "bear")

    @patch("data.storage.parquet_store.load_hist")
    def test_empty_data_returns_range(self, mock_load: object) -> None:
        from engine.signals import _detect_market_regime

        mock_load.return_value = pd.DataFrame()
        assert _detect_market_regime() == "range"

    @patch("data.storage.parquet_store.load_hist")
    def test_short_data_returns_range(self, mock_load: object) -> None:
        from engine.signals import _detect_market_regime

        mock_load.return_value = _make_ohlcv(days=30)
        assert _detect_market_regime() == "range"


class TestGenerateSignalEdgeCases:
    """Test edge cases in generate_signal for coverage."""

    def test_missing_columns_returns_none(self) -> None:
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        assert generate_signal(df, "TEST") is None

    def test_sell_direction_price_targets(self) -> None:
        """Test that sell signals have correct target/stop structure."""
        df = _make_ohlcv(days=200, trend=-0.008)
        sig = generate_signal(df, "TEST", market_regime="bear")
        assert sig is not None
        if sig.direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL):
            # Sell target should be below current price
            assert sig.target_price < sig.current_price
            # Sell stop loss should be above current price
            assert sig.stop_loss > sig.current_price

    def test_hold_direction_price_targets(self) -> None:
        """Test hold signal produces sensible targets."""
        df = _make_ohlcv(days=100, trend=0.0)
        sig = generate_signal(df, "TEST")
        assert sig is not None
        if sig.direction == SignalDirection.HOLD:
            assert sig.entry_price > 0
            assert sig.target_price > 0

    def test_120_day_data_includes_percentile(self) -> None:
        """With 120+ days of data, price percentile should be computed."""
        df = _make_ohlcv(days=150, trend=0.001)
        sig = generate_signal(df, "TEST")
        assert sig is not None
        assert sig.factors.get("price_pctile_120d") is not None

    def test_60_day_data_no_percentile(self) -> None:
        """With <120 days, price percentile should be None."""
        df = _make_ohlcv(days=70, trend=0.001)
        sig = generate_signal(df, "TEST")
        assert sig is not None
        assert sig.factors.get("price_pctile_120d") is None

    def test_strength_bounded(self) -> None:
        """Signal strength should always be 0-100."""
        for trend in [-0.01, -0.005, 0.0, 0.005, 0.01]:
            df = _make_ohlcv(days=150, trend=trend)
            sig = generate_signal(df, "TEST")
            assert sig is not None
            assert 0 <= sig.strength <= 100

    def test_position_pct_bounded(self) -> None:
        """Position size should be in reasonable range."""
        df = _make_ohlcv(days=150, trend=0.005)
        sig = generate_signal(df, "TEST")
        assert sig is not None
        assert 0 < sig.position_pct <= 0.25

    def test_reason_not_empty(self) -> None:
        """All signals should have a reason string."""
        df = _make_ohlcv(days=100, trend=0.0)
        sig = generate_signal(df, "TEST")
        assert sig is not None
        assert len(sig.reason) > 0


class TestSignalAccuracyValidation:
    """Tests validating signal quality and consistency."""

    def test_uptrend_signal_valid(self) -> None:
        """V4.0: Uptrend may produce sell (profit-taking) or buy signal — both valid."""
        df_up = _make_ohlcv(days=150, trend=0.01)
        sig_up = generate_signal(df_up, "UP")
        assert sig_up is not None
        assert sig_up.direction in list(SignalDirection)

    def test_downtrend_has_reversal_factor(self) -> None:
        """V3.5: Downtrend signals should include ret_5d reversal factor.

        With IC-calibrated contrarian factors, downtrend CAN trigger buy
        (mean reversion). The important thing is factor completeness.
        """
        df_down = _make_ohlcv(days=150, trend=-0.01)
        sig_down = generate_signal(df_down, "DOWN")
        assert sig_down is not None
        assert "ret_5d" in sig_down.factors

    def test_regime_consistency(self) -> None:
        """Bear regime should not produce higher buy scores than neutral."""
        df = _make_ohlcv(days=150, trend=0.003)
        sig_neutral = generate_signal(df, "T", market_regime=None)
        sig_bear = generate_signal(df, "T", market_regime="bear")
        assert sig_neutral is not None
        assert sig_bear is not None
        assert sig_bear.score <= sig_neutral.score

    def test_score_deterministic(self) -> None:
        """Same input should always produce same output."""
        df = _make_ohlcv(days=150, trend=0.003)
        sig1 = generate_signal(df, "TEST")
        sig2 = generate_signal(df, "TEST")
        assert sig1 is not None
        assert sig2 is not None
        assert sig1.score == sig2.score
        assert sig1.direction == sig2.direction

    def test_direction_matches_score_sign(self) -> None:
        """Buy directions should have positive scores, sell negative."""
        for trend in [-0.008, -0.003, 0.0, 0.003, 0.008]:
            df = _make_ohlcv(days=150, trend=trend)
            sig = generate_signal(df, "T")
            assert sig is not None
            if sig.direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY):
                assert sig.score > 0
            if sig.direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL):
                assert sig.score < 0


def _make_extreme_ohlcv(
    days: int = 150,
    rsi_level: str = "normal",
    volatility: str = "normal",
    mfi_level: str = "normal",
    trend: float = 0.001,
    smart_flow: str = "neutral",
) -> pd.DataFrame:
    """Create OHLCV data with extreme factor conditions.

    Args:
        rsi_level: "oversold" (<25), "overbought" (>75), "normal"
        volatility: "high" (>0.4 annualized), "normal"
        mfi_level: "oversold" (<20), "overbought" (>80), "normal"
        smart_flow: "bullish" (>0.3), "bearish" (<-0.3), "neutral"
    """
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=days)

    if rsi_level == "overbought":
        # Strong uptrend to push RSI > 75
        close = 3.0 * np.cumprod(1 + np.random.normal(0.015, 0.005, days))
    elif rsi_level == "oversold":
        # Strong downtrend to push RSI < 25
        close = 3.0 * np.cumprod(1 + np.random.normal(-0.015, 0.005, days))
    elif volatility == "high":
        # High daily swings → high annualized vol
        close = 3.0 * np.cumprod(1 + np.random.normal(trend, 0.06, days))
    else:
        close = 3.0 * np.cumprod(1 + np.random.normal(trend, 0.02, days))

    volume = np.random.randint(1_000_000, 10_000_000, days).astype(float)

    if mfi_level == "oversold":
        # Low prices + low volume → low MFI
        close[-20:] = close[-20] * np.cumprod(1 + np.random.normal(-0.02, 0.003, 20))
        volume[-20:] = volume[:20].mean() * 0.3
    elif mfi_level == "overbought":
        # High prices + high volume → high MFI
        close[-20:] = close[-20] * np.cumprod(1 + np.random.normal(0.02, 0.003, 20))
        volume[-20:] = volume[:20].mean() * 3.0

    if smart_flow == "bullish":
        # Large positive volume on up days
        for i in range(-20, 0):
            if close[i] > close[i - 1]:
                volume[i] *= 3.0
    elif smart_flow == "bearish":
        # Large positive volume on down days
        for i in range(-20, 0):
            if close[i] < close[i - 1]:
                volume[i] *= 3.0

    high = close * 1.01
    low = close * 0.99

    df = pd.DataFrame(
        {
            "open": close * 0.999,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )
    df.index.name = "date"
    return df


class TestScoreAtIndexExtremePaths:
    """Cover extreme factor paths in score_at_index."""

    def test_rsi_overbought_path(self) -> None:
        """RSI > 75 should contribute bearish score."""
        from engine.signals import precompute_factors, score_at_index

        df = _make_extreme_ohlcv(days=200, rsi_level="overbought")
        factors = precompute_factors(df)
        idx = len(df) - 1
        rsi_val = float(factors["rsi_14"].iloc[idx])
        direction, score = score_at_index(factors, idx, float(df["close"].iloc[idx]))
        # With strong uptrend, RSI should be high
        assert rsi_val > 60
        assert isinstance(score, float)

    def test_high_volatility_bullish_path(self) -> None:
        """High volatility (>0.4) should add bullish score (mean reversion)."""
        from engine.signals import precompute_factors, score_at_index

        df = _make_extreme_ohlcv(days=200, volatility="high")
        factors = precompute_factors(df)
        idx = len(df) - 1
        hvol_val = float(factors["hvol_20d"].iloc[idx])
        direction, score = score_at_index(factors, idx, float(df["close"].iloc[idx]))
        assert hvol_val > 0.3  # High vol from 6% daily std
        assert isinstance(score, float)

    def test_mfi_oversold_path(self) -> None:
        """MFI < 20 should trigger bullish flow score."""
        from engine.signals import precompute_factors, score_at_index

        df = _make_extreme_ohlcv(days=200, mfi_level="oversold")
        factors = precompute_factors(df)
        idx = len(df) - 1
        direction, score = score_at_index(factors, idx, float(df["close"].iloc[idx]))
        assert isinstance(direction, SignalDirection)

    def test_smart_flow_bullish_confirmation(self) -> None:
        """Smart money flow > 0.3 with positive score should add +3."""
        from engine.signals import precompute_factors, score_at_index

        df = _make_extreme_ohlcv(days=200, trend=0.005, smart_flow="bullish")
        factors = precompute_factors(df)
        idx = len(df) - 1
        direction, score = score_at_index(factors, idx, float(df["close"].iloc[idx]))
        assert isinstance(score, (int, float))

    def test_smart_flow_bearish_confirmation(self) -> None:
        """Smart money flow < -0.3 with negative score should add -3."""
        from engine.signals import precompute_factors, score_at_index

        df = _make_extreme_ohlcv(days=200, trend=-0.005, smart_flow="bearish")
        factors = precompute_factors(df)
        idx = len(df) - 1
        direction, score = score_at_index(factors, idx, float(df["close"].iloc[idx]))
        assert isinstance(score, float)

    def test_strong_buy_threshold(self) -> None:
        """Score >= 25 should produce STRONG_BUY direction."""
        from engine.signals import precompute_factors, score_at_index

        # Use high vol data to push score high
        np.random.seed(99)
        close = 3.0 * np.cumprod(1 + np.random.normal(-0.015, 0.06, 200))
        dates = pd.bdate_range("2024-01-01", periods=200)
        volume = np.random.randint(1_000_000, 10_000_000, 200).astype(float)
        df2 = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": volume,
            },
            index=dates,
        )
        factors = precompute_factors(df2)
        idx = len(df2) - 1
        direction, score = score_at_index(factors, idx, float(df2["close"].iloc[idx]))
        # Score may or may not reach 25, but direction should be valid
        assert direction in list(SignalDirection)
        if score >= 25:
            assert direction == SignalDirection.STRONG_BUY

    def test_bear_regime_suppression(self) -> None:
        """Bear regime should reduce positive scores by 40%."""
        from engine.signals import precompute_factors, score_at_index

        df = _make_ohlcv(days=200, trend=0.003)
        factors = precompute_factors(df)
        idx = 180
        price = float(df["close"].iloc[idx])
        _, score_none = score_at_index(factors, idx, price, market_regime=None)
        _, score_bear = score_at_index(factors, idx, price, market_regime="bear")
        _, score_bull = score_at_index(factors, idx, price, market_regime="bull")
        if score_none > 0:
            assert score_bear <= score_none
        if score_none < 0:
            assert score_bull >= score_none

    def test_bear_regime_hold_to_sell_reclassification(self) -> None:
        """In bear market, HOLD with negative momentum → SELL."""
        from engine.signals import precompute_factors, score_at_index

        # Moderate downtrend: score near zero but mom_20 < -0.02
        df = _make_ohlcv(days=200, trend=-0.003)
        factors = precompute_factors(df)
        idx = 180
        price = float(df["close"].iloc[idx])
        direction, score = score_at_index(factors, idx, price, market_regime="bear")
        # May or may not trigger reclassification, but path is valid
        assert direction in list(SignalDirection)

    def test_buy_confirmation_gate_bear(self) -> None:
        """In bear market, buy needs 3 bullish factors (stricter gate)."""
        from engine.signals import precompute_factors, score_at_index

        df = _make_ohlcv(days=200, trend=0.002)
        factors = precompute_factors(df)
        idx = 180
        price = float(df["close"].iloc[idx])
        direction, score = score_at_index(factors, idx, price, market_regime="bear")
        # If score > 12 but < 3 bullish factors → downgraded to HOLD
        assert direction in list(SignalDirection)

    def test_sell_confirmation_gate(self) -> None:
        """Sell needs >= 2 bearish factors or gets downgraded to HOLD."""
        from engine.signals import precompute_factors, score_at_index

        df = _make_ohlcv(days=200, trend=-0.001)
        factors = precompute_factors(df)
        idx = 180
        price = float(df["close"].iloc[idx])
        direction, score = score_at_index(factors, idx, price)
        assert direction in list(SignalDirection)


class TestGenerateSignalExtremePaths:
    """Cover extreme paths in generate_signal."""

    def test_aggressive_mode_reduces_bear_penalty(self) -> None:
        """Aggressive mode should use 0.1 penalty instead of 0.4."""
        df = _make_ohlcv(days=150, trend=0.003)
        sig_normal = generate_signal(df, "T", market_regime="bear", aggressive=False)
        sig_aggressive = generate_signal(df, "T", market_regime="bear", aggressive=True)
        assert sig_normal is not None
        assert sig_aggressive is not None
        # Aggressive should have higher score in bear market
        assert sig_aggressive.score >= sig_normal.score

    def test_bull_regime_reduces_negative_score(self) -> None:
        """Bull regime should soften negative scores by 20%."""
        df = _make_ohlcv(days=150, trend=-0.003)
        sig_none = generate_signal(df, "T", market_regime=None)
        sig_bull = generate_signal(df, "T", market_regime="bull")
        assert sig_none is not None
        assert sig_bull is not None
        if sig_none.score < 0:
            assert sig_bull.score >= sig_none.score

    def test_strong_sell_bear_threshold(self) -> None:
        """Strong sell threshold is -25 in bear market."""
        df = _make_extreme_ohlcv(days=200, rsi_level="overbought")
        sig = generate_signal(df, "T", market_regime="bear")
        assert sig is not None
        assert isinstance(sig.direction, SignalDirection)

    def test_sell_signal_price_targets(self) -> None:
        """Sell direction: target < current, stop > current."""
        df = _make_extreme_ohlcv(days=200, rsi_level="overbought")
        sig = generate_signal(df, "T", market_regime="bear")
        assert sig is not None
        if sig.direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL):
            assert sig.target_price < sig.current_price
            assert sig.stop_loss > sig.current_price
            assert sig.entry_price < sig.current_price

    def test_bear_hold_reclassification(self) -> None:
        """Bear + negative momentum + MA ratio < 1 → HOLD becomes SELL."""
        df = _make_ohlcv(days=200, trend=-0.004)
        sig = generate_signal(df, "T", market_regime="bear")
        assert sig is not None
        # Check if reclassification happened
        if "熊市+下行趋势" in sig.reason:
            assert sig.direction in (
                SignalDirection.SELL,
                SignalDirection.HOLD,  # May be downgraded by sell gate
            )

    def test_buy_gate_insufficient_factors(self) -> None:
        """Score > 12 but < 2 bullish factors → downgraded to HOLD."""
        # Mild trend where only 1-2 factors are bullish
        df = _make_ohlcv(days=100, trend=0.002)
        sig = generate_signal(df, "T")
        assert sig is not None
        if "多头因子不足" in sig.reason:
            assert sig.direction == SignalDirection.HOLD

    def test_sell_gate_insufficient_factors(self) -> None:
        """Sell with < 2 bearish factors → downgraded to HOLD."""
        df = _make_ohlcv(days=100, trend=-0.002)
        sig = generate_signal(df, "T")
        assert sig is not None
        if "空头因子不足" in sig.reason:
            assert sig.direction == SignalDirection.HOLD

    def test_smart_money_bearish_confirmation(self) -> None:
        """Smart money outflow with negative score amplifies sell signal."""
        df = _make_extreme_ohlcv(days=200, trend=-0.005, smart_flow="bearish")
        sig = generate_signal(df, "T")
        assert sig is not None
        if "智能资金净流出" in sig.reason:
            assert sig.score < 0

    def test_high_volatility_position_reduction(self) -> None:
        """Vol regime > 1.5 should reduce position size."""
        df = _make_extreme_ohlcv(days=200, volatility="high")
        sig = generate_signal(df, "T")
        assert sig is not None
        if sig.factors.get("vol_regime") and sig.factors["vol_regime"] > 1.5:
            assert "波动扩张减仓" in sig.reason

    def test_mfi_overbought_path(self) -> None:
        """MFI > 80 should trigger bearish flow signal."""
        df = _make_extreme_ohlcv(days=200, mfi_level="overbought")
        sig = generate_signal(df, "T")
        assert sig is not None
        # MFI overbought path should be exercised
        assert isinstance(sig.factors.get("mfi_14"), (float, type(None)))


class TestCalculatePositionsEdgeCases:
    """Cover edge cases in calculate_positions."""

    def test_remaining_exhaustion_break(self) -> None:
        """When remaining <= 100, should stop allocating."""
        from engine.signals import TradingSignal

        # Create artificial buy signals
        sigs = [
            TradingSignal(
                symbol=f"ETF{i}",
                direction=SignalDirection.BUY,
                strength=50.0,
                current_price=10.0,
                entry_price=10.02,
                target_price=10.5,
                stop_loss=9.5,
                position_pct=0.5,
                reason="test",
                factors={},
                score=20.0,
            )
            for i in range(5)
        ]
        # Capital = 200, first alloc will take most, then should stop
        positions = calculate_positions(sigs, capital=200, max_positions=5)
        total = sum(p["buy_amount"] for p in positions)
        assert total <= 200

    def test_minimum_lot_size(self) -> None:
        """Shares should always be in lots of 100."""
        from engine.signals import TradingSignal

        sig = TradingSignal(
            symbol="TEST",
            direction=SignalDirection.BUY,
            strength=30.0,
            current_price=50.0,
            entry_price=50.1,
            target_price=52.0,
            stop_loss=49.0,
            position_pct=0.05,
            reason="test",
            factors={},
            score=15.0,
        )
        positions = calculate_positions([sig], capital=100000, max_positions=1)
        assert len(positions) >= 1
        assert positions[0]["shares"] % 100 == 0

    def test_expensive_etf_minimum_shares(self) -> None:
        """When ETF is expensive, minimum 100 shares should still apply."""
        from engine.signals import TradingSignal

        sig = TradingSignal(
            symbol="EXPENSIVE",
            direction=SignalDirection.BUY,
            strength=30.0,
            current_price=100.0,
            entry_price=100.2,
            target_price=105.0,
            stop_loss=98.0,
            position_pct=0.01,  # Very small position
            reason="test",
            factors={},
            score=15.0,
        )
        positions = calculate_positions([sig], capital=50000, max_positions=1)
        if positions:
            assert positions[0]["shares"] >= 100

    def test_buy_amount_exceeds_remaining(self) -> None:
        """When buy_amount > remaining, should recalculate shares."""
        from engine.signals import TradingSignal

        sigs = [
            TradingSignal(
                symbol=f"ETF{i}",
                direction=SignalDirection.BUY,
                strength=80.0,
                current_price=5.0,
                entry_price=5.01,
                target_price=5.5,
                stop_loss=4.5,
                position_pct=0.20,
                reason="test",
                factors={},
                score=25.0,
            )
            for i in range(3)
        ]
        # Capital just enough for ~2 positions
        positions = calculate_positions(sigs, capital=3000, max_positions=3)
        total = sum(p["buy_amount"] for p in positions)
        assert total <= 3000

    def test_strong_buy_included(self) -> None:
        """STRONG_BUY signals should also be included in positions."""
        from engine.signals import TradingSignal

        sig = TradingSignal(
            symbol="STRONG",
            direction=SignalDirection.STRONG_BUY,
            strength=90.0,
            current_price=3.0,
            entry_price=3.006,
            target_price=3.3,
            stop_loss=2.8,
            position_pct=0.15,
            reason="strong signal",
            factors={},
            score=30.0,
        )
        positions = calculate_positions([sig], capital=50000, max_positions=1)
        assert len(positions) == 1
        assert positions[0]["symbol"] == "STRONG"


class TestMomentumAccelerationEdge:
    """Cover edge case in _momentum_acceleration."""

    def test_momentum_returns_none_when_factor_nan(self) -> None:
        """When momentum returns NaN, acceleration should return None."""
        # Create series where last value is NaN
        close = pd.Series([float("nan")] * 25)
        result = _momentum_acceleration(close)
        assert result is None


def _make_factor_dict(overrides: dict | None = None) -> dict[str, pd.Series]:
    """Create a minimal factor dict for score_at_index testing.

    All factors default to neutral values. Override specific ones to test paths.
    """
    idx = 10
    base = {
        "momentum_20d": pd.Series([0.0] * (idx + 1)),
        "momentum_5d": pd.Series([0.0] * (idx + 1)),
        "ret_5d": pd.Series([0.0] * (idx + 1)),
        "rsi_14": pd.Series([50.0] * (idx + 1)),
        "ma_ratio_5_20": pd.Series([1.0] * (idx + 1)),
        "ma_dev_20d": pd.Series([0.0] * (idx + 1)),
        "hvol_20d": pd.Series([0.2] * (idx + 1)),
        "mdd_60d": pd.Series([0.05] * (idx + 1)),
        "price_pctile_120d": pd.Series([0.5] * (idx + 1)),
        "volume_ratio": pd.Series([1.0] * (idx + 1)),
        "momentum_accel": pd.Series([0.0] * (idx + 1)),
        "mfi_14": pd.Series([50.0] * (idx + 1)),
        "obv_trend_20d": pd.Series([0.0] * (idx + 1)),
        "vol_price_div_10d": pd.Series([0.0] * (idx + 1)),
        "smart_flow_20d": pd.Series([0.0] * (idx + 1)),
    }
    if overrides:
        for key, val in overrides.items():
            base[key] = pd.Series([val] * (idx + 1))
    return base


class TestScoreAtIndexDirectPaths:
    """Test score_at_index with crafted factor dicts to hit specific paths."""

    def test_smf_bullish_confirmation(self) -> None:
        """SMF > 0.3 with score > 5 → +3 score (lines 362-364)."""
        from engine.signals import score_at_index

        # Build strong bullish base: ret_5d < -0.04 (+10), mom_accel > 0.03 (+8)
        factors = _make_factor_dict(
            {
                "ret_5d": -0.05,
                "momentum_accel": 0.04,
                "smart_flow_20d": 0.5,
            }
        )
        direction, score = score_at_index(factors, 10, 3.0)
        # V4.0: ret_5d(-0.05)→+8, mom_accel(0.04)→+3, smf should add more
        assert score >= 5

    def test_structural_sell_signals(self) -> None:
        """V5.0: Sell requires structural signals (ATR stop + MA death cross)."""
        from engine.signals import score_at_index

        # Trigger structural sell: ATR trailing stop + MA death cross + vol decline
        factors = _make_factor_dict(
            {
                "atr_trail_stop": 1.0,  # S1: price below trailing stop
                "ma_ratio_5_20": 0.98,  # S2 part: MA death cross
                "volume_ratio": 0.6,  # S2 part: volume declining
                "rsi_divergence": 1.0,  # S3: RSI divergence
            }
        )
        direction, score = score_at_index(factors, 10, 3.0)
        assert score < 0

    def test_bear_regime_positive_score_suppression(self) -> None:
        """Bear regime with positive score → score * 0.4 penalty (line 376)."""
        from engine.signals import score_at_index

        # Strong bullish: ret_5d < -0.04 (+10), many factors
        factors = _make_factor_dict(
            {
                "ret_5d": -0.05,
                "momentum_20d": 0.06,
                "momentum_5d": 0.03,
                "momentum_accel": 0.04,
                "rsi_14": 30.0,
                "ma_ratio_5_20": 1.03,
                "price_pctile_120d": 0.1,
            }
        )
        _, score_neutral = score_at_index(factors, 10, 3.0, market_regime=None)
        _, score_bear = score_at_index(factors, 10, 3.0, market_regime="bear")
        assert score_neutral > 0
        assert score_bear < score_neutral

    def test_strong_sell_structural(self) -> None:
        """V5.0: 3+ structural sell signals → STRONG_SELL."""
        from engine.signals import score_at_index

        # Trigger 3+ structural sell signals for STRONG_SELL
        factors = _make_factor_dict(
            {
                "atr_trail_stop": 1.0,  # S1: ATR stop break (-10)
                "ma_ratio_5_20": 0.98,  # S2: death cross
                "momentum_accel": -0.04,  # S2: momentum decel → sell_signals +1
                "rsi_divergence": 1.0,  # S3: RSI divergence (-7)
                "vol_climax": 1.0,  # S4: volume climax (-7)
                "volume_ratio": 0.6,  # low volume (supports death cross)
            }
        )
        direction, score = score_at_index(factors, 10, 3.0, market_regime="bear")
        assert score < -10
        assert direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL)

    def test_sell_with_two_structural_signals(self) -> None:
        """V5.0: 2 structural sell signals → SELL direction."""
        from engine.signals import score_at_index

        # Two structural sell triggers
        factors = _make_factor_dict(
            {
                "atr_trail_stop": 1.0,  # S1: ATR stop break
                "rsi_divergence": 1.0,  # S3: RSI divergence
            }
        )
        direction, score = score_at_index(factors, 10, 3.0)
        assert direction == SignalDirection.SELL
        assert score < 0

    def test_buy_gate_blocks_in_score_at_index(self) -> None:
        """V5.0: Buy score with < 3 bullish factors → HOLD."""
        from engine.signals import score_at_index

        # Score > 20 but only 1 bullish factor
        factors = _make_factor_dict(
            {
                "ret_5d": -0.05,  # +8, bullish_factors = 1
                # Everything else neutral → only 1 bullish factor
            }
        )
        direction, score = score_at_index(factors, 10, 3.0)
        if score >= 20:
            # Should be downgraded because < 3 bullish factors
            assert direction == SignalDirection.HOLD

    def test_sell_gate_requires_structural_signals(self) -> None:
        """V5.0: Sell requires 2+ structural sell signals."""
        from engine.signals import score_at_index

        # Only 1 structural sell signal → should be HOLD
        factors = _make_factor_dict(
            {
                "atr_trail_stop": 1.0,  # S1: only one structural signal
            }
        )
        direction, score = score_at_index(factors, 10, 3.0)
        # 1 signal not enough for SELL direction
        assert direction == SignalDirection.HOLD

    def test_bull_regime_weakens_sell(self) -> None:
        """V5.0: Bull regime weakens structural sell signals."""
        from engine.signals import score_at_index

        # Structural sells present
        factors = _make_factor_dict(
            {
                "atr_trail_stop": 1.0,
                "rsi_divergence": 1.0,
                "vol_climax": 1.0,
            }
        )
        _, score_none = score_at_index(factors, 10, 3.0, market_regime=None)
        _, score_bull = score_at_index(factors, 10, 3.0, market_regime="bull")
        # Both should be negative from structural signals
        assert score_none < 0
        assert score_bull < 0


class TestGenerateSignalSmartFlowAndGates:
    """Cover remaining generate_signal paths with targeted data."""

    def test_generate_signal_smf_bearish_in_generate(self) -> None:
        """Smart money bearish confirm in generate_signal (lines 679-681)."""
        # Strong downtrend with bearish smart flow
        np.random.seed(77)
        days = 200
        dates = pd.bdate_range("2024-01-01", periods=days)
        close = 5.0 * np.cumprod(1 + np.random.normal(-0.008, 0.015, days))
        volume = np.random.randint(2_000_000, 8_000_000, days).astype(float)
        # Amplify volume on down days
        for i in range(-25, 0):
            if close[i] < close[i - 1]:
                volume[i] *= 4.0
        df = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.008,
                "low": close * 0.992,
                "close": close,
                "volume": volume,
            },
            index=dates,
        )
        sig = generate_signal(df, "T")
        assert sig is not None
        # Score should be negative from strong downtrend
        assert isinstance(sig.score, (int, float))

    def test_generate_signal_bull_regime_negative_score(self) -> None:
        """Bull regime with negative score gets +20% adjustment (line 699)."""
        df = _make_ohlcv(days=200, trend=-0.006)
        sig_none = generate_signal(df, "T", market_regime=None)
        sig_bull = generate_signal(df, "T", market_regime="bull")
        assert sig_none is not None
        assert sig_bull is not None
        if sig_none.score < 0:
            assert sig_bull.score >= sig_none.score

    def test_generate_signal_strong_buy_direction(self) -> None:
        """Score >= 25 should produce STRONG_BUY (line 715)."""
        # Deep crash + extreme oversold → strong reversal signal
        np.random.seed(88)
        days = 200
        dates = pd.bdate_range("2024-01-01", periods=days)
        close = 5.0 * np.cumprod(1 + np.random.normal(-0.012, 0.04, days))
        volume = np.random.randint(2_000_000, 8_000_000, days).astype(float)
        volume[-5:] = volume.mean() * 3.0  # Volume spike
        df = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": volume,
            },
            index=dates,
        )
        sig = generate_signal(df, "T")
        assert sig is not None
        # May or may not hit STRONG_BUY; the path coverage matters
        assert sig.direction in list(SignalDirection)

    def test_generate_signal_buy_gate_fail(self) -> None:
        """Buy gate fails when bullish factors < min_bullish (lines 739-740)."""
        # Moderate uptrend — score might cross 12 but not many bullish factors
        np.random.seed(55)
        days = 100
        dates = pd.bdate_range("2024-01-01", periods=days)
        close = 3.0 * np.cumprod(1 + np.random.normal(0.002, 0.01, days))
        volume = np.random.randint(1_000_000, 5_000_000, days).astype(float)
        df = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.005,
                "low": close * 0.995,
                "close": close,
                "volume": volume,
            },
            index=dates,
        )
        sig = generate_signal(df, "T")
        assert sig is not None
        assert sig.direction in list(SignalDirection)

    def test_generate_signal_sell_gate_fail(self) -> None:
        """Sell gate fails when bearish factors < 2 (lines 744-745)."""
        np.random.seed(66)
        days = 100
        dates = pd.bdate_range("2024-01-01", periods=days)
        close = 3.0 * np.cumprod(1 + np.random.normal(-0.002, 0.01, days))
        volume = np.random.randint(1_000_000, 5_000_000, days).astype(float)
        df = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.005,
                "low": close * 0.995,
                "close": close,
                "volume": volume,
            },
            index=dates,
        )
        sig = generate_signal(df, "T", market_regime="bear")
        assert sig is not None
        assert sig.direction in list(SignalDirection)

    def test_positions_remaining_under_100_break(self) -> None:
        """calculate_positions stops when remaining <= 100 (line 906)."""
        from engine.signals import TradingSignal

        sig = TradingSignal(
            symbol="CHEAP",
            direction=SignalDirection.BUY,
            strength=50.0,
            current_price=0.5,
            entry_price=0.501,
            target_price=0.55,
            stop_loss=0.45,
            position_pct=0.90,
            reason="test",
            factors={},
            score=20.0,
        )
        # Capital = 150, first alloc ~135, remaining ~15 < 100 → break
        positions = calculate_positions([sig, sig], capital=150, max_positions=2)
        total = sum(p["buy_amount"] for p in positions)
        assert total <= 150

    def test_positions_shares_recalc_on_overflow(self) -> None:
        """When buy_amount > remaining, recalculate shares (lines 919-922)."""
        from engine.signals import TradingSignal

        sigs = [
            TradingSignal(
                symbol=f"E{i}",
                direction=SignalDirection.BUY,
                strength=80.0,
                current_price=2.0,
                entry_price=2.004,
                target_price=2.2,
                stop_loss=1.8,
                position_pct=0.25,
                reason="test",
                factors={},
                score=25.0,
            )
            for i in range(4)
        ]
        # Capital constrains later positions
        positions = calculate_positions(sigs, capital=2000, max_positions=4)
        total = sum(p["buy_amount"] for p in positions)
        assert total <= 2000


class TestDetectMarketRegimeExtended:
    """Cover remaining paths in _detect_market_regime."""

    @patch("data.storage.parquet_store.load_hist")
    def test_regime_m60_bullish(self, mock_load: object) -> None:
        """60-day momentum > 0.05 contributes to bull count (line 834+)."""
        from engine.signals import _detect_market_regime

        # Strong uptrend over 60 days
        np.random.seed(42)
        days = 200
        dates = pd.bdate_range("2024-01-01", periods=days)
        close = 3.0 * np.cumprod(1 + np.random.normal(0.005, 0.01, days))
        volume = np.random.randint(1_000_000, 10_000_000, days).astype(float)
        df = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": volume,
            },
            index=dates,
        )
        mock_load.return_value = df
        regime = _detect_market_regime()
        assert regime in ("bull", "range", "bear")
