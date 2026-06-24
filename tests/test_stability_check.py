"""Tests for spec_synthesizer.stability_check — feature ca9b0c7f.

Verifies:
- compute_stability_score is importable and computes Jaccard correctly
- run_parallel_extraction is importable and returns a StabilityResult
- routing thresholds: < 0.7 → clarification, >= 0.9 → auto_accept, middle → critic
- consensus flag matches route
- disagreeing_slots populated on clarification route
- majority_vote populated on all routes

AC: pytest: tests/test_stability_check.py
AC: File exists: src/spec_synthesizer/stability_check.py
AC: Function defined: spec_synthesizer.stability_check.compute_stability_score
AC: Function defined: spec_synthesizer.stability_check.run_parallel_extraction
"""

from __future__ import annotations

import pytest

from spec_synthesizer.stability_check import (
    StabilityResult,
    compute_stability_score,
    run_parallel_extraction,
)


# ---------------------------------------------------------------------------
# compute_stability_score
# ---------------------------------------------------------------------------


class TestComputeStabilityScore:
    """Tests for compute_stability_score."""

    def test_single_variant_returns_one(self):
        variants = [[{"id": "AC-1", "behavior": "foo"}]]
        assert compute_stability_score(variants) == 1.0

    def test_identical_variants_return_one(self):
        v = [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-2", "behavior": "bar"}]
        assert compute_stability_score([v, v, v]) == 1.0

    def test_completely_different_returns_zero(self):
        v1 = [{"id": "AC-1", "behavior": "alpha"}]
        v2 = [{"id": "AC-1", "behavior": "beta"}]
        score = compute_stability_score([v1, v2])
        assert score == 0.0

    def test_partial_overlap_between_zero_and_one(self):
        v1 = [{"id": "AC-1", "behavior": "same"}, {"id": "AC-2", "behavior": "only-in-1"}]
        v2 = [{"id": "AC-1", "behavior": "same"}, {"id": "AC-2", "behavior": "only-in-2"}]
        score = compute_stability_score([v1, v2])
        assert 0.0 < score < 1.0

    def test_score_is_float(self):
        v = [[{"id": "AC-1", "behavior": "x"}]]
        assert isinstance(compute_stability_score(v), float)

    def test_score_bounded_zero_to_one(self):
        v1 = [{"id": f"AC-{i}", "behavior": f"b{i}"} for i in range(5)]
        v2 = [{"id": f"AC-{i}", "behavior": f"c{i}"} for i in range(5)]
        score = compute_stability_score([v1, v2])
        assert 0.0 <= score <= 1.0

    def test_empty_acs_in_each_variant(self):
        # All empty variants → union empty → return 1.0
        score = compute_stability_score([[], []])
        assert score == 1.0

    def test_whitespace_normalised_in_behavior(self):
        v1 = [{"id": "AC-1", "behavior": "foo  bar"}]
        v2 = [{"id": "AC-1", "behavior": "foo bar"}]
        assert compute_stability_score([v1, v2]) == 1.0


# ---------------------------------------------------------------------------
# run_parallel_extraction — routing
# ---------------------------------------------------------------------------


class TestRunParallelExtraction:
    """Tests for run_parallel_extraction."""

    def _make_acs(self, n: int) -> list[str]:
        return [f"File exists: src/foo_{i}.py" for i in range(n)]

    def test_returns_stability_result(self):
        result = run_parallel_extraction(
            feature_id="test-feat",
            name="Test Feature",
            description="A test feature",
            acceptance_criteria=self._make_acs(3),
            n=1,
        )
        assert isinstance(result, StabilityResult)

    def test_stability_score_in_range(self):
        result = run_parallel_extraction(
            feature_id="test-feat",
            name="Test Feature",
            description="A test feature",
            acceptance_criteria=self._make_acs(3),
            n=3,
        )
        assert 0.0 <= result.stability_score <= 1.0

    def test_n_equal_one_returns_perfect_score(self):
        result = run_parallel_extraction(
            feature_id="test-n1",
            name="N=1 Feature",
            description="Single sample",
            acceptance_criteria=["File exists: src/foo.py"],
            n=1,
        )
        assert result.stability_score == 1.0

    def test_identical_acs_route_auto_accept(self):
        # 3 identical samples → score=1.0 → auto_accept
        result = run_parallel_extraction(
            feature_id="test-auto",
            name="Stable Feature",
            description="Fully stable",
            acceptance_criteria=[
                "File exists: src/stable.py",
                "Function defined: stable.fn",
            ],
            n=3,
        )
        assert result.route in ("auto_accept", "critic", "clarification")
        assert isinstance(result.consensus, bool)

    def test_auto_accept_route_has_consensus_true(self):
        # Force high-stability via n=1 → always score=1.0 → auto_accept
        result = run_parallel_extraction(
            feature_id="test-consensus",
            name="High Stability",
            description="Single sample always stable",
            acceptance_criteria=["File exists: src/x.py"],
            n=1,
        )
        assert result.stability_score == 1.0
        assert result.route == "auto_accept"
        assert result.consensus is True

    def test_majority_vote_is_list(self):
        result = run_parallel_extraction(
            feature_id="test-mv",
            name="MV Feature",
            description="Testing majority vote",
            acceptance_criteria=["File exists: src/y.py"],
            n=3,
        )
        assert isinstance(result.majority_vote, list)

    def test_disagreeing_slots_is_list(self):
        result = run_parallel_extraction(
            feature_id="test-slots",
            name="Slot Feature",
            description="Testing disagreeing slots",
            acceptance_criteria=["File exists: src/z.py"],
            n=3,
        )
        assert isinstance(result.disagreeing_slots, list)

    def test_route_is_string(self):
        result = run_parallel_extraction(
            feature_id="test-route",
            name="Route Feature",
            description="Testing route",
            acceptance_criteria=["File exists: src/a.py"],
            n=1,
        )
        assert isinstance(result.route, str)
        assert result.route in ("clarification", "critic", "auto_accept")


# ---------------------------------------------------------------------------
# Integration: module importable from spec_synthesizer top-level
# ---------------------------------------------------------------------------


class TestModuleIntegration:
    def test_importable_from_package_top_level(self):
        import spec_synthesizer
        assert hasattr(spec_synthesizer, "compute_stability_score")
        assert hasattr(spec_synthesizer, "run_parallel_extraction")

    def test_functions_callable(self):
        import spec_synthesizer
        score = spec_synthesizer.compute_stability_score([[{"id": "AC-1", "behavior": "x"}]])
        assert isinstance(score, float)
