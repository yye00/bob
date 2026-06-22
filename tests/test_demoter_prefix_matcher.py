"""Tests for bob3.demoter_prefix_matcher — F-b617e500.

Verifies that:
- is_structural_prefix_match uses START-OF-STRING matching, not substring.
- A prose AC quoting "pytest:" mid-sentence DEMOTES (returns False).
- A real "pytest: tests/foo.py" criterion is structural (returns True).
- get_prose_connectors returns the expected policy connector tokens.
"""
import pytest

from bob3.demoter_prefix_matcher import is_structural_prefix_match, get_prose_connectors


class TestIsStructuralPrefixMatchStartOfString:
    def test_prose_quoting_pytest_mid_sentence_demotes(self):
        """A prose AC that quotes 'pytest:' mid-sentence must NOT match as structural."""
        ac = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists"
        )
        assert is_structural_prefix_match(ac) is False

    def test_real_pytest_criterion_is_structural(self):
        """A real 'pytest: tests/foo.py' criterion must match as structural."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_file_exists_criterion_is_structural(self):
        """A 'file exists:' criterion must match as structural."""
        assert is_structural_prefix_match("file exists: src/bob3/demoter_prefix_matcher.py") is True

    def test_function_defined_criterion_is_structural(self):
        """A 'function defined:' criterion must match as structural."""
        assert is_structural_prefix_match("function defined: bob3.demoter_prefix_matcher.is_structural_prefix_match") is True

    def test_integration_criterion_is_structural(self):
        """An 'integration:' criterion must match as structural."""
        assert is_structural_prefix_match("integration: bob3.criterion_demoter") is True

    def test_prose_with_file_exists_mid_sentence_demotes(self):
        """Prose mentioning 'file exists:' mid-sentence must NOT match as structural."""
        ac = "behavior: the function checks file exists: src/foo.py before proceeding"
        assert is_structural_prefix_match(ac) is False

    def test_leading_whitespace_stripped(self):
        """Leading whitespace must be stripped before prefix comparison."""
        assert is_structural_prefix_match("  pytest: tests/bar.py") is True
        assert is_structural_prefix_match("\tfile exists: src/x.py") is True

    def test_case_insensitive_match(self):
        """Prefix matching must be case-insensitive."""
        assert is_structural_prefix_match("PYTEST: tests/bar.py") is True
        assert is_structural_prefix_match("File Exists: src/x.py") is True

    def test_none_returns_false(self):
        """None input must return False."""
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]

    def test_empty_string_returns_false(self):
        """Empty string must return False."""
        assert is_structural_prefix_match("") is False

    def test_non_string_returns_false(self):
        """Non-string types must return False, not raise."""
        assert is_structural_prefix_match(42) is False  # type: ignore[arg-type]
        assert is_structural_prefix_match([]) is False  # type: ignore[arg-type]


class TestGetProseConnectors:
    def test_returns_frozenset(self):
        """get_prose_connectors must return a frozenset."""
        result = get_prose_connectors()
        assert isinstance(result, frozenset)

    def test_covers_original_c09e9e64_tokens(self):
        """Registry must cover the original c09e9e64 connector tokens."""
        reg = get_prose_connectors()
        for token in ("all", "every", "route", "through", ";", "no direct"):
            assert token in reg, f"Expected token {token!r} in registry"

    def test_covers_15d1ac4f_regression_tokens(self):
        """Registry must cover the 15d1ac4f regression connector tokens."""
        reg = get_prose_connectors()
        for token in ("continues to", "separately", "invariant", "whole-suite", "no behavior"):
            assert token in reg, f"Expected token {token!r} in registry"

    def test_covers_policy_phrases(self):
        """Registry must cover additional policy-prose tokens."""
        reg = get_prose_connectors()
        for token in ("maintains", "preserves", "ensures", "guarantees", "unaffected"):
            assert token in reg, f"Expected token {token!r} in registry"

    def test_integration_body_matches_connector(self):
        """The 15d1ac4f integration body must contain at least one connector token."""
        integration_body = (
            "regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately (no behavior regression "
            "for the cross-feature regression detection path)"
        )
        reg = get_prose_connectors()
        matched = [tok for tok in reg if tok in integration_body]
        assert matched, f"No connector token found in integration body: {integration_body!r}"

    def test_all_tokens_are_nonempty_strings(self):
        """Every token in the registry must be a non-empty string."""
        for token in get_prose_connectors():
            assert isinstance(token, str) and len(token) > 0
