"""Boundary-case tests for the Devin-style editable plan.yaml gate (bcb6a22e).

AC: empty, zero, or minimum input returns a well-defined result rather than
raising (boundary case).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from bob3.orchestrator.plan_gate import (
    compute_plan_vs_spec_drift,
    emit_plan_ready_event,
    is_approved,
    load_plan,
    write_plan_artifact,
)


# ---------------------------------------------------------------------------
# Boundary: empty acceptance_criteria list (zero ACs)
# ---------------------------------------------------------------------------

def test_write_plan_with_empty_ac_list(tmp_path):
    """write_plan_artifact with acceptance_criteria=[] must succeed and write a valid file."""
    path = write_plan_artifact(
        feature_id="boundary-feat-001",
        name="Zero AC feature",
        description="A feature with no ACs yet",
        acceptance_criteria=[],
        workspace=tmp_path,
    )
    assert path.exists(), "plan.yaml must be created even with an empty AC list"
    data = yaml.safe_load(path.read_text())
    assert data["acceptance_criteria"] == []
    assert data["approved"] is False
    assert isinstance(data["spec_hash"], str)


# ---------------------------------------------------------------------------
# Boundary: single-character feature_id (minimum valid id)
# ---------------------------------------------------------------------------

def test_write_plan_with_minimal_feature_id(tmp_path):
    """write_plan_artifact with a single-char feature_id must succeed."""
    path = write_plan_artifact(
        feature_id="x",
        name="Minimal ID feature",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    assert path.exists()
    data = yaml.safe_load(path.read_text())
    assert data["feature_id"] == "x"


# ---------------------------------------------------------------------------
# Boundary: description=None (minimum description)
# ---------------------------------------------------------------------------

def test_write_plan_with_none_description(tmp_path):
    """write_plan_artifact with description=None must store an empty string and not raise."""
    path = write_plan_artifact(
        feature_id="boundary-feat-002",
        name="No-description feature",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    data = yaml.safe_load(path.read_text())
    assert data["description"] == ""


# ---------------------------------------------------------------------------
# Boundary: is_approved returns False (not raises) when plan.yaml is missing
# ---------------------------------------------------------------------------

def test_is_approved_missing_file_returns_false(tmp_path):
    """is_approved must return False (not raise) when plan.yaml does not exist."""
    result = is_approved("nonexistent-feature", workspace=tmp_path)
    assert result is False


# ---------------------------------------------------------------------------
# Boundary: load_plan returns None (not raises) when plan.yaml is missing
# ---------------------------------------------------------------------------

def test_load_plan_missing_returns_none(tmp_path):
    """load_plan must return None when the plan.yaml file does not exist."""
    result = load_plan("no-such-feature", workspace=tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# Boundary: compute_plan_vs_spec_drift with no prior plan.yaml
# ---------------------------------------------------------------------------

def test_compute_drift_no_prior_plan(tmp_path):
    """compute_plan_vs_spec_drift must return drift=True when there is no prior plan.yaml."""
    report = compute_plan_vs_spec_drift(
        "no-prior-plan", ["AC 1"], workspace=tmp_path
    )
    assert isinstance(report, dict)
    assert report["drift"] is True  # empty plan hash != current hash
    assert "added" in report
    assert "removed" in report


# ---------------------------------------------------------------------------
# Boundary: emit_plan_ready_event with empty plan_path string
# ---------------------------------------------------------------------------

def test_emit_plan_ready_event_empty_plan_path(tmp_path):
    """emit_plan_ready_event must succeed (not raise) even with an empty plan_path string."""
    emit_plan_ready_event(
        feature_id="boundary-feat-003",
        plan_path="",
        approved=False,
        workspace=tmp_path,
    )
    events_file = tmp_path / "runs" / "events.jsonl"
    assert events_file.exists()
    records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
    assert len(records) == 1
    assert records[0]["event"] == "PLAN_READY"
    assert records[0]["plan_path"] == ""


# ---------------------------------------------------------------------------
# Boundary: single-AC list (minimum non-empty)
# ---------------------------------------------------------------------------

def test_write_plan_with_single_ac(tmp_path):
    """write_plan_artifact with exactly one AC must write it without modification."""
    path = write_plan_artifact(
        feature_id="boundary-feat-004",
        name="Single AC feature",
        description="Has exactly one AC",
        acceptance_criteria=["File exists: src/foo.py"],
        workspace=tmp_path,
    )
    data = yaml.safe_load(path.read_text())
    assert data["acceptance_criteria"] == ["File exists: src/foo.py"]
    assert len(data["acceptance_criteria"]) == 1


# ---------------------------------------------------------------------------
# Boundary: write_plan_artifact is idempotent on second call with same args
# ---------------------------------------------------------------------------

def test_write_plan_idempotent_on_zero_ac(tmp_path):
    """write_plan_artifact called twice with empty ACs must return same hash both times."""
    fid = "boundary-feat-005"
    path1 = write_plan_artifact(
        feature_id=fid,
        name="Idempotent zero AC",
        description=None,
        acceptance_criteria=[],
        workspace=tmp_path,
    )
    path2 = write_plan_artifact(
        feature_id=fid,
        name="Idempotent zero AC",
        description=None,
        acceptance_criteria=[],
        workspace=tmp_path,
    )
    data1 = yaml.safe_load(path1.read_text())
    data2 = yaml.safe_load(path2.read_text())
    assert data1["spec_hash"] == data2["spec_hash"]
