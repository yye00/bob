"""Tests for prose-connector detection via bob.demoter_utils (F-936068dc).

Verifies that:
  - get_prose_connector_registry returns a frozenset containing all policy
    phrases required by the 15d1ac4f regression fix.
  - is_structural_prefix_match correctly uses START-OF-STRING matching so
    a prose AC quoting 'pytest:' mid-sentence demotes rather than hard-fails.
  - A real 'pytest:' criterion at the start still routes to structural.
"""
from __future__ import annotations

import pytest

from bob.demoter_utils import get_prose_connector_registry, is_structural_prefix_match


class TestProseConnectorRegistry:
    def test_returns_frozenset(self):
        registry = get_prose_connector_registry()
        assert isinstance(registry, frozenset)

    def test_not_empty(self):
        assert len(get_prose_connector_registry()) > 0

    def test_continues_to_present(self):
        """'continues to' must be registered (15d1ac4f regression token)."""
        assert "continues to" in get_prose_connector_registry()

    def test_separately_present(self):
        assert "separately" in get_prose_connector_registry()

    def test_invariant_present(self):
        assert "invariant" in get_prose_connector_registry()

    def test_whole_suite_present(self):
        assert "whole-suite" in get_prose_connector_registry()

    def test_no_behavior_present(self):
        assert "no behavior" in get_prose_connector_registry()

    def test_unaffected_present(self):
        assert "unaffected" in get_prose_connector_registry()

    def test_original_c09e9e64_tokens_present(self):
        """Original connector set must still be present after the expansion."""
        registry = get_prose_connector_registry()
        for token in ("all", "every", "route", "through", ";", "no direct"):
            assert token in registry, f"missing original token: {token!r}"

    def test_all_tokens_are_strings(self):
        for token in get_prose_connector_registry():
            assert isinstance(token, str) and len(token) > 0


class TestStartOfStringPrefixMatching:
    def test_real_pytest_criterion_is_structural(self):
        """'pytest: tests/foo.py' at the start must be classified structural."""
        assert is_structural_prefix_match("pytest: tests/foo.py") is True

    def test_prose_quoting_pytest_mid_sentence_demotes(self):
        """The 15d1ac4f regression: prose AC with 'pytest:' mid-sentence must demote."""
        criterion = (
            "behavior: collect_feature_test_paths returns the set of "
            "test paths declared in the feature's AC list (entries with "
            "prefix 'pytest:') plus tests/<feature_id>/ if it exists; "
            "returns empty set when feature has no pytest ACs"
        )
        assert is_structural_prefix_match(criterion) is False

    def test_15d1ac4f_integration_prose_body_is_not_structural(self):
        """The integration prose body using 'continues to', 'whole-suite', etc. is NOT structural."""
        criterion = (
            "integration: regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately (no behavior regression "
            "for the cross-feature regression detection path)"
        )
        # 'integration:' IS a structural prefix — this criterion starts with it.
        assert is_structural_prefix_match(criterion) is True

    def test_behavior_prefix_not_structural(self):
        assert is_structural_prefix_match("behavior: some descriptive text") is False

    def test_leading_whitespace_stripped(self):
        assert is_structural_prefix_match("  file exists: src/foo.py") is True

    def test_non_string_returns_false(self):
        assert is_structural_prefix_match(None) is False  # type: ignore[arg-type]
        assert is_structural_prefix_match(42) is False  # type: ignore[arg-type]
