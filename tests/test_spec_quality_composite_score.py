"""Tests for spec_quality.composite_score — weighted geometric mean and gate logic."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spec_quality.composite_score import (
    SUB_METRIC_WEIGHTS,
    calculate_geometric_mean,
    compute_spec_quality_score,
)

_ALL_HIGH = {k: 0.9 for k in SUB_METRIC_WEIGHTS}
_ALL_ONE = {k: 1.0 for k in SUB_METRIC_WEIGHTS}
_ALL_HALF = {k: 0.5 for k in SUB_METRIC_WEIGHTS}


class TestCalculateGeometricMean:
    def test_uniform_values_return_same_value(self):
        result = calculate_geometric_mean({k: 0.9 for k in SUB_METRIC_WEIGHTS}, SUB_METRIC_WEIGHTS)
        assert result == pytest.approx(0.9, abs=1e-6)

    def test_all_ones_returns_one(self):
        result = calculate_geometric_mean(_ALL_ONE, SUB_METRIC_WEIGHTS)
        assert result == pytest.approx(1.0, abs=1e-9)

    def test_zero_value_returns_zero(self):
        values = dict(_ALL_ONE)
        values["smell_density"] = 0.0
        result = calculate_geometric_mean(values, SUB_METRIC_WEIGHTS)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_low_value_dominates_over_arithmetic_mean(self):
        values = dict(_ALL_ONE)
        values["smell_density"] = 0.01
        result = calculate_geometric_mean(values, SUB_METRIC_WEIGHTS)
        # arithmetic mean would be 0.20*0.01 + 0.80*1.0 = 0.802
        assert result < 0.80

    def test_empty_values_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            calculate_geometric_mean({}, SUB_METRIC_WEIGHTS)

    def test_empty_weights_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            calculate_geometric_mean({"a": 0.5}, {})

    def test_missing_weight_raises_value_error(self):
        with pytest.raises(ValueError):
            calculate_geometric_mean({"unknown_metric": 0.5}, SUB_METRIC_WEIGHTS)

    def test_clamped_above_one(self):
        values = {k: 2.0 for k in SUB_METRIC_WEIGHTS}
        result = calculate_geometric_mean(values, SUB_METRIC_WEIGHTS)
        assert result <= 1.0

    def test_weights_sum_to_one(self):
        total = sum(SUB_METRIC_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9


class TestComputeSpecQualityScore:
    def test_returns_dict_with_score_and_gate(self):
        result = compute_spec_quality_score(_ALL_HIGH)
        assert isinstance(result, dict)
        assert "score" in result
        assert "gate" in result

    def test_score_is_float_in_unit_interval(self):
        result = compute_spec_quality_score(_ALL_HIGH)
        assert isinstance(result["score"], float)
        assert 0.0 <= result["score"] <= 1.0

    def test_gate_values_are_valid(self):
        result = compute_spec_quality_score(_ALL_HIGH)
        assert result["gate"] in ("green", "warn", "refuse")

    def test_all_ones_gives_green(self):
        result = compute_spec_quality_score(_ALL_ONE)
        assert result["score"] == pytest.approx(1.0, abs=1e-6)
        assert result["gate"] == "green"

    def test_all_half_gives_refuse(self):
        result = compute_spec_quality_score(_ALL_HALF)
        assert result["score"] == pytest.approx(0.5, abs=1e-5)
        assert result["gate"] == "refuse"

    def test_boundary_exactly_0_65_is_warn(self):
        metrics = {k: 0.65 for k in SUB_METRIC_WEIGHTS}
        result = compute_spec_quality_score(metrics)
        assert result["score"] == pytest.approx(0.65, abs=1e-5)
        assert result["gate"] == "warn"

    def test_boundary_exactly_0_80_is_green(self):
        metrics = {k: 0.80 for k in SUB_METRIC_WEIGHTS}
        result = compute_spec_quality_score(metrics)
        assert result["score"] == pytest.approx(0.80, abs=1e-5)
        assert result["gate"] == "green"

    def test_score_in_warn_range(self):
        metrics = {k: 0.72 for k in SUB_METRIC_WEIGHTS}
        result = compute_spec_quality_score(metrics)
        assert 0.65 <= result["score"] < 0.80
        assert result["gate"] == "warn"

    def test_correct_weights(self):
        assert SUB_METRIC_WEIGHTS["smell_density"] == pytest.approx(0.20)
        assert SUB_METRIC_WEIGHTS["predicate_coverage"] == pytest.approx(0.20)
        assert SUB_METRIC_WEIGHTS["contract_completeness"] == pytest.approx(0.15)
        assert SUB_METRIC_WEIGHTS["boundary_coverage"] == pytest.approx(0.10)
        assert SUB_METRIC_WEIGHTS["error_path_coverage"] == pytest.approx(0.10)
        assert SUB_METRIC_WEIGHTS["traceability"] == pytest.approx(0.10)
        assert SUB_METRIC_WEIGHTS["spec_executability"] == pytest.approx(0.10)
        assert SUB_METRIC_WEIGHTS["ac_atomicity"] == pytest.approx(0.05)

    def test_all_eight_metric_keys_present(self):
        expected = {
            "smell_density", "predicate_coverage", "contract_completeness",
            "boundary_coverage", "error_path_coverage", "traceability",
            "spec_executability", "ac_atomicity",
        }
        assert set(SUB_METRIC_WEIGHTS.keys()) == expected

    def test_extra_keys_ignored(self):
        metrics = dict(_ALL_HIGH)
        metrics["extra_unknown_key"] = 0.99
        result = compute_spec_quality_score(metrics)
        assert "score" in result

    def test_missing_metric_raises_value_error(self):
        metrics = {"smell_density": 0.9, "predicate_coverage": 0.9}
        with pytest.raises(ValueError):
            compute_spec_quality_score(metrics)

    def test_geometric_mean_not_arithmetic(self):
        metrics = dict(_ALL_ONE)
        metrics["smell_density"] = 0.01
        result = compute_spec_quality_score(metrics)
        assert result["score"] < 0.80
