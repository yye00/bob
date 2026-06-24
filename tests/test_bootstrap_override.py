"""Tests for bootstrap_override.may_bypass_readiness (73d63cdc).

Verifies the pure predicate logic:
- eligible when bootstrap_attempts==0 and research_iterations==0
- not eligible when bootstrap_attempts==1 (already used the bypass)
- not eligible when research_iterations>0 (research signal exists, no deadlock)
- not eligible when both counters are non-zero
- default field values on Feature allow bypass out-of-the-box
"""

from __future__ import annotations

from datetime import datetime

import pytest

from bob.models import Feature
from bob.orchestrator.bootstrap_override import may_bypass_readiness


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-test-0001",
        project_id="proj-test-0001",
        name="Test feature",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.56,
        risk_category="medium",
    )
    defaults.update(overrides)
    return Feature(**defaults)


class TestMayBypassReadiness:
    def test_eligible_when_both_zero(self):
        """Fresh feature with no attempts and no research → bypass allowed."""
        f = _feature(bootstrap_attempts=0, research_iterations=0)
        assert may_bypass_readiness(f) is True

    def test_not_eligible_when_bootstrap_used(self):
        """Once bootstrap_attempts==1 the bypass is exhausted."""
        f = _feature(bootstrap_attempts=1, research_iterations=0)
        assert may_bypass_readiness(f) is False

    def test_not_eligible_when_research_exists(self):
        """If research_iterations>0 there is already a signal — no deadlock."""
        f = _feature(bootstrap_attempts=0, research_iterations=1)
        assert may_bypass_readiness(f) is False

    def test_not_eligible_when_both_nonzero(self):
        f = _feature(bootstrap_attempts=1, research_iterations=2)
        assert may_bypass_readiness(f) is False

    def test_eligible_with_high_research_iteration_count_but_zero_bootstrap(self):
        """Sanity: research>0 always blocks — bootstrap_attempts value is irrelevant."""
        f = _feature(bootstrap_attempts=0, research_iterations=5)
        assert may_bypass_readiness(f) is False

    def test_feature_default_fields_allow_bypass(self):
        """Feature.__init__ defaults (bootstrap_attempts=0, research_iterations=0) should be bypass-eligible."""
        f = Feature(id="x", project_id="p", name="n")
        assert may_bypass_readiness(f) is True

    def test_none_bootstrap_attempts_treated_as_zero(self):
        """Guard against legacy rows where bootstrap_attempts may be None."""
        f = _feature(bootstrap_attempts=0, research_iterations=0)
        # Simulate a legacy row by patching the attribute.
        object.__setattr__(f, "bootstrap_attempts", None)
        assert may_bypass_readiness(f) is True

    def test_none_research_iterations_treated_as_zero(self):
        """Guard against legacy rows where research_iterations may be None."""
        f = _feature(bootstrap_attempts=0, research_iterations=0)
        object.__setattr__(f, "research_iterations", None)
        assert may_bypass_readiness(f) is True
