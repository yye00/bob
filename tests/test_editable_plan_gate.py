"""Tests for the Devin-style editable plan.yaml gate (feature 997c049a).

Covers:
- specs/editable_plan_gate/plan.yaml artifact exists
- bob3.spec_synthesis.emit_plan_ready_event
- bob3.implementer.check_plan_approval
- bob3.plan_editor.handle_plan_edits
- Integration with bob3.orchestrator
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from bob3.orchestrator.plan_gate import (
    ImplementerBlockedError,
    approve_plan,
    emit_plan_ready_event,
    is_approved,
    write_plan_artifact,
)


# ---------------------------------------------------------------------------
# AC: File exists: specs/editable_plan_gate/plan.yaml
# ---------------------------------------------------------------------------

def test_editable_plan_gate_plan_yaml_exists():
    """The specs/editable_plan_gate/plan.yaml artifact must exist on disk."""
    plan_path = Path("specs/editable_plan_gate/plan.yaml")
    assert plan_path.exists(), (
        f"Required artifact missing: {plan_path}. "
        "This file must be present for the Devin-style plan gate feature."
    )
    data = yaml.safe_load(plan_path.read_text())
    assert isinstance(data, dict), "plan.yaml must contain a YAML mapping"
    assert "feature_id" in data, "plan.yaml must contain feature_id key"


# ---------------------------------------------------------------------------
# AC: Function defined: bob3.spec_synthesis.emit_plan_ready_event
# ---------------------------------------------------------------------------

def test_spec_synthesis_emit_plan_ready_event_importable():
    """bob3.spec_synthesis.emit_plan_ready_event must be importable."""
    from bob3.spec_synthesis import emit_plan_ready_event as fn  # noqa: PLC0415
    assert callable(fn), "emit_plan_ready_event must be a callable function"


def test_spec_synthesis_emit_plan_ready_event_writes_event(tmp_path):
    """emit_plan_ready_event from spec_synthesis must append a PLAN_READY record."""
    from bob3.spec_synthesis import emit_plan_ready_event  # noqa: PLC0415

    emit_plan_ready_event(
        feature_id="test-feat-synth-001",
        plan_path="/some/path/plan.yaml",
        approved=False,
        workspace=tmp_path,
    )

    events_file = tmp_path / "runs" / "events.jsonl"
    assert events_file.exists(), "events.jsonl must be created"
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    assert any(r.get("event") == "PLAN_READY" for r in records)
    assert any(r.get("feature_id") == "test-feat-synth-001" for r in records)


def test_spec_synthesis_emit_plan_ready_event_invalid_feature_id_raises():
    """emit_plan_ready_event must raise ValueError when feature_id is empty."""
    from bob3.spec_synthesis import emit_plan_ready_event  # noqa: PLC0415

    with pytest.raises(ValueError, match="feature_id"):
        emit_plan_ready_event(
            feature_id="",
            plan_path="/some/path/plan.yaml",
            approved=False,
        )


# ---------------------------------------------------------------------------
# AC: Function defined: bob3.implementer.check_plan_approval
# ---------------------------------------------------------------------------

def test_implementer_check_plan_approval_importable():
    """bob3.implementer.check_plan_approval must be importable."""
    from bob3.implementer import check_plan_approval  # noqa: PLC0415
    assert callable(check_plan_approval), "check_plan_approval must be a callable"


def test_check_plan_approval_returns_false_when_missing(tmp_path):
    """check_plan_approval must return False when plan.yaml is absent."""
    from bob3.implementer import check_plan_approval  # noqa: PLC0415

    result = check_plan_approval(feature_id="no-such-feature-xyz", workspace=tmp_path)
    assert result is False


def test_check_plan_approval_returns_true_when_approved(tmp_path):
    """check_plan_approval must return True when plan.yaml.approved is true."""
    from bob3.implementer import check_plan_approval  # noqa: PLC0415

    fid = "approved-feature-001"
    write_plan_artifact(
        feature_id=fid,
        name="Approved feature",
        description="desc",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )

    result = check_plan_approval(feature_id=fid, workspace=tmp_path)
    assert result is True


def test_check_plan_approval_returns_false_when_not_approved(tmp_path):
    """check_plan_approval must return False when approved=false in plan.yaml."""
    from bob3.implementer import check_plan_approval  # noqa: PLC0415

    fid = "unapproved-feature-001"
    write_plan_artifact(
        feature_id=fid,
        name="Unapproved feature",
        description="desc",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=False,
    )

    result = check_plan_approval(feature_id=fid, workspace=tmp_path)
    assert result is False


def test_check_plan_approval_raises_on_empty_feature_id():
    """check_plan_approval must raise ValueError when feature_id is empty."""
    from bob3.implementer import check_plan_approval  # noqa: PLC0415

    with pytest.raises(ValueError, match="feature_id"):
        check_plan_approval(feature_id="")


# ---------------------------------------------------------------------------
# AC: Function defined: bob3.plan_editor.handle_plan_edits
# ---------------------------------------------------------------------------

def test_plan_editor_handle_plan_edits_importable():
    """bob3.plan_editor.handle_plan_edits must be importable."""
    from bob3.plan_editor import handle_plan_edits  # noqa: PLC0415
    assert callable(handle_plan_edits), "handle_plan_edits must be a callable"


def test_handle_plan_edits_detects_drift(tmp_path):
    """handle_plan_edits must detect drift when ACs change."""
    from bob3.plan_editor import handle_plan_edits  # noqa: PLC0415

    fid = "plan-edit-feat-001"
    write_plan_artifact(
        feature_id=fid,
        name="Edit test feature",
        description="desc",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )

    result = handle_plan_edits(
        feature_id=fid,
        name="Edit test feature",
        description="desc",
        new_acceptance_criteria=["AC 1", "AC 2 (new)"],
        workspace=tmp_path,
    )

    assert isinstance(result, dict)
    assert result["drift_detected"] is True
    assert "added" in result
    assert "AC 2 (new)" in result["added"]


def test_handle_plan_edits_no_drift(tmp_path):
    """handle_plan_edits returns drift_detected=False when ACs are unchanged."""
    from bob3.plan_editor import handle_plan_edits  # noqa: PLC0415

    fid = "plan-edit-feat-002"
    acs = ["AC 1", "AC 2"]
    write_plan_artifact(
        feature_id=fid,
        name="No drift feature",
        description="desc",
        acceptance_criteria=acs,
        workspace=tmp_path,
        auto_approve=True,
    )

    result = handle_plan_edits(
        feature_id=fid,
        name="No drift feature",
        description="desc",
        new_acceptance_criteria=acs,
        workspace=tmp_path,
    )

    assert result["drift_detected"] is False


def test_handle_plan_edits_resets_approval_on_drift(tmp_path):
    """handle_plan_edits must reset approved=False when drift is detected."""
    from bob3.plan_editor import handle_plan_edits  # noqa: PLC0415

    fid = "plan-edit-feat-003"
    write_plan_artifact(
        feature_id=fid,
        name="Drift reset feature",
        description="desc",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )

    result = handle_plan_edits(
        feature_id=fid,
        name="Drift reset feature",
        description="desc",
        new_acceptance_criteria=["AC 1", "AC 2"],
        workspace=tmp_path,
    )

    assert result["implementer_blocked"] is True
    assert result["approved"] is False


def test_handle_plan_edits_raises_on_empty_feature_id(tmp_path):
    """handle_plan_edits must raise ValueError when feature_id is empty."""
    from bob3.plan_editor import handle_plan_edits  # noqa: PLC0415

    with pytest.raises(ValueError, match="feature_id"):
        handle_plan_edits(
            feature_id="",
            name="Valid name",
            description="desc",
            new_acceptance_criteria=["AC 1"],
            workspace=tmp_path,
        )


# ---------------------------------------------------------------------------
# AC: integration: bob3.orchestrator
# ---------------------------------------------------------------------------

def test_plan_gate_integrated_with_orchestrator():
    """plan_gate functions are accessible via bob3.orchestrator integration."""
    from bob3.orchestrator.plan_gate import (  # noqa: PLC0415
        write_plan_artifact,
        is_approved,
        approve_plan,
        emit_plan_ready_event,
        ImplementerBlockedError,
        refuse_implementer_when_unapproved,
    )
    assert callable(write_plan_artifact)
    assert callable(is_approved)
    assert callable(approve_plan)
    assert callable(emit_plan_ready_event)
    assert issubclass(ImplementerBlockedError, RuntimeError)
    assert callable(refuse_implementer_when_unapproved)


def test_implementer_blocked_error_raised_when_not_approved(tmp_path):
    """refuse_implementer_when_unapproved must raise ImplementerBlockedError."""
    from bob3.orchestrator.plan_gate import (  # noqa: PLC0415
        refuse_implementer_when_unapproved,
        write_plan_artifact,
    )

    fid = "orchestrator-test-001"
    write_plan_artifact(
        feature_id=fid,
        name="Blocked feature",
        description="desc",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=False,
    )

    with pytest.raises(ImplementerBlockedError):
        refuse_implementer_when_unapproved(feature_id=fid, workspace=tmp_path)


def test_implementer_not_blocked_after_approval(tmp_path):
    """refuse_implementer_when_unapproved must not raise when plan is approved."""
    from bob3.orchestrator.plan_gate import (  # noqa: PLC0415
        refuse_implementer_when_unapproved,
        write_plan_artifact,
        approve_plan,
    )

    fid = "orchestrator-test-002"
    write_plan_artifact(
        feature_id=fid,
        name="Approvable feature",
        description="desc",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=False,
    )

    approve_plan(fid, workspace=tmp_path)

    # Must not raise
    refuse_implementer_when_unapproved(feature_id=fid, workspace=tmp_path)


def test_validate_plan_approved_blocks_implementer(tmp_path):
    """validate_plan_approved raises ImplementerBlockedError when unapproved."""
    from bob3.implementer import validate_plan_approved  # noqa: PLC0415

    fid = "validate-blocked-001"
    write_plan_artifact(
        feature_id=fid,
        name="Blocked impl",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=False,
    )

    with pytest.raises(ImplementerBlockedError):
        validate_plan_approved(feature_id=fid, workspace=tmp_path)


def test_validate_plan_approved_returns_true_when_approved(tmp_path):
    """validate_plan_approved returns True when plan is approved."""
    from bob3.implementer import validate_plan_approved  # noqa: PLC0415

    fid = "validate-approved-001"
    write_plan_artifact(
        feature_id=fid,
        name="Approved impl",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )

    result = validate_plan_approved(feature_id=fid, workspace=tmp_path)
    assert result is True


def test_plan_ready_event_written_by_write_plan_artifact(tmp_path):
    """write_plan_artifact must emit a PLAN_READY event to runs/events.jsonl."""
    fid = "event-test-001"
    write_plan_artifact(
        feature_id=fid,
        name="Event feature",
        description="desc",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )

    events_file = tmp_path / "runs" / "events.jsonl"
    assert events_file.exists(), "events.jsonl must exist after write_plan_artifact"
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    plan_ready = [r for r in records if r.get("event") == "PLAN_READY"]
    assert len(plan_ready) >= 1, "At least one PLAN_READY event must be emitted"
    assert plan_ready[0]["feature_id"] == fid
