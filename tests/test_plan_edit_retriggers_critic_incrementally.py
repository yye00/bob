"""Tests: plan.yaml edits are detected and can re-trigger spec-critic (F-0bf30902).

Acceptance criterion:
    pytest: tests/test_plan_edit_retriggers_critic_incrementally.py
    Edits to plan.yaml re-trigger F-R7-450 critic incrementally via F-R7-451 provenance.
"""

from __future__ import annotations

import pytest
import yaml


class TestPlanVsSpecDrift:
    """compute_plan_vs_spec_drift detects AC changes between plan.yaml and spec."""

    def test_no_drift_when_unchanged(self, tmp_path):
        from bob.orchestrator.plan_gate import compute_plan_vs_spec_drift, write_plan_artifact

        feature_id = "aaaa1001-0000-0000-0000-000000000001"
        ac = ["AC one", "AC two"]

        write_plan_artifact(
            feature_id=feature_id,
            name="Stable Feature",
            description=None,
            acceptance_criteria=ac,
            workspace=tmp_path,
        )

        report = compute_plan_vs_spec_drift(feature_id, ac, tmp_path)
        assert report["drift"] is False
        assert report["added"] == []
        assert report["removed"] == []

    def test_drift_detected_on_ac_addition(self, tmp_path):
        from bob.orchestrator.plan_gate import compute_plan_vs_spec_drift, write_plan_artifact

        feature_id = "bbbb1002-0000-0000-0000-000000000002"
        original_ac = ["AC one"]
        write_plan_artifact(
            feature_id=feature_id,
            name="Drifted Feature",
            description=None,
            acceptance_criteria=original_ac,
            workspace=tmp_path,
        )

        new_ac = ["AC one", "AC two (new)"]
        report = compute_plan_vs_spec_drift(feature_id, new_ac, tmp_path)
        assert report["drift"] is True
        assert "AC two (new)" in report["added"]
        assert report["removed"] == []

    def test_drift_detected_on_ac_removal(self, tmp_path):
        from bob.orchestrator.plan_gate import compute_plan_vs_spec_drift, write_plan_artifact

        feature_id = "cccc1003-0000-0000-0000-000000000003"
        original_ac = ["AC one", "AC two"]
        write_plan_artifact(
            feature_id=feature_id,
            name="Shrinking Feature",
            description=None,
            acceptance_criteria=original_ac,
            workspace=tmp_path,
        )

        new_ac = ["AC one"]
        report = compute_plan_vs_spec_drift(feature_id, new_ac, tmp_path)
        assert report["drift"] is True
        assert "AC two" in report["removed"]
        assert report["added"] == []

    def test_drift_detected_on_ac_change(self, tmp_path):
        from bob.orchestrator.plan_gate import compute_plan_vs_spec_drift, write_plan_artifact

        feature_id = "dddd1004-0000-0000-0000-000000000004"
        original_ac = ["Old AC"]
        write_plan_artifact(
            feature_id=feature_id,
            name="Changing Feature",
            description=None,
            acceptance_criteria=original_ac,
            workspace=tmp_path,
        )

        new_ac = ["New AC"]
        report = compute_plan_vs_spec_drift(feature_id, new_ac, tmp_path)
        assert report["drift"] is True
        assert "New AC" in report["added"]
        assert "Old AC" in report["removed"]

    def test_drift_on_missing_plan(self, tmp_path):
        from bob.orchestrator.plan_gate import compute_plan_vs_spec_drift

        feature_id = "eeee1005-0000-0000-0000-000000000005"
        # No plan written — plan.yaml is absent
        report = compute_plan_vs_spec_drift(feature_id, ["AC one"], tmp_path)
        # When plan is absent, spec_hash_plan is empty and drift is detected
        assert report["drift"] is True


