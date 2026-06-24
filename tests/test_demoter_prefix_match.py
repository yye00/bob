"""Tests for bob.demoter.is_structural_prefix_match and get_prose_connectors (F-9ed93698).

Verifies the public API exposed via bob.demoter for structural prefix matching
and the prose connector registry.  This file covers the four key regression cases
documented in the feature description:
  A1: 15d1ac4f prose-quoting-pytest → demotes (returns False)
  A2: 15d1ac4f integration-prose    → matched by registry token
  A3: real pytest criterion          → hard-match (returns True)
  A4: file exists criterion          → hard-match (returns True)
"""

import pytest

from bob.demoter import is_structural_prefix_match, get_prose_connectors


class TestIsStructuralPrefixMatchA1ProseQuotingPytest:
    """A1 regression: prose AC that quotes 'pytest:' mid-sentence must NOT match."""

    def test_15d1ac4f_prose_criterion_returns_false(self):
        """Full 15d1ac4f prose criterion quoting 'pytest:' mid-sentence demotes."""
        criterion = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists; "
            "returns empty set when feature has no pytest ACs"
        )
        assert is_structural_prefix_match(criterion) is False

    def test_short_prose_quoting_pytest_mid_sentence(self):
        """Short prose mentioning 'pytest:' as a quoted term must return False."""
        assert is_structural_prefix_match("behavior: entries with prefix 'pytest:'") is False

    def test_pytest_mid_word_does_not_match(self):
        """'pytest:' in a sentence body (not at start) does not match."""
        assert is_structural_prefix_match("some prefix is pytest: not at start") is False


class TestIsStructuralPrefixMatchA3RealPytest:
    """A3: real pytest criterion at start of string routes to structural."""

    def test_pytest_at_start_is_structural(self):
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_pytest_with_whitespace_stripped(self):
        """Leading whitespace is stripped before prefix check."""
        assert is_structural_prefix_match("  pytest: tests/foo.py") is True

    def test_pytest_case_insensitive(self):
        assert is_structural_prefix_match("Pytest: tests/foo.py") is True


class TestIsStructuralPrefixMatchA4FileExists:
    """A4: 'file exists:' criterion routes to structural."""

    def test_file_exists_at_start_is_structural(self):
        assert is_structural_prefix_match("file exists: tests/foo.py") is True

    def test_file_exists_case_insensitive(self):
        assert is_structural_prefix_match("FILE EXISTS: src/x.py") is True


class TestIsStructuralPrefixMatchOtherPrefixes:
    def test_function_defined_at_start(self):
        assert is_structural_prefix_match("function defined: bob.demoter.is_structural_prefix_match") is True

    def test_class_defined_at_start(self):
        assert is_structural_prefix_match("class defined: bob.SomeClass") is True

    def test_integration_at_start(self):
        assert is_structural_prefix_match("integration: bob.version_probe") is True

    def test_behavior_is_not_structural(self):
        assert is_structural_prefix_match("behavior: some description") is False

    def test_empty_string(self):
        assert is_structural_prefix_match("") is False

    def test_none_input(self):
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]

    def test_integer_input(self):
        assert is_structural_prefix_match(42) is False  # type: ignore[arg-type]


class TestGetProseConnectorsA2IntegrationBody:
    """A2 regression: 15d1ac4f integration body must be covered by the registry."""

    def test_returns_frozenset(self):
        assert isinstance(get_prose_connectors(), frozenset)

    def test_15d1ac4f_integration_body_covered(self):
        """The 15d1ac4f integration AC body must contain at least one registry token."""
        body = (
            "regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately "
            "(no behavior regression for the cross-feature regression detection path)"
        )
        registry = get_prose_connectors()
        assert any(token in body for token in registry), (
            f"No registry token matched the 15d1ac4f integration body; registry={registry!r}"
        )

    def test_c09e9e64_original_tokens_present(self):
        registry = get_prose_connectors()
        for token in ("all", "every", "route", "through", ";", "no direct"):
            assert token in registry, f"Missing original token: {token!r}"

    def test_15d1ac4f_regression_tokens_present(self):
        registry = get_prose_connectors()
        for token in ("continues to", "separately", "invariant", "whole-suite", "no behavior"):
            assert token in registry, f"Missing 15d1ac4f token: {token!r}"

    def test_policy_phrase_tokens_present(self):
        registry = get_prose_connectors()
        for token in ("maintains", "preserves", "ensures", "guarantees", "unaffected", "regression"):
            assert token in registry, f"Missing policy token: {token!r}"

    def test_registry_is_non_empty(self):
        assert len(get_prose_connectors()) > 0

    def test_registry_is_immutable(self):
        registry = get_prose_connectors()
        with pytest.raises((AttributeError, TypeError)):
            registry.add("new_token")  # type: ignore[union-attr]
