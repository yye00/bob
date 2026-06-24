"""Tests for bob.prose_ac_demoter (F-R7-578).

Key regression cases:
  A1 — Prose AC quoting "pytest:" mid-sentence must DEMOTE (not hard-fail).
  A2 — Real "pytest: tests/foo.py" criterion must ROUTE to structural (not demote).
  A3 — integration-prose body with "continues to" / "whole-suite" must DEMOTE.
  A4 — Real "file exists:" criterion hard-fails when file missing (structural, not demoted).
"""

import pytest

from bob.prose_ac_demoter import (
    is_structural_prefix_match,
    is_prose_ac,
    demote_if_prose,
    prose_connector_registry,
)


class TestIsStructuralPrefixMatch:
    def test_pytest_criterion_at_start_is_structural(self):
        """A criterion starting with 'pytest:' is structural."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_pytest_quoted_mid_sentence_is_not_structural(self):
        """A1: prose AC quoting 'pytest:' mid-sentence must return False (not structural)."""
        criterion = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists; "
            "returns empty set when feature has no pytest ACs"
        )
        assert is_structural_prefix_match(criterion) is False

    def test_file_exists_at_start_is_structural(self):
        assert is_structural_prefix_match("file exists: src/bob/foo.py") is True

    def test_function_defined_at_start_is_structural(self):
        assert is_structural_prefix_match("function defined: bob.foo.bar") is True

    def test_integration_at_start_is_structural(self):
        assert is_structural_prefix_match("integration: bob.orchestrator") is True

    def test_leading_whitespace_stripped(self):
        """Leading whitespace is stripped before prefix check."""
        assert is_structural_prefix_match("  pytest: tests/foo.py") is True

    def test_behavior_prefix_is_not_structural(self):
        """behavior: prefix is prose, not structural."""
        assert is_structural_prefix_match("behavior: some description") is False

    def test_none_returns_false(self):
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]

    def test_empty_string_returns_false(self):
        assert is_structural_prefix_match("") is False

    def test_case_insensitive_prefix(self):
        """Prefix check is case-insensitive."""
        assert is_structural_prefix_match("Pytest: tests/foo.py") is True
        assert is_structural_prefix_match("FILE EXISTS: src/x.py") is True


class TestIsProseAc:
    def test_behavior_ac_is_prose(self):
        """behavior: AC is prose."""
        assert is_prose_ac("behavior: returns a list of strings") is True

    def test_pytest_ac_is_not_prose(self):
        """pytest: AC is not prose — it is structural/executable."""
        assert is_prose_ac("pytest: tests/test_foo.py") is False

    def test_file_exists_is_not_prose(self):
        assert is_prose_ac("file exists: src/bar.py") is False

    def test_prose_quoting_pytest_mid_sentence_is_prose(self):
        """A1 regression: prose AC quoting 'pytest:' mid-sentence is still prose."""
        criterion = (
            "behavior: collect_feature_test_paths returns entries with prefix 'pytest:'"
        )
        assert is_prose_ac(criterion) is True

    def test_function_implemented_is_not_prose(self):
        """'function implemented' is a keyword marker → not prose."""
        assert is_prose_ac("the function implemented is correct") is False

    def test_none_is_treated_as_prose(self):
        """Non-string input is treated as prose (unexecutable)."""
        assert is_prose_ac(None) is True  # type: ignore[arg-type]


class TestDemoteIfProse:
    def test_prose_ac_returns_passing_tuple(self):
        """Prose AC returns (True, reason)."""
        result = demote_if_prose("behavior: describe something")
        assert result is not None
        passed, reason = result
        assert passed is True
        assert isinstance(reason, str)
        assert len(reason) > 0

    def test_real_pytest_ac_returns_none(self):
        """Real pytest: AC returns None (must be run, not demoted)."""
        result = demote_if_prose("pytest: tests/test_foo.py")
        assert result is None

    def test_file_exists_returns_none(self):
        """file exists: AC returns None (structural, must verify)."""
        result = demote_if_prose("file exists: src/x.py")
        assert result is None

    def test_prose_quoting_pytest_demotes(self):
        """A1 regression: prose AC quoting 'pytest:' mid-sentence must demote."""
        criterion = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists; "
            "returns empty set when feature has no pytest ACs"
        )
        result = demote_if_prose(criterion)
        assert result is not None
        passed, reason = result
        assert passed is True


class TestProseConnectorRegistry:
    def test_registry_returns_frozenset(self):
        result = prose_connector_registry()
        assert isinstance(result, frozenset)

    def test_registry_contains_continues_to(self):
        """'continues to' must be in registry (15d1ac4f regression token)."""
        assert "continues to" in prose_connector_registry()

    def test_registry_contains_separately(self):
        assert "separately" in prose_connector_registry()

    def test_registry_contains_invariant(self):
        assert "invariant" in prose_connector_registry()

    def test_registry_contains_whole_suite(self):
        assert "whole-suite" in prose_connector_registry()

    def test_registry_contains_no_behavior(self):
        assert "no behavior" in prose_connector_registry()

    def test_registry_contains_original_tokens(self):
        """Original c09e9e64 tokens must still be present."""
        registry = prose_connector_registry()
        assert "all" in registry
        assert "every" in registry
        assert "route" in registry
        assert "through" in registry
