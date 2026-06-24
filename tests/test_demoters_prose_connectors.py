"""Tests for bob.demoters.get_prose_connector_registry (F-b3790872).

Verifies that:
- The registry returns a non-empty frozenset
- The registry covers the original c09e9e64 connector tokens
- The registry covers the 15d1ac4f regression tokens ("continues to",
  "separately", "invariant", "whole-suite", "no behavior")
- Additional policy phrases are present ("maintains", "preserves", etc.)
- The integration-prose body for 15d1ac4f demotes because at least one
  connector from the registry appears in the body
"""
import pytest

from bob.demoters import get_prose_connector_registry


class TestGetProseConnectorRegistry:
    """Registry content and shape tests."""

    def test_returns_frozenset(self):
        assert isinstance(get_prose_connector_registry(), frozenset)

    def test_not_empty(self):
        assert len(get_prose_connector_registry()) > 0

    def test_all_tokens_are_non_empty_strings(self):
        for token in get_prose_connector_registry():
            assert isinstance(token, str) and len(token) > 0

    def test_c09e9e64_original_tokens_present(self):
        """Original connector tokens from the c09e9e64 form must be in the registry."""
        registry = get_prose_connector_registry()
        for token in ("all", "every", "route", "through", ";", "no direct"):
            assert token in registry, f"Missing original token: {token!r}"

    def test_15d1ac4f_regression_tokens_present(self):
        """Regression tokens from the 15d1ac4f form must be in the registry.

        These are the tokens that were absent from the original list, causing
        the integration-prose body to hard-fail instead of demoting.
        """
        registry = get_prose_connector_registry()
        for token in ("continues to", "separately", "invariant", "whole-suite", "no behavior"):
            assert token in registry, f"Missing 15d1ac4f regression token: {token!r}"

    def test_policy_phrase_tokens_present(self):
        """Additional policy-prose tokens must be in the registry."""
        registry = get_prose_connector_registry()
        for token in ("maintains", "preserves", "ensures", "guarantees", "unaffected"):
            assert token in registry, f"Missing policy token: {token!r}"

    def test_registry_is_immutable(self):
        """frozenset must not support add/remove operations."""
        registry = get_prose_connector_registry()
        with pytest.raises((AttributeError, TypeError)):
            registry.add("new_token")  # type: ignore[attr-defined]

    def test_registry_is_stable_across_calls(self):
        """Repeated calls must return equivalent sets."""
        r1 = get_prose_connector_registry()
        r2 = get_prose_connector_registry()
        assert r1 == r2


class TestRegistryCoversIntegrationProseBody:
    """The registry must demote the 15d1ac4f integration-prose regression body."""

    def test_integration_prose_body_contains_registry_token(self):
        """At least one registry token must appear in the 15d1ac4f integration body.

        This is the A2 regression case from F-b3790872: the body
        'regression-sweep / F-R7-532 invariant pass continues to run
        whole-suite pytest separately (no behavior regression ...'
        must find at least one connector and demote.
        """
        body = (
            "regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately "
            "(no behavior regression for the cross-feature regression detection path)"
        )
        registry = get_prose_connector_registry()
        body_lower = body.lower()
        matched = [token for token in registry if token in body_lower]
        assert len(matched) > 0, (
            f"No registry token found in integration-prose body.\n"
            f"Body: {body!r}\n"
            f"Registry: {sorted(registry)}"
        )
