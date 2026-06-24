"""Tests verifying that should_emit_function_defined_ac gates Function-defined AC
emission to only cases where the symbol appears verbatim in feature prose.

Feature: f5b3f1a4 — Synthesizer MUST NOT invent exact function names it then
hard-gates on.

Tests cover:
1. should_emit_function_defined_ac: verbatim match → True; absent → False
2. concept_token_match: strips generic verb prefix, matches significant tokens
3. Integration: bob.spec_synthesizer is importable and the gate function works
4. reaper.handle_exponential_backoff exists and is callable
"""
from __future__ import annotations

import pytest

from bob.spec_synthesizer import should_emit_function_defined_ac, should_emit_function_ac
from bob.enhanced_verification import concept_token_match
import bob.reaper as reaper_module


class TestShouldEmitFunctionDefinedAc:
    """should_emit_function_defined_ac: only True when symbol appears verbatim in prose."""

    def test_verbatim_match_returns_true(self):
        assert should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "The feature implements apply_exponential_backoff to refuse re-dispatch.",
        ) is True

    def test_absent_symbol_returns_false(self):
        assert should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "Provides exponential backoff after reaper reset.",
        ) is False

    def test_synonym_does_not_count(self):
        assert should_emit_function_defined_ac(
            "apply_backoff",
            "The feature applies backoff logic after a reap event.",
        ) is False

    def test_partial_match_does_not_count(self):
        # "backoff" ≠ "apply_exponential_backoff"
        assert should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "Uses a backoff strategy to limit re-dispatch.",
        ) is False

    def test_exact_word_boundary_match(self):
        assert should_emit_function_defined_ac(
            "compute_score",
            "Calls compute_score to evaluate spec quality.",
        ) is True

    def test_substring_not_counted_as_verbatim(self):
        # "compute_scores" does NOT contain word-boundary "compute_score"
        assert should_emit_function_defined_ac(
            "compute_score",
            "Uses compute_scores to evaluate all specs.",
        ) is False

    def test_alias_should_emit_function_ac_is_same(self):
        # should_emit_function_ac is a public alias of should_emit_function_defined_ac
        result_a = should_emit_function_defined_ac("my_func", "Calls my_func here.")
        result_b = should_emit_function_ac("my_func", "Calls my_func here.")
        assert result_a == result_b is True

    def test_symbol_in_backtick_prose(self):
        assert should_emit_function_defined_ac(
            "handle_backoff",
            "The module exposes `handle_backoff` for use in the dispatch loop.",
        ) is True

    def test_symbol_as_identifier_in_prose(self):
        assert should_emit_function_defined_ac(
            "scan_pending",
            "scan_pending scans the DB for pending features.",
        ) is True

    def test_description_mentions_different_name(self):
        assert should_emit_function_defined_ac(
            "send_alert",
            "The feature calls fire_notification whenever threshold exceeded.",
        ) is False


class TestConceptTokenMatch:
    """concept_token_match: strips generic verb, matches significant tokens."""

    def test_apply_vs_handle_exponential_backoff(self):
        # Classic case from feature 99b78f59
        assert concept_token_match(
            "apply_exponential_backoff",
            "handle_exponential_backoff",
        ) is True

    def test_compute_vs_calculate_score(self):
        assert concept_token_match(
            "compute_quality_score",
            "calculate_quality_score",
        ) is True

    def test_run_vs_execute_validation_pipeline(self):
        # Two significant tokens required — "validation" + "pipeline"
        assert concept_token_match(
            "run_validation_pipeline",
            "execute_validation_pipeline",
        ) is True

    def test_different_concept_tokens_returns_false(self):
        assert concept_token_match(
            "apply_exponential_backoff",
            "schedule_task",
        ) is False

    def test_exact_same_name_returns_true(self):
        assert concept_token_match(
            "handle_exponential_backoff",
            "handle_exponential_backoff",
        ) is True

    def test_only_verb_prefix_returns_false(self):
        # Single verb prefix — not enough significant tokens
        assert concept_token_match("apply", "handle") is False

    def test_short_significant_token_returns_false(self):
        # Tokens of length < 3 don't count
        assert concept_token_match("do_it", "run_it") is False

    def test_partial_concept_overlap_returns_false(self):
        # "exponential" token present but "backoff" missing
        assert concept_token_match(
            "apply_exponential_backoff",
            "handle_exponential_delay",
        ) is False

    def test_returns_bool_not_truthy(self):
        result = concept_token_match("apply_backoff", "handle_backoff")
        assert isinstance(result, bool)

    def test_make_vs_build_hash_map(self):
        assert concept_token_match("make_hash_map", "build_hash_map") is True


class TestIntegrationBobSpecSynthesizer:
    """Integration: bob.spec_synthesizer module is wired up correctly."""

    def test_module_importable(self):
        import bob.spec_synthesizer as mod
        assert mod is not None

    def test_should_emit_function_defined_ac_present(self):
        from bob.spec_synthesizer import should_emit_function_defined_ac
        assert callable(should_emit_function_defined_ac)

    def test_should_emit_function_ac_alias_present(self):
        from bob.spec_synthesizer import should_emit_function_ac
        assert callable(should_emit_function_ac)

    def test_alias_identical_to_original(self):
        from bob.spec_synthesizer import (
            should_emit_function_defined_ac,
            should_emit_function_ac,
        )
        assert should_emit_function_ac is should_emit_function_defined_ac

    def test_gate_rejects_invented_name_not_in_prose(self):
        # Prose describes behaviour but doesn't name the function
        result = should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "Applies exponential backoff by doubling the wait window on each reap.",
        )
        assert result is False, (
            "The gate must return False when the exact symbol is absent from prose"
        )

    def test_gate_accepts_verbatim_name_in_prose(self):
        result = should_emit_function_defined_ac(
            "apply_exponential_backoff",
            "Calls apply_exponential_backoff to enforce re-dispatch throttling.",
        )
        assert result is True


class TestReaperHandleExponentialBackoff:
    """reaper.handle_exponential_backoff exists and is callable (AC: Function defined)."""

    def test_handle_exponential_backoff_callable(self):
        assert callable(reaper_module.handle_exponential_backoff)

    def test_handle_exponential_backoff_raises_on_none(self):
        with pytest.raises((ValueError, AttributeError, TypeError)):
            reaper_module.handle_exponential_backoff(None)

    def test_handle_exponential_backoff_raises_on_non_feature(self):
        with pytest.raises((ValueError, AttributeError, TypeError)):
            reaper_module.handle_exponential_backoff("not-a-feature")

    def test_backoff_decision_class_importable(self):
        from bob.reaper import BackoffDecision
        assert BackoffDecision is not None

    def test_apply_alias_matches_handle(self):
        # apply_exponential_backoff is an alias
        assert reaper_module.apply_exponential_backoff is reaper_module.handle_exponential_backoff
