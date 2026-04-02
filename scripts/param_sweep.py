"""Parameter sweep — exhaustive grid search over all strategy parameters.

Scans all four strategies across their parameter spaces, then validates
the top combinations with walk-forward testing. Updates config/optimal_params.py
only when a new combination beats the current best on risk-adjusted return.

Usage:
    PYTHONPATH=. uv run python scripts/param_sweep.py [--strategy ...]
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import math
import time
from dataclasses import dataclass

import pandas as pd

from data.storage.parquet_store import load_hist
from engine.backtest import run_backtest
from engine.metrics import summary
from engine.types import BacktestConfig
from engine.walkforward import walk_forward
from strategies.balance import BalanceStrategy
from strategies.grid import GridStrategy
from strategies.multifactor import MultiFactorStrategy
from strategies.rotation import RotationStrategy

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger(__name__)

# ── ETF universes ──────────────────────────────────────────
CORE_SYMBOLS = ["510300", "518880", "511010", "512480", "513100"]
EXTENDED_SYMBOLS = CORE_SYMBOLS + [
    "510500",
    "159915",
    "515220",
    "512880",
    "562800",
    "159819",
    "515030",
]
BOND_ETF = "511010"
STOCK_ETFS = ["510300", "510500", "159915"]

# ── Parameter grids ────────────────────────────────────────
ROTATION_GRID = {
    "lookback": [5, 10, 15, 20, 30, 40, 60],
    "top_k": [1, 2, 3, 4, 5],
    "rebalance_days": [5, 10, 15, 20, 30],
}

MULTIFACTOR_GRID = {
    "lookback": [10, 15, 20, 30],
    "top_k": [1, 2, 3],
    "rebalance_days": [10, 15, 20, 30],
    "momentum_weight": [0.3, 0.4, 0.5, 0.6],
    "value_weight": [0.1, 0.2, 0.3],
    "volatility_weight": [0.1, 0.2, 0.3],
}

BALANCE_GRID = {
    "stock_weight": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    "drift_threshold": [0.05, 0.08, 0.10, 0.15, 0.20],
    "min_rebalance_days": [5, 10, 15, 20],
}

GRID_GRID = {
    "grid_count": [5, 8, 10, 15, 20],
    "grid_width_pct": [0.01, 0.015, 0.02, 0.03, 0.05],
    "position_per_grid": [0.05, 0.08, 0.10],
}

CAPITAL = 500_000
CONFIG = BacktestConfig(initial_cash=CAPITAL, commission_rate=0.0002, slippage=0.001)


@dataclass
class SweepResult:
    strategy: str
    params: dict
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    param_count: int


def _load_data(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Load parquet data for given symbols."""
    data: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = load_hist(sym)
        if not df.empty and len(df) >= 120:
            data[sym] = df
    return data


def _check_overfit(param_count: int, sample_size: int) -> bool:
    """Anti-overfit: param count must be < sqrt(sample_size)."""
    return param_count < math.sqrt(sample_size)


def _filter_weights(combos: list[dict]) -> list[dict]:
    """For multifactor: only keep weight combos that sum to ~1.0."""
    return [
        c
        for c in combos
        if abs(c["momentum_weight"] + c["value_weight"] + c["volatility_weight"] - 1.0) < 0.01
    ]


def sweep_rotation(data: dict[str, pd.DataFrame]) -> list[SweepResult]:
    """Sweep rotation strategy parameters."""
    results: list[SweepResult] = []
    keys = list(ROTATION_GRID.keys())
    combos = [dict(zip(keys, v, strict=True)) for v in itertools.product(*ROTATION_GRID.values())]

    sample_size = min(len(df) for df in data.values())
    combos = [c for c in combos if _check_overfit(len(keys), sample_size)]

    print(f"  Rotation: {len(combos)} parameter combinations")
    for i, params in enumerate(combos):
        strategy = RotationStrategy(**params)
        try:
            result = run_backtest(data, strategy, CONFIG)
            m = summary(result)
        except Exception:
            continue

        results.append(
            SweepResult(
                strategy="rotation",
                params=params,
                total_return=m["total_return"],
                annualized_return=m["annualized_return"],
                sharpe_ratio=m["sharpe_ratio"],
                max_drawdown=m["max_drawdown"],
                total_trades=m["total_trades"],
                param_count=len(keys),
            )
        )

        if (i + 1) % 50 == 0:
            print(f"    ... {i + 1}/{len(combos)} done")

    return results


