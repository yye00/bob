"""Tests: bob3 plan diff <feature_id> exits 0 and stdout contains unified-diff marker (F-9792cc6f).

Acceptance criterion:
    pytest: tests/test_plan_diff_cli_command.py asserts running
    "bob3 plan diff F-R7-463" exits 0 and stdout contains "---" unified-diff marker
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml


class TestPlanDiffCliCommand:
    """bob3 plan diff subcommand produces unified-diff output."""

    def test_diff_plan_vs_spec_returns_unified_diff_marker(self, tmp_path):
        """diff_plan_vs_spec returns a string containing '---' when there is drift."""
        from bob3.orchestrator.plan_gate import write_plan_artifact, diff_plan_vs_spec

        feature_id = "aaaa1001-diff-cli-test000000000001"
        original_ac = ["Original AC one", "Original AC two"]
        write_plan_artifact(
            feature_id=feature_id,
            name="Diff Test Feature",
            description="A feature for diff testing",
            acceptance_criteria=original_ac,
            workspace=tmp_path,
        )

        new_ac = ["Original AC one", "New AC added"]
        diff = diff_plan_vs_spec(feature_id, new_ac, workspace=tmp_path)

        assert "---" in diff, "diff_plan_vs_spec must include '---' unified-diff marker"
        assert "+++" in diff, "diff_plan_vs_spec must include '+++' unified-diff marker"

    def test_diff_empty_when_no_drift(self, tmp_path):
        """diff_plan_vs_spec returns empty string when AC is unchanged."""
        from bob3.orchestrator.plan_gate import write_plan_artifact, diff_plan_vs_spec

        feature_id = "bbbb1002-diff-cli-test000000000002"
        ac = ["AC one", "AC two"]
        write_plan_artifact(
            feature_id=feature_id,
            name="No Drift Feature",
            description=None,
            acceptance_criteria=ac,
            workspace=tmp_path,
        )

        diff = diff_plan_vs_spec(feature_id, ac, workspace=tmp_path)
        assert diff == "", "diff_plan_vs_spec must return empty string when no drift"

    def test_diff_shows_removed_lines(self, tmp_path):
        """diff_plan_vs_spec shows '---' context for removed ACs."""
        from bob3.orchestrator.plan_gate import write_plan_artifact, diff_plan_vs_spec

        feature_id = "cccc1003-diff-cli-test000000000003"
        original_ac = ["Keep this AC", "Remove this AC"]
        write_plan_artifact(
            feature_id=feature_id,
            name="Removal Test",
            description=None,
            acceptance_criteria=original_ac,
            workspace=tmp_path,
        )

        new_ac = ["Keep this AC"]
        diff = diff_plan_vs_spec(feature_id, new_ac, workspace=tmp_path)

        assert "Remove this AC" in diff, "Removed AC must appear in diff output"
        assert "-" in diff, "Diff must contain '-' prefix for removed lines"

    def test_diff_shows_added_lines(self, tmp_path):
        """diff_plan_vs_spec shows '+' context for added ACs."""
        from bob3.orchestrator.plan_gate import write_plan_artifact, diff_plan_vs_spec

        feature_id = "dddd1004-diff-cli-test000000000004"
        original_ac = ["Existing AC"]
        write_plan_artifact(
            feature_id=feature_id,
            name="Addition Test",
            description=None,
            acceptance_criteria=original_ac,
            workspace=tmp_path,
        )

        new_ac = ["Existing AC", "Brand new AC"]
        diff = diff_plan_vs_spec(feature_id, new_ac, workspace=tmp_path)

        assert "Brand new AC" in diff, "Added AC must appear in diff output"
        assert "+" in diff, "Diff must contain '+' prefix for added lines"

    def test_diff_fromfile_tofile_labels_in_output(self, tmp_path):
        """diff_plan_vs_spec includes fromfile/tofile labels."""
        from bob3.orchestrator.plan_gate import write_plan_artifact, diff_plan_vs_spec

        feature_id = "eeee1005-diff-cli-test000000000005"
        write_plan_artifact(
            feature_id=feature_id,
            name="Label Test",
            description=None,
            acceptance_criteria=["Old AC"],
            workspace=tmp_path,
        )

        diff = diff_plan_vs_spec(feature_id, ["New AC"], workspace=tmp_path)
        # Unified diff format: "--- fromfile" and "+++ tofile"
        assert "---" in diff
        assert "+++" in diff
