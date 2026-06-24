"""Tests for bob.spec_synthesizer.should_emit_function_ac.

Verifies that the synthesizer only emits a ``Function defined: <module>.<symbol>``
AC when the exact symbol appears verbatim in the feature prose — it MUST NOT invent
an exact symbol and hard-gate on it when the prose did not name it.

Feature: af78c082 — Synthesizer MUST NOT invent exact function names it then
hard-gates on.
"""
from __future__ import annotations

import pytest

from bob.spec_synthesizer import should_emit_function_ac


class TestShouldEmitFunctionAcVerbatimPresent:
    """should_emit_function_ac returns True only when symbol is verbatim in description."""

    def test_returns_true_when_symbol_verbatim_in_description(self):
        assert should_emit_function_ac(
            "apply_exponential_backoff",
            "The feature implements apply_exponential_backoff to delay retries.",
        )

    def test_returns_false_when_symbol_absent(self):
        assert not should_emit_function_ac(
            "apply_exponential_backoff",
            "The feature implements exponential backoff after reaper reset.",
        )

    def test_returns_false_when_synonym_used_not_exact_name(self):
        # "handle_exponential_backoff" ≠ "apply_exponential_backoff"
        assert not should_emit_function_ac(
            "apply_exponential_backoff",
            "The feature calls handle_exponential_backoff to manage delays.",
        )

    def test_returns_true_for_exact_word_boundary_match(self):
        assert should_emit_function_ac(
            "compute_score",
            "Uses compute_score to evaluate quality.",
        )

    def test_returns_false_for_partial_substring_without_word_boundary(self):
        # "compute_scores" contains "compute_score" as a prefix but is not an exact boundary match
        assert not should_emit_function_ac(
            "compute_score",
            "Uses compute_scores to evaluate quality.",
        )


class TestShouldEmitFunctionAcEdgeCases:
    """Edge cases for should_emit_function_ac."""

    def test_empty_symbol_returns_false(self):
        assert not should_emit_function_ac("", "Some description with no symbol.")

    def test_whitespace_only_symbol_returns_false(self):
        assert not should_emit_function_ac("   ", "Some description text.")

    def test_empty_description_returns_false(self):
        assert not should_emit_function_ac("my_func", "")

    def test_whitespace_only_description_returns_false(self):
        assert not should_emit_function_ac("my_func", "   ")

    def test_both_empty_returns_false(self):
        assert not should_emit_function_ac("", "")

    def test_symbol_at_start_of_description(self):
        assert should_emit_function_ac(
            "reset_state",
            "reset_state is called after each reaper cycle.",
        )

    def test_symbol_at_end_of_description(self):
        assert should_emit_function_ac(
            "reset_state",
            "The reaper cycle terminates with reset_state",
        )

    def test_case_sensitive_match(self):
        # Word-boundary regex is case sensitive — "Reset_State" ≠ "reset_state"
        assert not should_emit_function_ac(
            "reset_state",
            "The reaper calls Reset_State to clean up.",
        )

    def test_none_safe_via_falsy_check(self):
        # Public contract: empty-string check covers None-like falsy inputs passed
        # as the empty string; actual None would error on strip(), so we test str only.
        assert not should_emit_function_ac("", "description")
        assert not should_emit_function_ac("symbol", "")


class TestShouldEmitFunctionAcRejectsInventedName:
    """Verifies the synthesizer guidance: prose that describes a capability in
    natural language (without naming an exact function) should NOT produce a
    Function-defined AC via should_emit_function_ac."""

    def test_prose_describing_backoff_without_naming_function(self):
        description = (
            "After a reaper reset the system applies exponential backoff "
            "before re-dispatching the feature. The backoff duration doubles "
            "each attempt up to a maximum of 32 seconds."
        )
        # No exact symbol name in prose → synthesizer must not gate on an invented name
        assert not should_emit_function_ac("apply_exponential_backoff", description)
        assert not should_emit_function_ac("handle_exponential_backoff", description)

    def test_prose_naming_function_explicitly_allows_ac(self):
        description = (
            "Implement apply_exponential_backoff(feature, now) to delay "
            "re-dispatch with doubling intervals."
        )
        assert should_emit_function_ac("apply_exponential_backoff", description)
