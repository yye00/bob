"""Tests for hippy.bootstrap_readiness_override.should_bootstrap_bypass.

Verifies that should_bootstrap_bypass correctly allows one bypass execute
per feature when:
  - bootstrap_attempts < 1
  - research_iterations == 0
And blocks the bypass when either condition is not met.
"""

from __future__ import annotations

import pytest

from hippy.bootstrap_readiness_override import should_bootstrap_bypass
from bob.models import Feature


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-bypass-001",
        project_id="proj-001",
        name="Bypass test feature",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.3,
        risk_category="low",
    )
    defaults.update(overrides)
    return Feature(**defaults)


def test_should_bootstrap_bypass_fresh_feature_allowed():
    """Fresh feature (both counters zero) is allowed bypass."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    assert should_bootstrap_bypass(feature) is True


def test_should_bootstrap_bypass_after_first_use_blocked():
    """Feature that already used the bypass (bootstrap_attempts=1) is blocked."""
    feature = _feature(bootstrap_attempts=1, research_iterations=0)
    assert should_bootstrap_bypass(feature) is False


def test_should_bootstrap_bypass_with_research_blocked():
    """Feature with existing research iterations is blocked (no deadlock)."""
    feature = _feature(bootstrap_attempts=0, research_iterations=1)
    assert should_bootstrap_bypass(feature) is False


def test_should_bootstrap_bypass_both_nonzero_blocked():
    """Both counters nonzero — bypass blocked."""
    feature = _feature(bootstrap_attempts=1, research_iterations=2)
    assert should_bootstrap_bypass(feature) is False


def test_should_bootstrap_bypass_returns_bool():
    """Function always returns a bool, not a truthy/falsy value."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    result = should_bootstrap_bypass(feature)
    assert isinstance(result, bool)


def test_should_bootstrap_bypass_high_bootstrap_attempts_blocked():
    """bootstrap_attempts > 1 is also blocked (more than max)."""
    feature = _feature(bootstrap_attempts=5, research_iterations=0)
    assert should_bootstrap_bypass(feature) is False


def test_should_bootstrap_bypass_high_research_iterations_blocked():
    """Multiple research iterations present — bypass blocked."""
    feature = _feature(bootstrap_attempts=0, research_iterations=10)
    assert should_bootstrap_bypass(feature) is False


def test_should_bootstrap_bypass_accepts_plain_object():
    """Any object exposing the two counter attributes is accepted (duck-typed)."""

    class _Stub:
        bootstrap_attempts = 0
        research_iterations = 0

    assert should_bootstrap_bypass(_Stub()) is True
