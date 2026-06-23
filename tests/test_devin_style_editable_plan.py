"""Tests for Devin-style editable plan.yaml gate (bcb6a22e).

Covers:
  - File exists: specs/devin_style_editable_plan/plan.yaml
  - Function defined: orchestrator.emit_plan_ready_event
  - Function defined: implementer.refuse_start_unless_approved
  - integration: bob3.orchestrator (emit_plan_ready_event importable)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import bob3.orchestrator as orchestrator
import bob3.implementers as implementer
from bob3.orchestrator.plan_gate import (
    ImplementerBlockedError,
    write_plan_artifact,
    is_approved,
    emit_plan_ready_event,
    compute_plan_vs_spec_drift,
    refuse_implementer_when_unapproved,
)


# ---------------------------------------------------------------------------
# AC 1: specs/devin_style_editable_plan/plan.yaml exists
# ---------------------------------------------------------------------------

def test_plan_yaml_file_exists():
    """The plan.yaml committed to specs/devin_style_editable_plan/ must exist."""
    plan = Path("specs/devin_style_editable_plan/plan.yaml")
    assert plan.exists(), f"Expected {plan} to exist — run the plan-gate to create it"
    data = yaml.safe_load(plan.read_text())
    assert "feature_id" in data
    assert "acceptance_criteria" in data


# ---------------------------------------------------------------------------
# AC 2: orchestrator.emit_plan_ready_event is importable + callable
# ---------------------------------------------------------------------------

def test_orchestrator_emit_plan_ready_event_importable():
    """emit_plan_ready_event must be importable from bob3.orchestrator."""
    fn = getattr(orchestrator, "emit_plan_ready_event", None)
    assert callable(fn), "bob3.orchestrator.emit_plan_ready_event must be a callable"


def test_orchestrator_emit_plan_ready_event_appends_event(tmp_path):
    """emit_plan_ready_event must append a PLAN_READY record to runs/events.jsonl."""
    events_file = tmp_path / "runs" / "events.jsonl"
    orchestrator.emit_plan_ready_event(
        feature_id="bcb6a22e-6d0e-42dc-aa69-990fc171670f",
        plan_path=str(tmp_path / "specs" / "test" / "plan.yaml"),
        approved=False,
        workspace=tmp_path,
    )
    assert events_file.exists(), "runs/events.jsonl must be created"
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    assert len(records) == 1
    assert records[0]["event"] == "PLAN_READY"
    assert records[0]["feature_id"] == "bcb6a22e-6d0e-42dc-aa69-990fc171670f"
    assert records[0]["approved"] is False


# ---------------------------------------------------------------------------
# AC 3: implementer.refuse_start_unless_approved is importable + callable
# ---------------------------------------------------------------------------

def test_implementer_refuse_start_unless_approved_importable():
    """refuse_start_unless_approved must be importable from bob3.implementers."""
    fn = getattr(implementer, "refuse_start_unless_approved", None)
    assert callable(fn), "bob3.implementers.refuse_start_unless_approved must be callable"


def test_implementer_blocks_when_unapproved(tmp_path):
    """refuse_start_unless_approved must raise ImplementerBlockedError when plan is absent."""
    with pytest.raises(ImplementerBlockedError):
        implementer.refuse_start_unless_approved(
            feature_id="no-such-feature-id",
            workspace=tmp_path,
        )


def test_implementer_unblocked_when_approved(tmp_path):
    """refuse_start_unless_approved must not raise when plan.yaml has approved=true."""
    write_plan_artifact(
        feature_id="approved-feature",
        name="Test",
        description="",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    # Should NOT raise
    implementer.refuse_start_unless_approved(
        feature_id="approved-feature",
        workspace=tmp_path,
    )


# ---------------------------------------------------------------------------
# Core plan gate behaviour
# ---------------------------------------------------------------------------

def test_write_plan_artifact_creates_file(tmp_path):
    """write_plan_artifact must create specs/<feature>/plan.yaml."""
    path = write_plan_artifact(
        feature_id="feat-001",
        name="Gate test",
        description="desc",
        acceptance_criteria=["AC 1", "AC 2"],
        workspace=tmp_path,
    )
    assert path.exists()
    data = yaml.safe_load(path.read_text())
    assert data["feature_id"] == "feat-001"
    assert data["approved"] is False
    assert data["acceptance_criteria"] == ["AC 1", "AC 2"]
    assert "spec_hash" in data
    assert "written_at" in data


def test_auto_approve_sets_approved_true(tmp_path):
    """auto_approve=True must write approved=true."""
    path = write_plan_artifact(
        feature_id="feat-002",
        name="Auto approve",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    data = yaml.safe_load(path.read_text())
    assert data["approved"] is True


def test_is_approved_false_when_missing(tmp_path):
    """is_approved must return False when plan.yaml is absent."""
    assert is_approved("no-plan-here", tmp_path) is False


def test_is_approved_true_after_auto_approve(tmp_path):
    """is_approved must return True after writing with auto_approve=True."""
    write_plan_artifact(
        feature_id="feat-003",
        name="Approved",
        description=None,
        acceptance_criteria=["AC"],
        workspace=tmp_path,
        auto_approve=True,
    )
    assert is_approved("feat-003", tmp_path) is True


def test_drift_resets_approval(tmp_path):
    """Changing ACs must reset approved to False even when prior was True."""
    fid = "feat-004"
    write_plan_artifact(
        feature_id=fid,
        name="Drift test",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    assert is_approved(fid, tmp_path) is True

    # Write again with different ACs
    path = write_plan_artifact(
        feature_id=fid,
        name="Drift test",
        description=None,
        acceptance_criteria=["AC 1", "AC 2 — new"],
        workspace=tmp_path,
    )
    data = yaml.safe_load(path.read_text())
    assert data["approved"] is False


def test_idempotent_preserves_approval(tmp_path):
    """Re-running with same ACs must preserve approved=True."""
    fid = "feat-005"
    ac = ["AC 1", "AC 2"]
    write_plan_artifact(
        feature_id=fid,
        name="Idempotent",
        description=None,
        acceptance_criteria=ac,
        workspace=tmp_path,
        auto_approve=True,
    )
    path2 = write_plan_artifact(
        feature_id=fid,
        name="Idempotent",
        description=None,
        acceptance_criteria=ac,
        workspace=tmp_path,
    )
    data = yaml.safe_load(path2.read_text())
    assert data["approved"] is True


def test_compute_drift_detects_change(tmp_path):
    """compute_plan_vs_spec_drift must report drift=True when ACs change."""
    fid = "feat-006"
    write_plan_artifact(
        feature_id=fid,
        name="Drift",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    report = compute_plan_vs_spec_drift(fid, ["AC 1", "AC 2"], tmp_path)
    assert report["drift"] is True
    assert "AC 2" in report["added"]


def test_compute_drift_stable_when_same(tmp_path):
    """compute_plan_vs_spec_drift must report drift=False when ACs unchanged."""
    fid = "feat-007"
    ac = ["AC 1", "AC 2"]
    write_plan_artifact(
        feature_id=fid,
        name="Stable",
        description=None,
        acceptance_criteria=ac,
        workspace=tmp_path,
    )
    report = compute_plan_vs_spec_drift(fid, ac, tmp_path)
    assert report["drift"] is False


# ---------------------------------------------------------------------------
# integration: bob3.orchestrator — all plan_gate symbols reachable
# ---------------------------------------------------------------------------

def test_orchestrator_integration_symbols():
    """Key plan_gate symbols must be accessible from bob3.orchestrator."""
    assert callable(orchestrator.emit_plan_ready_event)
    assert callable(orchestrator.write_plan_artifact)
    assert callable(orchestrator.is_approved)
    assert callable(orchestrator.approve_plan)
    assert callable(orchestrator.refuse_implementer_when_unapproved)
    assert callable(orchestrator.compute_plan_vs_spec_drift)
    assert callable(orchestrator.load_plan)
