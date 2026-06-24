"""Tests for bob.demoter.get_prose_connector_registry (F-0234e7b3).

Verifies the public API exposed via bob.demoter returns the canonical
frozenset of prose-connector tokens that covers all required policy phrases.
"""
import pytest

from bob.demoter import get_prose_connector_registry


class TestGetProseConnectorRegistry:
    def test_returns_frozenset(self):
        registry = get_prose_connector_registry()
        assert isinstance(registry, frozenset)

    def test_original_c09e9e64_tokens_present(self):
        """Original tokens from c09e9e64 form must still be in registry."""
        registry = get_prose_connector_registry()
        originals = {"all", "every", "route", "through", ";", "no direct"}
        missing = originals - registry
        assert not missing, f"Missing original tokens: {missing}"

    def test_15d1ac4f_regression_tokens_present(self):
        """Tokens from 15d1ac4f regression must be in registry."""
        registry = get_prose_connector_registry()
        regression_tokens = {
            "continues to", "separately", "invariant", "whole-suite", "no behavior",
        }
        missing = regression_tokens - registry
        assert not missing, f"Missing 15d1ac4f tokens: {missing}"

    def test_policy_phrase_tokens_present(self):
        """Policy-phrase tokens covering 'continues to', 'unaffected' etc."""
        registry = get_prose_connector_registry()
        policy = {
            "continues to", "separately", "continues", "regression",
            "whole-suite", "no behavior", "maintains", "preserves",
            "ensures", "guarantees", "invariant", "unaffected",
        }
        missing = policy - registry
        assert not missing, f"Missing policy tokens: {missing}"

    def test_registry_is_non_empty(self):
        registry = get_prose_connector_registry()
        assert len(registry) > 0

    def test_registry_is_immutable(self):
        """frozenset cannot be modified — registry is the source of truth."""
        registry = get_prose_connector_registry()
        with pytest.raises((AttributeError, TypeError)):
            registry.add("new_token")  # type: ignore[union-attr]

    def test_15d1ac4f_integration_body_covered_by_registry(self):
        """The exact 15d1ac4f body must contain at least one registry token."""
        body = (
            "regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately "
            "(no behavior regression for the cross-feature regression detection path)"
        )
        registry = get_prose_connector_registry()
        assert any(token in body for token in registry), (
            "No registry token matched the 15d1ac4f integration body"
        )

    def test_calling_twice_returns_equal_registries(self):
        """Registry should be stable across multiple calls."""
        r1 = get_prose_connector_registry()
        r2 = get_prose_connector_registry()
        assert r1 == r2
