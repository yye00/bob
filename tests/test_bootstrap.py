"""Tests for bob77.bootstrap.check_bootstrap_readiness.

Verifies the check_bootstrap_readiness function allows one bypass per feature
when bootstrap_attempts < 1 and research_iterations == 0.
"""

from __future__ import annotations

import pytest

from bob77.bootstrap import check_bootstrap_readiness
from bob.models import Feature


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-b77-001",
        project_id="proj-b77-001",
        name="Test bootstrap readiness feature",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.3,
        risk_category="low",
    )
    defaults.update(overrides)
    return Feature(**defaults)


def test_fresh_feature_allowed():
    """Fresh feature with no bypass and no research is allowed to bypass."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    assert check_bootstrap_readiness(feature) is True


def test_after_bypass_blocked():
    """After one bypass (bootstrap_attempts=1), further bypasses are blocked."""
    feature = _feature(bootstrap_attempts=1, research_iterations=0)
    assert check_bootstrap_readiness(feature) is False


def test_with_research_blocked():
    """When research has run (research_iterations > 0), bypass is blocked."""
    feature = _feature(bootstrap_attempts=0, research_iterations=1)
    assert check_bootstrap_readiness(feature) is False


def test_both_nonzero_blocked():
    """When both bootstrap_attempts >= 1 and research_iterations > 0, blocked."""
    feature = _feature(bootstrap_attempts=1, research_iterations=2)
    assert check_bootstrap_readiness(feature) is False


def test_returns_bool():
    """check_bootstrap_readiness returns a plain bool, not a truthy value."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    result = check_bootstrap_readiness(feature)
    assert isinstance(result, bool)


def test_negative_bootstrap_attempts_raises():
    """Negative bootstrap_attempts raises ValueError."""
    feature = _feature(bootstrap_attempts=-1, research_iterations=0)
    with pytest.raises(ValueError, match="bootstrap_attempts"):
        check_bootstrap_readiness(feature)


def test_negative_research_iterations_raises():
    """Negative research_iterations raises ValueError."""
    feature = _feature(bootstrap_attempts=0, research_iterations=-1)
    with pytest.raises(ValueError, match="research_iterations"):
        check_bootstrap_readiness(feature)


def test_integration_with_feature_timeout():
    """Integration: bob.feature_timeout is importable alongside bob77.bootstrap."""
    from bob.feature_timeout import resolve_feature_timeout_seconds
    timeout = resolve_feature_timeout_seconds()
    assert timeout > 0
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    result = check_bootstrap_readiness(feature)
    assert result is True


def test_high_bootstrap_attempts_blocked():
    """Any bootstrap_attempts >= 1 blocks the bypass."""
    for attempts in (1, 2, 5, 100):
        feature = _feature(bootstrap_attempts=attempts, research_iterations=0)
        assert check_bootstrap_readiness(feature) is False


def test_high_research_iterations_blocked():
    """Any research_iterations > 0 blocks the bypass."""
    for iterations in (1, 3, 10):
        feature = _feature(bootstrap_attempts=0, research_iterations=iterations)
        assert check_bootstrap_readiness(feature) is False
