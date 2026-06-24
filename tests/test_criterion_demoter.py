"""Tests for bob.criterion_demoter public API (feature 81735692).

Covers:
- is_structural_prefix_match: START-OF-STRING prefix check, not substring
- get_prose_connectors: canonical frozenset used by both prose-AC and integration-AC demoters

Key regressions:
  A1: prose AC quoting "pytest:" mid-sentence DEMOTES (not hard-fail)
  A2: "regression-sweep ... continues to run whole-suite pytest separately" demotes
  A3: real "pytest: tests/foo.py" criterion still returns True (routes to pytest dispatch)
  A4: "file exists: src/bar.py" still returns True
"""
import pytest

from bob.criterion_demoter import (
    is_structural_prefix_match,
    get_prose_connectors,
    get_prose_connector_registry,
)


class TestIsStructuralPrefixMatch:
    def test_pytest_at_start_is_structural(self):
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_pytest_leading_whitespace_is_structural(self):
        assert is_structural_prefix_match("  pytest: tests/bar.py") is True

    def test_file_exists_at_start_is_structural(self):
        assert is_structural_prefix_match("file exists: src/criterion_demoter.py") is True

    def test_function_defined_at_start_is_structural(self):
        assert is_structural_prefix_match("function defined: bob.criterion_demoter.is_structural_prefix_match") is True

    def test_integration_at_start_is_structural(self):
        assert is_structural_prefix_match("integration: bob.orchestrator") is True

    def test_none_returns_false(self):
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]

    def test_empty_string_returns_false(self):
        assert is_structural_prefix_match("") is False

    def test_whitespace_only_returns_false(self):
        assert is_structural_prefix_match("   ") is False

    def test_regression_a1_prose_quoting_pytest_mid_sentence_demotes(self):
        """A1: prose AC with 'pytest:' quoted mid-sentence must NOT be classified structural."""
        criterion = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists; "
            "returns empty set when feature has no pytest ACs"
        )
        assert is_structural_prefix_match(criterion) is False, (
            "Mid-sentence 'pytest:' in prose text was wrongly classified as structural"
        )

    def test_regression_a3_real_pytest_criterion_routes_to_pytest(self):
        """A3: a real 'pytest: tests/foo.py' must return True."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_regression_a4_file_exists_still_structural(self):
        """A4: 'file exists: src/bar.py' must still return True."""
        assert is_structural_prefix_match("file exists: src/bar.py") is True

    def test_behavior_prefix_is_not_structural(self):
        assert is_structural_prefix_match("behavior: foo does X") is False

    def test_non_string_integer_returns_false(self):
        assert is_structural_prefix_match(42) is False  # type: ignore[arg-type]

    def test_non_string_list_returns_false(self):
        result = is_structural_prefix_match(["pytest: foo"])  # type: ignore[arg-type]
        assert result is not True


class TestGetProseConnectors:
    def test_returns_frozenset(self):
        assert isinstance(get_prose_connectors(), frozenset)

    def test_not_empty(self):
        assert len(get_prose_connectors()) > 0

    def test_all_tokens_are_non_empty_strings(self):
        for token in get_prose_connectors():
            assert isinstance(token, str) and len(token) > 0

    def test_get_prose_connectors_equals_get_prose_connector_registry(self):
        """get_prose_connectors and get_prose_connector_registry must return same set."""
        assert get_prose_connectors() == get_prose_connector_registry()

    def test_original_c09e9e64_tokens_present(self):
        registry = get_prose_connectors()
        for token in ("all", "every", "route", "through", "no direct"):
            assert token in registry, f"Missing original token: {token!r}"

    def test_regression_15d1ac4f_tokens_present(self):
        """A2: 15d1ac4f integration body tokens must all be in registry."""
        registry = get_prose_connectors()
        for token in ("continues to", "separately", "invariant", "whole-suite", "no behavior"):
            assert token in registry, f"Missing 15d1ac4f regression token: {token!r}"

    def test_policy_phrase_tokens_present(self):
        registry = get_prose_connectors()
        for token in ("maintains", "preserves", "ensures", "guarantees", "unaffected", "regression"):
            assert token in registry, f"Missing policy phrase token: {token!r}"

    def test_regression_a2_integration_body_matches_registry(self):
        """A2: the 15d1ac4f integration-prose body must match at least one connector."""
        import re
        body = (
            "regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately (no "
            "behavior regression for the cross-feature regression "
            "detection path)"
        ).lower()
        registry = get_prose_connectors()
        matched = [t for t in registry if re.search(r"\b" + re.escape(t) + r"\b", body)]
        assert len(matched) > 0, (
            f"No connector tokens matched in 15d1ac4f integration body. Registry: {sorted(registry)}"
        )
