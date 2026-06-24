"""Tests for the Devin-style editable plan.yaml gate before any implementer fires.

Covers the core contract:
1. spec-critic passes → plan.yaml written → PLAN_READY event emitted
2. Implementer blocks when plan.yaml is absent or unapproved
3. Implementer proceeds when plan.yaml.approved is true
4. Edits to plan.yaml re-trigger spec critic via drift detection
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from bob3.orchestrator.plan_gate import (
    ImplementerBlockedError,
    approve_plan,
    compute_plan_vs_spec_drift,
    diff_plan_vs_spec,
    emit_plan_ready_event,
    is_approved,
    load_plan,
    refuse_implementer_when_unapproved,
    retrigger_critic_on_edit,
    write_plan_artifact,
)
from bob3.spec_critic import emit_plan_ready
from bob3.implementer import check_plan_approved, validate_plan_approved


# ---------------------------------------------------------------------------
# Test: emit_plan_ready in bob3.spec_critic
# ---------------------------------------------------------------------------


def test_emit_plan_ready_appends_event(tmp_path):
    """emit_plan_ready must append a PLAN_READY event to runs/events.jsonl."""
    emit_plan_ready(
        feature_id="test-feat-001",
        plan_path=str(tmp_path / "specs" / "test-feat-001" / "plan.yaml"),
        approved=False,
        workspace=tmp_path,
    )
    events_file = tmp_path / "runs" / "events.jsonl"
    assert events_file.exists()
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    assert len(records) == 1
    assert records[0]["event"] == "PLAN_READY"
    assert records[0]["feature_id"] == "test-feat-001"
    assert records[0]["approved"] is False


def test_emit_plan_ready_with_approved_true(tmp_path):
    """emit_plan_ready with approved=True must record that in the event."""
    emit_plan_ready(
        feature_id="test-feat-002",
        plan_path="/some/path/plan.yaml",
        approved=True,
        workspace=tmp_path,
    )
    events_file = tmp_path / "runs" / "events.jsonl"
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    assert records[0]["approved"] is True


def test_emit_plan_ready_raises_on_empty_feature_id(tmp_path):
    """emit_plan_ready must raise ValueError when feature_id is empty."""
    with pytest.raises(ValueError, match="feature_id"):
        emit_plan_ready(
            feature_id="",
            plan_path="/some/path/plan.yaml",
            approved=False,
            workspace=tmp_path,
        )


# ---------------------------------------------------------------------------
# Test: write_plan_artifact creates plan.yaml
# ---------------------------------------------------------------------------


def test_write_plan_artifact_creates_file(tmp_path):
    """write_plan_artifact must create specs/<feature>/plan.yaml with correct fields."""
    path = write_plan_artifact(
        feature_id="plan-test-001",
        name="Test feature",
        description="A test feature for plan gate",
        acceptance_criteria=["File exists: src/foo.py", "pytest: tests/test_foo.py"],
        workspace=tmp_path,
    )
    assert path.exists()
    data = yaml.safe_load(path.read_text())
    assert data["feature_id"] == "plan-test-001"
    assert data["name"] == "Test feature"
    assert data["approved"] is False
    assert "spec_hash" in data
    assert "written_at" in data


def test_write_plan_artifact_emits_event(tmp_path):
    """write_plan_artifact must emit PLAN_READY event to runs/events.jsonl."""
    write_plan_artifact(
        feature_id="plan-test-002",
        name="Event test feature",
        description="Tests event emission",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    events_file = tmp_path / "runs" / "events.jsonl"
    assert events_file.exists()
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    plan_events = [r for r in records if r["event"] == "PLAN_READY" and r["feature_id"] == "plan-test-002"]
    assert len(plan_events) == 1


def test_write_plan_artifact_auto_approve(tmp_path):
    """write_plan_artifact with auto_approve=True must set approved=True."""
    path = write_plan_artifact(
        feature_id="plan-test-003",
        name="Auto-approve test",
        description="Tests auto approval",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    data = yaml.safe_load(path.read_text())
    assert data["approved"] is True


# ---------------------------------------------------------------------------
# Test: check_plan_approved in bob3.implementer
# ---------------------------------------------------------------------------


def test_check_plan_approved_returns_false_when_no_plan(tmp_path):
    """check_plan_approved must return False when plan.yaml does not exist."""
    result = check_plan_approved(feature_id="nonexistent", workspace=tmp_path)
    assert result is False


def test_check_plan_approved_returns_false_when_unapproved(tmp_path):
    """check_plan_approved must return False when plan.yaml exists with approved=false."""
    write_plan_artifact(
        feature_id="check-test-001",
        name="Check test",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    result = check_plan_approved(feature_id="check-test-001", workspace=tmp_path)
    assert result is False


def test_check_plan_approved_returns_true_when_approved(tmp_path):
    """check_plan_approved must return True when plan.yaml has approved=true."""
    write_plan_artifact(
        feature_id="check-test-002",
        name="Check approved test",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    result = check_plan_approved(feature_id="check-test-002", workspace=tmp_path)
    assert result is True


def test_check_plan_approved_after_manual_approval(tmp_path):
    """check_plan_approved must return True after approve_plan sets approved=true."""
    write_plan_artifact(
        feature_id="check-test-003",
        name="Manual approve test",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    approve_plan(feature_id="check-test-003", workspace=tmp_path)
    result = check_plan_approved(feature_id="check-test-003", workspace=tmp_path)
    assert result is True


def test_check_plan_approved_raises_on_empty_feature_id(tmp_path):
    """check_plan_approved must raise ValueError when feature_id is empty."""
    with pytest.raises(ValueError):
        check_plan_approved(feature_id="", workspace=tmp_path)


# ---------------------------------------------------------------------------
# Test: validate_plan_approved (raises by default)
# ---------------------------------------------------------------------------


def test_validate_plan_approved_raises_when_unapproved(tmp_path):
    """validate_plan_approved must raise ImplementerBlockedError when plan is not approved."""
    write_plan_artifact(
        feature_id="validate-test-001",
        name="Validate test",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    with pytest.raises(ImplementerBlockedError):
        validate_plan_approved(feature_id="validate-test-001", workspace=tmp_path)


def test_validate_plan_approved_returns_true_when_approved(tmp_path):
    """validate_plan_approved must return True when plan.yaml is approved."""
    write_plan_artifact(
        feature_id="validate-test-002",
        name="Validate approved test",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    result = validate_plan_approved(feature_id="validate-test-002", workspace=tmp_path)
    assert result is True


def test_validate_plan_approved_returns_false_when_raise_on_blocked_false(tmp_path):
    """validate_plan_approved with raise_on_blocked=False must return False when unapproved."""
    result = validate_plan_approved(
        feature_id="validate-test-003",
        workspace=tmp_path,
        raise_on_blocked=False,
    )
    assert result is False


# ---------------------------------------------------------------------------
# Test: refuse_implementer_when_unapproved
# ---------------------------------------------------------------------------


def test_refuse_implementer_raises_when_plan_absent(tmp_path):
    """refuse_implementer_when_unapproved must raise ImplementerBlockedError when plan absent."""
    with pytest.raises(ImplementerBlockedError):
        refuse_implementer_when_unapproved(feature_id="no-plan-feat", workspace=tmp_path)


def test_refuse_implementer_does_not_raise_when_approved(tmp_path):
    """refuse_implementer_when_unapproved must not raise when plan.yaml.approved is true."""
    write_plan_artifact(
        feature_id="approved-feat",
        name="Approved feature",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    refuse_implementer_when_unapproved(feature_id="approved-feat", workspace=tmp_path)  # no raise


# ---------------------------------------------------------------------------
# Test: drift detection and critic re-trigger
# ---------------------------------------------------------------------------


def test_compute_plan_vs_spec_drift_no_drift(tmp_path):
    """compute_plan_vs_spec_drift must report drift=False when AC is unchanged."""
    acs = ["AC 1", "AC 2"]
    write_plan_artifact(
        feature_id="drift-test-001",
        name="Drift test",
        description=None,
        acceptance_criteria=acs,
        workspace=tmp_path,
    )
    report = compute_plan_vs_spec_drift("drift-test-001", acs, workspace=tmp_path)
    assert report["drift"] is False
    assert report["added"] == []
    assert report["removed"] == []


def test_compute_plan_vs_spec_drift_detects_added_ac(tmp_path):
    """compute_plan_vs_spec_drift must report drift=True and list added ACs."""
    original_acs = ["AC 1"]
    write_plan_artifact(
        feature_id="drift-test-002",
        name="Drift added test",
        description=None,
        acceptance_criteria=original_acs,
        workspace=tmp_path,
    )
    new_acs = ["AC 1", "AC 2 (new)"]
    report = compute_plan_vs_spec_drift("drift-test-002", new_acs, workspace=tmp_path)
    assert report["drift"] is True
    assert "AC 2 (new)" in report["added"]


def test_compute_plan_vs_spec_drift_detects_removed_ac(tmp_path):
    """compute_plan_vs_spec_drift must report drift=True and list removed ACs."""
    original_acs = ["AC 1", "AC 2"]
    write_plan_artifact(
        feature_id="drift-test-003",
        name="Drift removed test",
        description=None,
        acceptance_criteria=original_acs,
        workspace=tmp_path,
    )
    new_acs = ["AC 1"]
    report = compute_plan_vs_spec_drift("drift-test-003", new_acs, workspace=tmp_path)
    assert report["drift"] is True
    assert "AC 2" in report["removed"]


def test_retrigger_critic_no_drift_returns_empty(tmp_path):
    """retrigger_critic_on_edit must return empty list when there is no drift."""
    acs = ["AC 1"]
    write_plan_artifact(
        feature_id="retrig-test-001",
        name="Retrigger no-drift",
        description=None,
        acceptance_criteria=acs,
        workspace=tmp_path,
    )
    result = retrigger_critic_on_edit(
        feature_id="retrig-test-001",
        name="Retrigger no-drift",
        description=None,
        acceptance_criteria=acs,
        workspace=tmp_path,
    )
    assert result == []


# ---------------------------------------------------------------------------
# Test: diff_plan_vs_spec
# ---------------------------------------------------------------------------


def test_diff_plan_vs_spec_empty_when_no_drift(tmp_path):
    """diff_plan_vs_spec must return empty string when there is no drift."""
    acs = ["AC 1", "AC 2"]
    write_plan_artifact(
        feature_id="diff-test-001",
        name="Diff test",
        description=None,
        acceptance_criteria=acs,
        workspace=tmp_path,
    )
    result = diff_plan_vs_spec("diff-test-001", acs, workspace=tmp_path)
    assert result == ""


def test_diff_plan_vs_spec_non_empty_when_drifted(tmp_path):
    """diff_plan_vs_spec must return a non-empty diff string when ACs have changed."""
    original_acs = ["AC 1"]
    write_plan_artifact(
        feature_id="diff-test-002",
        name="Diff drifted test",
        description=None,
        acceptance_criteria=original_acs,
        workspace=tmp_path,
    )
    new_acs = ["AC 1", "AC 2 (new)"]
    result = diff_plan_vs_spec("diff-test-002", new_acs, workspace=tmp_path)
    assert result != ""
    assert "AC 2 (new)" in result


# ---------------------------------------------------------------------------
# Test: integration with orchestrator — plan.yaml location
# ---------------------------------------------------------------------------


def test_plan_yaml_is_written_under_specs_dir(tmp_path):
    """plan.yaml must be created at specs/<feature_id>/plan.yaml."""
    feature_id = "integration-test-001"
    path = write_plan_artifact(
        feature_id=feature_id,
        name="Integration test",
        description="Tests integration location",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    expected = tmp_path / "specs" / feature_id / "plan.yaml"
    assert path == expected.resolve()
    assert expected.exists()


def test_approve_plan_updates_approved_flag(tmp_path):
    """approve_plan must set approved=true in existing plan.yaml."""
    feature_id = "approve-test-001"
    write_plan_artifact(
        feature_id=feature_id,
        name="Approve test",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    assert is_approved(feature_id, workspace=tmp_path) is False
    approve_plan(feature_id=feature_id, workspace=tmp_path)
    assert is_approved(feature_id, workspace=tmp_path) is True


def test_approve_plan_returns_false_when_plan_absent(tmp_path):
    """approve_plan must return False when plan.yaml does not exist."""
    result = approve_plan(feature_id="no-plan-here", workspace=tmp_path)
    assert result is False


def test_load_plan_returns_dict_when_present(tmp_path):
    """load_plan must return a dict with feature fields when plan.yaml exists."""
    feature_id = "load-test-001"
    write_plan_artifact(
        feature_id=feature_id,
        name="Load test",
        description="Test loading",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    data = load_plan(feature_id=feature_id, workspace=tmp_path)
    assert isinstance(data, dict)
    assert data["feature_id"] == feature_id
    assert data["name"] == "Load test"
