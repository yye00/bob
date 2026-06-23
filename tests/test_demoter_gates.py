"""Tests for bob3.demoter_gates — F-0a9d5eb0.

Verifies:
  1. is_structural_prefix_match uses START-OF-STRING position (not substring).
  2. A prose AC quoting "pytest:" mid-sentence correctly demotes (returns False).
  3. A real "pytest: tests/foo.py" criterion returns True (routes to pytest).
  4. get_prose_connectors returns a frozenset covering the required policy phrases.
  5. The registry is the single source of truth — callers can iterate/extend it.
"""
import pytest

from bob3.demoter_gates import (
    is_structural_prefix_match,
    get_prose_connectors,
)


class TestIsStructuralPrefixMatch:
    def test_real_pytest_criterion_returns_true(self):
        """A leading 'pytest:' criterion must return True (executable)."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_prose_quoting_pytest_mid_sentence_returns_false(self):
        """A prose AC that mentions 'pytest:' mid-sentence must return False.

        This is the A1 regression case from F-R7-576: the old substring match
        would see "pytest:" inside the text and incorrectly return True.
        """
        prose = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists; "
            "returns empty set when feature has no pytest ACs"
        )
        assert is_structural_prefix_match(prose) is False

    def test_file_exists_prefix_returns_true(self):
        assert is_structural_prefix_match("file exists: src/bob3/demoter_gates.py") is True

    def test_function_defined_prefix_returns_true(self):
        assert is_structural_prefix_match("function defined: bob3.demoter_gates.is_structural_prefix_match") is True

    def test_integration_prefix_returns_true(self):
        assert is_structural_prefix_match("integration: bob3.criterion_demoter") is True

    def test_leading_whitespace_stripped(self):
        """Leading whitespace must be stripped before checking prefix."""
        assert is_structural_prefix_match("  pytest: tests/foo.py") is True

    def test_behavior_prefix_not_structural_returns_false(self):
        """A 'behavior:' prefix is prose, not structural."""
        assert is_structural_prefix_match("behavior: some description") is False

    def test_none_input_returns_false(self):
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]

    def test_empty_string_returns_false(self):
        assert is_structural_prefix_match("") is False

    def test_integration_body_with_prose_connectors_returns_true(self):
        """An integration: criterion routes as structural regardless of connectors in body."""
        criterion = (
            "integration: regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately "
            "(no behavior regression for the cross-feature regression detection path)"
        )
        assert is_structural_prefix_match(criterion) is True


class TestGetProseConnectors:
    def test_returns_frozenset(self):
        result = get_prose_connectors()
        assert isinstance(result, frozenset)

    def test_nonempty(self):
        assert len(get_prose_connectors()) > 0

    def test_covers_original_c09e9e64_tokens(self):
        """Original connector tokens must be present."""
        registry = get_prose_connectors()
        for token in ("all", "every", "route", "through", ";", "no direct"):
            assert token in registry, f"Missing c09e9e64 token: {token!r}"

    def test_covers_15d1ac4f_regression_tokens(self):
        """The 15d1ac4f regression tokens must be present — A2 case."""
        registry = get_prose_connectors()
        required = ("continues to", "separately", "invariant", "whole-suite", "no behavior")
        for token in required:
            assert token in registry, f"Missing 15d1ac4f token: {token!r}"

    def test_covers_policy_prose_tokens(self):
        """Policy-prose tokens that indicate non-executable ACs must be present."""
        registry = get_prose_connectors()
        for token in ("maintains", "preserves", "ensures", "guarantees", "unaffected"):
            assert token in registry, f"Missing policy token: {token!r}"

    def test_all_tokens_are_nonempty_strings(self):
        for token in get_prose_connectors():
            assert isinstance(token, str) and len(token) > 0

    def test_prose_integration_body_matches_registry(self):
        """The A2 integration body must contain at least one registry token."""
        body = (
            "integration: regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately "
            "(no behavior regression for the cross-feature regression detection path)"
        )
        registry = get_prose_connectors()
        matched = [tok for tok in registry if tok in body]
        assert matched, f"No registry token matched in integration body: {body!r}"