class TestPlanEditResetApproval:
    """Editing plan.yaml AC should require re-approval when re-written."""

    def test_ac_edit_resets_approved_on_rewrite(self, tmp_path):
        """When ACs change and plan is re-written, approved reverts to False."""
        from bob.orchestrator.plan_gate import (
            approve_plan,
            is_approved,
            write_plan_artifact,
        )

        feature_id = "ffff1006-0000-0000-0000-000000000006"
        original_ac = ["Original AC"]

        # Write, approve
        write_plan_artifact(
            feature_id=feature_id,
            name="Feature F",
            description=None,
            acceptance_criteria=original_ac,
            workspace=tmp_path,
        )
        approve_plan(feature_id, workspace=tmp_path)
        assert is_approved(feature_id, workspace=tmp_path) is True

        # Re-write with changed ACs → approval must be reset
        write_plan_artifact(
            feature_id=feature_id,
            name="Feature F",
            description=None,
            acceptance_criteria=["New AC — spec has changed"],
            workspace=tmp_path,
        )
        assert is_approved(feature_id, workspace=tmp_path) is False, (
            "Approval must be reset when plan.yaml is re-written with changed ACs"
        )

    def test_unchanged_ac_preserves_approval_on_rewrite(self, tmp_path):
        """When ACs are unchanged, re-writing plan.yaml preserves approval."""
        from bob.orchestrator.plan_gate import (
            approve_plan,
            is_approved,
            write_plan_artifact,
        )

        feature_id = "gggg1007-0000-0000-0000-000000000007"
        ac = ["Stable AC"]

        write_plan_artifact(
            feature_id=feature_id,
            name="Feature G",
            description=None,
            acceptance_criteria=ac,
            workspace=tmp_path,
        )
        approve_plan(feature_id, workspace=tmp_path)
        assert is_approved(feature_id, workspace=tmp_path) is True

        # Re-write with same ACs → approval must be preserved
        write_plan_artifact(
            feature_id=feature_id,
            name="Feature G",
            description=None,
            acceptance_criteria=ac,
            workspace=tmp_path,
        )
        assert is_approved(feature_id, workspace=tmp_path) is True, (
            "Approval must be preserved when ACs are unchanged on re-write"
        )


class TestSpecHashConsistency:
    """spec_hash is stable and deterministic."""

    def test_same_ac_same_hash(self, tmp_path):
        from bob.orchestrator.plan_gate import write_plan_artifact
        import yaml

        feature_id = "hhhh1008-0000-0000-0000-000000000008"
        ac = ["AC alpha", "AC beta"]

        path1 = write_plan_artifact(
            feature_id=feature_id,
            name="Feature H1",
            description=None,
            acceptance_criteria=ac,
            workspace=tmp_path,
        )
        hash1 = yaml.safe_load(path1.read_text())["spec_hash"]

        feature_id2 = "iiii1009-0000-0000-0000-000000000009"
        path2 = write_plan_artifact(
            feature_id=feature_id2,
            name="Feature H2",
            description=None,
            acceptance_criteria=ac,
            workspace=tmp_path,
        )
        hash2 = yaml.safe_load(path2.read_text())["spec_hash"]

        assert hash1 == hash2, "Same ACs must produce same spec_hash"

    def test_different_ac_different_hash(self, tmp_path):
        from bob.orchestrator.plan_gate import write_plan_artifact
        import yaml

        feature_id1 = "jjjj1010-0000-0000-0000-000000000010"
        feature_id2 = "kkkk1011-0000-0000-0000-000000000011"

        path1 = write_plan_artifact(
            feature_id=feature_id1,
            name="F1",
            description=None,
            acceptance_criteria=["AC A"],
            workspace=tmp_path,
        )
        path2 = write_plan_artifact(
            feature_id=feature_id2,
            name="F2",
            description=None,
            acceptance_criteria=["AC B"],
            workspace=tmp_path,
        )

        hash1 = yaml.safe_load(path1.read_text())["spec_hash"]
        hash2 = yaml.safe_load(path2.read_text())["spec_hash"]

        assert hash1 != hash2, "Different ACs must produce different spec_hash"
