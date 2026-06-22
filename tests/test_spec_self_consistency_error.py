"""Error path tests for spec self-consistency stability check (feature ca9b0c7f).

AC: pytest: tests/test_spec_self_consistency_error.py — invalid input raises
ValueError and the function does not silently succeed (error path).
"""

from __future__ import annotations

import pytest

from spec_synthesizer.stability_check import (
    compute_stability_score,
    run_parallel_extraction,
)


class TestComputeStabilityScoreErrorPath:
    """Invalid inputs to compute_stability_score must raise ValueError."""

    def test_empty_list_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_stability_score([])

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_stability_score(None)  # type: ignore[arg-type]

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_stability_score("not-a-list")  # type: ignore[arg-type]

    def test_integer_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_stability_score(42)  # type: ignore[arg-type]

    def test_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_stability_score({"key": "value"})  # type: ignore[arg-type]

    def test_variant_not_a_list_raises_value_error(self):
        # Each variant must be a list of dicts, not a string
        with pytest.raises(ValueError):
            compute_stability_score(["not-a-list-of-dicts"])  # type: ignore[arg-type]

    def test_variant_is_int_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_stability_score([42])  # type: ignore[arg-type]

    def test_does_not_silently_succeed_on_empty(self):
        # Passing empty list must raise, not return a value
        raised = False
        try:
            compute_stability_score([])
        except ValueError:
            raised = True
        assert raised, "Expected ValueError for empty variants list"

    def test_does_not_silently_succeed_on_none(self):
        raised = False
        try:
            compute_stability_score(None)  # type: ignore[arg-type]
        except ValueError:
            raised = True
        assert raised, "Expected ValueError for None variants"


class TestRunParallelExtractionErrorPath:
    """Invalid inputs to run_parallel_extraction must raise ValueError."""

    def test_acceptance_criteria_not_a_list_raises(self):
        with pytest.raises(ValueError):
            run_parallel_extraction(
                feature_id="err-test",
                name="Error Feature",
                description="Testing error path",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_acceptance_criteria_none_raises(self):
        with pytest.raises(ValueError):
            run_parallel_extraction(
                feature_id="err-test",
                name="Error Feature",
                description="Testing error path",
                acceptance_criteria=None,  # type: ignore[arg-type]
            )

    def test_acceptance_criteria_dict_raises(self):
        with pytest.raises(ValueError):
            run_parallel_extraction(
                feature_id="err-test",
                name="Error Feature",
                description="Testing error path",
                acceptance_criteria={"key": "val"},  # type: ignore[arg-type]
            )

    def test_n_zero_raises_value_error(self):
        with pytest.raises(ValueError):
            run_parallel_extraction(
                feature_id="err-n0",
                name="Error N=0",
                description="n=0 is invalid",
                acceptance_criteria=["File exists: src/foo.py"],
                n=0,
            )

    def test_n_negative_raises_value_error(self):
        with pytest.raises(ValueError):
            run_parallel_extraction(
                feature_id="err-neg",
                name="Error Negative N",
                description="negative n is invalid",
                acceptance_criteria=["File exists: src/foo.py"],
                n=-1,
            )

    def test_n_float_raises_value_error(self):
        with pytest.raises(ValueError):
            run_parallel_extraction(
                feature_id="err-float",
                name="Error Float N",
                description="float n is invalid",
                acceptance_criteria=["File exists: src/foo.py"],
                n=3.0,  # type: ignore[arg-type]
            )

    def test_n_string_raises_value_error(self):
        with pytest.raises(ValueError):
            run_parallel_extraction(
                feature_id="err-str-n",
                name="Error String N",
                description="string n is invalid",
                acceptance_criteria=["File exists: src/foo.py"],
                n="3",  # type: ignore[arg-type]
            )

    def test_does_not_silently_succeed_on_bad_acceptance_criteria(self):
        raised = False
        try:
            run_parallel_extraction(
                feature_id="err-silent",
                name="Silent Error",
                description="Should raise",
                acceptance_criteria=123,  # type: ignore[arg-type]
            )
        except ValueError:
            raised = True
        assert raised, "Expected ValueError for non-list acceptance_criteria"

    def test_does_not_silently_succeed_on_zero_n(self):
        raised = False
        try:
            run_parallel_extraction(
                feature_id="err-zero-n",
                name="Zero N",
                description="n=0 should raise",
                acceptance_criteria=["File exists: src/foo.py"],
                n=0,
            )
        except ValueError:
            raised = True
        assert raised, "Expected ValueError for n=0"
