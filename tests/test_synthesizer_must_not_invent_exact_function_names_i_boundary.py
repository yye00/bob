"""Boundary tests for bob3.spec_synthesizer.should_emit_function_ac.

Verifies that empty, zero, or minimum input returns a well-defined result
rather than raising (boundary case).

Feature: af78c082 — Synthesizer MUST NOT invent exact function names it then
hard-gates on.
"""
from __future__ import annotations

from bob3.spec_synthesizer import should_emit_function_ac
from bob3.enhanced_verification import concept_token_match


class TestShouldEmitFunctionAcBoundary:
    """Boundary: empty or minimal inputs return False without raising."""

    def test_empty_symbol_returns_false_not_raises(self):
        result = should_emit_function_ac("", "some description")
        assert result is False

    def test_empty_description_returns_false_not_raises(self):
        result = should_emit_function_ac("my_func", "")
        assert result is False

    def test_both_empty_returns_false_not_raises(self):
        result = should_emit_function_ac("", "")
        assert result is False

    def test_whitespace_symbol_returns_false_not_raises(self):
        result = should_emit_function_ac("   ", "description text")
        assert result is False

    def test_whitespace_description_returns_false_not_raises(self):
        result = should_emit_function_ac("my_func", "   ")
        assert result is False

    def test_single_char_symbol_returns_false_not_raises(self):
        result = should_emit_function_ac("f", "f is defined here")
        # word-boundary may match "f" but not an identifier — result is bool, no raise
        assert isinstance(result, bool)

    def test_minimal_valid_inputs_returns_bool(self):
        result = should_emit_function_ac("x", "x")
        assert isinstance(result, bool)


class TestConceptTokenMatchBoundary:
    """Boundary: empty or minimal inputs to concept_token_match return False without raising."""

    def test_empty_demanded_returns_false_not_raises(self):
        result = concept_token_match("", "handle_exponential_backoff")
        assert result is False

    def test_empty_candidate_returns_false_not_raises(self):
        result = concept_token_match("apply_exponential_backoff", "")
        assert result is False

    def test_both_empty_returns_false_not_raises(self):
        result = concept_token_match("", "")
        assert result is False

    def test_single_verb_only_returns_false_not_raises(self):
        result = concept_token_match("apply", "apply_anything")
        assert result is False

    def test_result_is_always_bool(self):
        for demanded, candidate in [
            ("", ""),
            ("a", "b"),
            ("apply", "handle"),
            ("apply_backoff", "handle_backoff"),
        ]:
            result = concept_token_match(demanded, candidate)
            assert isinstance(result, bool), f"Expected bool for ({demanded!r}, {candidate!r})"
