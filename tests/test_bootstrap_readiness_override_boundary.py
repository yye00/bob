"""Boundary tests for hippy.bootstrap_readiness_override.should_bootstrap_bypass.

Empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

import pytest

from hippy.bootstrap_readiness_override import should_bootstrap_bypass
from bob.models import Feature


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-br-boundary-001",
        project_id="proj-br-001",
        name="Boundary test feature",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.0,
        risk_category="low",
    )
    defaults.update(overrides)
    return Feature(**defaults)


def test_boundary_both_zero_returns_true():
    """Both counters at zero (minimum) returns True without raising."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    result = should_bootstrap_bypass(feature)
    assert result is True


def test_boundary_bootstrap_attempts_at_limit_returns_false():
    """bootstrap_attempts at exactly max (1) returns False without raising."""
    feature = _feature(bootstrap_attempts=1, research_iterations=0)
    result = should_bootstrap_bypass(feature)
    assert result is False


def test_boundary_readiness_score_zero_does_not_raise():
    """readiness_score=0.0 (minimum) does not cause an exception."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0, readiness_score=0.0)
    result = should_bootstrap_bypass(feature)
    assert isinstance(result, bool)


def test_boundary_readiness_score_one_does_not_raise():
    """readiness_score=1.0 (maximum) does not cause an exception."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0, readiness_score=1.0)
    result = should_bootstrap_bypass(feature)
    assert isinstance(result, bool)


def test_boundary_feature_with_minimum_required_fields():
    """Feature with only mandatory fields set returns a well-defined result."""
    feature = _feature()
    result = should_bootstrap_bypass(feature)
    assert result is True


def test_boundary_research_iterations_zero_explicit():
    """Explicitly zero research_iterations returns True (not an error)."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    result = should_bootstrap_bypass(feature)
    assert result is True


def test_boundary_bootstrap_attempts_one_research_zero():
    """At the exact bypass boundary: bootstrap_attempts=1, research=0 → False."""
    feature = _feature(bootstrap_attempts=1, research_iterations=0)
    result = should_bootstrap_bypass(feature)
    assert result is False


def test_boundary_none_counters_default_to_zero():
    """None counters are treated as zero (minimum) and return True."""

    class _Stub:
        bootstrap_attempts = None
        research_iterations = None

    result = should_bootstrap_bypass(_Stub())
    assert result is True
