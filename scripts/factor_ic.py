"""Factor IC (Information Coefficient) evaluation.

Computes rank IC between each factor and forward returns across all ETFs.
IC = Spearman correlation between factor value and next-day / next-5-day return.

A factor is useful if |IC| > 0.02 and stable across time.

Usage:
    PYTHONPATH=. uv run python scripts/factor_ic.py
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy import stats

from data.storage.parquet_store import load_hist
from factors.flow import compute_flow_factors
from factors.momentum import compute_momentum_factors
from factors.value import compute_value_factors
from factors.volatility import compute_volatility_factors

logging.basicConfig(level=logging.WARNING)

SYMBOLS = [
    "510300",
    "518880",
    "511010",
    "512480",
    "513100",
    "510500",
    "159915",
    "515220",
    "512880",
    "562800",
    "159819",
    "515030",
    "159611",
    "159866",
    "159869",
    "159870",
]

# OHLCV base columns to exclude from IC calculation
BASE_COLS = {"open", "high", "low", "close", "volume", "amount", "turnover"}


def compute_all_factors(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all factor families to a single-symbol DataFrame."""
    result = compute_momentum_factors(df)
    result = compute_value_factors(result)
    result = compute_volatility_factors(result)
    result = compute_flow_factors(result)
    return result


def calc_ic_series(
    factor_values: pd.Series,
    forward_returns: pd.Series,
) -> float:
    """Compute rank IC (Spearman) between factor and forward return."""
    mask = factor_values.notna() & forward_returns.notna()
    fv = factor_values[mask]
    fr = forward_returns[mask]
    if len(fv) < 30:
        return float("nan")
    corr, _ = stats.spearmanr(fv, fr)
    return float(corr)


def evaluate_factors() -> pd.DataFrame:
    """Evaluate factors using time-series IC per symbol, then average.

    For each symbol: IC = Spearman(factor[t], return[t+1]) over all dates.
    Then average IC across symbols for a pooled estimate.
    """
    print("Loading and computing factors for all symbols...")

    symbol_data: dict[str, pd.DataFrame] = {}
    factor_cols: list[str] | None = None

    for sym in SYMBOLS:
        df = load_hist(sym)
        if df.empty or len(df) < 120:
            continue

        enriched = compute_all_factors(df)
        enriched["fwd_ret_1d"] = enriched["close"].pct_change().shift(-1)
        enriched["fwd_ret_5d"] = enriched["close"].shift(-5) / enriched["close"] - 1

        symbol_data[sym] = enriched

        if factor_cols is None:
            factor_cols = [
                c
                for c in enriched.columns
                if c not in BASE_COLS
                and c not in {"fwd_ret_1d", "fwd_ret_5d", "symbol"}
                and not c.startswith("fwd_")
            ]

    if not symbol_data or factor_cols is None:
        print("No data loaded!")
        return pd.DataFrame()

    print(f"Evaluating {len(factor_cols)} factors across {len(symbol_data)} symbols...")

    results = []
    for factor_name in sorted(factor_cols):
        ics_1d: list[float] = []
        ics_5d: list[float] = []

        for _sym, enriched in symbol_data.items():
            if factor_name not in enriched.columns:
                continue

            ic1 = calc_ic_series(enriched[factor_name], enriched["fwd_ret_1d"])
            ic5 = calc_ic_series(enriched[factor_name], enriched["fwd_ret_5d"])

            if not np.isnan(ic1):
                ics_1d.append(ic1)
            if not np.isnan(ic5):
                ics_5d.append(ic5)

        if not ics_1d:
            continue

        mean_ic_1d = float(np.mean(ics_1d))
        mean_ic_5d = float(np.mean(ics_5d)) if ics_5d else 0.0
        ic_std = float(np.std(ics_1d)) if len(ics_1d) > 1 else 0.0
        ir = mean_ic_1d / ic_std if ic_std > 0 else 0.0

        if abs(mean_ic_1d) >= 0.03 and abs(ir) >= 0.3:
            verdict = "STRONG"
        elif abs(mean_ic_1d) >= 0.02:
            verdict = "USEFUL"
        elif abs(mean_ic_1d) < 0.01:
            verdict = "WEAK"
        else:
            verdict = "MARGINAL"

        results.append(
            {
                "factor": factor_name,
                "ic_1d": round(mean_ic_1d, 4),
                "ic_5d": round(mean_ic_5d, 4),
                "ic_std": round(ic_std, 4),
                "ir": round(ir, 2),
                "n_symbols": len(ics_1d),
                "verdict": verdict,
            }
        )

    if not results:
        return pd.DataFrame()

    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values("ic_1d", key=abs, ascending=False)
    return df_results


def save_ic_results(results: pd.DataFrame) -> None:
    """Persist IC results to data_store/factor_ic_history/."""
    import json
    from datetime import date
    from pathlib import Path

    out_dir = Path("data_store/factor_ic_history")
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    records = results.to_dict(orient="records")

    out_path = out_dir / f"{today}.json"
    out_path.write_text(
        json.dumps({"date": today, "factors": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Also write latest.json for quick access
    latest_path = out_dir / "latest.json"
    latest_path.write_text(
        json.dumps({"date": today, "factors": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n  IC results saved to {out_path}")


def main() -> None:
    print("═" * 60)
    print("  Factor IC Evaluation — ETF Quant Platform")
    print("═" * 60)

    results = evaluate_factors()

    if results.empty:
        print("No results.")
        return

    save_ic_results(results)

    header = (
        f"  {'Factor':<22} {'IC1d':>7} {'IC5d':>7} {'Std':>7} {'IR':>6} {'N':>4} {'Verdict':>8}"
    )
    print(f"\n{'─' * 68}")
    print(header)
    print(f"{'─' * 68}")

    for _, row in results.iterrows():
        tag = " **" if row["verdict"] == "STRONG" else ""
        tag = " x" if row["verdict"] == "WEAK" else tag

        line = (
            f"  {row['factor']:<22} {row['ic_1d']:>7.4f}"
            f" {row['ic_5d']:>7.4f} {row['ic_std']:>7.4f}"
            f" {row['ir']:>6.2f} {row['n_symbols']:>4}"
            f" {row['verdict']:>8}{tag}"
        )
        print(line)

    # Summary
    strong = results[results["verdict"] == "STRONG"]
    useful = results[results["verdict"].isin(["STRONG", "USEFUL"])]
    weak = results[results["verdict"] == "WEAK"]

    print(f"\n{'═' * 60}")
    print(f"  Summary: {len(strong)} strong, {len(useful)} useful, {len(weak)} weak factors")
    if len(weak) > 0:
        print(f"  Weak factors (IC < 0.01): {', '.join(weak['factor'].tolist())}")
        print("  → Consider removing these from signal engine")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
