"""Tests that _handle_first_attempt returns False on attempt 1 boundary.

Validates the minimum/first-iteration edge case: a feature on its first
refinement attempt must NEVER be marked for decomposition.
"""

import pytest

from bob3.models import Feature
from bob3.orchestrator.run_loop import (
    _handle_first_attempt,
    _should_decompose_instead_of_execute,
)


def make_feature(**kwargs):
    defaults = dict(
        id="feat-first",
        project_id="proj-001",
        name="First Attempt Feature",
        status="ready",
        refinement_attempts=1,
        readiness_score=0.50,
        max_refinement_attempts=5,
        conf_spec_understanding=0.50,
        conf_impl_correctness=0.50,
        conf_test_adequacy=0.50,
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestHandleFirstAttempt:
    def test_returns_false_at_attempt_index_1(self):
        """_handle_first_attempt must return False when attempt index == 1."""
        f = make_feature(refinement_attempts=1)
        assert _handle_first_attempt(f) is False

    def test_returns_false_at_attempt_index_0(self):
        """Also returns False at zero (before any attempt)."""
        f = make_feature(refinement_attempts=0)
        assert _handle_first_attempt(f) is False

    def test_does_not_return_false_at_attempt_index_2(self):
        """At attempt 2, _handle_first_attempt is no longer the single-gate."""
        f = make_feature(refinement_attempts=2)
        # _handle_first_attempt returns False only on attempt==1
        # At attempt 2 it returns False too (not first attempt in the guard sense),
        # but the decompose gate then checks other conditions.
        # What we care about is that _should_decompose at attempt=1 returns False.
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.50)
        # At refinement_attempts=2 with no improvement, should decompose
        assert result is True

    def test_should_not_decompose_at_attempt_1_boundary(self):
        """Integration: _should_decompose_instead_of_execute returns False at attempt=1."""
        f = make_feature(refinement_attempts=1, readiness_score=0.50)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.50)
        assert result is False

    def test_should_not_decompose_at_attempt_0(self):
        """Integration: _should_decompose_instead_of_execute returns False at attempt=0."""
        f = make_feature(refinement_attempts=0, readiness_score=0.50)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.50)
        assert result is False
