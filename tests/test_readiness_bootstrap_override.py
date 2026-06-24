"""Tests for bob3.readiness.check_bootstrap_override.

Verifies that check_bootstrap_override allows exactly one bypass execute per
feature when bootstrap_attempts < 1 and research_iterations == 0.
"""

from __future__ import annotations

import pytest

from bob3.readiness import check_bootstrap_override
from bob3.models import Feature


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-rbo-001",
        project_id="proj-rbo-001",
        name="Readiness bootstrap override test feature",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.3,
        risk_category="low",
    )
    defaults.update(overrides)
    return Feature(**defaults)


def test_fresh_feature_allowed():
    """Fresh feature (both counters zero) is allowed the bypass."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    assert check_bootstrap_override(feature) is True


def test_after_first_use_blocked():
    """Feature that already used the bypass (bootstrap_attempts=1) is blocked."""
    feature = _feature(bootstrap_attempts=1, research_iterations=0)
    assert check_bootstrap_override(feature) is False


def test_with_research_blocked():
    """Feature with existing research iterations is blocked."""
    feature = _feature(bootstrap_attempts=0, research_iterations=1)
    assert check_bootstrap_override(feature) is False


def test_both_nonzero_blocked():
    """Both counters nonzero — bypass blocked."""
    feature = _feature(bootstrap_attempts=1, research_iterations=2)
    assert check_bootstrap_override(feature) is False


def test_returns_bool():
    """Function always returns a strict bool."""
    feature = _feature(bootstrap_attempts=0, research_iterations=0)
    result = check_bootstrap_override(feature)
    assert isinstance(result, bool)


def test_high_bootstrap_attempts_blocked():
    """bootstrap_attempts > 1 is blocked (more than max)."""
    feature = _feature(bootstrap_attempts=5, research_iterations=0)
    assert check_bootstrap_override(feature) is False


def test_high_research_iterations_blocked():
    """Multiple research iterations — bypass blocked."""
    feature = _feature(bootstrap_attempts=0, research_iterations=10)
    assert check_bootstrap_override(feature) is False


def test_negative_bootstrap_attempts_raises():
    """Negative bootstrap_attempts raises ValueError."""
    feature = _feature(bootstrap_attempts=-1, research_iterations=0)
    with pytest.raises(ValueError, match="bootstrap_attempts"):
        check_bootstrap_override(feature)


def test_negative_research_iterations_raises():
    """Negative research_iterations raises ValueError."""
    feature = _feature(bootstrap_attempts=0, research_iterations=-1)
    with pytest.raises(ValueError, match="research_iterations"):
        check_bootstrap_override(feature)