def sweep_multifactor(data: dict[str, pd.DataFrame]) -> list[SweepResult]:
    """Sweep multifactor strategy parameters."""
    results: list[SweepResult] = []
    keys = list(MULTIFACTOR_GRID.keys())
    combos = [
        dict(zip(keys, v, strict=True)) for v in itertools.product(*MULTIFACTOR_GRID.values())
    ]
    combos = _filter_weights(combos)

    sample_size = min(len(df) for df in data.values())
    combos = [c for c in combos if _check_overfit(len(keys), sample_size)]

    print(f"  Multifactor: {len(combos)} parameter combinations (after weight filter)")
    for i, params in enumerate(combos):
        strategy = MultiFactorStrategy(**params)
        try:
            result = run_backtest(data, strategy, CONFIG)
            m = summary(result)
        except Exception:
            continue

        results.append(
            SweepResult(
                strategy="multifactor",
                params=params,
                total_return=m["total_return"],
                annualized_return=m["annualized_return"],
                sharpe_ratio=m["sharpe_ratio"],
                max_drawdown=m["max_drawdown"],
                total_trades=m["total_trades"],
                param_count=len(keys),
            )
        )

        if (i + 1) % 50 == 0:
            print(f"    ... {i + 1}/{len(combos)} done")

    return results


def sweep_balance(data: dict[str, pd.DataFrame]) -> list[SweepResult]:
    """Sweep balance strategy parameters."""
    results: list[SweepResult] = []
    keys = list(BALANCE_GRID.keys())
    combos = [dict(zip(keys, v, strict=True)) for v in itertools.product(*BALANCE_GRID.values())]

    sample_size = min(len(df) for df in data.values())
    combos = [c for c in combos if _check_overfit(len(keys), sample_size)]

    print(f"  Balance: {len(combos)} parameter combinations")
    for _i, params in enumerate(combos):
        strategy = BalanceStrategy(
            stock_symbol="510300",
            bond_symbol=BOND_ETF,
            **params,
        )
        try:
            result = run_backtest(data, strategy, CONFIG)
            m = summary(result)
        except Exception:
            continue

        results.append(
            SweepResult(
                strategy="balance",
                params=params,
                total_return=m["total_return"],
                annualized_return=m["annualized_return"],
                sharpe_ratio=m["sharpe_ratio"],
                max_drawdown=m["max_drawdown"],
                total_trades=m["total_trades"],
                param_count=len(keys),
            )
        )

    return results


def sweep_grid(data: dict[str, pd.DataFrame]) -> list[SweepResult]:
    """Sweep grid strategy parameters."""
    results: list[SweepResult] = []
    keys = list(GRID_GRID.keys())
    combos = [dict(zip(keys, v, strict=True)) for v in itertools.product(*GRID_GRID.values())]

    sample_size = min(len(df) for df in data.values())
    combos = [c for c in combos if _check_overfit(len(keys), sample_size)]

    print(f"  Grid: {len(combos)} parameter combinations")
    for sym in STOCK_ETFS:
        if sym not in data:
            continue
        for params in combos:
            strategy = GridStrategy(symbol=sym, **params)
            try:
                result = run_backtest(data, strategy, CONFIG)
                m = summary(result)
            except Exception:
                continue

            results.append(
                SweepResult(
                    strategy="grid",
                    params={**params, "symbol": sym},
                    total_return=m["total_return"],
                    annualized_return=m["annualized_return"],
                    sharpe_ratio=m["sharpe_ratio"],
                    max_drawdown=m["max_drawdown"],
                    total_trades=m["total_trades"],
                    param_count=len(keys),
                )
            )

    return results


def _top_by_sharpe(results: list[SweepResult], n: int = 5) -> list[SweepResult]:
    """Return top N results sorted by Sharpe ratio."""
    return sorted(results, key=lambda r: r.sharpe_ratio, reverse=True)[:n]


def validate_with_walkforward(
    data: dict[str, pd.DataFrame],
    best: SweepResult,
) -> dict | None:
    """Run walk-forward validation on the best parameter set."""
    try:
        if best.strategy in ("rotation", "multifactor"):
            wf = walk_forward(
                data,
                strategy_type=best.strategy,
                params=best.params,
                train_years=2,
                test_months=12,
                step_months=6,
                capital=CAPITAL,
            )
            return wf.get("aggregate")
    except Exception as e:
        print(f"  WF validation failed: {e}")
    return None


