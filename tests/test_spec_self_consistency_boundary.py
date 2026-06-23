"""Boundary tests for spec self-consistency stability check (feature ca9b0c7f).

AC: pytest: tests/test_spec_self_consistency_boundary.py — empty, zero, or
minimum input returns a well-defined result rather than raising (boundary case).
"""

from __future__ import annotations

import pytest

from spec_synthesizer.stability_check import (
    compute_stability_score,
    run_parallel_extraction,
)


class TestComputeStabilityScoreBoundary:
    """Boundary cases for compute_stability_score."""

    def test_single_empty_variant_returns_one(self):
        # Minimum input: one variant with no ACs
        score = compute_stability_score([[]])
        assert score == 1.0

    def test_two_empty_variants_return_one(self):
        # Empty union → return 1.0 by convention
        score = compute_stability_score([[], []])
        assert score == 1.0

    def test_three_empty_variants_return_one(self):
        score = compute_stability_score([[], [], []])
        assert score == 1.0

    def test_single_variant_with_one_ac(self):
        # Minimum meaningful input: one variant, one AC
        score = compute_stability_score([[{"id": "AC-1", "behavior": "exists"}]])
        assert score == 1.0

    def test_variants_with_missing_id_key(self):
        # AC dict missing 'id' — should not raise; falls back to empty string id
        v = [[{"behavior": "something"}], [{"behavior": "something"}]]
        score = compute_stability_score(v)
        assert 0.0 <= score <= 1.0

    def test_variants_with_missing_behavior_key(self):
        # AC dict missing 'behavior' — should not raise
        v = [[{"id": "AC-1"}], [{"id": "AC-1"}]]
        score = compute_stability_score(v)
        assert 0.0 <= score <= 1.0

    def test_variants_with_empty_string_fields(self):
        v = [[{"id": "", "behavior": ""}], [{"id": "", "behavior": ""}]]
        score = compute_stability_score(v)
        assert 0.0 <= score <= 1.0

    def test_single_variant_empty_list_is_boundary(self):
        # single variant, empty list — same as empty variant
        score = compute_stability_score([[]])
        assert isinstance(score, float)
        assert score == 1.0


class TestRunParallelExtractionBoundary:
    """Boundary cases for run_parallel_extraction."""

    def test_empty_acceptance_criteria_returns_result(self):
        # Zero ACs — should not raise, returns a StabilityResult
        result = run_parallel_extraction(
            feature_id="boundary-empty",
            name="Boundary Empty",
            description="No ACs",
            acceptance_criteria=[],
            n=3,
        )
        assert result is not None
        assert isinstance(result.stability_score, float)
        assert result.route in ("clarification", "critic", "auto_accept")
        assert isinstance(result.consensus, bool)
        assert isinstance(result.disagreeing_slots, list)
        assert isinstance(result.majority_vote, list)

    def test_n_equals_one_minimum_samples(self):
        # n=1 is minimum; score must be 1.0 trivially
        result = run_parallel_extraction(
            feature_id="boundary-n1",
            name="N=1 Boundary",
            description="Single sample boundary",
            acceptance_criteria=["File exists: src/foo.py"],
            n=1,
        )
        assert result.stability_score == 1.0
        assert result.route == "auto_accept"
        assert result.consensus is True

    def test_single_ac_multiple_samples(self):
        # Exactly one AC; with 3 seeds the base AC is stable (no perturbation at h!=1)
        result = run_parallel_extraction(
            feature_id="boundary-single-ac",
            name="Single AC Boundary",
            description="One acceptance criterion",
            acceptance_criteria=["File exists: src/solo.py"],
            n=3,
        )
        assert 0.0 <= result.stability_score <= 1.0
        assert result.route in ("clarification", "critic", "auto_accept")

    def test_empty_acs_route_is_auto_accept(self):
        # Empty variants → score = 1.0 → auto_accept
        result = run_parallel_extraction(
            feature_id="boundary-all-empty",
            name="All Empty Boundary",
            description="All empty",
            acceptance_criteria=[],
            n=3,
        )
        assert result.stability_score == 1.0
        assert result.route == "auto_accept"
        assert result.consensus is True

    def test_whitespace_only_behavior_normalizes(self):
        # AC with whitespace-only behavior should not raise
        result = run_parallel_extraction(
            feature_id="boundary-whitespace",
            name="Whitespace Boundary",
            description="Whitespace ACs",
            acceptance_criteria=["   "],
            n=1,
        )
        assert isinstance(result.stability_score, float)
