"""Tests for bob3.enhanced_verification.concept_token_match.

Verifies that the verifier correctly demotes a ``Function defined:`` AC from
hard-fail to PASS-with-WARNING when the demanded symbol is absent but a
concept-token-equivalent function exists.

Feature: af78c082 — Synthesizer MUST NOT invent exact function names it then
hard-gates on.
"""
from __future__ import annotations

import pytest

from bob3.enhanced_verification import concept_token_match


class TestConceptTokenMatchEquivalentNames:
    """concept_token_match returns True for semantically equivalent function names."""

    def test_apply_vs_handle_exponential_backoff(self):
        # The canonical bob63-drain case: demanded invented name vs implementer's name
        assert concept_token_match("apply_exponential_backoff", "handle_exponential_backoff")

    def test_handle_vs_apply_exponential_backoff(self):
        assert concept_token_match("handle_exponential_backoff", "apply_exponential_backoff")

    def test_compute_vs_calculate_quality_score(self):
        assert concept_token_match("compute_quality_score", "calculate_quality_score")

    def test_run_vs_execute_validation_check(self):
        assert concept_token_match("run_validation_check", "execute_validation_check")

    def test_get_vs_resolve_feature_status(self):
        assert concept_token_match("get_feature_status", "resolve_feature_status")

    def test_make_vs_build_retry_context(self):
        assert concept_token_match("make_retry_context", "build_retry_context")

    def test_different_verb_same_concept(self):
        # do_ vs perform_ — both in generic prefix set
        assert concept_token_match("do_circuit_breaker_check", "perform_circuit_breaker_check")


class TestConceptTokenMatchNonEquivalentNames:
    """concept_token_match returns False when names share no concept tokens."""

    def test_completely_different_names(self):
        assert not concept_token_match("apply_exponential_backoff", "schedule_task")

    def test_single_shared_token_insufficient(self):
        # "backoff" alone is not enough — need both tokens
        assert not concept_token_match("apply_exponential_backoff", "handle_backoff_state")

    def test_no_shared_tokens_at_all(self):
        assert not concept_token_match("reset_feature_state", "compute_quality_score")


class TestConceptTokenMatchEdgeCases:
    """Edge cases for concept_token_match."""

    def test_empty_demanded_returns_false(self):
        assert not concept_token_match("", "handle_exponential_backoff")

    def test_empty_candidate_returns_false(self):
        assert not concept_token_match("apply_exponential_backoff", "")

    def test_both_empty_returns_false(self):
        assert not concept_token_match("", "")

    def test_short_single_token_returns_false(self):
        # Single short word → fewer than 2 significant tokens → no match possible
        assert not concept_token_match("reap", "reap_feature")

    def test_single_verb_only_returns_false(self):
        # "apply" alone → stripped → 0 significant tokens → False
        assert not concept_token_match("apply", "apply_anything")

    def test_two_short_tokens_filtered_out(self):
        # tokens < 3 chars are filtered; "do_it" → significant=[] → False
        assert not concept_token_match("do_it", "execute_it_now")

    def test_exact_same_name_matches(self):
        assert concept_token_match("apply_exponential_backoff", "apply_exponential_backoff")

    def test_candidate_longer_still_matches(self):
        # demanded tokens are a subset of candidate's name
        assert concept_token_match(
            "apply_exponential_backoff",
            "handle_exponential_backoff_and_reset",
        )

    def test_case_insensitive_matching(self):
        assert concept_token_match("apply_ExPonential_BackOff", "handle_exponential_backoff")


class TestConceptTokenMatchSignificantTokenThreshold:
    """concept_token_match requires ≥2 significant tokens after verb stripping."""

    def test_two_significant_tokens_required(self):
        # "apply_foo_bar" → tokens [foo, bar] (both ≥3 chars) → 2 significant → ok
        assert concept_token_match("apply_foo_bar", "handle_foo_bar")

    def test_one_significant_token_after_stripping_returns_false(self):
        # "apply_fo" → after stripping apply → [fo] (len 2 < 3) → 0 significant → False
        assert not concept_token_match("apply_fo", "handle_fo_bar")

    def test_demanded_with_two_short_tokens_after_strip(self):
        # "run_ab_cd" → [ab, cd] → filtered by len<3 → 0 significant → False
        assert not concept_token_match("run_ab_cd", "execute_ab_cd_now")
