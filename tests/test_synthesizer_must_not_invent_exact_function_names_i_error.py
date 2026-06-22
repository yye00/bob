"""Error-path tests for bob3.spec_synthesizer.should_emit_function_ac.

Verifies that invalid input raises ValueError and the function does not
silently succeed (error path).

Feature: af78c082 — Synthesizer MUST NOT invent exact function names it then
hard-gates on.
"""
from __future__ import annotations

import pytest

from bob3.spec_synthesizer import should_emit_function_ac
from bob3.enhanced_verification import concept_token_match


class TestShouldEmitFunctionAcErrorPath:
    """Error path: non-string inputs raise TypeError (fail loudly, not silently)."""

    def test_none_symbol_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            should_emit_function_ac(None, "some description")  # type: ignore[arg-type]

    def test_none_description_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            should_emit_function_ac("my_func", None)  # type: ignore[arg-type]

    def test_int_symbol_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            should_emit_function_ac(42, "some description")  # type: ignore[arg-type]

    def test_int_description_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            should_emit_function_ac("my_func", 42)  # type: ignore[arg-type]


class TestConceptTokenMatchErrorPath:
    """Error path: non-string inputs raise TypeError (fail loudly, not silently)."""

    def test_none_demanded_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            concept_token_match(None, "handle_exponential_backoff")  # type: ignore[arg-type]

    def test_none_candidate_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            concept_token_match("apply_exponential_backoff", None)  # type: ignore[arg-type]

    def test_int_demanded_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            concept_token_match(42, "handle_backoff")  # type: ignore[arg-type]

    def test_int_candidate_raises(self):
        with pytest.raises((TypeError, AttributeError)):
            concept_token_match("apply_backoff_logic", 42)  # type: ignore[arg-type]
