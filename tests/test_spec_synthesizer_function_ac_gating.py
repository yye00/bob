"""Tests for Feature 7aa952bc — Synthesizer MUST NOT invent exact function names.

Verifies:
1. should_emit_function_defined_ac gates Function-defined AC emission to only
   cases where the symbol appears verbatim in feature prose.
2. extract_verbatim_symbols extracts identifiers that appear verbatim in prose.
3. Integration: bob3.spec_synthesizer exports both functions correctly.
4. reaper.handle_exponential_backoff exists and is callable.
"""
from __future__ import annotations

import pytest

from bob3.spec_synthesizer import (
    should_emit_function_defined_ac,
    extract_verbatim_symbols,
)
import bob3.reaper as reaper_module


class TestShouldEmitFunctionDefinedAcGating:
    """should_emit_function_defined_ac: only True when symbol appears verbatim in prose."""

    def test_verbatim_symbol_in_prose_returns_true(self):
        assert should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "The feature implements apply_exponential_backoff to limit re-dispatch.",
        ) is True

    def test_absent_symbol_returns_false(self):
        # Classic case: prose describes behavior but never names the exact function
        assert should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "Provides exponential backoff after reaper reset.",
        ) is False

    def test_synthesizer_must_not_invent_name_not_in_prose(self):
        # The synthesizer invented "apply_exponential_backoff" but prose only says "backoff"
        assert should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "Applies backoff by doubling the wait on each reaper cycle.",
        ) is False

    def test_word_boundary_respected(self):
        # "compute_scores" should not match "compute_score"
        assert should_emit_function_defined_ac(
            "compute_score",
            "Uses compute_scores to evaluate all specs.",
        ) is False

    def test_exact_word_boundary_match_succeeds(self):
        assert should_emit_function_defined_ac(
            "compute_score",
            "Calls compute_score to evaluate spec quality.",
        ) is True

    def test_camelcase_in_prose_not_matched_by_snake_name(self):
        assert should_emit_function_defined_ac(
            "apply_backoff",
            "The feature calls applyBackoff to throttle dispatch.",
        ) is False

    def test_symbol_as_first_word_in_prose(self):
        assert should_emit_function_defined_ac(
            "scan_pending",
            "scan_pending scans the DB for pending features.",
        ) is True

    def test_description_with_different_function_name(self):
        assert should_emit_function_defined_ac(
            "send_alert",
            "The feature calls fire_notification when threshold is exceeded.",
        ) is False

    def test_empty_symbol_returns_false(self):
        assert should_emit_function_defined_ac("", "Some prose") is False

    def test_blank_description_returns_false(self):
        assert should_emit_function_defined_ac("my_func", "   ") is False

    def test_non_string_symbol_raises_type_error(self):
        with pytest.raises(TypeError):
            should_emit_function_defined_ac(None, "some description")  # type: ignore

    def test_non_string_description_raises_type_error(self):
        with pytest.raises(TypeError):
            should_emit_function_defined_ac("my_func", 42)  # type: ignore


class TestExtractVerbatimSymbols:
    """extract_verbatim_symbols extracts Python identifiers from prose."""

    def test_extracts_function_name_from_prose(self):
        symbols = extract_verbatim_symbols(
            "Calls apply_exponential_backoff to limit re-dispatch."
        )
        assert "apply_exponential_backoff" in symbols

    def test_returns_list(self):
        result = extract_verbatim_symbols("Call my_func here.")
        assert isinstance(result, list)

    def test_empty_string_returns_empty_list(self):
        assert extract_verbatim_symbols("") == []

    def test_blank_string_returns_empty_list(self):
        assert extract_verbatim_symbols("   ") == []

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError):
            extract_verbatim_symbols(42)  # type: ignore

    def test_deduplicates_tokens(self):
        symbols = extract_verbatim_symbols("call foo and call foo again")
        assert symbols.count("foo") == 1

    def test_preserves_order_of_first_occurrence(self):
        symbols = extract_verbatim_symbols("alpha beta gamma")
        assert symbols.index("alpha") < symbols.index("beta") < symbols.index("gamma")

    def test_multi_word_function_name_extracted(self):
        symbols = extract_verbatim_symbols(
            "The handle_exponential_backoff function applies backoff logic."
        )
        assert "handle_exponential_backoff" in symbols

    def test_snake_case_identifier_extracted(self):
        symbols = extract_verbatim_symbols("Use check_startup_crash_exemption here.")
        assert "check_startup_crash_exemption" in symbols

    def test_numbers_in_identifier_extracted(self):
        symbols = extract_verbatim_symbols("Calls do_thing2 to process.")
        assert "do_thing2" in symbols


class TestIntegrationSpecSynthesizerFunctionAcGating:
    """Integration: bob3.spec_synthesizer module exports gating functions correctly."""

    def test_should_emit_function_defined_ac_importable(self):
        from bob3.spec_synthesizer import should_emit_function_defined_ac
        assert callable(should_emit_function_defined_ac)

    def test_extract_verbatim_symbols_importable(self):
        from bob3.spec_synthesizer import extract_verbatim_symbols
        assert callable(extract_verbatim_symbols)

    def test_gate_rejects_invented_symbol_absent_from_prose(self):
        # This is the failure mode from feature 99b78f59
        result = should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "Applies exponential backoff by doubling the wait window on each reap.",
        )
        assert result is False

    def test_extract_then_gate_positive_flow(self):
        prose = "Calls handle_exponential_backoff to enforce throttling."
        symbols = extract_verbatim_symbols(prose)
        assert "handle_exponential_backoff" in symbols
        assert should_emit_function_defined_ac("handle_exponential_backoff", prose) is True

    def test_extract_then_gate_negative_flow(self):
        prose = "Applies exponential backoff by doubling the wait window on each reap."
        symbols = extract_verbatim_symbols(prose)
        # The invented name is NOT in the symbols extracted from prose
        assert "apply_exponential_backoff" not in symbols
        assert should_emit_function_defined_ac("apply_exponential_backoff", prose) is False

    def test_module_is_bob3_spec_synthesizer(self):
        import bob3.spec_synthesizer as mod
        assert mod.__name__ == "bob3.spec_synthesizer"


class TestReaperHandleExponentialBackoff:
    """reaper.handle_exponential_backoff exists and is callable (F-7aa952bc AC)."""

    def test_handle_exponential_backoff_is_callable(self):
        assert callable(reaper_module.handle_exponential_backoff)

    def test_apply_alias_present(self):
        # apply_exponential_backoff is an alias for handle_exponential_backoff
        assert hasattr(reaper_module, "apply_exponential_backoff")
        assert callable(reaper_module.apply_exponential_backoff)

    def test_aliases_are_same_object(self):
        assert (
            reaper_module.apply_exponential_backoff
            is reaper_module.handle_exponential_backoff
        )

    def test_handle_exponential_backoff_raises_on_invalid_input(self):
        with pytest.raises((ValueError, AttributeError, TypeError)):
            reaper_module.handle_exponential_backoff(None)
