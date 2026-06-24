"""Tests for bob75.plan_manager — emit_plan_ready and write_and_emit_plan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from bob75.plan_manager import emit_plan_ready, write_and_emit_plan
from bob.orchestrator.plan_gate import ImplementerBlockedError
from bob75.implementer import check_plan_approved


class TestEmitPlanReady:
    """Tests for emit_plan_ready function."""

    def test_emits_event_to_jsonl(self, tmp_path):
        """emit_plan_ready writes a PLAN_READY record to runs/events.jsonl."""
        emit_plan_ready(
            feature_id="feat-001",
            plan_path="specs/feat-001/plan.yaml",
            approved=False,
            workspace=tmp_path,
        )
        events_file = tmp_path / "runs" / "events.jsonl"
        assert events_file.exists()
        records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
        assert len(records) == 1
        assert records[0]["event"] == "PLAN_READY"
        assert records[0]["feature_id"] == "feat-001"
        assert records[0]["approved"] is False

    def test_emits_approved_true_when_specified(self, tmp_path):
        """emit_plan_ready records approved=True when passed."""
        emit_plan_ready(
            feature_id="feat-002",
            plan_path="specs/feat-002/plan.yaml",
            approved=True,
            workspace=tmp_path,
        )
        events_file = tmp_path / "runs" / "events.jsonl"
        records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
        assert records[0]["approved"] is True

    def test_empty_feature_id_raises_value_error(self, tmp_path):
        """emit_plan_ready raises ValueError for empty feature_id."""
        with pytest.raises(ValueError, match="feature_id"):
            emit_plan_ready(
                feature_id="",
                plan_path="specs/x/plan.yaml",
                approved=False,
                workspace=tmp_path,
            )

    def test_none_feature_id_raises_value_error(self, tmp_path):
        """emit_plan_ready raises ValueError for None feature_id."""
        with pytest.raises(ValueError, match="feature_id"):
            emit_plan_ready(
                feature_id=None,  # type: ignore[arg-type]
                plan_path="specs/x/plan.yaml",
                approved=False,
                workspace=tmp_path,
            )

    def test_plan_path_as_path_object(self, tmp_path):
        """emit_plan_ready accepts Path objects for plan_path."""
        emit_plan_ready(
            feature_id="feat-003",
            plan_path=Path("specs/feat-003/plan.yaml"),
            approved=False,
            workspace=tmp_path,
        )
        events_file = tmp_path / "runs" / "events.jsonl"
        records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
        assert records[0]["plan_path"] == "specs/feat-003/plan.yaml"

    def test_multiple_emissions_accumulate(self, tmp_path):
        """emit_plan_ready appends to the events file (does not overwrite)."""
        for i in range(3):
            emit_plan_ready(
                feature_id=f"feat-{i:03d}",
                plan_path=f"specs/feat-{i:03d}/plan.yaml",
                approved=False,
                workspace=tmp_path,
            )
        events_file = tmp_path / "runs" / "events.jsonl"
        records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
        assert len(records) == 3


class TestWriteAndEmitPlan:
    """Tests for write_and_emit_plan convenience function."""

    def test_writes_plan_yaml_and_emits_event(self, tmp_path):
        """write_and_emit_plan creates plan.yaml and emits PLAN_READY."""
        path = write_and_emit_plan(
            feature_id="wae-001",
            name="Test feature",
            description="A test feature",
            acceptance_criteria=["File exists: src/foo.py"],
            workspace=tmp_path,
        )
        assert path.exists()
        data = yaml.safe_load(path.read_text())
        assert data["feature_id"] == "wae-001"
        assert data["approved"] is False

        events_file = tmp_path / "runs" / "events.jsonl"
        assert events_file.exists()
        records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
        assert any(r["event"] == "PLAN_READY" and r["feature_id"] == "wae-001" for r in records)

    def test_auto_approve_flag(self, tmp_path):
        """write_and_emit_plan with auto_approve=True writes approved=True."""
        path = write_and_emit_plan(
            feature_id="wae-002",
            name="Auto-approved feature",
            description=None,
            acceptance_criteria=["File exists: src/bar.py"],
            workspace=tmp_path,
            auto_approve=True,
        )
        data = yaml.safe_load(path.read_text())
        assert data["approved"] is True

    def test_invalid_feature_id_raises(self, tmp_path):
        """write_and_emit_plan raises ValueError for invalid feature_id."""
        with pytest.raises(ValueError):
            write_and_emit_plan(
                feature_id="",
                name="Some feature",
                description=None,
                acceptance_criteria=["AC 1"],
                workspace=tmp_path,
            )


class TestCheckPlanApproved:
    """Tests for bob75.implementer.check_plan_approved function."""

    def test_approved_plan_returns_true(self, tmp_path):
        """check_plan_approved returns True when plan.yaml is approved."""
        write_and_emit_plan(
            feature_id="impl-001",
            name="Approved feature",
            description=None,
            acceptance_criteria=["File exists: src/foo.py"],
            workspace=tmp_path,
            auto_approve=True,
        )
        result = check_plan_approved("impl-001", workspace=tmp_path)
        assert result is True

    def test_unapproved_plan_raises(self, tmp_path):
        """check_plan_approved raises ImplementerBlockedError for unapproved plan."""
        write_and_emit_plan(
            feature_id="impl-002",
            name="Unapproved feature",
            description=None,
            acceptance_criteria=["File exists: src/bar.py"],
            workspace=tmp_path,
            auto_approve=False,
        )
        with pytest.raises(ImplementerBlockedError):
            check_plan_approved("impl-002", workspace=tmp_path)

    def test_missing_plan_raises(self, tmp_path):
        """check_plan_approved raises ImplementerBlockedError when plan.yaml missing."""
        with pytest.raises(ImplementerBlockedError):
            check_plan_approved("nonexistent-feature", workspace=tmp_path)

    def test_raise_on_blocked_false_returns_false_for_missing(self, tmp_path):
        """check_plan_approved returns False when raise_on_blocked=False and plan missing."""
        result = check_plan_approved(
            "nonexistent-feature",
            workspace=tmp_path,
            raise_on_blocked=False,
        )
        assert result is False

    def test_raise_on_blocked_false_returns_false_for_unapproved(self, tmp_path):
        """check_plan_approved returns False when raise_on_blocked=False and not approved."""
        write_and_emit_plan(
            feature_id="impl-003",
            name="Unapproved feature",
            description=None,
            acceptance_criteria=["File exists: src/baz.py"],
            workspace=tmp_path,
            auto_approve=False,
        )
        result = check_plan_approved(
            "impl-003",
            workspace=tmp_path,
            raise_on_blocked=False,
        )
        assert result is False

    def test_empty_feature_id_raises_value_error(self, tmp_path):
        """check_plan_approved raises ValueError for empty feature_id."""
        with pytest.raises(ValueError, match="feature_id"):
            check_plan_approved("", workspace=tmp_path)

    def test_none_feature_id_raises_value_error(self, tmp_path):
        """check_plan_approved raises ValueError for None feature_id."""
        with pytest.raises(ValueError, match="feature_id"):
            check_plan_approved(None, workspace=tmp_path)  # type: ignore[arg-type]
