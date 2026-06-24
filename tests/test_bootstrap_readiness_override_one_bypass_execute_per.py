"""Tests for bootstrap_readiness_override_one_bypass_execute_per.

Verifies that the bootstrap readiness override function correctly allows
one bypass execute per feature when:
- bootstrap_attempts < 1
- research_iterations == 0
And blocks the bypass when either condition is not met.
"""

from __future__ import annotations

import pytest

from bob.bootstrap_readiness_override_one_bypass_execute_per import (
    bootstrap_readiness_override_one_bypass_execute_per,
)
from bob.models import Feature


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-test-bypass-001",
        project_id="proj-test-001",
        name="Test bypass feature",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.3,
        risk_category="low",
    )
    defaults.update(overrides)
    return Feature(**defaults)


def test_bootstrap_readiness_override_one_bypass_execute_per():
    """Main AC test: bypass allowed for fresh feature, blocked after first use."""
    # Fresh feature — bypass allowed
    fresh = _feature(bootstrap_attempts=0, research_iterations=0)
    assert bootstrap_readiness_override_one_bypass_execute_per(fresh) is True

    # Already used bypass — blocked
    used = _feature(bootstrap_attempts=1, research_iterations=0)
    assert bootstrap_readiness_override_one_bypass_execute_per(used) is False

    # Research exists — no deadlock, blocked
    researched = _feature(bootstrap_attempts=0, research_iterations=1)
    assert bootstrap_readiness_override_one_bypass_execute_per(researched) is False

    # Both non-zero — blocked
    both = _feature(bootstrap_attempts=1, research_iterations=2)
    assert bootstrap_readiness_override_one_bypass_execute_per(both) is False


def test_bypass_allowed_when_counters_zero():
    """Bypass is allowed when both bootstrap_attempts and research_iterations are 0."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    result = bootstrap_readiness_override_one_bypass_execute_per(feature)
    assert result is True


def test_bypass_blocked_when_bootstrap_attempts_equals_one():
    """Bypass is blocked once bootstrap_attempts == 1."""
    feature = _feature(bootstrap_attempts=1, research_iterations=0)
    result = bootstrap_readiness_override_one_bypass_execute_per(feature)
    assert result is False


def test_bypass_blocked_when_research_iterations_nonzero():
    """Bypass is blocked when research has already run (research_iterations > 0)."""
    feature = _feature(bootstrap_attempts=0, research_iterations=3)
    result = bootstrap_readiness_override_one_bypass_execute_per(feature)
    assert result is False


def test_bypass_blocked_when_both_counters_nonzero():
    """Bypass is blocked when both bootstrap_attempts >= 1 and research_iterations > 0."""
    feature = _feature(bootstrap_attempts=2, research_iterations=5)
    result = bootstrap_readiness_override_one_bypass_execute_per(feature)
    assert result is False


def test_zero_bootstrap_attempts_allowed():
    """Explicit zero bootstrap_attempts allows bypass when research_iterations is 0."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    result = bootstrap_readiness_override_one_bypass_execute_per(feature)
    assert result is True


def test_zero_research_iterations_allows_bypass():
    """Explicit zero research_iterations allows bypass when bootstrap_attempts is 0."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    result = bootstrap_readiness_override_one_bypass_execute_per(feature)
    assert result is True


def test_high_bootstrap_attempts_blocked():
    """Any bootstrap_attempts >= 1 blocks the bypass."""
    for attempts in (1, 2, 5, 100):
        feature = _feature(bootstrap_attempts=attempts, research_iterations=0)
        assert bootstrap_readiness_override_one_bypass_execute_per(feature) is False
