"""Tests for bob.demoter_markers — canonical marker registry (feature 277f1294).

Verifies:
- is_structural_prefix_match uses START-OF-STRING position (not substring).
- A prose AC quoting "pytest:" mid-sentence returns False (the root-cause defect).
- A real "pytest: tests/foo.py" criterion returns True.
- get_connector_registry() returns a frozenset covering all required policy phrases.
"""
from __future__ import annotations

import pytest

from bob.demoter_markers import is_structural_prefix_match, get_connector_registry


class TestIsStructuralPrefixMatch:
    def test_real_pytest_criterion_returns_true(self):
        """A real 'pytest:' criterion at line start must return True."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_file_exists_criterion_returns_true(self):
        assert is_structural_prefix_match("file exists: src/bob/demoter_markers.py") is True

    def test_function_defined_criterion_returns_true(self):
        assert is_structural_prefix_match("function defined: bob.demoter_markers.is_structural_prefix_match") is True

    def test_integration_criterion_returns_true(self):
        assert is_structural_prefix_match("integration: bob.spec_loader") is True

    def test_leading_whitespace_stripped_before_matching(self):
        """Leading whitespace must be stripped before the prefix check."""
        assert is_structural_prefix_match("   pytest: tests/foo.py") is True

    def test_prose_ac_quoting_pytest_mid_sentence_returns_false(self):
        """Core regression: prose AC with 'pytest:' mid-sentence must NOT match.

        This is the root-cause defect from F-R7-576: substring matching caused
        'behavior: ... entries with prefix "pytest:" ...' to be classified as
        structural, producing false hard-fails.
        """
        prose = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists; "
            "returns empty set when feature has no pytest ACs"
        )
        assert is_structural_prefix_match(prose) is False

    def test_prose_with_file_exists_mid_sentence_returns_false(self):
        """A prose AC mentioning 'file exists' in the middle must return False."""
        prose = "behavior: verify that file exists in the target directory"
        assert is_structural_prefix_match(prose) is False

    def test_empty_string_returns_false(self):
        assert is_structural_prefix_match("") is False

    def test_none_returns_false(self):
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]

    def test_integer_returns_false(self):
        assert is_structural_prefix_match(42) is False  # type: ignore[arg-type]

    def test_whitespace_only_returns_false(self):
        assert is_structural_prefix_match("   ") is False

    def test_case_insensitive_prefix_match(self):
        """Prefix matching should be case-insensitive."""
        assert is_structural_prefix_match("Pytest: tests/foo.py") is True

    def test_pytest_criterion_references_existing_file(self):
        """The AC 'pytest: tests/foo.py' references a file that must exist."""
        import os
        assert os.path.exists("tests/foo.py"), "tests/foo.py must exist for routing verification"


class TestGetConnectorRegistry:
    def test_returns_frozenset(self):
        result = get_connector_registry()
        assert isinstance(result, frozenset)

    def test_nonempty(self):
        assert len(get_connector_registry()) > 0

    def test_all_tokens_are_nonempty_strings(self):
        for token in get_connector_registry():
            assert isinstance(token, str) and len(token) > 0

    def test_covers_original_c09e9e64_tokens(self):
        """Covers the original connector tokens from the c09e9e64 form."""
        registry = get_connector_registry()
        for token in ("all", "every", "route", "through", ";", "no direct"):
            assert token in registry, f"Missing original token: {token!r}"

    def test_covers_15d1ac4f_regression_tokens(self):
        """Covers the tokens from the 15d1ac4f regression form.

        The integration AC 'regression-sweep ... continues to run whole-suite
        pytest separately (no behavior regression ...)' was not demoted because
        'continues to', 'separately', 'invariant', 'whole-suite', 'no behavior'
        were absent from the connector list.
        """
        registry = get_connector_registry()
        required = ("continues to", "separately", "invariant", "whole-suite", "no behavior")
        for token in required:
            assert token in registry, f"Missing 15d1ac4f token: {token!r}"

    def test_covers_policy_phrase_tokens(self):
        """Covers additional policy-prose tokens."""
        registry = get_connector_registry()
        for token in ("maintains", "preserves", "ensures", "guarantees", "unaffected"):
            assert token in registry, f"Missing policy token: {token!r}"

    def test_15d1ac4f_integration_prose_demotes_with_registry(self):
        """The 15d1ac4f integration-prose body uses registry tokens.

        Verifies that at least one token from the integration body appears
        in the registry, enabling the integration-AC resolver to demote it.
        """
        integration_body = (
            "integration: regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately (no "
            "behavior regression for the cross-feature regression detection path)"
        )
        registry = get_connector_registry()
        body_lower = integration_body.lower()
        matching = [t for t in registry if t in body_lower]
        assert len(matching) > 0, (
            "No connector token from the registry matched the 15d1ac4f "
            f"integration prose body. Registry: {registry!r}"
        )
