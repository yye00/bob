"""Regression test — F-caef0dcf / 1c574f4a prose-demotion via policy verbs.

Asserts that the EXACT AC body from feature 1c574f4a (F-R7-479 RCA auto-reset
extension) resolves with a demote_prose_ac path, not a hard-fail.

Background: feature 1c574f4a NH'd in bob version 16 round 13 because its AC:

  "integration: dd11d1f8-class failures (verification gate failed on
   plausible-fixable emission, attempts<5) MUST trigger fresh-attempt grant
   rather than NH-demote"

...contained neither a Python-dotted reference (the hyphen in 'dd11d1f8-class'
broke the dotted-token regex) nor any F-R7-578 descriptive-prose connector.
The fix adds policy-verb connectors ("must", "trigger", "rather than", "grant",
"demote", "plausibl", "fixable") to a separate registry partition.
"""
import pathlib
from unittest.mock import patch

from bob.verification.integration_ac_resolver import (
    _is_prose_body,
    resolve_integration_ac,
)
from bob.verification.policy_verb_registry import policy_verb_connectors

# The EXACT AC body from feature 1c574f4a that caused the NH
_CRITERION_1C574F4A = (
    "integration: dd11d1f8-class failures (verification gate failed on "
    "plausible-fixable emission, attempts<5) MUST trigger fresh-attempt grant "
    "rather than NH-demote"
)


def test_policy_verb_connectors_contains_required_tokens():
    """policy_verb_connectors must contain the 15 required stems."""
    required = {
        "must", "should", "trigger", "rather than", "grant", "demote",
        "reset", "reopen", "emit", "classify", "reclassif", "escalate",
        "honor", "plausibl", "fixable",
    }
    registry = policy_verb_connectors()
    missing = required - registry
    assert not missing, f"policy_verb_connectors missing tokens: {missing}"


def test_1c574f4a_body_is_prose_via_policy_verbs():
    """The 1c574f4a integration body must be identified as prose (via policy verbs)."""
    body = _CRITERION_1C574F4A[len("integration:"):]
    assert _is_prose_body(body) is True, (
        "1c574f4a body not detected as prose; "
        "policy-verb connectors may be missing from registry"
    )


def test_1c574f4a_resolves_to_demote_not_hard_fail(tmp_path):
    """resolve_integration_ac must demote the 1c574f4a body, not hard-fail it."""
    with patch("bob.enhanced_verification._integration_wired", return_value=False):
        ok, reason = resolve_integration_ac(_CRITERION_1C574F4A, tmp_path)

    assert ok is True, (
        f"Expected prose-demotion (ok=True) for 1c574f4a body, got ok=False. "
        f"Reason: {reason}"
    )
    assert "demoted" in reason.lower(), (
        f"Expected demotion message in reason, got: {reason!r}"
    )


def test_1c574f4a_wired_target_returns_true_not_demoted(tmp_path):
    """If _integration_wired returns True for a real dotted target, ok=True with no demotion msg."""
    # Use a criterion that has BOTH a dotted target AND the 1c574f4a body shape.
    criterion_with_dotted = (
        "integration: bob.real.module MUST trigger fresh-attempt grant "
        "rather than NH-demote"
    )
    with patch("bob.enhanced_verification._integration_wired", return_value=True):
        ok, reason = resolve_integration_ac(criterion_with_dotted, tmp_path)

    assert ok is True
    # When wired, reason should be empty (not a demotion)
    assert reason == "", f"Expected empty reason for wired target, got: {reason!r}"
