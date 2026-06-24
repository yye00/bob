"""Tests for emit_function_defined_ac verbatim-check guard.

Verifies that ``bob.spec_synthesizer.emit_function_defined_ac`` only emits
a ``Function defined:`` AC when the symbol appears verbatim in the feature
prose — and returns None when the prose does NOT name the symbol exactly.

This is the core protection against the synthesizer inventing an exact
function name that hard-gates implementers on a name they cannot predict
(the root cause of feature 99b78f59 being NH-demoted despite being correct).

Feature: 7a531943 — Synthesizer MUST NOT invent exact function names it then
hard-gates on.
"""
from __future__ import annotations

import pytest

from bob.spec_synthesizer import emit_function_defined_ac


class TestEmitFunctionDefinedAcVerbatimCheck:
    """emit_function_defined_ac: only emits AC when symbol is verbatim in prose."""

    def test_returns_ac_string_when_symbol_verbatim_in_prose(self):
        result = emit_function_defined_ac(
            "bob.reaper",
            "apply_exponential_backoff",
            "The feature calls apply_exponential_backoff to limit re-dispatch.",
        )
        assert result == "Function defined: bob.reaper.apply_exponential_backoff"

    def test_returns_none_when_symbol_absent_from_prose(self):
        result = emit_function_defined_ac(
            "bob.reaper",
            "apply_exponential_backoff",
            "Provides exponential backoff after reaper reset.",
        )
        assert result is None

    def test_returns_none_when_prose_uses_synonym(self):
        result = emit_function_defined_ac(
            "bob.reaper",
            "apply_backoff",
            "The feature applies backoff logic after a reap event.",
        )
        assert result is None

    def test_returns_none_when_only_partial_match(self):
        result = emit_function_defined_ac(
            "bob.reaper",
            "apply_exponential_backoff",
            "Uses a backoff strategy to limit re-dispatch.",
        )
        assert result is None

    def test_returns_ac_when_symbol_appears_verbatim_with_backticks(self):
        result = emit_function_defined_ac(
            "bob.spec_synthesizer",
            "emit_function_defined_ac",
            "Callers use `emit_function_defined_ac` to gate AC emission.",
        )
        assert result == "Function defined: bob.spec_synthesizer.emit_function_defined_ac"

    def test_word_boundary_prevents_substring_match(self):
        # "compute_scores" should NOT match the symbol "compute_score"
        result = emit_function_defined_ac(
            "bob.scorer",
            "compute_score",
            "Uses compute_scores to evaluate all specs.",
        )
        assert result is None

    def test_returns_ac_for_exact_boundary_match(self):
        result = emit_function_defined_ac(
            "bob.scorer",
            "compute_score",
            "Calls compute_score to evaluate spec quality.",
        )
        assert result == "Function defined: bob.scorer.compute_score"

    def test_returns_none_for_empty_prose(self):
        result = emit_function_defined_ac(
            "bob.reaper",
            "my_func",
            "",
        )
        assert result is None

    def test_return_type_is_str_or_none(self):
        present = emit_function_defined_ac("bob.mod", "foo", "foo is defined here")
        absent = emit_function_defined_ac("bob.mod", "bar", "unrelated description")
        assert isinstance(present, str)
        assert absent is None

    def test_module_and_symbol_in_returned_string(self):
        result = emit_function_defined_ac(
            "bob.mymodule",
            "my_symbol",
            "Expose my_symbol for external callers.",
        )
        assert result is not None
        assert "bob.mymodule" in result
        assert "my_symbol" in result


class TestEmitFunctionDefinedAcErrorPaths:
    """emit_function_defined_ac: invalid inputs raise expected exceptions."""

    def test_empty_module_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_function_defined_ac("", "my_func", "prose")

    def test_blank_module_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_function_defined_ac("   ", "my_func", "prose")

    def test_empty_symbol_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_function_defined_ac("bob.mod", "", "prose")

    def test_blank_symbol_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_function_defined_ac("bob.mod", "   ", "prose")

    def test_none_module_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_function_defined_ac(None, "my_func", "prose")  # type: ignore[arg-type]

    def test_none_symbol_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_function_defined_ac("bob.mod", None, "prose")  # type: ignore[arg-type]

    def test_none_description_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_function_defined_ac("bob.mod", "my_func", None)  # type: ignore[arg-type]

    def test_int_module_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_function_defined_ac(42, "my_func", "prose")  # type: ignore[arg-type]


class TestEmitFunctionDefinedAcIntegration:
    """Integration: emit_function_defined_ac is importable from bob.spec_synthesizer."""

    def test_function_importable(self):
        from bob.spec_synthesizer import emit_function_defined_ac as fn
        assert callable(fn)

    def test_real_world_case_invented_name_returns_none(self):
        # Simulates the 99b78f59 scenario: prose describes backoff behaviour
        # but doesn't mention the exact function name the synthesizer would invent.
        prose = (
            "Exponential backoff after reaper-reset: after a reaper reset, the system "
            "doubles the wait window on each successive failed attempt to prevent "
            "tight re-dispatch loops."
        )
        result = emit_function_defined_ac("bob.reaper", "apply_exponential_backoff", prose)
        assert result is None, (
            "The gate must return None when the exact symbol is absent from prose — "
            "the synthesizer must not invent 'apply_exponential_backoff' from the "
            "description alone."
        )

    def test_real_world_case_named_symbol_returns_ac(self):
        # If the prose DOES name the function, the AC is emitted.
        prose = (
            "Expose apply_exponential_backoff as the public entry point for "
            "backoff calculation."
        )
        result = emit_function_defined_ac("bob.reaper", "apply_exponential_backoff", prose)
        assert result == "Function defined: bob.reaper.apply_exponential_backoff"
