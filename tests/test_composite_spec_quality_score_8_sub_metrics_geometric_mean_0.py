"""Tests for composite_spec_quality_score_8_sub_metrics_geometric_mean_0."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob3.composite_spec_quality_score_8_sub_metrics_geometric_mean_0 import (
    SUB_METRIC_WEIGHTS,
    composite_spec_quality_score_8_sub_metrics_geometric_mean_0,
)

_ALL_METRICS_HIGH = {
    "smell_density": 0.9,
    "predicate_coverage": 0.9,
    "contract_completeness": 0.9,
    "boundary_coverage": 0.9,
    "error_path_coverage": 0.9,
    "traceability": 0.9,
    "spec_executability": 0.9,
    "ac_atomicity": 0.9,
}

_ALL_METRICS_ONE = {k: 1.0 for k in SUB_METRIC_WEIGHTS}


def test_composite_spec_quality_score_8_sub_metrics_geometric_mean_0():
    """Core AC test: function exists and computes 8-sub-metric geometric mean with 0.65/0.80 gates."""
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0(_ALL_METRICS_HIGH)

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "score" in result, "Result must contain 'score' key"
    assert "gate" in result, "Result must contain 'gate' key"
    assert isinstance(result["score"], float), f"Expected float score, got {type(result['score'])}"
    assert 0.0 <= result["score"] <= 1.0, f"Score {result['score']} not in [0, 1]"
    assert result["gate"] in ("green", "warn", "refuse"), f"Unexpected gate value: {result['gate']!r}"


def test_gate_green_above_0_80():
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0(_ALL_METRICS_ONE)
    assert result["score"] == pytest.approx(1.0, abs=1e-6)
    assert result["gate"] == "green"


def test_gate_warn_between_0_65_and_0_80():
    metrics = {k: 0.72 for k in SUB_METRIC_WEIGHTS}
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0(metrics)
    assert result["score"] == pytest.approx(0.72, abs=1e-5)
    assert 0.65 <= result["score"] < 0.80
    assert result["gate"] == "warn"


def test_gate_refuse_below_0_65():
    metrics = {k: 0.5 for k in SUB_METRIC_WEIGHTS}
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0(metrics)
    assert result["score"] == pytest.approx(0.5, abs=1e-5)
    assert result["score"] < 0.65
    assert result["gate"] == "refuse"


def test_weights_sum_to_one():
    total = sum(SUB_METRIC_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


def test_all_eight_metrics_present_in_weights():
    expected = {
        "smell_density", "predicate_coverage", "contract_completeness",
        "boundary_coverage", "error_path_coverage", "traceability",
        "spec_executability", "ac_atomicity",
    }
    assert set(SUB_METRIC_WEIGHTS.keys()) == expected


def test_correct_weights_per_spec():
    assert SUB_METRIC_WEIGHTS["smell_density"] == pytest.approx(0.20)
    assert SUB_METRIC_WEIGHTS["predicate_coverage"] == pytest.approx(0.20)
    assert SUB_METRIC_WEIGHTS["contract_completeness"] == pytest.approx(0.15)
    assert SUB_METRIC_WEIGHTS["boundary_coverage"] == pytest.approx(0.10)
    assert SUB_METRIC_WEIGHTS["error_path_coverage"] == pytest.approx(0.10)
    assert SUB_METRIC_WEIGHTS["traceability"] == pytest.approx(0.10)
    assert SUB_METRIC_WEIGHTS["spec_executability"] == pytest.approx(0.10)
    assert SUB_METRIC_WEIGHTS["ac_atomicity"] == pytest.approx(0.05)


def test_geometric_mean_not_arithmetic():
    metrics = {k: 1.0 for k in SUB_METRIC_WEIGHTS}
    metrics["smell_density"] = 0.01
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0(metrics)
    assert result["score"] < 0.80, "Low metric should drag score below arithmetic mean result"


def test_zero_metric_yields_zero_score():
    metrics = {k: 1.0 for k in SUB_METRIC_WEIGHTS}
    metrics["smell_density"] = 0.0
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0(metrics)
    assert result["score"] == pytest.approx(0.0, abs=1e-9)
    assert result["gate"] == "refuse"


def test_missing_metric_raises():
    metrics = {"smell_density": 0.9, "predicate_coverage": 0.9}
    with pytest.raises((ValueError, KeyError)):
        composite_spec_quality_score_8_sub_metrics_geometric_mean_0(metrics)


def test_score_clamped_to_unit_interval():
    metrics = {k: 1.5 for k in SUB_METRIC_WEIGHTS}
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0(metrics)
    assert result["score"] <= 1.0


def test_boundary_exactly_0_65_is_warn():
    metrics = {k: 0.65 for k in SUB_METRIC_WEIGHTS}
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0(metrics)
    assert result["score"] == pytest.approx(0.65, abs=1e-5)
    assert result["gate"] == "warn"


def test_boundary_exactly_0_80_is_green():
    metrics = {k: 0.80 for k in SUB_METRIC_WEIGHTS}
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0(metrics)
    assert result["score"] == pytest.approx(0.80, abs=1e-5)
    assert result["gate"] == "green"
