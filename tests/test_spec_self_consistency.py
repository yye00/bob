"""Tests for spec_extractor.run_stability_check, normalize_variants, compute_jaccard_score.

AC: pytest: tests/test_spec_self_consistency.py
Integration: bob3.spec_quality.spec_extractor
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.spec_extractor import (
    compute_jaccard_score,
    normalize_variants,
    run_stability_check,
)
from bob3.spec_quality.self_consistency import SelfConsistencyResult


class TestRunStabilityCheck:
    """Tests for spec_extractor.run_stability_check."""

    def test_returns_self_consistency_result(self, tmp_path):
        result = run_stability_check(
            feature_id="feat-001",
            name="Test Feature",
            description="A feature for testing.",
            acceptance_criteria=["File exists: src/foo.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result, SelfConsistencyResult)

    def test_stability_score_in_range(self, tmp_path):
        result = run_stability_check(
            feature_id="feat-002",
            name="Range Test",
            description="Score must be in [0, 1].",
            acceptance_criteria=["File exists: src/bar.py", "pytest: tests/test_bar.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert 0.0 <= result.stability_score <= 1.0

    def test_route_is_valid_value(self, tmp_path):
        result = run_stability_check(
            feature_id="feat-003",
            name="Route Test",
            description="Route must be one of the valid values.",
            acceptance_criteria=["pytest: tests/test_x.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert result.route in ("clarification", "critic", "auto_accept")

    def test_consensus_is_bool(self, tmp_path):
        result = run_stability_check(
            feature_id="feat-004",
            name="Consensus Bool Test",
            description="consensus must be bool.",
            acceptance_criteria=["File exists: src/x.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.consensus, bool)

    def test_consensus_true_only_for_auto_accept(self, tmp_path):
        result = run_stability_check(
            feature_id="feat-005",
            name="Consensus Route Correlation",
            description="consensus must be True only when route == auto_accept.",
            acceptance_criteria=["File exists: src/x.py"],
            n=1,
            variants_dir=tmp_path,
        )
        if result.route == "auto_accept":
            assert result.consensus is True
        else:
            assert result.consensus is False

    def test_n1_returns_score_1_and_auto_accept(self, tmp_path):
        result = run_stability_check(
            feature_id="feat-006",
            name="N=1 Trivial",
            description="N=1 should produce score=1.0 and auto_accept.",
            acceptance_criteria=["File exists: src/trivial.py"],
            n=1,
            variants_dir=tmp_path,
        )
        assert result.stability_score == pytest.approx(1.0, abs=1e-9)
        assert result.route == "auto_accept"
        assert result.consensus is True

    def test_default_n_is_3(self, tmp_path):
        result = run_stability_check(
            feature_id="feat-007",
            name="Default N",
            description="Default n=3 must work.",
            acceptance_criteria=["File exists: src/default.py"],
            variants_dir=tmp_path,
        )
        assert isinstance(result, SelfConsistencyResult)
        assert 0.0 <= result.stability_score <= 1.0

    def test_disagreeing_slots_is_list(self, tmp_path):
        result = run_stability_check(
            feature_id="feat-008",
            name="Disagreeing Slots",
            description="disagreeing_slots must be a list.",
            acceptance_criteria=["File exists: src/s.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.disagreeing_slots, list)

    def test_majority_vote_is_list(self, tmp_path):
        result = run_stability_check(
            feature_id="feat-009",
            name="Majority Vote",
            description="majority_vote must be a list.",
            acceptance_criteria=["File exists: src/mv.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.majority_vote, list)

    def test_low_stability_routes_to_clarification(self, tmp_path):
        from bob3.spec_quality.self_consistency import (
            CLARIFICATION_THRESHOLD,
            jaccard_stability,
            _route_result,
        )

        variants = [
            [{"id": "AC-1", "behavior": "alpha"}],
            [{"id": "AC-1", "behavior": "beta"}],
            [{"id": "AC-1", "behavior": "gamma"}],
        ]
        score = jaccard_stability(variants)
        assert score < CLARIFICATION_THRESHOLD

        routed = _route_result(score=score, variants=variants)
        assert routed.route == "clarification"
        assert routed.consensus is False
        assert len(routed.disagreeing_slots) > 0

    def test_high_stability_routes_to_auto_accept(self, tmp_path):
        from bob3.spec_quality.self_consistency import _route_result, AUTO_ACCEPT_THRESHOLD

        variants = [
            [{"id": "AC-1", "behavior": "file exists"}],
            [{"id": "AC-1", "behavior": "file exists"}],
            [{"id": "AC-1", "behavior": "file exists"}],
        ]
        routed = _route_result(score=1.0, variants=variants)
        assert routed.route == "auto_accept"
        assert routed.consensus is True
        assert routed.stability_score >= AUTO_ACCEPT_THRESHOLD


class TestNormalizeVariants:
    """Tests for spec_extractor.normalize_variants."""

    def test_returns_list(self):
        variants = [[{"id": "AC-1", "behavior": "foo"}]]
        result = normalize_variants(variants)
        assert isinstance(result, list)

    def test_each_element_is_tuple(self):
        variants = [[{"id": "AC-1", "behavior": "foo"}]]
        result = normalize_variants(variants)
        assert isinstance(result[0], tuple)

    def test_inner_tuples_are_string_pairs(self):
        variants = [[{"id": "AC-1", "behavior": "foo"}]]
        result = normalize_variants(variants)
        for pair in result[0]:
            assert len(pair) == 2
            assert isinstance(pair[0], str)
            assert isinstance(pair[1], str)

    def test_empty_variant_list(self):
        result = normalize_variants([])
        assert result == []

    def test_whitespace_normalization_in_behavior(self):
        variants = [[{"id": "AC-1", "behavior": "  foo   bar  "}]]
        result = normalize_variants(variants)
        # behavior should have whitespace collapsed
        behavior_values = [pair[1] for pair in result[0]]
        assert "foo bar" in behavior_values

    def test_multiple_variants(self):
        variants = [
            [{"id": "AC-1", "behavior": "a"}],
            [{"id": "AC-1", "behavior": "a"}],
        ]
        result = normalize_variants(variants)
        assert len(result) == 2
        assert result[0] == result[1]

    def test_sorted_tuples_for_canonical_form(self):
        variants = [[
            {"id": "AC-2", "behavior": "b"},
            {"id": "AC-1", "behavior": "a"},
        ]]
        result = normalize_variants(variants)
        # Result must be sorted
        pairs = list(result[0])
        assert pairs == sorted(pairs)

    def test_variant_with_missing_id_defaults_to_empty(self):
        variants = [[{"behavior": "no id"}]]
        result = normalize_variants(variants)
        assert isinstance(result, list)
        ids = [pair[0] for pair in result[0]]
        assert "" in ids

    def test_variant_with_missing_behavior_defaults_to_empty(self):
        variants = [[{"id": "AC-1"}]]
        result = normalize_variants(variants)
        behaviors = [pair[1] for pair in result[0]]
        assert "" in behaviors


class TestComputeJaccardScore:
    """Tests for spec_extractor.compute_jaccard_score."""

    def test_single_variant_returns_one(self):
        variants = [[{"id": "AC-1", "behavior": "foo"}]]
        score = compute_jaccard_score(variants)
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_identical_variants_return_one(self):
        ac = [{"id": "AC-1", "behavior": "file exists"}]
        variants = [ac, ac, ac]
        score = compute_jaccard_score(variants)
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_completely_disjoint_returns_zero(self):
        variants = [
            [{"id": "AC-1", "behavior": "alpha"}],
            [{"id": "AC-2", "behavior": "beta"}],
        ]
        score = compute_jaccard_score(variants)
        assert score == pytest.approx(0.0, abs=1e-9)

    def test_partial_overlap_between_zero_and_one(self):
        variants = [
            [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-2", "behavior": "only-in-A"}],
            [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-3", "behavior": "only-in-B"}],
        ]
        score = compute_jaccard_score(variants)
        # intersection=1 ("shared"), union=3 → 1/3
        assert score == pytest.approx(1 / 3, abs=1e-6)

    def test_score_in_range_zero_to_one(self):
        variants = [
            [{"id": "AC-1", "behavior": "a"}, {"id": "AC-2", "behavior": "b"}],
            [{"id": "AC-1", "behavior": "a"}, {"id": "AC-3", "behavior": "c"}],
        ]
        score = compute_jaccard_score(variants)
        assert 0.0 <= score <= 1.0

    def test_empty_variants_each_empty_returns_one(self):
        variants = [[], []]
        score = compute_jaccard_score(variants)
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_score_is_float(self):
        variants = [[{"id": "AC-1", "behavior": "x"}]]
        score = compute_jaccard_score(variants)
        assert isinstance(score, float)

    def test_below_clarification_threshold(self):
        from bob3.spec_quality.self_consistency import CLARIFICATION_THRESHOLD

        variants = [
            [{"id": "AC-1", "behavior": "one"}],
            [{"id": "AC-2", "behavior": "two"}],
            [{"id": "AC-3", "behavior": "three"}],
        ]
        score = compute_jaccard_score(variants)
        # All disjoint → 0 < CLARIFICATION_THRESHOLD
        assert score < CLARIFICATION_THRESHOLD

    def test_above_auto_accept_threshold(self):
        from bob3.spec_quality.self_consistency import AUTO_ACCEPT_THRESHOLD

        ac = [{"id": "AC-1", "behavior": "stable"}]
        variants = [ac, ac, ac]
        score = compute_jaccard_score(variants)
        assert score >= AUTO_ACCEPT_THRESHOLD
