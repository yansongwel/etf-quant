"""Market regime detection — determines if we're in bull/bear/range market.

Uses broad market index (沪深300) to classify the current environment,
then adjusts factor weights accordingly.

Regimes:
- BULL: 20d momentum > 3%, MA5 > MA20 → favor momentum
- BEAR: 20d momentum < -3%, MA5 < MA20 → favor value (contrarian)
- RANGE: sideways → favor volatility (avoid high-vol, seek mean reversion)
"""

from __future__ import annotations

import logging
from enum import StrEnum

from data.storage.parquet_store import load_hist
from factors.momentum import momentum, moving_average_ratio

logger = logging.getLogger(__name__)

BENCHMARK = "510300"  # 沪深300ETF as market proxy


class MarketRegime(StrEnum):
    BULL = "bull"
    BEAR = "bear"
    RANGE = "range"


REGIME_LABELS = {
    MarketRegime.BULL: "牛市（趋势向上）",
    MarketRegime.BEAR: "熊市（趋势向下）",
    MarketRegime.RANGE: "震荡市（横盘整理）",
}

# Adaptive weights per regime
REGIME_WEIGHTS = {
    MarketRegime.BULL: {"momentum": 0.65, "value": 0.15, "volatility": 0.20},
    MarketRegime.BEAR: {"momentum": 0.20, "value": 0.50, "volatility": 0.30},
    MarketRegime.RANGE: {"momentum": 0.35, "value": 0.35, "volatility": 0.30},
}


def detect_regime(benchmark: str = BENCHMARK) -> dict:
    """Detect current market regime based on benchmark ETF.

    Returns:
        Dict with regime, label, indicators, and adaptive weights.
    """
    df = load_hist(benchmark)
    if df.empty or len(df) < 60:
        return {
            "regime": MarketRegime.RANGE.value,
            "label": REGIME_LABELS[MarketRegime.RANGE],
            "weights": REGIME_WEIGHTS[MarketRegime.RANGE],
            "indicators": {},
            "note": "数据不足，使用默认震荡市权重",
        }

    close = df["close"]
    mom_20 = float(momentum(close, 20).iloc[-1])
    mom_60 = float(momentum(close, 60).iloc[-1])
    ma_ratio_val = float(moving_average_ratio(close, 5, 20).iloc[-1])

    # Classify
    if mom_20 > 0.03 and ma_ratio_val > 1.01:
        regime = MarketRegime.BULL
    elif mom_20 < -0.03 and ma_ratio_val < 0.99:
        regime = MarketRegime.BEAR
    else:
        regime = MarketRegime.RANGE

    weights = REGIME_WEIGHTS[regime]

    return {
        "regime": regime.value,
        "label": REGIME_LABELS[regime],
        "weights": weights,
        "indicators": {
            "momentum_20d": round(mom_20 * 100, 2),
            "momentum_60d": round(mom_60 * 100, 2),
            "ma_ratio_5_20": round(ma_ratio_val, 4),
            "benchmark": benchmark,
        },
    }
