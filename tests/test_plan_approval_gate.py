"""Tests for the Devin-style plan.yaml approval gate (026abd96).

Covers: write_plan_artifact, is_approved, emit_plan_ready_event,
check_plan_approved, validate_plan_approved, and orchestrator integration.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from bob.orchestrator.plan_gate import (
    ImplementerBlockedError,
    approve_plan,
    compute_plan_vs_spec_drift,
    diff_plan_vs_spec,
    emit_plan_ready_event,
    is_approved,
    load_plan,
    refuse_implementer_when_unapproved,
    write_plan_artifact,
)
from bob.implementer import check_plan_approved, validate_plan_approved
from bob.planner import emit_plan_ready_event as planner_emit_plan_ready_event


# ---------------------------------------------------------------------------
# write_plan_artifact — basic behaviour
# ---------------------------------------------------------------------------

def test_write_plan_artifact_creates_file(tmp_path):
    """write_plan_artifact must create specs/<feature>/plan.yaml."""
    path = write_plan_artifact(
        feature_id="feat-001",
        name="My Feature",
        description="A test feature",
        acceptance_criteria=["File exists: src/foo.py"],
        workspace=tmp_path,
    )
    assert path.exists()
    assert path.name == "plan.yaml"
    assert path.parent.name == "feat-001"


def test_write_plan_artifact_default_unapproved(tmp_path):
    """By default, plan.yaml must be written with approved: false."""
    path = write_plan_artifact(
        feature_id="feat-002",
        name="My Feature",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    data = yaml.safe_load(path.read_text())
    assert data["approved"] is False


def test_write_plan_artifact_auto_approve(tmp_path):
    """auto_approve=True must write approved: true."""
    path = write_plan_artifact(
        feature_id="feat-003",
        name="Auto-approved feature",
        description="CI path",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    data = yaml.safe_load(path.read_text())
    assert data["approved"] is True


def test_write_plan_artifact_contains_expected_fields(tmp_path):
    """plan.yaml must contain all required fields."""
    acs = ["File exists: src/foo.py", "Function defined: foo.bar"]
    path = write_plan_artifact(
        feature_id="feat-004",
        name="Full-field feature",
        description="Full description",
        acceptance_criteria=acs,
        workspace=tmp_path,
    )
    data = yaml.safe_load(path.read_text())
    assert data["feature_id"] == "feat-004"
    assert data["name"] == "Full-field feature"
    assert data["description"] == "Full description"
    assert data["acceptance_criteria"] == acs
    assert "spec_hash" in data
    assert "written_at" in data


def test_write_plan_artifact_emits_plan_ready_event(tmp_path):
    """write_plan_artifact must append a PLAN_READY event to runs/events.jsonl."""
    write_plan_artifact(
        feature_id="feat-005",
        name="Event feature",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    events_file = tmp_path / "runs" / "events.jsonl"
    assert events_file.exists()
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    assert any(r["event"] == "PLAN_READY" and r["feature_id"] == "feat-005" for r in records)


# ---------------------------------------------------------------------------
# is_approved
# ---------------------------------------------------------------------------

def test_is_approved_false_when_file_missing(tmp_path):
    assert is_approved("no-such-feature", workspace=tmp_path) is False


def test_is_approved_false_when_approved_is_false(tmp_path):
    write_plan_artifact(
        feature_id="feat-006",
        name="Unapproved",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    assert is_approved("feat-006", workspace=tmp_path) is False


def test_is_approved_true_after_auto_approve(tmp_path):
    write_plan_artifact(
        feature_id="feat-007",
        name="Approved",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    assert is_approved("feat-007", workspace=tmp_path) is True


def test_is_approved_true_after_approve_plan(tmp_path):
    write_plan_artifact(
        feature_id="feat-008",
        name="To Approve",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    approve_plan("feat-008", workspace=tmp_path)
    assert is_approved("feat-008", workspace=tmp_path) is True


# ---------------------------------------------------------------------------
# emit_plan_ready_event — direct
# ---------------------------------------------------------------------------

def test_emit_plan_ready_event_writes_jsonl(tmp_path):
    emit_plan_ready_event("feat-009", "/tmp/plan.yaml", approved=False, workspace=tmp_path)
    events_file = tmp_path / "runs" / "events.jsonl"
    assert events_file.exists()
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    assert records[0]["event"] == "PLAN_READY"
    assert records[0]["feature_id"] == "feat-009"
    assert records[0]["approved"] is False


def test_planner_emit_plan_ready_event_is_same_function(tmp_path):
    """bob.planner.emit_plan_ready_event must delegate correctly."""
    planner_emit_plan_ready_event("feat-010", "", approved=True, workspace=tmp_path)
    events_file = tmp_path / "runs" / "events.jsonl"
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    assert records[0]["event"] == "PLAN_READY"
    assert records[0]["feature_id"] == "feat-010"
    assert records[0]["approved"] is True


# ---------------------------------------------------------------------------
# check_plan_approved / validate_plan_approved
# ---------------------------------------------------------------------------

def test_check_plan_approved_false_when_unapproved(tmp_path):
    write_plan_artifact(
        feature_id="feat-011",
        name="Unapproved",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    assert check_plan_approved("feat-011", workspace=tmp_path) is False


def test_check_plan_approved_true_when_approved(tmp_path):
    write_plan_artifact(
        feature_id="feat-012",
        name="Approved",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    assert check_plan_approved("feat-012", workspace=tmp_path) is True


def test_validate_plan_approved_raises_when_unapproved(tmp_path):
    write_plan_artifact(
        feature_id="feat-013",
        name="Blocked feature",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    with pytest.raises(ImplementerBlockedError):
        validate_plan_approved("feat-013", workspace=tmp_path)


def test_validate_plan_approved_returns_true_when_approved(tmp_path):
    write_plan_artifact(
        feature_id="feat-014",
        name="Approved",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    result = validate_plan_approved("feat-014", workspace=tmp_path)
    assert result is True


def test_validate_plan_approved_raises_on_empty_feature_id(tmp_path):
    with pytest.raises(ValueError, match="feature_id"):
        validate_plan_approved("", workspace=tmp_path)


# ---------------------------------------------------------------------------
# refuse_implementer_when_unapproved
# ---------------------------------------------------------------------------

def test_refuse_implementer_raises_when_unapproved(tmp_path):
    with pytest.raises(ImplementerBlockedError):
        refuse_implementer_when_unapproved("no-plan-feature", workspace=tmp_path)


def test_refuse_implementer_passes_when_approved(tmp_path):
    write_plan_artifact(
        feature_id="feat-015",
        name="Approved",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    # Must not raise
    refuse_implementer_when_unapproved("feat-015", workspace=tmp_path)


# ---------------------------------------------------------------------------
# compute_plan_vs_spec_drift
# ---------------------------------------------------------------------------

def test_drift_detected_on_ac_change(tmp_path):
    write_plan_artifact(
        feature_id="feat-016",
        name="Drift test",
        description=None,
        acceptance_criteria=["Old AC"],
        workspace=tmp_path,
    )
    report = compute_plan_vs_spec_drift("feat-016", ["New AC"], workspace=tmp_path)
    assert report["drift"] is True
    assert "New AC" in report["added"]
    assert "Old AC" in report["removed"]


def test_no_drift_when_ac_unchanged(tmp_path):
    acs = ["AC 1", "AC 2"]
    write_plan_artifact(
        feature_id="feat-017",
        name="No drift",
        description=None,
        acceptance_criteria=acs,
        workspace=tmp_path,
    )
    report = compute_plan_vs_spec_drift("feat-017", acs, workspace=tmp_path)
    assert report["drift"] is False


# ---------------------------------------------------------------------------
# diff_plan_vs_spec
# ---------------------------------------------------------------------------

def test_diff_plan_vs_spec_returns_empty_when_no_drift(tmp_path):
    acs = ["AC 1"]
    write_plan_artifact(
        feature_id="feat-018",
        name="Diff test",
        description=None,
        acceptance_criteria=acs,
        workspace=tmp_path,
    )
    diff = diff_plan_vs_spec("feat-018", acs, workspace=tmp_path)
    assert diff == ""


def test_diff_plan_vs_spec_returns_diff_when_drifted(tmp_path):
    write_plan_artifact(
        feature_id="feat-019",
        name="Diff test",
        description=None,
        acceptance_criteria=["Old AC"],
        workspace=tmp_path,
    )
    diff = diff_plan_vs_spec("feat-019", ["New AC"], workspace=tmp_path)
    assert "Old AC" in diff
    assert "New AC" in diff


# ---------------------------------------------------------------------------
# orchestrator integration — plan_gate is importable from bob.orchestrator
# ---------------------------------------------------------------------------

def test_plan_gate_importable_from_orchestrator():
    """Verify bob.orchestrator.plan_gate is importable (integration AC)."""
    from bob.orchestrator import plan_gate  # noqa: F401
    assert hasattr(plan_gate, "write_plan_artifact")
    assert hasattr(plan_gate, "is_approved")
    assert hasattr(plan_gate, "emit_plan_ready_event")


def test_orchestrator_init_exports_plan_gate():
    """bob.orchestrator package must not hide plan_gate."""
    import bob.orchestrator.plan_gate as pg
    assert callable(pg.write_plan_artifact)
    assert callable(pg.is_approved)
