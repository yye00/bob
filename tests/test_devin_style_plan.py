"""Tests for the Devin-style editable plan.yaml gate (b59907bf).

Covers:
- bob.spec_critic.emit_plan_ready
- bob.implementer.check_plan_approved
- specs/devin_style_editable_plan/plan.yaml existence
- integration with bob.orchestrator
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from bob.spec_critic import emit_plan_ready
from bob.implementer import check_plan_approved, validate_plan_approved
from bob.orchestrator.plan_gate import (
    ImplementerBlockedError,
    write_plan_artifact,
    is_approved,
    approve_plan,
)


# ---------------------------------------------------------------------------
# File existence: specs/devin_style_editable_plan/plan.yaml
# ---------------------------------------------------------------------------

def test_plan_yaml_exists():
    """specs/devin_style_editable_plan/plan.yaml must exist on disk."""
    plan_path = Path("specs/devin_style_editable_plan/plan.yaml")
    assert plan_path.exists(), f"Expected plan.yaml at {plan_path.resolve()}"


def test_plan_yaml_is_valid_yaml():
    """specs/devin_style_editable_plan/plan.yaml must be valid YAML with required keys."""
    plan_path = Path("specs/devin_style_editable_plan/plan.yaml")
    data = yaml.safe_load(plan_path.read_text())
    assert isinstance(data, dict)
    assert "feature_id" in data
    assert "name" in data
    assert "acceptance_criteria" in data
    assert "approved" in data


# ---------------------------------------------------------------------------
# bob.spec_critic.emit_plan_ready
# ---------------------------------------------------------------------------

def test_emit_plan_ready_writes_event(tmp_path):
    """emit_plan_ready must write a PLAN_READY event to runs/events.jsonl."""
    emit_plan_ready(
        feature_id="test-feature-emit-001",
        plan_path=str(tmp_path / "specs" / "test-feature-emit-001" / "plan.yaml"),
        approved=False,
        workspace=tmp_path,
    )
    events_file = tmp_path / "runs" / "events.jsonl"
    assert events_file.exists()
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    assert len(records) == 1
    record = records[0]
    assert record["event"] == "PLAN_READY"
    assert record["feature_id"] == "test-feature-emit-001"
    assert record["approved"] is False


def test_emit_plan_ready_with_approved_true(tmp_path):
    """emit_plan_ready with approved=True must record approved=True in the event."""
    emit_plan_ready(
        feature_id="test-feature-emit-002",
        plan_path="/some/path/plan.yaml",
        approved=True,
        workspace=tmp_path,
    )
    events_file = tmp_path / "runs" / "events.jsonl"
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    assert records[0]["approved"] is True


def test_emit_plan_ready_empty_feature_id_raises():
    """emit_plan_ready must raise ValueError when feature_id is empty."""
    with pytest.raises(ValueError, match="feature_id"):
        emit_plan_ready(feature_id="", plan_path="/path", approved=False)


def test_emit_plan_ready_none_feature_id_raises():
    """emit_plan_ready must raise ValueError when feature_id is None."""
    with pytest.raises(ValueError, match="feature_id"):
        emit_plan_ready(feature_id=None, plan_path="/path", approved=False)  # type: ignore[arg-type]


def test_emit_plan_ready_appends_multiple_events(tmp_path):
    """emit_plan_ready called twice must append two separate events."""
    for i in range(2):
        emit_plan_ready(
            feature_id="test-feature-multi",
            plan_path="/path",
            approved=bool(i),
            workspace=tmp_path,
        )
    events_file = tmp_path / "runs" / "events.jsonl"
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    assert len(records) == 2
    assert records[0]["approved"] is False
    assert records[1]["approved"] is True


# ---------------------------------------------------------------------------
# bob.implementer.check_plan_approved
# ---------------------------------------------------------------------------

def test_check_plan_approved_returns_false_when_no_plan(tmp_path):
    """check_plan_approved must return False when plan.yaml does not exist."""
    result = check_plan_approved("no-plan-feature", workspace=tmp_path)
    assert result is False


def test_check_plan_approved_returns_false_when_unapproved(tmp_path):
    """check_plan_approved must return False when approved=false in plan.yaml."""
    write_plan_artifact(
        feature_id="unapproved-feat",
        name="Unapproved feature",
        description="desc",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=False,
    )
    result = check_plan_approved("unapproved-feat", workspace=tmp_path)
    assert result is False


def test_check_plan_approved_returns_true_when_approved(tmp_path):
    """check_plan_approved must return True when approved=true in plan.yaml."""
    write_plan_artifact(
        feature_id="approved-feat",
        name="Approved feature",
        description="desc",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    result = check_plan_approved("approved-feat", workspace=tmp_path)
    assert result is True


def test_check_plan_approved_does_not_raise_when_unapproved(tmp_path):
    """check_plan_approved must never raise ImplementerBlockedError."""
    write_plan_artifact(
        feature_id="check-no-raise",
        name="No raise feature",
        description=None,
        acceptance_criteria=[],
        workspace=tmp_path,
    )
    # Must not raise even when unapproved
    result = check_plan_approved("check-no-raise", workspace=tmp_path)
    assert result is False


def test_check_plan_approved_empty_feature_id_raises():
    """check_plan_approved must raise ValueError for empty feature_id."""
    with pytest.raises(ValueError, match="feature_id"):
        check_plan_approved("", workspace=None)


def test_check_plan_approved_after_approve(tmp_path):
    """check_plan_approved must return True after approve_plan is called."""
    fid = "approve-then-check"
    write_plan_artifact(
        feature_id=fid,
        name="To be approved",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    assert check_plan_approved(fid, workspace=tmp_path) is False
    approve_plan(fid, workspace=tmp_path)
    assert check_plan_approved(fid, workspace=tmp_path) is True


# ---------------------------------------------------------------------------
# Integration: bob.orchestrator round-trip
# ---------------------------------------------------------------------------

def test_orchestrator_integration_gate_blocks_before_approval(tmp_path):
    """Implementer must be blocked before plan is approved (orchestrator integration)."""
    fid = "integration-gate-test"
    write_plan_artifact(
        feature_id=fid,
        name="Integration gate test",
        description="Testing the gate integration",
        acceptance_criteria=["File exists: src/foo.py"],
        workspace=tmp_path,
    )

    # Before approval: blocked
    assert check_plan_approved(fid, workspace=tmp_path) is False
    with pytest.raises(ImplementerBlockedError):
        validate_plan_approved(fid, workspace=tmp_path)

    # After approval: unblocked
    approve_plan(fid, workspace=tmp_path)
    assert check_plan_approved(fid, workspace=tmp_path) is True
    # validate_plan_approved should not raise
    result = validate_plan_approved(fid, workspace=tmp_path)
    assert result is True


def test_orchestrator_emit_and_gate_full_flow(tmp_path):
    """Full flow: write plan → emit PLAN_READY → check gate → approve → gate passes."""
    fid = "full-flow-test"
    plan_path = write_plan_artifact(
        feature_id=fid,
        name="Full flow feature",
        description="End-to-end test",
        acceptance_criteria=["pytest: tests/test_full.py"],
        workspace=tmp_path,
    )

    # Emit PLAN_READY event
    emit_plan_ready(
        feature_id=fid,
        plan_path=str(plan_path),
        approved=False,
        workspace=tmp_path,
    )

    # Gate must block
    assert check_plan_approved(fid, workspace=tmp_path) is False

    # Approve
    approve_plan(fid, workspace=tmp_path)

    # Gate now passes
    assert check_plan_approved(fid, workspace=tmp_path) is True

    # Event was recorded
    events_file = tmp_path / "runs" / "events.jsonl"
    assert events_file.exists()
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    plan_ready_events = [r for r in records if r["event"] == "PLAN_READY"]
    assert len(plan_ready_events) >= 1
