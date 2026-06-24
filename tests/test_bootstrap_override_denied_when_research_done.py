"""Tests that bootstrap bypass is denied when research has already been done (73d63cdc)."""

from __future__ import annotations

import pytest

from bob.models import Feature
from bob.orchestrator.bootstrap_override import may_bypass_readiness


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-test-research",
        project_id="proj-test-research",
        name="Denied when research done test",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.50,
        risk_category="medium",
    )
    defaults.update(overrides)
    return Feature(**defaults)


class TestDeniedWhenResearchDone:
    def test_denied_when_research_iterations_is_one(self):
        """Bypass denied when research_iterations == 1."""
        f = _feature(bootstrap_attempts=0, research_iterations=1)
        assert may_bypass_readiness(f) is False

    def test_denied_when_research_iterations_is_many(self):
        """Bypass denied for any research_iterations > 0."""
        for iters in (1, 2, 5, 10, 100):
            f = _feature(bootstrap_attempts=0, research_iterations=iters)
            assert may_bypass_readiness(f) is False, f"iters={iters}"

    def test_allowed_when_research_iterations_is_zero(self):
        """Bypass allowed only when research_iterations == 0 and bootstrap_attempts == 0."""
        f = _feature(bootstrap_attempts=0, research_iterations=0)
        assert may_bypass_readiness(f) is True

    def test_denied_when_both_research_and_bootstrap_nonzero(self):
        """Both counters non-zero → denied."""
        f = _feature(bootstrap_attempts=1, research_iterations=1)
        assert may_bypass_readiness(f) is False

    def test_research_iterations_none_treated_as_zero(self):
        """None research_iterations treated as 0 → bypass allowed (if bootstrap_attempts==0)."""
        f = _feature(bootstrap_attempts=0, research_iterations=0)
        object.__setattr__(f, "research_iterations", None)
        assert may_bypass_readiness(f) is True

    def test_research_overrides_bootstrap_zero(self):
        """Having research_iterations > 0 blocks bypass even if bootstrap_attempts == 0."""
        f = _feature(bootstrap_attempts=0, research_iterations=3)
        assert may_bypass_readiness(f) is False
