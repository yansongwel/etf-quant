"""Strategy recommendation engine.

Given a capital amount, evaluates all strategies against available ETFs,
ranks by risk-adjusted return, and produces actionable recommendations.

IMPORTANT: For research/education only. Not investment advice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from data.storage.parquet_store import load_hist
from engine.backtest import run_backtest
from engine.metrics import summary
from engine.types import BacktestConfig
from strategies.balance import BalanceStrategy
from strategies.multifactor import MultiFactorStrategy
from strategies.rotation import RotationStrategy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategyRecommendation:
    """A recommended strategy with projected performance."""

    strategy_name: str
    strategy_id: str
    symbols: list[str]
    params: dict
    metrics: dict[str, float]
    rank: int
    recommendation: str  # Human-readable recommendation

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "strategy_id": self.strategy_id,
            "symbols": self.symbols,
            "params": self.params,
            "metrics": {
                k: round(v, 4) if isinstance(v, float) else v for k, v in self.metrics.items()
            },
            "rank": self.rank,
            "recommendation": self.recommendation,
        }


def _load_all_available() -> dict[str, pd.DataFrame]:
    """Load all available ETF data from storage."""
    from config.settings import settings

    data_dir = settings.data.data_dir / "etf_hist"
    if not data_dir.exists():
        return {}

    data = {}
    for f in data_dir.glob("*.parquet"):
        df = load_hist(f.stem)
        if not df.empty and len(df) >= 60:
            data[f.stem] = df
    return data


def _score_strategy(metrics: dict) -> float:
    """Composite score for ranking strategies. Higher is better."""
    ann_ret = metrics.get("annualized_return", 0)
    sharpe = metrics.get("sharpe_ratio", 0)
    mdd = metrics.get("max_drawdown", 0.01)
    calmar = metrics.get("calmar_ratio", 0)

    # Weighted combination: Sharpe (40%) + Calmar (30%) + Return/MDD (30%)
    score = sharpe * 0.4 + calmar * 0.3 + (ann_ret / max(mdd, 0.01)) * 0.3
    return score


def recommend_strategies(
    capital: float = 5000.0,
    max_results: int = 5,
) -> list[StrategyRecommendation]:
    """Evaluate all strategies and return ranked recommendations.

    Args:
        capital: Available capital in CNY.
        max_results: Maximum recommendations to return.
    """
    all_data = _load_all_available()
    if not all_data:
        logger.warning("No ETF data available for recommendations")
        return []

    symbols = list(all_data.keys())
    config = BacktestConfig(
        initial_cash=capital,
        commission_rate=0.0002,
        slippage=0.001,
    )

    candidates: list[tuple[float, StrategyRecommendation]] = []

    # ── Strategy 1: Rotation (various lookbacks) ──────
    for lookback in [10, 20, 40]:
        for top_k in [2, 3]:
            if top_k > len(symbols):
                continue
            strategy = RotationStrategy(lookback=lookback, top_k=top_k, rebalance_days=lookback)
            result = run_backtest(all_data, strategy, config)
            metrics = summary(result)
            score = _score_strategy(metrics)

            rec = StrategyRecommendation(
                strategy_name=f"动量轮动 (周期{lookback}天, Top{top_k})",
                strategy_id="rotation",
                symbols=symbols,
                params={"lookback": lookback, "top_k": top_k, "rebalance_days": lookback},
                metrics=metrics,
                rank=0,
                recommendation=_build_recommendation("rotation", metrics, capital, top_k),
            )
            candidates.append((score, rec))

    # ── Strategy 2: Balance (various weights) ─────────
    stock_etfs = [s for s in symbols if s not in ("511010",)]
    bond_etfs = [s for s in symbols if s in ("511010",)]
    if stock_etfs and bond_etfs:
        for stock_w in [0.5, 0.6, 0.7]:
            # Use best performing stock ETF
            for stock_sym in stock_etfs[:3]:
                pair_data = {stock_sym: all_data[stock_sym], bond_etfs[0]: all_data[bond_etfs[0]]}
                strategy = BalanceStrategy(
                    stock_symbol=stock_sym,
                    bond_symbol=bond_etfs[0],
                    stock_weight=stock_w,
                    drift_threshold=0.08,
                )
                result = run_backtest(pair_data, strategy, config)
                metrics = summary(result)
                score = _score_strategy(metrics)

                from config.constants import DEFAULT_ETF_LIST

                stock_name = next(
                    (e["name"] for e in DEFAULT_ETF_LIST if e["symbol"] == stock_sym),
                    stock_sym,
                )
                rec = StrategyRecommendation(
                    strategy_name=(
                        f"股债平衡 ({stock_name} "
                        f"{int(stock_w * 100)}%/债{int((1 - stock_w) * 100)}%)"
                    ),
                    strategy_id="balance",
                    symbols=[stock_sym, bond_etfs[0]],
                    params={
                        "stock_symbol": stock_sym,
                        "bond_symbol": bond_etfs[0],
                        "stock_weight": stock_w,
                    },
                    metrics=metrics,
                    rank=0,
                    recommendation=_build_recommendation("balance", metrics, capital, 2, stock_w),
                )
                candidates.append((score, rec))

    # ── Strategy 3: MultiFactor ───────────────────────
    for mom_w, val_w, vol_w in [(0.5, 0.3, 0.2), (0.3, 0.4, 0.3), (0.7, 0.2, 0.1)]:
        strategy = MultiFactorStrategy(
            lookback=20,
            top_k=3,
            rebalance_days=20,
            momentum_weight=mom_w,
            value_weight=val_w,
            volatility_weight=vol_w,
        )
        result = run_backtest(all_data, strategy, config)
        metrics = summary(result)
        score = _score_strategy(metrics)

        label = f"多因子 (动量{int(mom_w * 100)}%+价值{int(val_w * 100)}%+波动{int(vol_w * 100)}%)"
        rec = StrategyRecommendation(
            strategy_name=label,
            strategy_id="multifactor",
            symbols=symbols,
            params={"momentum_weight": mom_w, "value_weight": val_w, "volatility_weight": vol_w},
            metrics=metrics,
            rank=0,
            recommendation=_build_recommendation("multifactor", metrics, capital, 3),
        )
        candidates.append((score, rec))

    # ── Rank and return top N ─────────────────────────
    candidates.sort(key=lambda x: x[0], reverse=True)

    results = []
    for rank, (_score, rec) in enumerate(candidates[:max_results], 1):
        results.append(
            StrategyRecommendation(
                strategy_name=rec.strategy_name,
                strategy_id=rec.strategy_id,
                symbols=rec.symbols,
                params=rec.params,
                metrics=rec.metrics,
                rank=rank,
                recommendation=rec.recommendation,
            )
        )

    return results


def _build_recommendation(
    strategy_id: str,
    metrics: dict,
    capital: float,
    positions: int,
    stock_weight: float = 0.0,
) -> str:
    """Build human-readable recommendation text."""
    ret = metrics.get("total_return", 0)
    mdd = metrics.get("max_drawdown", 0)
    trades = metrics.get("total_trades", 0)

    per_position = capital / positions if positions > 0 else capital

    parts = [f"投入¥{capital:.0f}"]

    if strategy_id == "balance":
        stock_amt = capital * stock_weight
        bond_amt = capital * (1 - stock_weight)
        parts.append(f"股票ETF ¥{stock_amt:.0f} + 债券ETF ¥{bond_amt:.0f}")
    else:
        parts.append(f"每只ETF约¥{per_position:.0f}")

    if ret > 0:
        parts.append(f"历史回测收益{ret:+.1%}")
    else:
        parts.append(f"历史回测收益{ret:+.1%}（注意风险）")

    parts.append(f"最大回撤{mdd:.1%}")
    parts.append(f"共{trades}笔交易")

    return " | ".join(parts)
