"""Tests for composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob3.composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate import (
    composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate,
)


def test_composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate():
    """Core AC test: function exists and computes 8-sub-metric geometric mean with 0.65/0.80 gates."""
    metrics = {
        "smell_density": 0.9,
        "predicate_coverage": 0.9,
        "contract_completeness": 0.9,
        "boundary_coverage": 0.9,
        "error_path_coverage": 0.9,
        "traceability": 0.9,
        "spec_executability": 0.9,
        "ac_atomicity": 0.9,
    }

    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate(metrics)

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "score" in result, "Result must contain 'score' key"
    assert "gate" in result, "Result must contain 'gate' key"
    assert isinstance(result["score"], float), f"Expected float score, got {type(result['score'])}"
    assert 0.0 <= result["score"] <= 1.0, f"Score {result['score']} not in [0, 1]"
    assert result["gate"] in ("green", "warn", "refuse"), f"Unexpected gate value: {result['gate']!r}"


def test_gate_green_above_0_80():
    """Score >= 0.80 should yield gate='green'."""
    metrics = {
        "smell_density": 1.0,
        "predicate_coverage": 1.0,
        "contract_completeness": 1.0,
        "boundary_coverage": 1.0,
        "error_path_coverage": 1.0,
        "traceability": 1.0,
        "spec_executability": 1.0,
        "ac_atomicity": 1.0,
    }
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate(metrics)
    assert result["score"] == pytest.approx(1.0, abs=1e-6)
    assert result["gate"] == "green"


def test_gate_warn_between_0_65_and_0_80():
    """Score in [0.65, 0.80) should yield gate='warn'."""
    # Use values that produce geometric mean around 0.71
    metrics = {
        "smell_density": 0.72,
        "predicate_coverage": 0.72,
        "contract_completeness": 0.72,
        "boundary_coverage": 0.72,
        "error_path_coverage": 0.72,
        "traceability": 0.72,
        "spec_executability": 0.72,
        "ac_atomicity": 0.72,
    }
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate(metrics)
    assert result["score"] == pytest.approx(0.72, abs=1e-5)
    assert 0.65 <= result["score"] < 0.80
    assert result["gate"] == "warn"


def test_gate_refuse_below_0_65():
    """Score < 0.65 should yield gate='refuse'."""
    metrics = {
        "smell_density": 0.5,
        "predicate_coverage": 0.5,
        "contract_completeness": 0.5,
        "boundary_coverage": 0.5,
        "error_path_coverage": 0.5,
        "traceability": 0.5,
        "spec_executability": 0.5,
        "ac_atomicity": 0.5,
    }
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate(metrics)
    assert result["score"] == pytest.approx(0.5, abs=1e-5)
    assert result["score"] < 0.65
    assert result["gate"] == "refuse"


def test_weights_sum_to_one():
    """The 8 sub-metric weights must sum to 1.0."""
    from bob3.composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate import (
        SUB_METRIC_WEIGHTS,
    )
    total = sum(SUB_METRIC_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


def test_all_eight_metrics_present_in_weights():
    """All 8 specified sub-metrics must have defined weights."""
    from bob3.composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate import (
        SUB_METRIC_WEIGHTS,
    )
    expected_metrics = {
        "smell_density",
        "predicate_coverage",
        "contract_completeness",
        "boundary_coverage",
        "error_path_coverage",
        "traceability",
        "spec_executability",
        "ac_atomicity",
    }
    assert set(SUB_METRIC_WEIGHTS.keys()) == expected_metrics


def test_correct_weights_per_spec():
    """Weights must match spec: smell_density=0.20, predicate_coverage=0.20, etc."""
    from bob3.composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate import (
        SUB_METRIC_WEIGHTS,
    )
    assert SUB_METRIC_WEIGHTS["smell_density"] == pytest.approx(0.20)
    assert SUB_METRIC_WEIGHTS["predicate_coverage"] == pytest.approx(0.20)
    assert SUB_METRIC_WEIGHTS["contract_completeness"] == pytest.approx(0.15)
    assert SUB_METRIC_WEIGHTS["boundary_coverage"] == pytest.approx(0.10)
    assert SUB_METRIC_WEIGHTS["error_path_coverage"] == pytest.approx(0.10)
    assert SUB_METRIC_WEIGHTS["traceability"] == pytest.approx(0.10)
    assert SUB_METRIC_WEIGHTS["spec_executability"] == pytest.approx(0.10)
    assert SUB_METRIC_WEIGHTS["ac_atomicity"] == pytest.approx(0.05)


def test_geometric_mean_not_arithmetic():
    """Geometric mean differs from arithmetic mean for unequal values."""
    # One very low metric brings geometric mean much lower than arithmetic
    metrics = {
        "smell_density": 0.01,
        "predicate_coverage": 1.0,
        "contract_completeness": 1.0,
        "boundary_coverage": 1.0,
        "error_path_coverage": 1.0,
        "traceability": 1.0,
        "spec_executability": 1.0,
        "ac_atomicity": 1.0,
    }
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate(metrics)
    # With weighted geometric mean, one low value (weight 0.20) dominates significantly
    # Arithmetic would give: 0.20*0.01 + 0.80*1.0 = 0.802; geo mean is lower
    assert result["score"] < 0.80, "Low metric should drag score below arithmetic mean result"


def test_zero_metric_yields_zero_score():
    """A zero value for any metric should yield score=0.0."""
    metrics = {
        "smell_density": 0.0,
        "predicate_coverage": 1.0,
        "contract_completeness": 1.0,
        "boundary_coverage": 1.0,
        "error_path_coverage": 1.0,
        "traceability": 1.0,
        "spec_executability": 1.0,
        "ac_atomicity": 1.0,
    }
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate(metrics)
    assert result["score"] == pytest.approx(0.0, abs=1e-9)
    assert result["gate"] == "refuse"


def test_missing_metric_raises():
    """Providing fewer than 8 metrics should raise ValueError."""
    metrics = {
        "smell_density": 0.9,
        "predicate_coverage": 0.9,
        # missing 6 metrics
    }
    with pytest.raises((ValueError, KeyError)):
        composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate(metrics)


def test_score_clamped_to_unit_interval():
    """Score is clamped to [0, 1] even with out-of-range inputs."""
    # Over 1.0 values should be clamped
    metrics = {
        "smell_density": 1.5,
        "predicate_coverage": 1.5,
        "contract_completeness": 1.5,
        "boundary_coverage": 1.5,
        "error_path_coverage": 1.5,
        "traceability": 1.5,
        "spec_executability": 1.5,
        "ac_atomicity": 1.5,
    }
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate(metrics)
    assert result["score"] <= 1.0


def test_boundary_exactly_0_65_is_warn():
    """Score exactly at 0.65 boundary should yield 'warn', not 'refuse'."""
    # Set all to 0.65 so geometric mean = 0.65
    metrics = {
        "smell_density": 0.65,
        "predicate_coverage": 0.65,
        "contract_completeness": 0.65,
        "boundary_coverage": 0.65,
        "error_path_coverage": 0.65,
        "traceability": 0.65,
        "spec_executability": 0.65,
        "ac_atomicity": 0.65,
    }
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate(metrics)
    assert result["score"] == pytest.approx(0.65, abs=1e-5)
    assert result["gate"] == "warn"


def test_boundary_exactly_0_80_is_green():
    """Score exactly at 0.80 boundary should yield 'green'."""
    metrics = {
        "smell_density": 0.80,
        "predicate_coverage": 0.80,
        "contract_completeness": 0.80,
        "boundary_coverage": 0.80,
        "error_path_coverage": 0.80,
        "traceability": 0.80,
        "spec_executability": 0.80,
        "ac_atomicity": 0.80,
    }
    result = composite_spec_quality_score_8_sub_metrics_geometric_mean_0_65_0_80_gate(metrics)
    assert result["score"] == pytest.approx(0.80, abs=1e-5)
    assert result["gate"] == "green"
