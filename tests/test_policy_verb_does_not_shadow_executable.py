"""Test: policy-verb demoter must NOT short-circuit real wiring checks.

Asserts that 'integration: bob.real.module' (a clean dotted reference) still
routes to _integration_wired and is NOT swallowed by the policy-verb/prose
demotion path.

This is a safeguard against the policy-verb expansion accidentally treating
every integration AC as prose and granting a spurious pass.
"""
import pathlib
from unittest.mock import patch, MagicMock

from bob.verification.integration_ac_resolver import resolve_integration_ac


class TestPolicyVerbDoesNotShadowExecutable:

    def test_clean_dotted_reference_routes_to_wiring_lookup(self, tmp_path):
        """'integration: bob.real.module' must call _integration_wired, not demote."""
        criterion = "integration: bob.real.module"
        mock_wired = MagicMock(return_value=True)
        with patch("bob.enhanced_verification._integration_wired", mock_wired):
            ok, reason = resolve_integration_ac(criterion, tmp_path)

        mock_wired.assert_called_once()
        assert ok is True
        assert reason == "", f"Expected empty reason (wired target), got: {reason!r}"

    def test_clean_dotted_reference_fails_when_not_wired(self, tmp_path):
        """A non-wired dotted target without prose must hard-fail."""
        criterion = "integration: bob.not_wired.module"
        mock_wired = MagicMock(return_value=False)
        with patch("bob.enhanced_verification._integration_wired", mock_wired):
            ok, reason = resolve_integration_ac(criterion, tmp_path)

        mock_wired.assert_called_once()
        assert ok is False
        assert "no wired" in reason.lower()

    def test_dotted_with_must_still_calls_wiring_first(self, tmp_path):
        """Even if body contains 'must', a valid dotted target must be wiring-checked first."""
        criterion = "integration: bob.gate.check MUST pass before promotion"
        mock_wired = MagicMock(return_value=True)
        with patch("bob.enhanced_verification._integration_wired", mock_wired):
            ok, reason = resolve_integration_ac(criterion, tmp_path)

        # Wiring check must be attempted — if it succeeds, that's the result.
        mock_wired.assert_called_once()
        assert ok is True
        assert reason == ""

    def test_dotted_with_must_hard_fails_when_not_wired(self, tmp_path):
        """Dotted target + policy verbs but not wired: body IS prose, so demote."""
        # This is an edge case: body has a dotted target AND policy verbs.
        # _integration_wired returns False, then _is_prose_body fires (body has 'must').
        criterion = "integration: bob.gate.check MUST pass before promotion"
        mock_wired = MagicMock(return_value=False)
        with patch("bob.enhanced_verification._integration_wired", mock_wired):
            ok, reason = resolve_integration_ac(criterion, tmp_path)

        # Body has spaces and 'must' (a policy-verb connector), so it's prose → demote
        assert ok is True
        assert "demoted" in reason.lower()

    def test_bare_dotted_no_prose_hard_fails(self, tmp_path):
        """A dotted target with no prose connectors, not wired, must hard-fail."""
        # Body has no spaces or prose tokens: 'bob.module' alone → not prose
        criterion = "integration: bob.module"
        mock_wired = MagicMock(return_value=False)
        with patch("bob.enhanced_verification._integration_wired", mock_wired):
            ok, reason = resolve_integration_ac(criterion, tmp_path)

        assert ok is False
        assert "no wired" in reason.lower()