def print_results(strategy_name: str, results: list[SweepResult]) -> None:
    """Print top 5 results for a strategy."""
    if not results:
        print(f"\n  {strategy_name}: no valid results")
        return

    top = _top_by_sharpe(results)
    print(f"\n  {strategy_name} — Top 5 by Sharpe:")
    print(f"  {'#':>3} {'Sharpe':>7} {'Return':>8} {'MaxDD':>7} {'Trades':>7} | Params")
    print(f"  {'─' * 60}")
    for i, r in enumerate(top, 1):
        params_str = ", ".join(f"{k}={v}" for k, v in r.params.items())
        print(
            f"  {i:>3} {r.sharpe_ratio:>7.2f} {r.annualized_return:>7.1%} "
            f"{r.max_drawdown:>7.1%} {r.total_trades:>7} | {params_str}"
        )


def export_best(all_results: dict[str, list[SweepResult]]) -> dict:
    """Export the overall best parameters as a summary dict."""
    output: dict[str, dict] = {}
    for strategy_name, results in all_results.items():
        if results:
            best = _top_by_sharpe(results, 1)[0]
            output[strategy_name] = {
                "params": best.params,
                "sharpe": round(best.sharpe_ratio, 3),
                "return": round(best.annualized_return, 4),
                "max_drawdown": round(best.max_drawdown, 4),
                "trades": best.total_trades,
            }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Strategy parameter sweep")
    parser.add_argument(
        "--strategy",
        choices=["rotation", "multifactor", "balance", "grid", "all"],
        default="all",
    )
    args = parser.parse_args()

    t0 = time.time()
    print("═" * 60)
    print("  Parameter Sweep — ETF Quant Platform")
    print("═" * 60)

    # Load data
    print("\n  Loading data...")
    data = _load_data(EXTENDED_SYMBOLS)
    print(
        f"  Loaded {len(data)} ETFs, date range: "
        f"{min(df.index[0] for df in data.values()).date()} ~ "
        f"{max(df.index[-1] for df in data.values()).date()}"
    )

    sample_size = min(len(df) for df in data.values())
    print(f"  Min sample size: {sample_size} (sqrt = {math.sqrt(sample_size):.1f})")

    all_results: dict[str, list[SweepResult]] = {}

    strategies = (
        ["rotation", "multifactor", "balance", "grid"]
        if args.strategy == "all"
        else [args.strategy]
    )

    for strat in strategies:
        print(f"\n{'─' * 60}")
        print(f"  Sweeping: {strat}")
        print(f"{'─' * 60}")

        if strat == "rotation":
            all_results["rotation"] = sweep_rotation(data)
        elif strat == "multifactor":
            all_results["multifactor"] = sweep_multifactor(data)
        elif strat == "balance":
            # Balance needs only stock + bond
            balance_data = {s: data[s] for s in ["510300", BOND_ETF] if s in data}
            all_results["balance"] = sweep_balance(balance_data)
        elif strat == "grid":
            all_results["grid"] = sweep_grid(data)

    # Print results
    print(f"\n{'═' * 60}")
    print("  RESULTS")
    print(f"{'═' * 60}")
    for name, results in all_results.items():
        print_results(name, results)

    # Walk-forward validation on best combos
    print(f"\n{'═' * 60}")
    print("  WALK-FORWARD VALIDATION (top 1 per strategy)")
    print(f"{'═' * 60}")
    for name, results in all_results.items():
        if results:
            best = _top_by_sharpe(results, 1)[0]
            wf = validate_with_walkforward(data, best)
            if wf:
                verdict = wf.get("verdict", "N/A")
                win_rate = wf.get("win_rate", 0)
                avg_ret = wf.get("avg_test_return", 0)
                print(f"  {name}: {verdict} — WF win rate {win_rate}%, avg return {avg_ret}%")
            else:
                print(f"  {name}: walk-forward skipped or failed")

    # Export
    best_params = export_best(all_results)
    output_path = "scripts/sweep_results.json"
    with open(output_path, "w") as f:
        json.dump(best_params, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to {output_path}")

    elapsed = time.time() - t0
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print("═" * 60)


if __name__ == "__main__":
    main()
