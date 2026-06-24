"""Tests for feature 76be57c4 — Synthesizer MUST NOT invent exact function names.

Verifies the two-halves fix:
  HALF 1 — spec_synthesizer.should_emit_function_defined_ac gates exact-name ACs
            on verbatim symbol presence in the feature prose.
  HALF 2 — enhanced_verification.concept_token_match + check_function_defined_with_concept_tokens
            demote absent-but-equivalent function names to PASS-with-warning
            rather than hard-failing.
"""
from __future__ import annotations

import pytest

from bob.spec_synthesizer import should_emit_function_defined_ac, emit_function_defined_ac
from bob.enhanced_verification import concept_token_match, check_function_name_equivalence


# ---------------------------------------------------------------------------
# HALF 1: synthesizer only emits Function-defined ACs when the symbol is
#         verbatim in the prose description.
# ---------------------------------------------------------------------------

class TestShouldEmitFunctionDefinedAc:
    """should_emit_function_defined_ac — word-boundary verbatim match guard."""

    def test_symbol_present_verbatim_returns_true(self):
        desc = "Call apply_exponential_backoff to limit re-dispatch frequency."
        assert should_emit_function_defined_ac("apply_exponential_backoff", desc) is True

    def test_symbol_absent_from_prose_returns_false(self):
        # The synthesizer invented a name that is NOT in the description.
        desc = "Apply exponential backoff when the reaper resets a feature."
        assert should_emit_function_defined_ac("apply_exponential_backoff", desc) is False

    def test_partial_match_is_not_a_verbatim_match(self):
        desc = "Call backoff to limit re-dispatch."
        # "apply_exponential_backoff" != "backoff"
        assert should_emit_function_defined_ac("apply_exponential_backoff", desc) is False

    def test_word_boundary_respected_prefix(self):
        # "my_func" should NOT match when embedded as "my_func_extra"
        desc = "Use my_func_extra to compute the result."
        assert should_emit_function_defined_ac("my_func", desc) is False

    def test_word_boundary_respected_suffix(self):
        # "func" should NOT match inside "my_func"
        desc = "Call my_func to process data."
        # "func" appears as part of "my_func" — word-boundary should not match
        assert should_emit_function_defined_ac("func", desc) is False

    def test_exact_word_present_returns_true(self):
        desc = "The handle_backoff function manages retry timing."
        assert should_emit_function_defined_ac("handle_backoff", desc) is True

    def test_empty_symbol_returns_false(self):
        assert should_emit_function_defined_ac("", "some description") is False

    def test_empty_description_returns_false(self):
        assert should_emit_function_defined_ac("my_func", "") is False

    def test_non_string_symbol_raises(self):
        with pytest.raises(TypeError):
            should_emit_function_defined_ac(123, "description")  # type: ignore[arg-type]

    def test_non_string_description_raises(self):
        with pytest.raises(TypeError):
            should_emit_function_defined_ac("func", None)  # type: ignore[arg-type]


class TestEmitFunctionDefinedAc:
    """emit_function_defined_ac — returns the AC string or None."""

    def test_symbol_in_prose_emits_ac_string(self):
        desc = "Call should_refuse_redispatch to block early re-dispatch."
        result = emit_function_defined_ac("bob.reaper", "should_refuse_redispatch", desc)
        assert result == "Function defined: bob.reaper.should_refuse_redispatch"

    def test_symbol_not_in_prose_returns_none(self):
        # The synthesizer invented "apply_exponential_backoff"; prose only says "exponential backoff"
        desc = "Apply exponential backoff when a feature is repeatedly reaped."
        result = emit_function_defined_ac("bob.reaper", "apply_exponential_backoff", desc)
        assert result is None

    def test_empty_module_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_function_defined_ac("", "my_func", "some description with my_func")

    def test_empty_symbol_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_function_defined_ac("bob.reaper", "", "some description")

    def test_none_module_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_function_defined_ac(None, "func", "desc")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# HALF 2: verification layer — concept-token match demotes absent-but-equivalent
#         function names to PASS-with-warning rather than hard-fail.
# ---------------------------------------------------------------------------

class TestConceptTokenMatch:
    """concept_token_match — the exponential-backoff false-negative case."""

    def test_original_false_negative_case(self):
        # The canonical motivating case: synthesizer demanded apply_exponential_backoff
        # but the implementer used handle_exponential_backoff. Both contain the
        # significant tokens {exponential, backoff} → should match.
        assert concept_token_match("apply_exponential_backoff", "handle_exponential_backoff") is True

    def test_totally_unrelated_functions_return_false(self):
        assert concept_token_match("apply_exponential_backoff", "schedule_task") is False

    def test_exact_same_name_returns_true(self):
        # Needs >= 2 significant tokens after verb-prefix strip
        assert concept_token_match("apply_exponential_backoff", "apply_exponential_backoff") is True

    def test_different_verb_prefix_same_concept(self):
        assert concept_token_match("compute_quality_score", "run_quality_score") is True

    def test_shared_single_significant_token_returns_false(self):
        # Only one significant token (< 2 required) → False
        assert concept_token_match("do_backoff", "handle_backoff") is False

    def test_empty_demanded_returns_false(self):
        assert concept_token_match("", "handle_exponential_backoff") is False

    def test_empty_candidate_returns_false(self):
        assert concept_token_match("apply_exponential_backoff", "") is False

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError):
            concept_token_match(None, "func")  # type: ignore[arg-type]


class TestCheckFunctionNameEquivalence:
    """check_function_name_equivalence — public alias for concept_token_match."""

    def test_delegates_to_concept_token_match_true(self):
        assert check_function_name_equivalence(
            "apply_exponential_backoff", "handle_exponential_backoff"
        ) is True

    def test_delegates_to_concept_token_match_false(self):
        assert check_function_name_equivalence(
            "apply_exponential_backoff", "get_features_list"
        ) is False

    def test_returns_bool(self):
        result = check_function_name_equivalence("compute_score", "run_score_engine")
        assert isinstance(result, bool)
