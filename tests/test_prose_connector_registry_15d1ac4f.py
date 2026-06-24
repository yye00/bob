"""Regression test — F-30176f30 / F-R7-577 fix.

Asserts that the exact 15d1ac4f integration body resolves with a prose-demote
path AND that the prose_connector_registry contains all required tokens.
"""
import pathlib
from unittest.mock import patch

from bob.verification.structural_prefix_match import prose_connector_registry
from bob.verification.integration_ac_resolver import (
    _is_prose_body,
    extract_integration_targets,
)


# The exact criterion from the 15d1ac4f regression
_CRITERION_15D1AC4F = (
    "integration: regression-sweep / F-R7-532 invariant pass "
    "continues to run whole-suite pytest separately "
    "(no behavior regression for the cross-feature regression detection path)"
)


def test_registry_contains_required_tokens():
    """prose_connector_registry must contain all tokens that cover the 15d1ac4f form."""
    registry = prose_connector_registry()
    required = {
        "all", "every", "route", "through", ";", "no direct",
        "continues to", "separately", "continues", "regression",
        "whole-suite", "no behavior", "maintains", "preserves",
        "ensures", "guarantees", "invariant", "unaffected",
    }
    missing = required - registry
    assert not missing, f"prose_connector_registry missing tokens: {missing}"


def test_15d1ac4f_integration_body_is_prose():
    """The exact 15d1ac4f integration body must be identified as prose."""
    body = _CRITERION_15D1AC4F[len("integration:"):]
    assert _is_prose_body(body) is True, (
        "15d1ac4f integration body not detected as prose; "
        "connector tokens may be missing from registry"
    )


def test_15d1ac4f_resolves_to_demote(tmp_path):
    """resolve_integration_ac must demote the 15d1ac4f criterion to WARNING."""
    from bob.verification.integration_ac_resolver import resolve_integration_ac

    with patch("bob.enhanced_verification._integration_wired", return_value=False):
        ok, reason = resolve_integration_ac(_CRITERION_15D1AC4F, tmp_path)

    assert ok is True, f"Expected demote (True), got False. Reason: {reason}"
    assert "demoted" in reason.lower(), (
        f"Expected demotion message, got: {reason!r}"
    )


def test_c09e9e64_regression_body_still_demotes(tmp_path):
    """The older c09e9e64 integration body must still demote correctly."""
    from bob.verification.integration_ac_resolver import resolve_integration_ac

    criterion = (
        "integration: all spec_findings.yaml writes in bob.reviews route "
        "through atomic_write_yaml; no direct yaml.dump calls"
    )
    with patch("bob.enhanced_verification._integration_wired", return_value=False):
        ok, reason = resolve_integration_ac(criterion, tmp_path)

    assert ok is True
    assert "demoted" in reason.lower()
