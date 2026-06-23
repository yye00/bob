"""Error-path tests: invalid input raises ValueError; function does not silently succeed.

AC: pytest: tests/test_composite_spec_quality_score_8_sub_metrics_geometr_error.py
    — invalid input raises ValueError and the function does not silently succeed
    (error path).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spec_quality.composite_score import SUB_METRIC_WEIGHTS, calculate_geometric_mean, compute_spec_quality_score


def _all_valid() -> dict:
    return {k: 0.9 for k in SUB_METRIC_WEIGHTS}


class TestComputeSpecQualityScoreErrorPaths:
    def test_empty_dict_raises_value_error(self):
        """An empty metrics dict is rejected with ValueError."""
        with pytest.raises(ValueError):
            compute_spec_quality_score({})

    def test_missing_one_metric_raises_value_error(self):
        """Providing 7 of 8 metrics raises ValueError naming the missing key."""
        metrics = dict(_all_valid())
        del metrics["ac_atomicity"]
        with pytest.raises(ValueError, match="ac_atomicity"):
            compute_spec_quality_score(metrics)

    def test_missing_multiple_metrics_raises_value_error(self):
        """Providing only 2 of 8 metrics raises ValueError."""
        metrics = {"smell_density": 0.9, "predicate_coverage": 0.9}
        with pytest.raises(ValueError):
            compute_spec_quality_score(metrics)

    def test_completely_wrong_keys_raises_value_error(self):
        """Completely unrecognized metric names raise ValueError."""
        metrics = {
            "foo": 0.5, "bar": 0.5, "baz": 0.5, "qux": 0.5,
            "a": 0.5, "b": 0.5, "c": 0.5, "d": 0.5,
        }
        with pytest.raises(ValueError):
            compute_spec_quality_score(metrics)

    def test_none_as_input_raises(self):
        """Passing None raises (TypeError or ValueError), not returning silently."""
        with pytest.raises((TypeError, ValueError, AttributeError)):
            compute_spec_quality_score(None)  # type: ignore[arg-type]

    def test_string_as_input_raises(self):
        """Passing a string raises, not returning silently."""
        with pytest.raises((TypeError, ValueError, AttributeError)):
            compute_spec_quality_score("not a dict")  # type: ignore[arg-type]


class TestCalculateGeometricMeanErrorPaths:
    def test_empty_values_raises_value_error(self):
        """Empty values dict raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            calculate_geometric_mean({}, SUB_METRIC_WEIGHTS)

    def test_empty_weights_raises_value_error(self):
        """Empty weights dict raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            calculate_geometric_mean({"a": 0.5}, {})

    def test_key_not_in_weights_raises_value_error(self):
        """A metric key absent from weights raises ValueError."""
        with pytest.raises(ValueError):
            calculate_geometric_mean({"unknown": 0.5}, SUB_METRIC_WEIGHTS)

    def test_does_not_silently_succeed_on_missing_key(self):
        """Partial metrics must NOT silently return a value — ValueError must propagate."""
        partial = {"smell_density": 0.9}
        raised = False
        try:
            result = compute_spec_quality_score(partial)
            # If we reach here without raising, the test should fail
        except (ValueError, KeyError):
            raised = True
        assert raised, "Expected ValueError or KeyError for partial metrics, but none was raised"
