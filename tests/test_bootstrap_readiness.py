"""Tests for bob72.bootstrap_readiness.check_bootstrap_override.

Verifies the check_bootstrap_override function allows one bypass per feature
when bootstrap_attempts < 1 and research_iterations == 0.
"""

from __future__ import annotations

import pytest

from bob72.bootstrap_readiness import check_bootstrap_override
from bob.models import Feature


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-br-001",
        project_id="proj-br-001",
        name="Test bootstrap readiness feature",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.3,
        risk_category="low",
    )
    defaults.update(overrides)
    return Feature(**defaults)


def test_check_bootstrap_override_fresh_feature_allowed():
    """Fresh feature with no bypass and no research is allowed to bypass."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    assert check_bootstrap_override(feature) is True


def test_check_bootstrap_override_after_bypass_blocked():
    """After one bypass (bootstrap_attempts=1), further bypasses are blocked."""
    feature = _feature(bootstrap_attempts=1, research_iterations=0)
    assert check_bootstrap_override(feature) is False


def test_check_bootstrap_override_with_research_blocked():
    """When research has run (research_iterations > 0), bypass is blocked."""
    feature = _feature(bootstrap_attempts=0, research_iterations=1)
    assert check_bootstrap_override(feature) is False


def test_check_bootstrap_override_both_nonzero_blocked():
    """When both bootstrap_attempts >= 1 and research_iterations > 0, blocked."""
    feature = _feature(bootstrap_attempts=1, research_iterations=2)
    assert check_bootstrap_override(feature) is False


def test_check_bootstrap_override_high_bootstrap_attempts_blocked():
    """Any bootstrap_attempts >= 1 blocks the bypass."""
    for attempts in (1, 2, 5, 100):
        feature = _feature(bootstrap_attempts=attempts, research_iterations=0)
        assert check_bootstrap_override(feature) is False, f"Expected False for bootstrap_attempts={attempts}"


def test_check_bootstrap_override_high_research_iterations_blocked():
    """Any research_iterations > 0 blocks the bypass."""
    for iterations in (1, 3, 10):
        feature = _feature(bootstrap_attempts=0, research_iterations=iterations)
        assert check_bootstrap_override(feature) is False, f"Expected False for research_iterations={iterations}"


def test_check_bootstrap_override_returns_bool():
    """check_bootstrap_override returns a plain bool, not a truthy value."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    result = check_bootstrap_override(feature)
    assert isinstance(result, bool)


def test_check_bootstrap_override_integration_with_feature_watchdog():
    """Integration: check_bootstrap_override can be used alongside bob.feature_watchdog."""
    from bob.feature_watchdog import FeatureWatchdog  # noqa: F401 — import verifies integration
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    result = check_bootstrap_override(feature)
    assert result is True
