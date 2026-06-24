"""Tests that decomposition is NOT triggered when readiness is improving."""

import pytest

from bob.models import Feature
from bob.orchestrator.run_loop import (
    _readiness_did_not_improve,
    _should_decompose_instead_of_execute,
)


def make_feature(**kwargs):
    defaults = dict(
        id="feat-improving",
        project_id="proj-001",
        name="Improving Feature",
        status="ready",
        refinement_attempts=2,
        readiness_score=0.72,
        max_refinement_attempts=5,
        conf_spec_understanding=0.72,
        conf_impl_correctness=0.72,
        conf_test_adequacy=0.72,
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestDoesNotDecomposeWhenImproving:
    def test_no_decompose_when_score_increased_significantly(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.78)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)
        assert result is False

    def test_no_decompose_when_score_increased_slightly(self):
        f = make_feature(refinement_attempts=3, readiness_score=0.67)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)
        assert result is False

    def test_decompose_when_score_flat_multiple_attempts(self):
        f = make_feature(refinement_attempts=4, readiness_score=0.65)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)
        assert result is True

    def test_decompose_when_score_decreasing(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.60)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)
        assert result is True

    def test_readiness_did_not_improve_false_on_increase(self):
        f = make_feature(readiness_score=0.75)
        assert _readiness_did_not_improve(f, previous_score=0.65) is False

    def test_readiness_did_not_improve_true_on_flat(self):
        f = make_feature(readiness_score=0.65)
        assert _readiness_did_not_improve(f, previous_score=0.65) is True
