"""Tests: plan.yaml is written after spec-critic passes (F-0bf30902).

Acceptance criterion:
    pytest: tests/test_plan_artifact_written_after_critic.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


class TestWritePlanArtifact:
    """write_plan_artifact writes a valid plan.yaml under specs/<feature_id>/."""

    def test_plan_yaml_created(self, tmp_path):
        from bob.orchestrator.plan_gate import write_plan_artifact

        feature_id = "aaaa1111-0000-0000-0000-000000000001"
        ac = ["File exists: src/foo.py", "pytest: tests/test_foo.py"]

        plan_path = write_plan_artifact(
            feature_id=feature_id,
            name="My Feature",
            description="Does something",
            acceptance_criteria=ac,
            workspace=tmp_path,
        )

        assert plan_path.exists(), "plan.yaml must exist after write_plan_artifact"

    def test_plan_yaml_location(self, tmp_path):
        from bob.orchestrator.plan_gate import write_plan_artifact

        feature_id = "bbbb2222-0000-0000-0000-000000000002"
        plan_path = write_plan_artifact(
            feature_id=feature_id,
            name="Feature B",
            description=None,
            acceptance_criteria=["AC1"],
            workspace=tmp_path,
        )

        expected = tmp_path / "specs" / feature_id / "plan.yaml"
        assert plan_path == expected.resolve()

    def test_plan_yaml_content(self, tmp_path):
        from bob.orchestrator.plan_gate import write_plan_artifact

        feature_id = "cccc3333-0000-0000-0000-000000000003"
        ac = ["AC one", "AC two"]

        plan_path = write_plan_artifact(
            feature_id=feature_id,
            name="Feature C",
            description="A description",
            acceptance_criteria=ac,
            workspace=tmp_path,
        )

        data = yaml.safe_load(plan_path.read_text())
        assert data["feature_id"] == feature_id
        assert data["name"] == "Feature C"
        assert data["acceptance_criteria"] == ac
        assert "spec_hash" in data
        assert "written_at" in data

    def test_plan_yaml_default_unapproved(self, tmp_path):
        from bob.orchestrator.plan_gate import write_plan_artifact

        feature_id = "dddd4444-0000-0000-0000-000000000004"

        plan_path = write_plan_artifact(
            feature_id=feature_id,
            name="Feature D",
            description=None,
            acceptance_criteria=["AC"],
            workspace=tmp_path,
        )

        data = yaml.safe_load(plan_path.read_text())
        assert data["approved"] is False, "Default plan should be unapproved"

    def test_auto_approve_flag(self, tmp_path):
        from bob.orchestrator.plan_gate import write_plan_artifact

        feature_id = "eeee5555-0000-0000-0000-000000000005"

        plan_path = write_plan_artifact(
            feature_id=feature_id,
            name="Feature E",
            description=None,
            acceptance_criteria=["AC"],
            workspace=tmp_path,
            auto_approve=True,
        )

        data = yaml.safe_load(plan_path.read_text())
        assert data["approved"] is True

    def test_plan_ready_logged(self, tmp_path, caplog):
        import logging
        from bob.orchestrator.plan_gate import write_plan_artifact

        feature_id = "ffff6666-0000-0000-0000-000000000006"

        with caplog.at_level(logging.INFO, logger="bob.orchestrator.plan_gate"):
            write_plan_artifact(
                feature_id=feature_id,
                name="Feature F",
                description=None,
                acceptance_criteria=["AC"],
                workspace=tmp_path,
            )

        assert any("PLAN_READY" in record.message for record in caplog.records), (
            "write_plan_artifact must log a PLAN_READY event"
        )

    def test_idempotent_preserves_approval_when_spec_unchanged(self, tmp_path):
        from bob.orchestrator.plan_gate import write_plan_artifact, approve_plan

        feature_id = "gggg7777-0000-0000-0000-000000000007"
        ac = ["Stable AC"]

        # First write → unapproved
        write_plan_artifact(
            feature_id=feature_id,
            name="Feature G",
            description=None,
            acceptance_criteria=ac,
            workspace=tmp_path,
        )
        # Manually approve
        approve_plan(feature_id, workspace=tmp_path)

        # Second write with SAME ac → should preserve approval
        plan_path = write_plan_artifact(
            feature_id=feature_id,
            name="Feature G",
            description=None,
            acceptance_criteria=ac,
            workspace=tmp_path,
        )
        data = yaml.safe_load(plan_path.read_text())
        assert data["approved"] is True, "Idempotent re-write must preserve approval when spec unchanged"

    def test_spec_change_resets_approval(self, tmp_path):
        from bob.orchestrator.plan_gate import write_plan_artifact, approve_plan

        feature_id = "hhhh8888-0000-0000-0000-000000000008"

        write_plan_artifact(
            feature_id=feature_id,
            name="Feature H",
            description=None,
            acceptance_criteria=["Old AC"],
            workspace=tmp_path,
        )
        approve_plan(feature_id, workspace=tmp_path)

        # Write with CHANGED ac → approval should NOT carry over
        plan_path = write_plan_artifact(
            feature_id=feature_id,
            name="Feature H",
            description=None,
            acceptance_criteria=["New AC — spec changed"],
            workspace=tmp_path,
        )
        data = yaml.safe_load(plan_path.read_text())
        assert data["approved"] is False, "Spec change must reset approval to False"


class TestIsApproved:
    """is_approved returns correct boolean based on plan.yaml state."""

    def test_returns_false_when_file_absent(self, tmp_path):
        from bob.orchestrator.plan_gate import is_approved

        assert is_approved("nonexistent-feature-id", workspace=tmp_path) is False

    def test_returns_false_when_approved_false(self, tmp_path):
        from bob.orchestrator.plan_gate import write_plan_artifact, is_approved

        feature_id = "iiii9999-0000-0000-0000-000000000009"
        write_plan_artifact(
            feature_id=feature_id,
            name="Feature I",
            description=None,
            acceptance_criteria=["AC"],
            workspace=tmp_path,
        )
        assert is_approved(feature_id, workspace=tmp_path) is False

    def test_returns_true_after_approve(self, tmp_path):
        from bob.orchestrator.plan_gate import write_plan_artifact, approve_plan, is_approved

        feature_id = "jjjj0000-0000-0000-0000-000000000010"
        write_plan_artifact(
            feature_id=feature_id,
            name="Feature J",
            description=None,
            acceptance_criteria=["AC"],
            workspace=tmp_path,
        )
        approve_plan(feature_id, workspace=tmp_path)
        assert is_approved(feature_id, workspace=tmp_path) is True

    def test_returns_false_on_malformed_file(self, tmp_path):
        from bob.orchestrator.plan_gate import is_approved

        feature_id = "kkkk1111-0000-0000-0000-000000000011"
        plan_dir = tmp_path / "specs" / feature_id
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.yaml").write_text(":: not valid yaml ::")

        assert is_approved(feature_id, workspace=tmp_path) is False
