"""Tests: implementer refuses to start when plan.yaml.approved=false (F-0bf30902).

Acceptance criterion:
    Implementer refuses to start when plan.yaml.approved=false
    (test_implementer_blocked_until_approved.py)
"""

from __future__ import annotations

import pytest


class TestImplementerBlockedUntilApproved:
    """Implementer refuses to start when plan.yaml.approved=false."""

    def test_is_approved_returns_false_blocks_implementer(self, tmp_path):
        """When is_approved returns False, an implementer guard should block."""
        from bob3.orchestrator.plan_gate import is_approved, write_plan_artifact

        feature_id = "aaaa0001-0000-0000-0000-000000000001"
        write_plan_artifact(
            feature_id=feature_id,
            name="Blocked Feature",
            description="This should be blocked",
            acceptance_criteria=["pytest: tests/test_blocked.py"],
            workspace=tmp_path,
        )

        # Default — approved=False → implementer must block
        approved = is_approved(feature_id, workspace=tmp_path)
        assert approved is False, "implementer must be blocked when approved=False"

    def test_is_approved_returns_true_allows_implementer(self, tmp_path):
        """When is_approved returns True, an implementer guard should allow."""
        from bob3.orchestrator.plan_gate import (
            approve_plan,
            is_approved,
            write_plan_artifact,
        )

        feature_id = "bbbb0002-0000-0000-0000-000000000002"
        write_plan_artifact(
            feature_id=feature_id,
            name="Allowed Feature",
            description="This should be allowed",
            acceptance_criteria=["pytest: tests/test_allowed.py"],
            workspace=tmp_path,
        )
        approve_plan(feature_id, workspace=tmp_path)

        approved = is_approved(feature_id, workspace=tmp_path)
        assert approved is True, "implementer must be allowed when approved=True"

    def test_missing_plan_blocks_implementer(self, tmp_path):
        """When plan.yaml is absent, is_approved returns False (safe default)."""
        from bob3.orchestrator.plan_gate import is_approved

        feature_id = "cccc0003-0000-0000-0000-000000000003"
        # No write_plan_artifact call — file does not exist
        approved = is_approved(feature_id, workspace=tmp_path)
        assert approved is False, "missing plan.yaml must block implementer"

    def test_auto_approve_allows_implementer(self, tmp_path):
        """With auto_approve=True, is_approved returns True immediately."""
        from bob3.orchestrator.plan_gate import is_approved, write_plan_artifact

        feature_id = "dddd0004-0000-0000-0000-000000000004"
        write_plan_artifact(
            feature_id=feature_id,
            name="CI Feature",
            description="Auto-approved in CI",
            acceptance_criteria=["pytest: tests/test_ci.py"],
            workspace=tmp_path,
            auto_approve=True,
        )

        approved = is_approved(feature_id, workspace=tmp_path)
        assert approved is True, "auto_approve=True must let implementer proceed"

    def test_implementer_guard_pattern(self, tmp_path):
        """The guard pattern used by implementers: raise if not approved."""
        from bob3.orchestrator.plan_gate import is_approved, write_plan_artifact

        feature_id = "eeee0005-0000-0000-0000-000000000005"
        write_plan_artifact(
            feature_id=feature_id,
            name="Guard Pattern Feature",
            description="Testing the guard pattern",
            acceptance_criteria=["pytest: tests/test_guard.py"],
            workspace=tmp_path,
        )

        def implementer_start(fid: str, ws) -> str:
            if not is_approved(fid, workspace=ws):
                raise PermissionError(
                    f"Implementer blocked: plan.yaml not approved for {fid}"
                )
            return "started"

        with pytest.raises(PermissionError, match="plan.yaml not approved"):
            implementer_start(feature_id, tmp_path)
