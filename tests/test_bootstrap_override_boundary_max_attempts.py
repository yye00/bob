"""Tests boundary condition: may_bypass_readiness returns False at max (73d63cdc).

AC: asserts may_bypass_readiness returns False when bootstrap_attempts == max (1) boundary.
"""

from __future__ import annotations

import pytest

from bob3.models import Feature
from bob3.orchestrator.bootstrap_override import max_bootstrap_attempts, may_bypass_readiness


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-test-boundary",
        project_id="proj-test-boundary",
        name="Boundary max attempts test",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.40,
        risk_category="medium",
    )
    defaults.update(overrides)
    return Feature(**defaults)


class TestBoundaryMaxAttempts:
    def test_max_bootstrap_attempts_returns_one(self):
        """max_bootstrap_attempts() returns 1."""
        assert max_bootstrap_attempts() == 1

    def test_may_bypass_false_at_max_boundary(self):
        """may_bypass_readiness returns False when bootstrap_attempts == max (1)."""
        max_val = max_bootstrap_attempts()
        f = _feature(bootstrap_attempts=max_val, research_iterations=0)
        assert may_bypass_readiness(f) is False

    def test_may_bypass_true_just_below_max(self):
        """may_bypass_readiness returns True when bootstrap_attempts == max - 1 (0)."""
        max_val = max_bootstrap_attempts()
        f = _feature(bootstrap_attempts=max_val - 1, research_iterations=0)
        assert may_bypass_readiness(f) is True

    def test_may_bypass_false_above_max(self):
        """may_bypass_readiness returns False when bootstrap_attempts > max."""
        max_val = max_bootstrap_attempts()
        for extra in (1, 2, 10):
            f = _feature(bootstrap_attempts=max_val + extra, research_iterations=0)
            assert may_bypass_readiness(f) is False, f"attempts={max_val + extra}"

    def test_boundary_is_strict_less_than(self):
        """The boundary check is strictly < max, so == max is denied."""
        max_val = max_bootstrap_attempts()
        at_max = _feature(bootstrap_attempts=max_val, research_iterations=0)
        below_max = _feature(bootstrap_attempts=max_val - 1, research_iterations=0)
        assert may_bypass_readiness(at_max) is False
        assert may_bypass_readiness(below_max) is True
