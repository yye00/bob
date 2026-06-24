"""Tests for bob.criterion_demoter.get_prose_connector_registry (F-0234e7b3).

Key regression tests:
- Registry covers the 15d1ac4f form using "continues to", "separately",
  "invariant", "whole-suite", "no behavior".
- Registry is the single source of truth; both prose-AC demoter and
  integration-AC resolver consume it.
"""
import pytest

from bob.demoter import get_prose_connector_registry
from bob.verification.structural_prefix_match import prose_connector_registry


class TestRegistryContract:
    """Registry must be frozenset of non-empty strings."""

    def test_returns_frozenset(self):
        registry = get_prose_connector_registry()
        assert isinstance(registry, frozenset)

    def test_not_empty(self):
        registry = get_prose_connector_registry()
        assert len(registry) > 0

    def test_all_tokens_are_non_empty_strings(self):
        for token in get_prose_connector_registry():
            assert isinstance(token, str)
            assert len(token) > 0

    def test_consistent_with_structural_prefix_match_module(self):
        """Demoter public registry must equal the underlying structural_prefix_match registry."""
        assert get_prose_connector_registry() == prose_connector_registry()


class TestOriginalC09e9e64Tokens:
    """Coverage for the original c09e9e64 form connector tokens."""

    def test_all_in_registry(self):
        registry = get_prose_connector_registry()
        assert "all" in registry

    def test_every_in_registry(self):
        assert "every" in get_prose_connector_registry()

    def test_route_in_registry(self):
        assert "route" in get_prose_connector_registry()

    def test_through_in_registry(self):
        assert "through" in get_prose_connector_registry()

    def test_no_direct_in_registry(self):
        assert "no direct" in get_prose_connector_registry()


class TestRegression15d1ac4fTokens:
    """
    Regression A2: 15d1ac4f integration-prose.

    The integration body:
        "integration: regression-sweep / F-R7-532 invariant pass
         continues to run whole-suite pytest separately (no
         behavior regression for the cross-feature regression
         detection path)"
    must be demoted — connector tokens "continues to", "separately",
    "invariant", "whole-suite", "no behavior" must all be in the registry.
    """

    def test_continues_to_in_registry(self):
        assert "continues to" in get_prose_connector_registry()

    def test_separately_in_registry(self):
        assert "separately" in get_prose_connector_registry()

    def test_invariant_in_registry(self):
        assert "invariant" in get_prose_connector_registry()

    def test_whole_suite_in_registry(self):
        assert "whole-suite" in get_prose_connector_registry()

    def test_no_behavior_in_registry(self):
        assert "no behavior" in get_prose_connector_registry()


class TestPolicyPhraseTokens:
    """Additional policy-phrase tokens required by the feature spec."""

    def test_maintains_in_registry(self):
        assert "maintains" in get_prose_connector_registry()

    def test_preserves_in_registry(self):
        assert "preserves" in get_prose_connector_registry()

    def test_ensures_in_registry(self):
        assert "ensures" in get_prose_connector_registry()

    def test_guarantees_in_registry(self):
        assert "guarantees" in get_prose_connector_registry()

    def test_unaffected_in_registry(self):
        assert "unaffected" in get_prose_connector_registry()

    def test_regression_in_registry(self):
        assert "regression" in get_prose_connector_registry()

    def test_continues_in_registry(self):
        assert "continues" in get_prose_connector_registry()


class TestIntegrationACDemotionWithRegistry:
    """The registry must cause integration prose ACs to demote rather than hard-fail."""

    def test_15d1ac4f_integration_body_has_connector_match(self):
        """
        The 15d1ac4f integration body must match at least one connector token
        from the registry so it demotes instead of hard-failing.
        """
        import re
        body = (
            "regression-sweep / F-R7-532 invariant pass "
            "continues to run whole-suite pytest separately (no "
            "behavior regression for the cross-feature regression "
            "detection path)"
        )
        body_lower = body.lower()
        registry = get_prose_connector_registry()
        matched = [
            token for token in registry
            if re.search(r"\b" + re.escape(token) + r"\b", body_lower)
        ]
        assert len(matched) > 0, (
            f"No connector tokens matched in 15d1ac4f body. "
            f"Registry: {sorted(registry)}"
        )
