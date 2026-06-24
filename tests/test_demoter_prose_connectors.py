"""Tests for bob.demoter.get_prose_connector_registry (F-1f398865).

Verifies that the prose connector registry exposed via bob.demoter:
  - Contains all original c09e9e64 tokens
  - Contains the 15d1ac4f regression tokens that caused NH'd features
  - Contains additional policy-phrase tokens
  - Returns a frozenset (immutable, single source of truth)
  - Correctly covers the 15d1ac4f integration body text
"""
import pytest

from bob.demoter import get_prose_connector_registry


class TestGetProseConnectorRegistryType:
    def test_returns_frozenset(self):
        result = get_prose_connector_registry()
        assert isinstance(result, frozenset)

    def test_is_non_empty(self):
        result = get_prose_connector_registry()
        assert len(result) > 0

    def test_all_tokens_are_strings(self):
        for token in get_prose_connector_registry():
            assert isinstance(token, str)
            assert len(token) > 0

    def test_is_immutable(self):
        registry = get_prose_connector_registry()
        with pytest.raises((AttributeError, TypeError)):
            registry.add("cannot_add")  # type: ignore[union-attr]

    def test_repeated_calls_return_same_tokens(self):
        first = get_prose_connector_registry()
        second = get_prose_connector_registry()
        assert first == second


class TestC09e9e64OriginalTokens:
    """Original tokens that covered the c09e9e64 form of integration ACs."""

    def test_all_original_tokens_present(self):
        registry = get_prose_connector_registry()
        for token in ("all", "every", "route", "through", ";", "no direct"):
            assert token in registry, f"Missing original c09e9e64 token: {token!r}"

    def test_all_present(self):
        assert "all" in get_prose_connector_registry()

    def test_every_present(self):
        assert "every" in get_prose_connector_registry()

    def test_route_present(self):
        assert "route" in get_prose_connector_registry()

    def test_through_present(self):
        assert "through" in get_prose_connector_registry()

    def test_semicolon_present(self):
        assert ";" in get_prose_connector_registry()

    def test_no_direct_present(self):
        assert "no direct" in get_prose_connector_registry()


class TestRegression15d1ac4fTokens:
    """Tokens needed to cover the 15d1ac4f integration AC body that caused NH failures."""

    def test_continues_to_present(self):
        assert "continues to" in get_prose_connector_registry()

    def test_separately_present(self):
        assert "separately" in get_prose_connector_registry()

    def test_invariant_present(self):
        assert "invariant" in get_prose_connector_registry()

    def test_whole_suite_present(self):
        assert "whole-suite" in get_prose_connector_registry()

    def test_no_behavior_present(self):
        assert "no behavior" in get_prose_connector_registry()

    def test_all_15d1ac4f_tokens_present(self):
        registry = get_prose_connector_registry()
        for token in ("continues to", "separately", "invariant", "whole-suite", "no behavior"):
            assert token in registry, f"Missing 15d1ac4f regression token: {token!r}"

    def test_integration_body_covered(self):
        """The actual 15d1ac4f integration body must match at least one registry token."""
        body = (
            "regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately "
            "(no behavior regression for the cross-feature regression detection path)"
        )
        registry = get_prose_connector_registry()
        assert any(token in body for token in registry), (
            f"No registry token matched the 15d1ac4f body; registry={registry!r}"
        )


class TestPolicyPhraseTokens:
    """Additional policy-phrase tokens covering common prose patterns."""

    def test_maintains_present(self):
        assert "maintains" in get_prose_connector_registry()

    def test_preserves_present(self):
        assert "preserves" in get_prose_connector_registry()

    def test_ensures_present(self):
        assert "ensures" in get_prose_connector_registry()

    def test_guarantees_present(self):
        assert "guarantees" in get_prose_connector_registry()

    def test_unaffected_present(self):
        assert "unaffected" in get_prose_connector_registry()

    def test_regression_present(self):
        assert "regression" in get_prose_connector_registry()

    def test_all_policy_tokens_present(self):
        registry = get_prose_connector_registry()
        for token in ("maintains", "preserves", "ensures", "guarantees", "unaffected", "regression"):
            assert token in registry, f"Missing policy token: {token!r}"
