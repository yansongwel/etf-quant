"""Tests for param_sweep script utilities."""

from __future__ import annotations

from scripts.param_sweep import (
    SweepResult,
    _check_overfit,
    _filter_weights,
    _top_by_sharpe,
    export_best,
)


class TestCheckOverfit:
    def test_passes_when_params_less_than_sqrt(self) -> None:
        assert _check_overfit(3, 100) is True  # 3 < sqrt(100) = 10

    def test_fails_when_params_exceed_sqrt(self) -> None:
        assert _check_overfit(11, 100) is False  # 11 > sqrt(100) = 10

    def test_edge_case_equal(self) -> None:
        assert _check_overfit(10, 100) is False  # 10 == sqrt(100), not strictly less


class TestFilterWeights:
    def test_keeps_weights_summing_to_one(self) -> None:
        combos = [
            {"momentum_weight": 0.5, "value_weight": 0.3, "volatility_weight": 0.2},
            {"momentum_weight": 0.4, "value_weight": 0.3, "volatility_weight": 0.3},
        ]
        result = _filter_weights(combos)
        assert len(result) == 2

    def test_filters_weights_not_summing_to_one(self) -> None:
        combos = [
            {"momentum_weight": 0.5, "value_weight": 0.3, "volatility_weight": 0.3},  # sum=1.1
            {"momentum_weight": 0.2, "value_weight": 0.2, "volatility_weight": 0.2},  # sum=0.6
        ]
        result = _filter_weights(combos)
        assert len(result) == 0

    def test_empty_input(self) -> None:
        assert _filter_weights([]) == []


class TestTopBySharpe:
    def _make_result(self, sharpe: float) -> SweepResult:
        return SweepResult(
            strategy="test",
            params={},
            total_return=0.0,
            annualized_return=0.0,
            sharpe_ratio=sharpe,
            max_drawdown=0.0,
            total_trades=0,
            param_count=3,
        )

    def test_returns_top_n(self) -> None:
        results = [self._make_result(s) for s in [0.5, 1.2, 0.8, 0.3, 1.5, 0.9]]
        top = _top_by_sharpe(results, 3)
        assert len(top) == 3
        assert top[0].sharpe_ratio == 1.5
        assert top[1].sharpe_ratio == 1.2
        assert top[2].sharpe_ratio == 0.9

    def test_returns_all_if_fewer_than_n(self) -> None:
        results = [self._make_result(0.5), self._make_result(1.0)]
        top = _top_by_sharpe(results, 5)
        assert len(top) == 2

    def test_empty_results(self) -> None:
        assert _top_by_sharpe([], 5) == []


class TestExportBest:
    def test_exports_best_per_strategy(self) -> None:
        r1 = SweepResult(
            strategy="rotation",
            params={"lookback": 10, "top_k": 1},
            total_return=1.5,
            annualized_return=0.25,
            sharpe_ratio=0.8,
            max_drawdown=0.3,
            total_trades=50,
            param_count=3,
        )
        r2 = SweepResult(
            strategy="rotation",
            params={"lookback": 20, "top_k": 2},
            total_return=1.2,
            annualized_return=0.18,
            sharpe_ratio=0.6,
            max_drawdown=0.25,
            total_trades=30,
            param_count=3,
        )
        output = export_best({"rotation": [r1, r2]})
        assert "rotation" in output
        assert output["rotation"]["sharpe"] == 0.8
        assert output["rotation"]["params"]["lookback"] == 10

    def test_skips_empty_strategies(self) -> None:
        output = export_best({"rotation": [], "multifactor": []})
        assert output == {}
