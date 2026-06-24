"""Tests for bob.spec_stability_checker (feature 5cdc0a7d).

AC: pytest: tests/test_spec_stability_checker.py
"""

from __future__ import annotations

import pytest

from bob.spec_stability_checker import (
    compute_stability_score,
    run_parallel_extractions,
)


# ---------------------------------------------------------------------------
# compute_stability_score tests
# ---------------------------------------------------------------------------


class TestComputeStabilityScore:
    """Tests for compute_stability_score."""

    def test_identical_variants_score_one(self):
        variants = [
            [{"id": "AC-1", "behavior": "File exists: src/foo.py"}],
            [{"id": "AC-1", "behavior": "File exists: src/foo.py"}],
            [{"id": "AC-1", "behavior": "File exists: src/foo.py"}],
        ]
        score = compute_stability_score(variants)
        assert score == 1.0

    def test_single_variant_score_one(self):
        variants = [[{"id": "AC-1", "behavior": "Do something"}]]
        score = compute_stability_score(variants)
        assert score == 1.0

    def test_completely_disjoint_variants_score_zero(self):
        variants = [
            [{"id": "AC-1", "behavior": "alpha"}],
            [{"id": "AC-2", "behavior": "beta"}],
        ]
        score = compute_stability_score(variants)
        assert score == 0.0

    def test_partial_overlap(self):
        # Two variants sharing 1 of 2 ACs → Jaccard = 1/3
        variants = [
            [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-2", "behavior": "only-a"}],
            [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-3", "behavior": "only-b"}],
        ]
        score = compute_stability_score(variants)
        # union=3, intersection=1 → 1/3
        assert abs(score - 1 / 3) < 1e-9

    def test_score_in_range(self):
        variants = [
            [{"id": "AC-1", "behavior": "alpha"}, {"id": "AC-2", "behavior": "beta"}],
            [{"id": "AC-1", "behavior": "alpha"}, {"id": "AC-3", "behavior": "gamma"}],
            [{"id": "AC-1", "behavior": "alpha"}, {"id": "AC-4", "behavior": "delta"}],
        ]
        score = compute_stability_score(variants)
        assert 0.0 <= score <= 1.0

    def test_whitespace_normalisation(self):
        variants = [
            [{"id": "AC-1", "behavior": "File   exists:   src/foo.py"}],
            [{"id": "AC-1", "behavior": "File exists: src/foo.py"}],
        ]
        # Whitespace is collapsed → same after normalization → score = 1.0
        score = compute_stability_score(variants)
        assert score == 1.0

    def test_empty_variants_raises(self):
        with pytest.raises(ValueError):
            compute_stability_score([])

    def test_none_raises(self):
        with pytest.raises(ValueError):
            compute_stability_score(None)  # type: ignore[arg-type]

    def test_non_list_element_raises(self):
        with pytest.raises(ValueError):
            compute_stability_score(["not-a-list"])  # type: ignore[arg-type]

    def test_returns_float(self):
        score = compute_stability_score([[{"id": "AC-1", "behavior": "foo"}]])
        assert isinstance(score, float)


# ---------------------------------------------------------------------------
# run_parallel_extractions tests
# ---------------------------------------------------------------------------


class TestRunParallelExtractions:
    """Tests for run_parallel_extractions (note: plural)."""

    def test_returns_dict_with_required_keys(self):
        result = run_parallel_extractions(
            feature_id="test-feat",
            name="Test Feature",
            description="A test feature",
            acceptance_criteria=["File exists: src/foo.py", "pytest: tests/test_foo.py"],
            n=3,
        )
        assert "stability_score" in result
        assert "route" in result
        assert "consensus" in result
        assert "disagreeing_slots" in result
        assert "majority_vote" in result

    def test_stability_score_in_range(self):
        result = run_parallel_extractions(
            feature_id="range-test",
            name="Range Test",
            description="Score range check",
            acceptance_criteria=["File exists: src/foo.py"],
            n=3,
        )
        assert 0.0 <= result["stability_score"] <= 1.0

    def test_route_is_valid_value(self):
        result = run_parallel_extractions(
            feature_id="route-test",
            name="Route Test",
            description="Route value check",
            acceptance_criteria=["File exists: src/bar.py"],
            n=3,
        )
        assert result["route"] in ("clarification", "critic", "auto_accept")

    def test_consensus_is_bool(self):
        result = run_parallel_extractions(
            feature_id="consensus-test",
            name="Consensus Test",
            description="Consensus bool check",
            acceptance_criteria=["File exists: src/foo.py"],
            n=3,
        )
        assert isinstance(result["consensus"], bool)

    def test_empty_acs_returns_auto_accept(self):
        # Empty variants → Jaccard = 1.0 → auto_accept
        result = run_parallel_extractions(
            feature_id="empty-acs",
            name="Empty ACs",
            description="No ACs",
            acceptance_criteria=[],
            n=3,
        )
        assert result["stability_score"] == 1.0
        assert result["route"] == "auto_accept"
        assert result["consensus"] is True

    def test_n_equals_one_returns_auto_accept(self):
        # Single sample → score = 1.0
        result = run_parallel_extractions(
            feature_id="n1-test",
            name="N=1 Test",
            description="Single sample",
            acceptance_criteria=["File exists: src/foo.py"],
            n=1,
        )
        assert result["stability_score"] == 1.0
        assert result["route"] == "auto_accept"
        assert result["consensus"] is True

    def test_low_stability_route_clarification(self):
        # Force low stability by using _override_variants with disjoint sets
        result = run_parallel_extractions(
            feature_id="low-stability",
            name="Low Stability",
            description="Disjoint variants",
            acceptance_criteria=[],
            n=3,
            _override_variants=[
                [{"id": "AC-1", "behavior": "alpha"}],
                [{"id": "AC-2", "behavior": "beta"}],
                [{"id": "AC-3", "behavior": "gamma"}],
            ],
        )
        assert result["route"] == "clarification"
        assert result["consensus"] is False
        assert len(result["disagreeing_slots"]) > 0

    def test_high_stability_route_auto_accept(self):
        # Identical variants → score = 1.0 → auto_accept
        identical = [{"id": "AC-1", "behavior": "foo"}]
        result = run_parallel_extractions(
            feature_id="high-stability",
            name="High Stability",
            description="Identical variants",
            acceptance_criteria=[],
            n=3,
            _override_variants=[identical, identical, identical],
        )
        assert result["route"] == "auto_accept"
        assert result["consensus"] is True
        assert result["disagreeing_slots"] == []

    def test_invalid_acceptance_criteria_raises(self):
        with pytest.raises(ValueError):
            run_parallel_extractions(
                feature_id="err",
                name="Err",
                description="Bad AC",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_n_zero_raises(self):
        with pytest.raises(ValueError):
            run_parallel_extractions(
                feature_id="err-n0",
                name="Err N0",
                description="n=0",
                acceptance_criteria=["File exists: src/foo.py"],
                n=0,
            )

    def test_n_negative_raises(self):
        with pytest.raises(ValueError):
            run_parallel_extractions(
                feature_id="err-neg",
                name="Err Neg",
                description="n=-1",
                acceptance_criteria=["File exists: src/foo.py"],
                n=-1,
            )

    def test_majority_vote_is_list(self):
        result = run_parallel_extractions(
            feature_id="mv-test",
            name="MV Test",
            description="Majority vote",
            acceptance_criteria=["File exists: src/foo.py"],
            n=3,
        )
        assert isinstance(result["majority_vote"], list)

    def test_disagreeing_slots_is_list(self):
        result = run_parallel_extractions(
            feature_id="ds-test",
            name="DS Test",
            description="Disagreeing slots",
            acceptance_criteria=["File exists: src/foo.py"],
            n=3,
        )
        assert isinstance(result["disagreeing_slots"], list)
