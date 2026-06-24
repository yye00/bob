"""Tests for Jaccard normalization in the self-consistency check.

Feature: 289249a9-4e29-4cbc-b418-c242c024bdfe
Spec: Spec self-consistency — N-sample stability check pre-critic
"""

from __future__ import annotations

import pytest

from bob.spec_quality.self_consistency import jaccard_stability


class TestJaccardNormalization:
    def test_identical_variants_score_one(self):
        variants = [
            [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-2", "behavior": "bar"}],
            [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-2", "behavior": "bar"}],
            [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-2", "behavior": "bar"}],
        ]
        score = jaccard_stability(variants)
        assert score == pytest.approx(1.0)

    def test_completely_different_variants_score_zero(self):
        variants = [
            [{"id": "AC-1", "behavior": "foo"}],
            [{"id": "AC-2", "behavior": "bar"}],
            [{"id": "AC-3", "behavior": "baz"}],
        ]
        score = jaccard_stability(variants)
        assert score == pytest.approx(0.0)

    def test_partial_overlap_between_zero_and_one(self):
        variants = [
            [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-2", "behavior": "bar"}],
            [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-3", "behavior": "baz"}],
        ]
        score = jaccard_stability(variants)
        assert 0.0 < score < 1.0

    def test_single_variant_returns_one(self):
        variants = [[{"id": "AC-1", "behavior": "foo"}]]
        score = jaccard_stability(variants)
        assert score == pytest.approx(1.0)

    def test_empty_variants_returns_one(self):
        score = jaccard_stability([])
        assert score == pytest.approx(1.0)

    def test_score_is_float_in_range(self):
        variants = [
            [{"id": "AC-1", "behavior": "alpha"}],
            [{"id": "AC-1", "behavior": "beta"}],
        ]
        score = jaccard_stability(variants)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_normalization_ignores_field_order_within_tuple(self):
        # behavior and id swapped — should still be treated as equal tuples
        variants = [
            [{"id": "AC-1", "behavior": "do the thing"}],
            [{"behavior": "do the thing", "id": "AC-1"}],
        ]
        score = jaccard_stability(variants)
        assert score == pytest.approx(1.0)

    def test_two_identical_two_different(self):
        variants = [
            [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-2", "behavior": "bar"}],
            [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-2", "behavior": "bar"}],
            [{"id": "AC-99", "behavior": "zzz"}],
        ]
        # intersection of all 3 is empty (AC-99+zzz not in first two; AC-1+foo not in third)
        # union has 3 tuples → score = 0/3 = 0.0
        score = jaccard_stability(variants)
        assert score == pytest.approx(0.0)

    def test_whitespace_normalized_behavior(self):
        variants = [
            [{"id": "AC-1", "behavior": "  do the thing  "}],
            [{"id": "AC-1", "behavior": "do the thing"}],
        ]
        score = jaccard_stability(variants)
        assert score == pytest.approx(1.0)
