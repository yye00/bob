"""Tests for the synthesizer 'MUST NOT invent exact function names' feature.

Feature: 1fdb257c-d1cc-42a3-a894-52c6d3c59fa9 — Synthesizer MUST NOT invent exact
function names it then hard-gates on. Function-defined ACs are contractual only
when the symbol appears verbatim in the feature prose.

Covers:
1. spec_synthesizer.should_emit_function_ac — verbatim-in-prose gate
2. enhanced_verification.check_criterion_with_concept_token_matching — fuzzy fallback
3. bob3.reaper.handle_exponential_backoff — the function that triggered the drain
"""
from __future__ import annotations

import pathlib
import pytest


class TestShouldEmitFunctionAcVerbatimGate:
    """should_emit_function_ac: only emit Function-defined AC when symbol is in prose."""

    def test_returns_true_when_symbol_verbatim_in_prose(self):
        from spec_synthesizer import should_emit_function_ac
        assert should_emit_function_ac(
            "apply_exponential_backoff",
            "The feature implements apply_exponential_backoff to refuse re-dispatch.",
        ) is True

    def test_returns_false_when_symbol_absent_from_prose(self):
        from spec_synthesizer import should_emit_function_ac
        assert should_emit_function_ac(
            "apply_exponential_backoff",
            "Provides exponential backoff after a reaper reset.",
        ) is False

    def test_returns_false_for_synonym_not_exact_symbol(self):
        from spec_synthesizer import should_emit_function_ac
        # "handle_exponential_backoff" is not the same as "apply_exponential_backoff"
        assert should_emit_function_ac(
            "apply_exponential_backoff",
            "Calls handle_exponential_backoff to delay retries.",
        ) is False

    def test_returns_true_for_word_boundary_match(self):
        from spec_synthesizer import should_emit_function_ac
        assert should_emit_function_ac(
            "check_stale_bytecode",
            "Uses check_stale_bytecode before launching.",
        ) is True

    def test_returns_false_for_partial_match_without_boundary(self):
        from spec_synthesizer import should_emit_function_ac
        # "check_stale_bytecodes" is not an exact boundary match for "check_stale_bytecode"
        assert should_emit_function_ac(
            "check_stale_bytecode",
            "Uses check_stale_bytecodes before launching.",
        ) is False

    def test_empty_symbol_returns_false(self):
        from spec_synthesizer import should_emit_function_ac
        assert should_emit_function_ac("", "some description") is False

    def test_empty_description_returns_false(self):
        from spec_synthesizer import should_emit_function_ac
        assert should_emit_function_ac("my_func", "") is False


class TestCheckCriterionWithConceptTokenMatching:
    """check_criterion_with_concept_token_matching: fuzzy demote on name equivalence."""

    def test_returns_true_for_exact_function_present(self, tmp_path):
        from enhanced_verification import check_criterion_with_concept_token_matching
        # Create a file with the exact function
        (tmp_path / "reaper.py").write_text("def apply_exponential_backoff(f, n): pass\n")
        result = check_criterion_with_concept_token_matching(
            "Function defined: reaper.apply_exponential_backoff",
            tmp_path,
        )
        assert result is True

    def test_returns_true_for_concept_equivalent_function(self, tmp_path):
        from enhanced_verification import check_criterion_with_concept_token_matching
        # handle_exponential_backoff matches concept tokens of apply_exponential_backoff
        (tmp_path / "reaper.py").write_text("def handle_exponential_backoff(f, n): pass\n")
        result = check_criterion_with_concept_token_matching(
            "Function defined: reaper.apply_exponential_backoff",
            tmp_path,
        )
        assert result is True

    def test_returns_false_when_no_concept_match(self, tmp_path):
        from enhanced_verification import check_criterion_with_concept_token_matching
        # schedule_task shares no concept tokens with apply_exponential_backoff
        (tmp_path / "reaper.py").write_text("def schedule_task(f): pass\n")
        result = check_criterion_with_concept_token_matching(
            "Function defined: reaper.apply_exponential_backoff",
            tmp_path,
        )
        assert result is False

    def test_non_function_defined_criterion_delegates(self, tmp_path):
        from enhanced_verification import check_criterion_with_concept_token_matching
        # File exists: criterion — just check it delegates (returns bool)
        result = check_criterion_with_concept_token_matching(
            "File exists: src/bob3/reaper.py",
            tmp_path,
        )
        assert isinstance(result, bool)

    def test_returns_bool_for_any_criterion(self, tmp_path):
        from enhanced_verification import check_criterion_with_concept_token_matching
        result = check_criterion_with_concept_token_matching(
            "pytest: tests/test_foo.py",
            tmp_path,
        )
        assert isinstance(result, bool)


class TestReaperHandleExponentialBackoff:
    """handle_exponential_backoff exists in bob3.reaper and is callable."""

    def test_function_is_defined(self):
        from bob3.reaper import handle_exponential_backoff
        assert callable(handle_exponential_backoff)

    def test_function_returns_backoff_decision(self):
        from bob3.reaper import handle_exponential_backoff, BackoffDecision
        import types

        # Build a minimal feature-like object
        feature = types.SimpleNamespace(
            id="test-feature",
            attempts=1,
            reap_count=1,
            status="nh_demoted",
        )
        import datetime
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        result = handle_exponential_backoff(feature, now)
        assert isinstance(result, BackoffDecision)

    def test_apply_exponential_backoff_alias_present(self):
        """apply_exponential_backoff must be an alias for handle_exponential_backoff."""
        import bob3.reaper as r
        assert hasattr(r, "apply_exponential_backoff")
        assert r.apply_exponential_backoff is r.handle_exponential_backoff
