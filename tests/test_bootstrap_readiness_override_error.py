"""Error path tests for hippy.bootstrap_readiness_override.should_bootstrap_bypass.

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from hippy.bootstrap_readiness_override import should_bootstrap_bypass
from bob.models import Feature


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-br-error-001",
        project_id="proj-br-001",
        name="Error path test feature",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.3,
        risk_category="low",
    )
    defaults.update(overrides)
    return Feature(**defaults)


def test_error_negative_bootstrap_attempts_raises():
    """Negative bootstrap_attempts is invalid and raises ValueError."""
    feature = _feature(bootstrap_attempts=-1, research_iterations=0)
    with pytest.raises(ValueError, match="bootstrap_attempts"):
        should_bootstrap_bypass(feature)


def test_error_negative_research_iterations_raises():
    """Negative research_iterations is invalid and raises ValueError."""
    feature = _feature(bootstrap_attempts=0, research_iterations=-1)
    with pytest.raises(ValueError, match="research_iterations"):
        should_bootstrap_bypass(feature)


def test_error_none_feature_raises():
    """None instead of a Feature raises TypeError, does not silently succeed."""
    with pytest.raises((TypeError, ValueError)):
        should_bootstrap_bypass(None)  # type: ignore[arg-type]


def test_error_negative_counters_do_not_return_true():
    """Negative counters must not silently return True (bypass must not fire)."""
    feature = _feature(bootstrap_attempts=-5, research_iterations=-3)
    with pytest.raises(ValueError):
        result = should_bootstrap_bypass(feature)
        # If no exception, result must not be True (bypass must never fire on invalid input)
        assert result is not True


def test_error_non_integer_bootstrap_attempts_raises():
    """A non-integer counter is invalid and raises (does not silently succeed)."""

    class _Stub:
        bootstrap_attempts = "zero"
        research_iterations = 0

    with pytest.raises((TypeError, ValueError)):
        should_bootstrap_bypass(_Stub())
