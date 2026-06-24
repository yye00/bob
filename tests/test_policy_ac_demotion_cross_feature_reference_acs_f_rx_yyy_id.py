"""Tests for bob.policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id.

Feature: 8e763d7b-cc10-4fac-93e0-0cd075d47ec7
AC: pytest: tests/test_policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id.py::test_policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id

This feature provides the delegation module that wraps enhanced_verification.py's
demote_cross_feature_criterion() function. When a criterion body contains a token
matching \\bF-R\\d+-\\d{3}\\b, it is demoted to PASS with a WARNING record instead of
hard-failing, since per-feature verification cannot statically verify cross-feature
policy claims.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Canonical AC test — the named test that the AC requires to pass
# ---------------------------------------------------------------------------


def test_policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id():
    """Core AC test: function exists, returns (True, reason) for cross-feature ref ACs."""
    from bob.policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id import (
        policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id,
    )

    # Exact pattern from the feature description
    criterion = "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
    result = policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id(criterion)

    assert result is not None, "Expected demotion for cross-feature reference criterion"
    passed, reason = result
    assert passed is True
    assert reason
    assert "F-R7-478" in reason or "cross-feature" in reason.lower()


# ---------------------------------------------------------------------------
# Module and function importability
# ---------------------------------------------------------------------------


class TestImportability:
    def test_module_importable(self):
        """Feature module must be importable."""
        import bob.policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id  # noqa: F401

    def test_function_importable(self):
        """Canonical function must be importable from the feature module."""
        from bob.policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id import (
            policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id,
        )

        assert callable(policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id)


# ---------------------------------------------------------------------------
# Cross-feature reference detection
# ---------------------------------------------------------------------------


class TestCrossFeatureReferenceDetection:
    def setup_method(self):
        from bob.policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id import (
            policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id,
        )
        self.fn = policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id

    def test_f_r7_pattern_demoted(self):
        """Criterion with F-R7-NNN token must be demoted to PASS."""
        result = self.fn("integration: F-R7-532 invariant pass continues to run")
        assert result is not None
        passed, reason = result
        assert passed is True

    def test_f_r7_different_number_demoted(self):
        """Any F-R7-NNN numeric suffix must trigger demotion."""
        result = self.fn("behavior: F-R7-001 path must not be affected")
        assert result is not None
        passed, reason = result
        assert passed is True

    def test_f_r_with_different_group_demoted(self):
        """F-R5-NNN or other group variants should also match."""
        result = self.fn("integration: F-R5-123 path must remain unaffected")
        assert result is not None
        passed, reason = result
        assert passed is True

    def test_reason_is_non_empty_string(self):
        """Demotion reason must be a non-empty string."""
        result = self.fn("integration: F-R7-478 unlimited spawn-retry path")
        assert result is not None
        _, reason = result
        assert isinstance(reason, str)
        assert len(reason) > 0

    def test_no_cross_feature_ref_returns_none(self):
        """Criterion with no F-RX-YYY token must return None (no demotion)."""
        result = self.fn("integration: module bob.verifier must be imported")
        assert result is None

    def test_plain_criterion_returns_none(self):
        """A plain function-existence criterion must return None."""
        result = self.fn("function defined: bob.some_module.some_function")
        assert result is None

    def test_f_r_token_as_substring_not_matched(self):
        """F-RX-YYY must be a word-boundary match (not substring of larger token)."""
        # 'XF-R7-582X' should NOT match since it lacks word boundary
        result = self.fn("integration: XF-R7-582X must not trigger")
        assert result is None

    def test_multiple_cross_feature_refs_demoted(self):
        """Criterion with multiple F-RX-YYY tokens still demotes."""
        result = self.fn(
            "integration: F-R7-478 and F-R7-532 paths remain unaffected"
        )
        assert result is not None
        passed, _ = result
        assert passed is True


# ---------------------------------------------------------------------------
# Delegation to enhanced_verification.demote_cross_feature_criterion
# ---------------------------------------------------------------------------


class TestDelegation:
    def test_delegates_to_enhanced_verification(self):
        """Function must delegate to enhanced_verification.demote_cross_feature_criterion."""
        from unittest.mock import patch
        import bob.enhanced_verification as ev
        from bob.policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id import (
            policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id,
        )

        sentinel = (True, "sentinel-reason")
        with patch.object(ev, "demote_cross_feature_criterion", return_value=sentinel) as mock_fn:
            result = policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id(
                "integration: F-R7-478 unlimited spawn-retry path"
            )

        mock_fn.assert_called_once()
        assert result == sentinel

    def test_workspace_passed_through(self):
        """workspace parameter must be forwarded to demote_cross_feature_criterion."""
        import pathlib
        from unittest.mock import patch
        import bob.enhanced_verification as ev
        from bob.policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id import (
            policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id,
        )

        workspace = pathlib.Path("/tmp/test-workspace")
        sentinel = (True, "sentinel-reason")
        with patch.object(ev, "demote_cross_feature_criterion", return_value=sentinel) as mock_fn:
            policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id(
                "integration: F-R7-478 path remains unaffected",
                workspace=workspace,
            )

        call_kwargs = mock_fn.call_args
        assert call_kwargs is not None
        # workspace must appear either as positional arg or keyword arg
        args, kwargs = call_kwargs
        assert workspace in args or kwargs.get("workspace") == workspace
