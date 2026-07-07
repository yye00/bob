"""Feature af78c082 / ba8812cb: Synthesizer MUST NOT invent exact function
names it then hard-gates on.

Covers both halves of the fix:

HALF 1 (synthesis): ``should_emit_function_ac`` only warrants a
``Function defined:`` AC when the symbol appears verbatim in the prose.

HALF 2 (verification): ``concept_token_match`` treats a synthesizer-invented
name as satisfied-by-equivalent when a defined function shares the salient
concept tokens (e.g. apply_exponential_backoff vs handle_exponential_backoff).
"""
from __future__ import annotations

import pytest

from bob.spec_synthesizer import should_emit_function_ac
from bob.enhanced_verification import concept_token_match


class TestShouldEmitFunctionAc:
    """HALF 1 — verbatim gating of Function-defined ACs."""

    def test_symbol_named_verbatim_warrants_ac(self):
        assert should_emit_function_ac(
            "apply_exponential_backoff",
            "The reaper must apply_exponential_backoff after a reset.",
        ) is True

    def test_symbol_absent_from_prose_does_not_warrant_ac(self):
        # The 99b78f59 drain: prose only described the behavior, never named
        # the concrete symbol — so no exact Function-defined AC should emit.
        assert should_emit_function_ac(
            "apply_exponential_backoff",
            "The reaper applies exponential backoff after a reset.",
        ) is False

    def test_case_insensitive_verbatim_match(self):
        assert should_emit_function_ac(
            "handle_backoff",
            "call Handle_Backoff to enforce the window",
        ) is True

    def test_whole_word_only_not_substring(self):
        # "backoff" must not match inside "backoffs" / longer words.
        assert should_emit_function_ac(
            "backoff",
            "compute the backoffs for each attempt",
        ) is False

    def test_returns_bool(self):
        assert isinstance(
            should_emit_function_ac("f", "f is here"), bool
        )


class TestConceptTokenMatch:
    """HALF 2 — concept-token equivalence for invented names."""

    def test_verb_prefix_difference_is_equivalent(self):
        assert concept_token_match(
            "apply_exponential_backoff", "handle_exponential_backoff"
        ) is True

    def test_unrelated_names_not_equivalent(self):
        assert concept_token_match(
            "apply_exponential_backoff", "schedule_task"
        ) is False

    def test_partial_token_overlap_not_equivalent(self):
        # Shares only one significant token → not a match.
        assert concept_token_match(
            "apply_exponential_backoff", "handle_backoff_reset"
        ) is False

    def test_single_significant_token_returns_false(self):
        # After stripping the verb, only one significant token remains → too
        # weak to match reliably.
        assert concept_token_match("apply_backoff", "handle_backoff") is False

    def test_exact_names_are_equivalent(self):
        assert concept_token_match(
            "compute_backoff_seconds", "compute_backoff_seconds"
        ) is True


class TestIntegration:
    """Both halves compose: an invented name is advisory, a real one contractual."""

    def test_reaper_capability_present_under_equivalence(self):
        # handle_exponential_backoff exists in bob.reaper; the invented
        # apply_exponential_backoff is satisfied-by-equivalent.
        from bob import reaper

        assert hasattr(reaper, "handle_exponential_backoff")
        assert concept_token_match(
            "apply_exponential_backoff", "handle_exponential_backoff"
        ) is True

    def test_prose_named_symbol_still_gated(self):
        # When prose names the symbol verbatim, the AC IS warranted (contractual).
        assert should_emit_function_ac(
            "handle_exponential_backoff",
            "Combined entry point: handle_exponential_backoff enforces the window.",
        ) is True
