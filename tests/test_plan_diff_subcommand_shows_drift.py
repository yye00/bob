"""Tests: diff_plan_vs_spec shows drift between plan.yaml and current spec (F-9792cc6f).

Acceptance criterion:
    pytest: tests/test_plan_diff_subcommand_shows_drift.py
"""

from __future__ import annotations

import pytest
import yaml


class TestPlanDiffSubcommandShowsDrift:
    """diff_plan_vs_spec correctly detects and displays spec drift."""

    def test_drift_detected_and_shown_in_diff(self, tmp_path):
        """When spec AC changes after plan.yaml written, diff shows drift."""
        from bob3.orchestrator.plan_gate import write_plan_artifact, diff_plan_vs_spec

        feature_id = "aaaa4001-diff-subcommand-test000000001"
        original_ac = ["AC alpha", "AC beta"]
        write_plan_artifact(
            feature_id=feature_id,
            name="Drift Feature",
            description=None,
            acceptance_criteria=original_ac,
            workspace=tmp_path,
        )

        new_ac = ["AC alpha", "AC gamma (changed)"]
        diff = diff_plan_vs_spec(feature_id, new_ac, workspace=tmp_path)

        assert diff, "diff must be non-empty when drift is present"
        assert "---" in diff, "unified-diff '---' marker must appear"
        assert "AC gamma (changed)" in diff or "+AC gamma" in diff or "gamma" in diff

    def test_no_drift_shows_empty_diff(self, tmp_path):
        """When spec AC is unchanged, diff returns empty string."""
        from bob3.orchestrator.plan_gate import write_plan_artifact, diff_plan_vs_spec

        feature_id = "bbbb4002-diff-subcommand-test000000002"
        ac = ["Stable AC one", "Stable AC two"]
        write_plan_artifact(
            feature_id=feature_id,
            name="Stable Feature",
            description=None,
            acceptance_criteria=ac,
            workspace=tmp_path,
        )

        diff = diff_plan_vs_spec(feature_id, ac, workspace=tmp_path)
        assert diff == "", f"Expected empty diff for unchanged AC, got: {diff!r}"

    def test_drift_on_full_replacement(self, tmp_path):
        """Complete AC replacement shows all old lines removed, new lines added."""
        from bob3.orchestrator.plan_gate import write_plan_artifact, diff_plan_vs_spec

        feature_id = "cccc4003-diff-subcommand-test000000003"
        original_ac = ["Completely replaced AC"]
        write_plan_artifact(
            feature_id=feature_id,
            name="Replacement Feature",
            description=None,
            acceptance_criteria=original_ac,
            workspace=tmp_path,
        )

        new_ac = ["Brand new AC"]
        diff = diff_plan_vs_spec(feature_id, new_ac, workspace=tmp_path)

        assert "Completely replaced AC" in diff
        assert "Brand new AC" in diff
        assert "---" in diff

    def test_drift_on_ac_ordering_change(self, tmp_path):
        """Reordering AC elements is detected as drift (hash-based comparison)."""
        from bob3.orchestrator.plan_gate import write_plan_artifact, compute_plan_vs_spec_drift

        feature_id = "dddd4004-diff-subcommand-test000000004"
        original_ac = ["AC one", "AC two"]
        write_plan_artifact(
            feature_id=feature_id,
            name="Ordering Feature",
            description=None,
            acceptance_criteria=original_ac,
            workspace=tmp_path,
        )

        reversed_ac = ["AC two", "AC one"]
        report = compute_plan_vs_spec_drift(feature_id, reversed_ac, workspace=tmp_path)
        # Order matters since hash is based on joined string
        assert report["drift"] is True, "Reordering AC must be detected as drift"

    def test_drift_report_includes_added_and_removed_keys(self, tmp_path):
        """compute_plan_vs_spec_drift report has 'added' and 'removed' lists."""
        from bob3.orchestrator.plan_gate import write_plan_artifact, compute_plan_vs_spec_drift

        feature_id = "eeee4005-diff-subcommand-test000000005"
        original_ac = ["Keep this", "Remove this"]
        write_plan_artifact(
            feature_id=feature_id,
            name="Keys Feature",
            description=None,
            acceptance_criteria=original_ac,
            workspace=tmp_path,
        )

        new_ac = ["Keep this", "Add this"]
        report = compute_plan_vs_spec_drift(feature_id, new_ac, workspace=tmp_path)

        assert "added" in report
        assert "removed" in report
        assert "Add this" in report["added"]
        assert "Remove this" in report["removed"]
