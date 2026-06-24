"""Tests for enhanced_verification demoter functions (F-6557a4d4).

Verifies:
  1. is_structural_prefix_match uses START-OF-STRING position matching
     so mid-sentence quotes of "pytest:" do NOT classify as structural.
  2. get_prose_connector_registry covers policy phrases required by
     F-R7-577: "continues to", "separately", "invariant", "whole-suite",
     "no behavior regression", "unaffected".
  3. A real "pytest: tests/foo.py" criterion IS classified as structural.
  4. A prose AC quoting "pytest:" mid-sentence is NOT classified as structural.
"""

import pytest

from bob.enhanced_verification import (
    is_structural_prefix_match,
    get_prose_connector_registry,
)


class TestIsStructuralPrefixMatchStartOfString:
    """is_structural_prefix_match must use position-0 matching, not substring."""

    def test_real_pytest_criterion_is_structural(self):
        """A leading 'pytest:' criterion must be classified as structural."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_pytest_quoted_mid_sentence_is_not_structural(self):
        """Prose quoting 'pytest:' mid-sentence must NOT be structural.

        This is the exact defect: the 15d1ac4f AC
        "entries with prefix 'pytest:'" contains the substring "pytest:"
        but it is NOT a structural criterion.
        """
        prose_ac = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists; "
            "returns empty set when feature has no pytest ACs"
        )
        assert is_structural_prefix_match(prose_ac) is False

    def test_file_exists_prefix_is_structural(self):
        """'file exists:' at start is structural."""
        assert is_structural_prefix_match("file exists: src/bob/foo.py") is True

    def test_file_exists_quoted_mid_sentence_is_not_structural(self):
        """'file exists:' occurring mid-sentence must not trigger structural match."""
        prose = "the module checks file exists: condition before running"
        assert is_structural_prefix_match(prose) is False

    def test_function_defined_prefix_is_structural(self):
        assert is_structural_prefix_match("function defined: bob.foo.bar") is True

    def test_integration_prefix_is_structural(self):
        assert is_structural_prefix_match("integration: bob.orchestrator") is True

    def test_whitespace_before_prefix_still_matches(self):
        """Leading whitespace should be stripped before prefix check."""
        assert is_structural_prefix_match("  pytest: tests/foo.py") is True

    def test_plain_prose_without_any_prefix_is_not_structural(self):
        assert is_structural_prefix_match("the feature should handle errors gracefully") is False

    def test_none_returns_false(self):
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]

    def test_empty_string_returns_false(self):
        assert is_structural_prefix_match("") is False


class TestGetProseConnectorRegistry:
    """get_prose_connector_registry must cover all required policy phrases."""

    def test_returns_frozenset(self):
        registry = get_prose_connector_registry()
        assert isinstance(registry, frozenset)

    def test_nonempty(self):
        assert len(get_prose_connector_registry()) > 0

    def test_original_c09e9e64_tokens_present(self):
        """Original connector set from c09e9e64 must be present."""
        registry = get_prose_connector_registry()
        for token in ("all", "every", "through", ";", "no direct"):
            assert token in registry, f"Expected original token {token!r} in registry"

    def test_15d1ac4f_regression_tokens_present(self):
        """Tokens required to fix the 15d1ac4f regression must be present."""
        registry = get_prose_connector_registry()
        required = ("continues to", "separately", "invariant", "whole-suite", "no behavior")
        for token in required:
            assert token in registry, f"Required regression token {token!r} missing from registry"

    def test_policy_phrase_unaffected_present(self):
        assert "unaffected" in get_prose_connector_registry()

    def test_all_tokens_are_nonempty_strings(self):
        for token in get_prose_connector_registry():
            assert isinstance(token, str) and len(token) > 0

    def test_integration_regression_body_contains_registry_token(self):
        """The 15d1ac4f integration AC body must contain at least one registry token.

        Reproduces the exact body that failed in F-R7-577 to confirm the
        registry now covers it.
        """
        body = (
            "regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately (no "
            "behavior regression for the cross-feature regression "
            "detection path)"
        )
        registry = get_prose_connector_registry()
        assert any(token in body for token in registry), (
            "Integration AC body contains no registry token — prose demotion would fail"
        )
