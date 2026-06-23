"""One-shot property tests for bootstrap_override (73d63cdc).

Tests that:
1. may_bypass_readiness is strictly True iff bootstrap_attempts==0 AND research_iterations==0
2. The bypass is ONE-SHOT: after incrementing bootstrap_attempts, may_bypass_readiness returns False
3. readiness_score has no influence on the predicate (it is an input to the GATE, not to the bypass check)
4. risk_category has no influence on the predicate
"""

from __future__ import annotations

import pytest

from bob3.models import Feature
from bob3.orchestrator.bootstrap_override import may_bypass_readiness


def _feature(**overrides) -> Feature:
    defaults = dict(
        id="feat-test-oneshot",
        project_id="proj-test-oneshot",
        name="One-shot test",
        bootstrap_attempts=0,
        research_iterations=0,
        readiness_score=0.40,
        risk_category="high",
    )
    defaults.update(overrides)
    return Feature(**defaults)


class TestOneShot:
    def test_one_shot_semantics(self):
        """Bypass is allowed exactly once: before incrementing bootstrap_attempts."""
        f = _feature(bootstrap_attempts=0, research_iterations=0)
        assert may_bypass_readiness(f) is True

        # Simulate what run_loop does after granting the bypass.
        object.__setattr__(f, "bootstrap_attempts", 1)
        assert may_bypass_readiness(f) is False

    def test_readiness_score_irrelevant(self):
        """The bypass predicate does not depend on readiness_score at all."""
        for score in (0.0, 0.1, 0.56, 0.79, 1.0):
            f = _feature(bootstrap_attempts=0, research_iterations=0, readiness_score=score)
            assert may_bypass_readiness(f) is True, f"score={score} should allow bypass"

    def test_risk_category_irrelevant(self):
        """The bypass predicate does not depend on risk_category."""
        for cat in ("low", "medium", "high", "critical"):
            f = _feature(bootstrap_attempts=0, research_iterations=0, risk_category=cat)
            assert may_bypass_readiness(f) is True, f"category={cat} should allow bypass"

    def test_any_research_iteration_blocks_bypass(self):
        """Even one research iteration means there is a signal — no bypass needed."""
        for iters in (1, 2, 5, 10):
            f = _feature(bootstrap_attempts=0, research_iterations=iters)
            assert may_bypass_readiness(f) is False, f"iterations={iters} should block bypass"

    def test_any_bootstrap_attempt_exhausts_bypass(self):
        """bootstrap_attempts >= 1 exhausts the allowance."""
        for attempts in (1, 2, 3):
            f = _feature(bootstrap_attempts=attempts, research_iterations=0)
            assert may_bypass_readiness(f) is False, f"attempts={attempts} should block bypass"

    def test_bypass_independent_of_other_fields(self):
        """Fields like refinement_attempts, status, name do not affect the predicate."""
        f = _feature(
            bootstrap_attempts=0,
            research_iterations=0,
            refinement_attempts=3,
            status="ready",
            name="anything",
        )
        assert may_bypass_readiness(f) is True
