"""Tests that the bootstrap bypass is denied after the first use (73d63cdc)."""

from __future__ import annotations

import pytest

from bob3.models import Feature
from bob3.orchestrator.bootstrap_override import (
    handle_second_attempt_denied,
    may_bypass_readiness,
)


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-test-denied",
        project_id="proj-test-denied",
        name="Denied after first use test",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.40,
        risk_category="medium",
    )
    defaults.update(overrides)
    return Feature(**defaults)


class TestDeniedAfterFirstUse:
    def test_handle_second_attempt_denied_returns_false_when_attempts_is_one(self):
        """handle_second_attempt_denied returns False when bootstrap_attempts == 1."""
        f = _feature(bootstrap_attempts=1)
        assert handle_second_attempt_denied(f) is False

    def test_handle_second_attempt_denied_returns_false_when_attempts_above_one(self):
        """handle_second_attempt_denied returns False for any attempts >= 1."""
        for attempts in (1, 2, 5, 100):
            f = _feature(bootstrap_attempts=attempts)
            assert handle_second_attempt_denied(f) is False, f"attempts={attempts}"

    def test_handle_second_attempt_denied_returns_true_when_attempts_is_zero(self):
        """handle_second_attempt_denied returns True (not denied) when attempts == 0."""
        f = _feature(bootstrap_attempts=0)
        assert handle_second_attempt_denied(f) is True

    def test_may_bypass_false_after_first_use(self):
        """may_bypass_readiness returns False once bootstrap_attempts reaches 1."""
        f = _feature(bootstrap_attempts=0, research_iterations=0)
        assert may_bypass_readiness(f) is True

        object.__setattr__(f, "bootstrap_attempts", 1)
        assert may_bypass_readiness(f) is False

    def test_both_functions_agree_on_denial(self):
        """handle_second_attempt_denied and may_bypass_readiness agree: both False post-use."""
        f = _feature(bootstrap_attempts=1, research_iterations=0)
        assert may_bypass_readiness(f) is False
        assert handle_second_attempt_denied(f) is False

    def test_none_bootstrap_attempts_treated_as_zero(self):
        """handle_second_attempt_denied treats None as 0 (not denied)."""
        f = _feature(bootstrap_attempts=0)
        object.__setattr__(f, "bootstrap_attempts", None)
        assert handle_second_attempt_denied(f) is True
