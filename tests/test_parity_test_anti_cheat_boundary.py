"""Boundary tests for parity_test_anti_cheat — empty/zero/minimum inputs.

Feature 8ff7325a-aab0-43f3-89e9-ce039e624cee

Empty, zero, or minimum inputs must return a well-defined result rather than
raising.
"""

from __future__ import annotations

from bob.spec_quality.parity_test_anti_cheat import (
    synthesize_parity_ac,
    is_parity_intent,
    has_execution_substrate,
    ensure_randomized_parity_coverage,
)


class TestSynthesizeParityAcBoundary:
    def test_empty_intent_returns_empty_list(self):
        assert synthesize_parity_ac("") == []

    def test_whitespace_intent_returns_empty_list(self):
        assert synthesize_parity_ac("   \n\t ") == []

    def test_num_seeds_zero_falls_back_to_default(self):
        # zero seeds is meaningless — use a sane default rather than emitting "0"
        acs = synthesize_parity_ac("output equals reference", num_seeds=0)
        assert acs != []
        assert "0 randomized" not in " ".join(acs)

    def test_num_seeds_one_is_promoted_to_minimum(self):
        # a single seed is still a lone frozen input — promote to the minimum.
        acs = synthesize_parity_ac("output equals reference", num_seeds=1)
        assert acs != []
        assert "1 randomized seed " not in (" ".join(acs) + " ")


class TestEnsureRandomizedParityCoverageBoundary:
    def test_empty_criteria_list(self):
        out = ensure_randomized_parity_coverage([], intent="output equals reference")
        # non-empty parity intent still yields the randomized companion
        assert isinstance(out, list)
        assert any(
            c.strip().lower().startswith(("property:", "behavior:")) for c in out
        )

    def test_empty_criteria_and_empty_intent(self):
        out = ensure_randomized_parity_coverage([], intent="")
        assert out == []

    def test_empty_intent_leaves_criteria_untouched(self):
        criteria = ["File exists: src/x.py"]
        out = ensure_randomized_parity_coverage(criteria, intent="")
        assert out == criteria


class TestPredicatesBoundary:
    def test_is_parity_intent_empty(self):
        assert is_parity_intent("") is False

    def test_has_execution_substrate_empty(self):
        assert has_execution_substrate("") is False
