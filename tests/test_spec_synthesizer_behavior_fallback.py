"""Tests for synthesizer behavior fallback when prose does NOT name a function.

Feature 2bebad63: Synthesizer MUST NOT invent exact function names it then
hard-gates on — Function-defined ACs are contractual only when the symbol
appears verbatim in the feature prose.

These tests verify that:
- emit_function_defined_ac_only_when_prose_names_symbol returns None when
  the prose does NOT contain the symbol (caller must use behavior AC instead)
- It returns the AC string when the prose DOES contain the symbol verbatim
- The concept-token equivalence in enhanced_verification demotes rather than
  hard-fails when a functionally-equivalent symbol is present
"""
from __future__ import annotations

import pytest

from bob3.spec_synthesizer import (
    emit_function_defined_ac_only_when_prose_names_symbol,
    should_emit_function_defined_ac,
    emit_function_defined_ac,
)
from bob3.enhanced_verification import concept_token_match


class TestEmitFunctionDefinedAcOnlyWhenProseNamesSymbol:
    """Tests for the canonical synthesizer guard function."""

    def test_returns_ac_when_symbol_verbatim_in_prose_as_identifier(self):
        """When prose contains the exact identifier token, emit the AC."""
        result = emit_function_defined_ac_only_when_prose_names_symbol(
            "bob3.reaper",
            "apply_exponential_backoff",
            "Call apply_exponential_backoff to limit re-dispatch after reset.",
        )
        # "apply_exponential_backoff" is verbatim in the description → should emit
        assert result == "Function defined: bob3.reaper.apply_exponential_backoff"

    def test_returns_none_when_symbol_not_in_prose(self):
        """When prose mentions concept but not the exact symbol, return None."""
        result = emit_function_defined_ac_only_when_prose_names_symbol(
            "bob3.reaper",
            "apply_exponential_backoff",
            "Use exponential backoff after reset to limit re-dispatch frequency.",
        )
        # The prose describes the behavior but does NOT name apply_exponential_backoff verbatim
        assert result is None

    def test_returns_ac_string_when_symbol_verbatim_in_prose(self):
        """When the prose explicitly names the symbol, emit the AC."""
        description = (
            "The function handle_exponential_backoff computes delays after reset."
        )
        result = emit_function_defined_ac_only_when_prose_names_symbol(
            "bob3.reaper",
            "handle_exponential_backoff",
            description,
        )
        assert result == "Function defined: bob3.reaper.handle_exponential_backoff"

    def test_returns_none_for_generic_description_with_no_symbol(self):
        """Pure prose descriptions without identifier tokens yield None."""
        result = emit_function_defined_ac_only_when_prose_names_symbol(
            "bob3.orchestrator",
            "run_feature_batch",
            "The orchestrator runs features in parallel batches.",
        )
        assert result is None

    def test_raises_type_error_on_non_string_module(self):
        with pytest.raises(TypeError):
            emit_function_defined_ac_only_when_prose_names_symbol(
                42, "my_func", "description"  # type: ignore[arg-type]
            )

    def test_raises_type_error_on_non_string_symbol(self):
        with pytest.raises(TypeError):
            emit_function_defined_ac_only_when_prose_names_symbol(
                "bob3.mod", None, "description"  # type: ignore[arg-type]
            )

    def test_raises_value_error_on_blank_symbol(self):
        with pytest.raises(ValueError):
            emit_function_defined_ac_only_when_prose_names_symbol(
                "bob3.mod", "   ", "description"
            )

    def test_raises_value_error_on_blank_module(self):
        with pytest.raises(ValueError):
            emit_function_defined_ac_only_when_prose_names_symbol(
                "", "my_func", "description"
            )

    def test_delegates_to_emit_function_defined_ac(self):
        """Verifies the function delegates correctly and produces consistent output."""
        module = "bob3.spec_synthesizer"
        symbol = "emit_function_defined_ac_only_when_prose_names_symbol"
        description = (
            f"The synthesizer guard emit_function_defined_ac_only_when_prose_names_symbol "
            f"prevents name invention."
        )
        result = emit_function_defined_ac_only_when_prose_names_symbol(
            module, symbol, description
        )
        expected = emit_function_defined_ac(module, symbol, description)
        assert result == expected


class TestConceptTokenMatchForBehaviorFallback:
    """Tests for concept-token matching that enables behavior-based equivalence."""

    def test_apply_vs_handle_exponential_backoff(self):
        """The canonical example from the feature description."""
        assert concept_token_match(
            "apply_exponential_backoff", "handle_exponential_backoff"
        ) is True

    def test_exact_match_passes(self):
        """Exact symbol match always passes."""
        assert concept_token_match(
            "apply_exponential_backoff", "apply_exponential_backoff"
        ) is True

    def test_unrelated_symbols_do_not_match(self):
        """Completely unrelated symbols return False."""
        assert concept_token_match("apply_exponential_backoff", "schedule_task") is False

    def test_generic_verb_only_does_not_match(self):
        """Generic verbs stripped, no significant tokens remain → False."""
        assert concept_token_match("apply", "handle") is False

    def test_run_vs_execute_for_batch(self):
        """Different verbs with same concept tokens match."""
        assert concept_token_match("run_feature_batch", "execute_feature_batch") is True

    def test_get_vs_compute_backoff_delay(self):
        """get_ vs compute_ are both generic verbs; 'backoff_delay' concept tokens match."""
        assert concept_token_match("get_backoff_delay", "compute_backoff_delay") is True

    def test_missing_concept_token_does_not_match(self):
        """When candidate lacks significant tokens from demanded, no match."""
        assert concept_token_match("apply_exponential_backoff", "apply_linear_delay") is False


class TestShouldEmitFunctionDefinedAcVerbatim:
    """Tests for the verbatim-in-prose check underlying the guard."""

    def test_verbatim_symbol_in_prose_returns_true(self):
        assert should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "Call apply_exponential_backoff to limit re-dispatch.",
        ) is True

    def test_symbol_absent_from_prose_returns_false(self):
        assert should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "Use exponential backoff after reset.",
        ) is False

    def test_partial_match_not_sufficient(self):
        """'exponential_backoff' is NOT 'apply_exponential_backoff'."""
        assert should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "The exponential_backoff logic applies after reset.",
        ) is False
