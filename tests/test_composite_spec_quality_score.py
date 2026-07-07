"""Tests for src/bob/composite_spec_quality_score.py.

AC coverage:
  - File exists: src/bob/composite_spec_quality_score.py
  - Function defined: bob.composite_spec_quality_score.spec_quality_score
  - Function defined: bob.composite_spec_quality_score.spec_quality_gate
  - integration: bob.spec_quality_gate
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.composite_spec_quality_score import (
    SUB_METRIC_WEIGHTS,
    spec_quality_gate,
    spec_quality_score,
)


def _all_metrics(value: float) -> dict:
    return {k: value for k in SUB_METRIC_WEIGHTS}


class TestWeights:
    def test_eight_sub_metrics_present(self):
        assert len(SUB_METRIC_WEIGHTS) == 8

    def test_weights_sum_to_one(self):
        assert sum(SUB_METRIC_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)

    def test_expected_weight_values(self):
        assert SUB_METRIC_WEIGHTS["smell_density"] == pytest.approx(0.20)
        assert SUB_METRIC_WEIGHTS["predicate_coverage"] == pytest.approx(0.20)
        assert SUB_METRIC_WEIGHTS["contract_completeness"] == pytest.approx(0.15)
        assert SUB_METRIC_WEIGHTS["boundary_coverage"] == pytest.approx(0.10)
        assert SUB_METRIC_WEIGHTS["error_path_coverage"] == pytest.approx(0.10)
        assert SUB_METRIC_WEIGHTS["traceability"] == pytest.approx(0.10)
        assert SUB_METRIC_WEIGHTS["spec_executability"] == pytest.approx(0.10)
        assert SUB_METRIC_WEIGHTS["ac_atomicity"] == pytest.approx(0.05)


class TestSpecQualityScore:
    def test_all_ones_returns_one(self):
        assert spec_quality_score(_all_metrics(1.0)) == pytest.approx(1.0, abs=1e-9)

    def test_all_zero_returns_zero(self):
        assert spec_quality_score(_all_metrics(0.0)) == pytest.approx(0.0, abs=1e-9)

    def test_single_zero_collapses_to_zero(self):
        m = _all_metrics(0.95)
        m["ac_atomicity"] = 0.0
        assert spec_quality_score(m) == pytest.approx(0.0, abs=1e-9)

    def test_uniform_value_equals_that_value(self):
        # Weighted geometric mean of a constant v (weights sum to 1) is v.
        assert spec_quality_score(_all_metrics(0.72)) == pytest.approx(0.72, abs=1e-6)

    def test_clamps_above_one(self):
        assert spec_quality_score(_all_metrics(3.0)) <= 1.0

    def test_returns_float(self):
        assert isinstance(spec_quality_score(_all_metrics(0.8)), float)

    def test_missing_metric_raises_value_error(self):
        m = _all_metrics(0.9)
        del m["traceability"]
        with pytest.raises(ValueError, match="traceability"):
            spec_quality_score(m)

    def test_empty_raises_value_error(self):
        with pytest.raises(ValueError):
            spec_quality_score({})


class TestSpecQualityGate:
    def test_green_at_and_above_080(self):
        assert spec_quality_gate(0.80) == "green"
        assert spec_quality_gate(0.95) == "green"

    def test_warn_between_065_and_080(self):
        assert spec_quality_gate(0.65) == "warn"
        assert spec_quality_gate(0.79) == "warn"

    def test_refuse_below_065(self):
        assert spec_quality_gate(0.64) == "refuse"
        assert spec_quality_gate(0.0) == "refuse"

    def test_accepts_metrics_dict(self):
        # Gate may also be called with a metrics mapping (computes score first).
        assert spec_quality_gate(_all_metrics(1.0)) == "green"
        assert spec_quality_gate(_all_metrics(0.70)) == "warn"
        assert spec_quality_gate(_all_metrics(0.5)) == "refuse"

    def test_invalid_type_raises(self):
        with pytest.raises((TypeError, ValueError)):
            spec_quality_gate("nope")


class TestIntegration:
    def test_importable_from_bob_spec_quality_gate(self):
        import bob.spec_quality_gate as sqg

        assert hasattr(sqg, "spec_quality_score")
        assert hasattr(sqg, "spec_quality_gate")
        assert sqg.spec_quality_gate(0.85) == "green"
