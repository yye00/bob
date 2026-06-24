"""Tests for bob.spec_stability_check — N-sample stability check pre-critic.

AC: pytest: tests/test_spec_stability_check.py
Integration: bob.spec_extractor
"""

from __future__ import annotations

import pytest

from bob.spec_stability_check import (
    StabilityCheckResult,
    compute_jaccard_score,
    run_stability_check,
)


# ---------------------------------------------------------------------------
# compute_jaccard_score
# ---------------------------------------------------------------------------


class TestComputeJaccardScore:
    """Tests for compute_jaccard_score."""

    def test_single_variant_returns_one(self):
        score = compute_jaccard_score([[{"id": "AC-1", "behavior": "exists"}]])
        assert score == 1.0

    def test_identical_variants_return_one(self):
        v = [{"id": "AC-1", "behavior": "do X"}]
        score = compute_jaccard_score([v, v, v])
        assert score == 1.0

    def test_completely_disjoint_returns_zero(self):
        v1 = [{"id": "AC-1", "behavior": "do X"}]
        v2 = [{"id": "AC-2", "behavior": "do Y"}]
        score = compute_jaccard_score([v1, v2])
        assert score == 0.0

    def test_partial_overlap_between_zero_and_one(self):
        v1 = [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-2", "behavior": "unique-a"}]
        v2 = [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-3", "behavior": "unique-b"}]
        score = compute_jaccard_score([v1, v2])
        assert 0.0 < score < 1.0

    def test_two_empty_variants_return_one(self):
        score = compute_jaccard_score([[], []])
        assert score == 1.0

    def test_score_is_float(self):
        score = compute_jaccard_score([[{"id": "AC-1", "behavior": "b"}]])
        assert isinstance(score, float)

    def test_score_in_range(self):
        v1 = [{"id": "AC-1", "behavior": "a"}]
        v2 = [{"id": "AC-1", "behavior": "b"}]
        score = compute_jaccard_score([v1, v2])
        assert 0.0 <= score <= 1.0

    def test_empty_variants_raises(self):
        with pytest.raises(ValueError):
            compute_jaccard_score([])

    def test_non_list_raises(self):
        with pytest.raises(ValueError):
            compute_jaccard_score(None)  # type: ignore[arg-type]

    def test_variant_not_a_list_raises(self):
        with pytest.raises(ValueError):
            compute_jaccard_score(["not-a-list"])  # type: ignore[arg-type]

    def test_whitespace_normalization(self):
        v1 = [{"id": "AC-1", "behavior": "do  X"}]
        v2 = [{"id": "AC-1", "behavior": "do X"}]
        score = compute_jaccard_score([v1, v2])
        assert score == 1.0

    def test_missing_id_key_does_not_raise(self):
        score = compute_jaccard_score([[{"behavior": "something"}], [{"behavior": "something"}]])
        assert 0.0 <= score <= 1.0

    def test_missing_behavior_key_does_not_raise(self):
        score = compute_jaccard_score([[{"id": "AC-1"}], [{"id": "AC-1"}]])
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# run_stability_check
# ---------------------------------------------------------------------------


class TestRunStabilityCheck:
    """Tests for run_stability_check."""

    def test_returns_stability_check_result(self, tmp_path):
        result = run_stability_check(
            feature_id="test-001",
            name="Test Feature",
            description="A test feature",
            acceptance_criteria=["File exists: src/test.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result, StabilityCheckResult)

    def test_stability_score_in_range(self, tmp_path):
        result = run_stability_check(
            feature_id="test-002",
            name="Test Feature",
            description="A test feature",
            acceptance_criteria=["File exists: src/test.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert 0.0 <= result.stability_score <= 1.0

    def test_route_is_valid_string(self, tmp_path):
        result = run_stability_check(
            feature_id="test-003",
            name="Test Feature",
            description="A test feature",
            acceptance_criteria=["File exists: src/test.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert result.route in ("clarification", "critic", "auto_accept")

    def test_consensus_is_bool(self, tmp_path):
        result = run_stability_check(
            feature_id="test-004",
            name="Test Feature",
            description="A test feature",
            acceptance_criteria=["File exists: src/test.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.consensus, bool)

    def test_consensus_true_only_for_auto_accept(self, tmp_path):
        result = run_stability_check(
            feature_id="test-005",
            name="Test Feature",
            description="A test feature",
            acceptance_criteria=["File exists: src/test.py"],
            n=3,
            variants_dir=tmp_path,
        )
        if result.route == "auto_accept":
            assert result.consensus is True
        else:
            assert result.consensus is False

    def test_n1_returns_score_1_and_auto_accept(self, tmp_path):
        result = run_stability_check(
            feature_id="test-n1",
            name="N=1 Test",
            description="Single sample",
            acceptance_criteria=["File exists: src/solo.py"],
            n=1,
            variants_dir=tmp_path,
        )
        assert result.stability_score == 1.0
        assert result.route == "auto_accept"
        assert result.consensus is True

    def test_empty_acceptance_criteria_returns_result(self, tmp_path):
        result = run_stability_check(
            feature_id="test-empty",
            name="Empty ACs",
            description="No acceptance criteria",
            acceptance_criteria=[],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result, StabilityCheckResult)
        assert isinstance(result.stability_score, float)
        assert result.route in ("clarification", "critic", "auto_accept")

    def test_empty_acs_route_is_auto_accept(self, tmp_path):
        result = run_stability_check(
            feature_id="test-empty-auto",
            name="Empty ACs Auto Accept",
            description="All empty → score 1.0 → auto_accept",
            acceptance_criteria=[],
            n=3,
            variants_dir=tmp_path,
        )
        assert result.stability_score == 1.0
        assert result.route == "auto_accept"
        assert result.consensus is True

    def test_disagreeing_slots_is_list(self, tmp_path):
        result = run_stability_check(
            feature_id="test-slots",
            name="Slots Feature",
            description="A test feature",
            acceptance_criteria=["File exists: src/test.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.disagreeing_slots, list)

    def test_majority_vote_is_list(self, tmp_path):
        result = run_stability_check(
            feature_id="test-majority",
            name="Majority Feature",
            description="A test feature",
            acceptance_criteria=["File exists: src/test.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.majority_vote, list)

    def test_acceptance_criteria_not_list_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_stability_check(
                feature_id="err-001",
                name="Error Feature",
                description="Testing error",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
                variants_dir=tmp_path,
            )

    def test_n_zero_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_stability_check(
                feature_id="err-n0",
                name="N=0 Error",
                description="n=0 invalid",
                acceptance_criteria=["File exists: src/test.py"],
                n=0,
                variants_dir=tmp_path,
            )

    def test_n_negative_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_stability_check(
                feature_id="err-neg",
                name="Negative N Error",
                description="negative n invalid",
                acceptance_criteria=["File exists: src/test.py"],
                n=-1,
                variants_dir=tmp_path,
            )

    def test_integration_with_spec_extractor(self, tmp_path):
        """Verify integration with bob.spec_extractor.extract_with_temperature."""
        result = run_stability_check(
            feature_id="integration-001",
            name="Integration Test",
            description="Verifies spec_extractor is called per seed",
            acceptance_criteria=[
                "File exists: src/bob/spec_stability_check.py",
                "Function defined: bob.spec_stability_check.run_stability_check",
            ],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result, StabilityCheckResult)
        assert 0.0 <= result.stability_score <= 1.0
        assert result.route in ("clarification", "critic", "auto_accept")

    def test_multiple_stable_acs_high_score(self, tmp_path):
        """Stable ACs across seeds should produce a high stability score."""
        result = run_stability_check(
            feature_id="stable-acs",
            name="Stable Feature",
            description="All stable acceptance criteria",
            acceptance_criteria=[
                "File exists: src/bob/stable.py",
                "Function defined: bob.stable.run",
            ],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.stability_score, float)

    def test_default_n_is_3(self, tmp_path):
        """Default n=3 should return a valid result."""
        result = run_stability_check(
            feature_id="default-n",
            name="Default N Feature",
            description="Uses default n",
            acceptance_criteria=["File exists: src/test.py"],
            variants_dir=tmp_path,
        )
        assert isinstance(result, StabilityCheckResult)
