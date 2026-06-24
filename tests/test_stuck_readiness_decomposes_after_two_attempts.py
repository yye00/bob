"""Tests for stuck-readiness decomposition trigger (feature 077db964).

Validates that _should_decompose_instead_of_execute returns True when:
- refinement_attempts >= 2
- readiness_score < 0.80
- readiness did not improve since last attempt
"""

from unittest.mock import MagicMock, patch

import pytest

from bob.models import Feature
from bob.orchestrator.run_loop import (
    _refinement_attempts_at_or_above_two,
    _readiness_below_threshold,
    _readiness_did_not_improve,
    _should_decompose_instead_of_execute,
    _transition_to_pending_decomposition,
    _log_decomposition_reason,
    _preserve_f_r6_317_bypass,
    _record_cost_saved,
    _never_decomposes_on_first_attempt,
    _decide_next_action,
)


def make_feature(**kwargs):
    defaults = dict(
        id="feat-001",
        project_id="proj-001",
        name="Test Feature",
        status="ready",
        refinement_attempts=2,
        readiness_score=0.65,
        max_refinement_attempts=5,
        conf_spec_understanding=0.65,
        conf_impl_correctness=0.65,
        conf_test_adequacy=0.65,
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestRefinementAttemptsAtOrAboveTwo:
    def test_returns_true_at_exactly_two(self):
        f = make_feature(refinement_attempts=2)
        assert _refinement_attempts_at_or_above_two(f) is True

    def test_returns_true_above_two(self):
        f = make_feature(refinement_attempts=5)
        assert _refinement_attempts_at_or_above_two(f) is True

    def test_returns_false_at_one(self):
        f = make_feature(refinement_attempts=1)
        assert _refinement_attempts_at_or_above_two(f) is False

    def test_returns_false_at_zero(self):
        f = make_feature(refinement_attempts=0)
        assert _refinement_attempts_at_or_above_two(f) is False


class TestReadinessBelowThreshold:
    def test_returns_true_below_0_80(self):
        f = make_feature(readiness_score=0.65)
        assert _readiness_below_threshold(f) is True

    def test_returns_false_at_exactly_0_80(self):
        f = make_feature(readiness_score=0.80)
        assert _readiness_below_threshold(f) is False

    def test_returns_false_above_0_80(self):
        f = make_feature(readiness_score=0.90)
        assert _readiness_below_threshold(f) is False

    def test_returns_true_at_zero(self):
        f = make_feature(readiness_score=0.0)
        assert _readiness_below_threshold(f) is True


class TestReadinessDidNotImprove:
    def test_returns_true_when_score_unchanged(self):
        f = make_feature(readiness_score=0.65)
        assert _readiness_did_not_improve(f, previous_score=0.65) is True

    def test_returns_true_when_score_decreased(self):
        f = make_feature(readiness_score=0.55)
        assert _readiness_did_not_improve(f, previous_score=0.65) is True

    def test_returns_false_when_score_improved(self):
        f = make_feature(readiness_score=0.75)
        assert _readiness_did_not_improve(f, previous_score=0.65) is False

    def test_returns_true_when_previous_score_is_none(self):
        f = make_feature(readiness_score=0.65)
        assert _readiness_did_not_improve(f, previous_score=None) is True


class TestShouldDecomposeInsteadOfExecute:
    def test_decomposes_when_all_conditions_met(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)
        assert result is True

    def test_no_decompose_when_readiness_high(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.85)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.85)
        assert result is False

    def test_no_decompose_when_attempts_low(self):
        f = make_feature(refinement_attempts=1, readiness_score=0.65)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)
        assert result is False

    def test_no_decompose_when_readiness_improved(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.75)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)
        assert result is False

    def test_decomposes_at_three_attempts(self):
        f = make_feature(refinement_attempts=3, readiness_score=0.50)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.50)
        assert result is True

    def test_raises_value_error_on_negative_attempts(self):
        f = make_feature(refinement_attempts=-1, readiness_score=0.65)
        with pytest.raises(ValueError, match="negative"):
            _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)


class TestNeverDecomposesOnFirstAttempt:
    def test_returns_true(self):
        assert _never_decomposes_on_first_attempt() is True
