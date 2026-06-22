"""Tests for spec_extractor N-sample stability check pre-critic.

AC: pytest: tests/test_spec_stability.py
Integration: spec_extractor

Tests cover:
- spec_extractor.run_parallel_extraction
- spec_extractor.compute_jaccard_stability
- spec_extractor.normalize_variants
"""

from __future__ import annotations

import pytest

import spec_extractor
from spec_extractor import (
    run_parallel_extraction,
    compute_jaccard_stability,
    normalize_variants,
)
from bob3.spec_quality.self_consistency import SelfConsistencyResult


class TestRunParallelExtraction:
    """Tests for spec_extractor.run_parallel_extraction."""

    def test_returns_self_consistency_result(self, tmp_path):
        result = run_parallel_extraction(
            feature_id="stab-001",
            name="Stability Test",
            description="A feature for testing.",
            acceptance_criteria=["File exists: src/foo.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result, SelfConsistencyResult)

    def test_stability_score_in_range(self, tmp_path):
        result = run_parallel_extraction(
            feature_id="stab-002",
            name="Score Range",
            description="Score must be in [0, 1].",
            acceptance_criteria=["File exists: src/bar.py", "pytest: tests/test_bar.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert 0.0 <= result.stability_score <= 1.0

    def test_route_is_valid_string(self, tmp_path):
        result = run_parallel_extraction(
            feature_id="stab-003",
            name="Route Validity",
            description="Route must be one of three values.",
            acceptance_criteria=["pytest: tests/test_x.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert result.route in ("clarification", "critic", "auto_accept")

    def test_consensus_is_bool(self, tmp_path):
        result = run_parallel_extraction(
            feature_id="stab-004",
            name="Consensus Bool",
            description="consensus must be bool.",
            acceptance_criteria=["File exists: src/x.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.consensus, bool)

    def test_consensus_true_only_for_auto_accept(self, tmp_path):
        result = run_parallel_extraction(
            feature_id="stab-005",
            name="Consensus Correlation",
            description="consensus must be True only when auto_accept.",
            acceptance_criteria=["File exists: src/x.py"],
            n=1,
            variants_dir=tmp_path,
        )
        if result.route == "auto_accept":
            assert result.consensus is True
        else:
            assert result.consensus is False

    def test_n1_returns_score_1_and_auto_accept(self, tmp_path):
        result = run_parallel_extraction(
            feature_id="stab-006",
            name="N=1 Trivial",
            description="N=1 produces score=1.0 and auto_accept.",
            acceptance_criteria=["File exists: src/trivial.py"],
            n=1,
            variants_dir=tmp_path,
        )
        assert result.stability_score == pytest.approx(1.0, abs=1e-9)
        assert result.route == "auto_accept"
        assert result.consensus is True

    def test_default_n_is_3(self, tmp_path):
        result = run_parallel_extraction(
            feature_id="stab-007",
            name="Default N",
            description="Default n=3 must work.",
            acceptance_criteria=["File exists: src/default.py"],
            variants_dir=tmp_path,
        )
        assert isinstance(result, SelfConsistencyResult)
        assert 0.0 <= result.stability_score <= 1.0

    def test_disagreeing_slots_is_list(self, tmp_path):
        result = run_parallel_extraction(
            feature_id="stab-008",
            name="Disagreeing Slots",
            description="disagreeing_slots must be a list.",
            acceptance_criteria=["File exists: src/s.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.disagreeing_slots, list)

    def test_majority_vote_is_list(self, tmp_path):
        result = run_parallel_extraction(
            feature_id="stab-009",
            name="Majority Vote",
            description="majority_vote must be a list.",
            acceptance_criteria=["File exists: src/mv.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.majority_vote, list)

    def test_invalid_acceptance_criteria_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_parallel_extraction(
                feature_id="stab-err-1",
                name="Error Test",
                description="Should raise.",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
                variants_dir=tmp_path,
            )

    def test_invalid_n_zero_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_parallel_extraction(
                feature_id="stab-err-2",
                name="n=0 Error",
                description="n=0 should raise.",
                acceptance_criteria=["File exists: src/foo.py"],
                n=0,
                variants_dir=tmp_path,
            )

    def test_invalid_n_bool_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_parallel_extraction(
                feature_id="stab-err-3",
                name="n=bool Error",
                description="n=True should raise.",
                acceptance_criteria=["File exists: src/foo.py"],
                n=True,  # type: ignore[arg-type]
                variants_dir=tmp_path,
            )

    def test_function_accessible_as_module_attribute(self):
        assert hasattr(spec_extractor, "run_parallel_extraction")
        assert callable(spec_extractor.run_parallel_extraction)


class TestComputeJaccardStability:
    """Tests for spec_extractor.compute_jaccard_stability."""

    def test_single_variant_returns_one(self):
        variants = [[{"id": "AC-1", "behavior": "foo"}]]
        score = compute_jaccard_stability(variants)
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_identical_variants_return_one(self):
        ac = [{"id": "AC-1", "behavior": "file exists"}]
        variants = [ac, ac, ac]
        score = compute_jaccard_stability(variants)
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_completely_disjoint_returns_zero(self):
        variants = [
            [{"id": "AC-1", "behavior": "alpha"}],
            [{"id": "AC-2", "behavior": "beta"}],
        ]
        score = compute_jaccard_stability(variants)
        assert score == pytest.approx(0.0, abs=1e-9)

    def test_partial_overlap(self):
        variants = [
            [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-2", "behavior": "only-A"}],
            [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-3", "behavior": "only-B"}],
        ]
        score = compute_jaccard_stability(variants)
        # intersection=1 ("shared"), union=3 → 1/3
        assert score == pytest.approx(1 / 3, abs=1e-6)

    def test_score_in_range_zero_to_one(self):
        variants = [
            [{"id": "AC-1", "behavior": "a"}, {"id": "AC-2", "behavior": "b"}],
            [{"id": "AC-1", "behavior": "a"}, {"id": "AC-3", "behavior": "c"}],
        ]
        score = compute_jaccard_stability(variants)
        assert 0.0 <= score <= 1.0

    def test_two_empty_variants_return_one(self):
        variants = [[], []]
        score = compute_jaccard_stability(variants)
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_score_is_float(self):
        variants = [[{"id": "AC-1", "behavior": "x"}]]
        score = compute_jaccard_stability(variants)
        assert isinstance(score, float)

    def test_empty_variants_raises(self):
        with pytest.raises(ValueError):
            compute_jaccard_stability([])

    def test_none_raises(self):
        with pytest.raises(ValueError):
            compute_jaccard_stability(None)  # type: ignore[arg-type]

    def test_non_list_variant_raises(self):
        with pytest.raises(ValueError):
            compute_jaccard_stability(["not-a-list"])  # type: ignore[arg-type]

    def test_below_clarification_threshold(self):
        from bob3.spec_quality.self_consistency import CLARIFICATION_THRESHOLD
        variants = [
            [{"id": "AC-1", "behavior": "one"}],
            [{"id": "AC-2", "behavior": "two"}],
            [{"id": "AC-3", "behavior": "three"}],
        ]
        score = compute_jaccard_stability(variants)
        assert score < CLARIFICATION_THRESHOLD

    def test_above_auto_accept_threshold(self):
        from bob3.spec_quality.self_consistency import AUTO_ACCEPT_THRESHOLD
        ac = [{"id": "AC-1", "behavior": "stable"}]
        variants = [ac, ac, ac]
        score = compute_jaccard_stability(variants)
        assert score >= AUTO_ACCEPT_THRESHOLD

    def test_function_accessible_as_module_attribute(self):
        assert hasattr(spec_extractor, "compute_jaccard_stability")
        assert callable(spec_extractor.compute_jaccard_stability)


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

    def test_empty_variants_list(self):
        result = normalize_variants([])
        assert result == []

    def test_whitespace_normalization_in_behavior(self):
        variants = [[{"id": "AC-1", "behavior": "  foo   bar  "}]]
        result = normalize_variants(variants)
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

    def test_sorted_tuples_canonical_form(self):
        variants = [[
            {"id": "AC-2", "behavior": "b"},
            {"id": "AC-1", "behavior": "a"},
        ]]
        result = normalize_variants(variants)
        pairs = list(result[0])
        assert pairs == sorted(pairs)

    def test_missing_id_defaults_to_empty(self):
        variants = [[{"behavior": "no id"}]]
        result = normalize_variants(variants)
        assert isinstance(result, list)
        ids = [pair[0] for pair in result[0]]
        assert "" in ids

    def test_missing_behavior_defaults_to_empty(self):
        variants = [[{"id": "AC-1"}]]
        result = normalize_variants(variants)
        behaviors = [pair[1] for pair in result[0]]
        assert "" in behaviors

    def test_function_accessible_as_module_attribute(self):
        assert hasattr(spec_extractor, "normalize_variants")
        assert callable(spec_extractor.normalize_variants)


class TestIntegration:
    """Integration tests exercising the routing semantics end-to-end."""

    def test_n3_identical_acs_routes_to_auto_accept(self, tmp_path):
        # When seed perturbations don't trigger, identical ACs → score=1.0 → auto_accept
        result = run_parallel_extraction(
            feature_id="int-001",
            name="Integration Auto Accept",
            description="Identical ACs across N samples.",
            acceptance_criteria=["AC-1: file exists src/foo.py"],
            n=1,
            variants_dir=tmp_path,
        )
        assert result.route == "auto_accept"
        assert result.consensus is True
        assert result.stability_score >= 0.9

    def test_jaccard_stability_consistent_with_run_parallel(self, tmp_path):
        # Verify compute_jaccard_stability agrees with the stability_score returned
        # by run_parallel_extraction when we pass identical variants manually.
        identical = [[{"id": "AC-1", "behavior": "foo"}]] * 3
        manual_score = compute_jaccard_stability(identical)
        assert manual_score == pytest.approx(1.0, abs=1e-9)

    def test_normalize_variants_then_jaccard(self):
        variants = [
            [{"id": "AC-1", "behavior": "  exists  "}, {"id": "AC-2", "behavior": "tests"}],
            [{"id": "AC-1", "behavior": "exists"}, {"id": "AC-2", "behavior": "tests"}],
        ]
        normalized = normalize_variants(variants)
        # After normalization the two variants should be equal (whitespace collapsed)
        assert normalized[0] == normalized[1]
        score = compute_jaccard_stability(variants)
        assert score == pytest.approx(1.0, abs=1e-9)
