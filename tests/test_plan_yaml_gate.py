"""Tests for bob3.plan_yaml_gate — the public facade for plan.yaml gate operations.

Covers load_plan_yaml and validate_plan_approved in both happy-path and error
cases.  Integration with bob3.orchestrator is verified by the fact that the
module delegates to bob3.orchestrator.plan_gate internally.
"""

from __future__ import annotations

import pytest
import yaml

from bob3.orchestrator.plan_gate import write_plan_artifact, approve_plan
from bob3.plan_yaml_gate import (
    ImplementerBlockedError,
    load_plan_yaml,
    validate_plan_approved,
)


# ---------------------------------------------------------------------------
# load_plan_yaml — happy path
# ---------------------------------------------------------------------------


def test_load_plan_yaml_returns_dict_when_file_exists(tmp_path):
    """load_plan_yaml returns a dict with the expected keys when plan.yaml exists."""
    write_plan_artifact(
        feature_id="test-feat-001",
        name="Feature One",
        description="A test feature",
        acceptance_criteria=["File exists: src/foo.py"],
        workspace=tmp_path,
    )
    plan = load_plan_yaml("test-feat-001", workspace=tmp_path)
    assert isinstance(plan, dict)
    assert plan["feature_id"] == "test-feat-001"
    assert plan["name"] == "Feature One"
    assert plan["acceptance_criteria"] == ["File exists: src/foo.py"]
    assert plan["approved"] is False


def test_load_plan_yaml_returns_none_when_file_missing(tmp_path):
    """load_plan_yaml returns None when no plan.yaml exists for the feature."""
    result = load_plan_yaml("nonexistent-feature", workspace=tmp_path)
    assert result is None


def test_load_plan_yaml_preserves_approved_true(tmp_path):
    """load_plan_yaml returns approved=True after approve_plan is called."""
    write_plan_artifact(
        feature_id="test-feat-002",
        name="Feature Two",
        description=None,
        acceptance_criteria=["AC 1", "AC 2"],
        workspace=tmp_path,
    )
    approve_plan("test-feat-002", workspace=tmp_path)
    plan = load_plan_yaml("test-feat-002", workspace=tmp_path)
    assert plan is not None
    assert plan["approved"] is True


def test_load_plan_yaml_returns_all_acceptance_criteria(tmp_path):
    """load_plan_yaml returns the full acceptance_criteria list unchanged."""
    acs = ["File exists: a", "Function defined: b.c", "pytest: tests/test_x.py"]
    write_plan_artifact(
        feature_id="test-feat-003",
        name="Feature Three",
        description="desc",
        acceptance_criteria=acs,
        workspace=tmp_path,
    )
    plan = load_plan_yaml("test-feat-003", workspace=tmp_path)
    assert plan["acceptance_criteria"] == acs


# ---------------------------------------------------------------------------
# load_plan_yaml — error path
# ---------------------------------------------------------------------------


def test_load_plan_yaml_raises_on_empty_feature_id(tmp_path):
    """load_plan_yaml raises ValueError when feature_id is empty."""
    with pytest.raises(ValueError, match="feature_id"):
        load_plan_yaml("", workspace=tmp_path)


def test_load_plan_yaml_raises_on_none_feature_id(tmp_path):
    """load_plan_yaml raises ValueError when feature_id is None."""
    with pytest.raises(ValueError, match="feature_id"):
        load_plan_yaml(None, workspace=tmp_path)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_plan_approved — happy path
# ---------------------------------------------------------------------------


def test_validate_plan_approved_does_not_raise_when_approved(tmp_path):
    """validate_plan_approved does not raise when plan.yaml has approved=true."""
    write_plan_artifact(
        feature_id="test-feat-004",
        name="Approved feature",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    # Should not raise
    validate_plan_approved("test-feat-004", workspace=tmp_path)


def test_validate_plan_approved_does_not_raise_after_approve_plan(tmp_path):
    """validate_plan_approved passes after approve_plan is called explicitly."""
    write_plan_artifact(
        feature_id="test-feat-005",
        name="Manually approved",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    approve_plan("test-feat-005", workspace=tmp_path)
    # Should not raise
    validate_plan_approved("test-feat-005", workspace=tmp_path)


# ---------------------------------------------------------------------------
# validate_plan_approved — error paths (ImplementerBlockedError)
# ---------------------------------------------------------------------------


def test_validate_plan_approved_raises_when_not_approved(tmp_path):
    """validate_plan_approved raises ImplementerBlockedError when approved=false."""
    write_plan_artifact(
        feature_id="test-feat-006",
        name="Unapproved feature",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    with pytest.raises(ImplementerBlockedError):
        validate_plan_approved("test-feat-006", workspace=tmp_path)


def test_validate_plan_approved_raises_when_plan_missing(tmp_path):
    """validate_plan_approved raises ImplementerBlockedError when plan.yaml is absent."""
    with pytest.raises(ImplementerBlockedError):
        validate_plan_approved("ghost-feature-id", workspace=tmp_path)


def test_validate_plan_approved_error_message_contains_feature_id(tmp_path):
    """ImplementerBlockedError message contains the feature_id for diagnostics."""
    fid = "test-feat-007"
    write_plan_artifact(
        feature_id=fid,
        name="Feature Seven",
        description=None,
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
    )
    with pytest.raises(ImplementerBlockedError, match=fid):
        validate_plan_approved(fid, workspace=tmp_path)


# ---------------------------------------------------------------------------
# validate_plan_approved — ValueError for invalid feature_id
# ---------------------------------------------------------------------------


def test_validate_plan_approved_raises_on_empty_feature_id(tmp_path):
    """validate_plan_approved raises ValueError when feature_id is empty."""
    with pytest.raises(ValueError, match="feature_id"):
        validate_plan_approved("", workspace=tmp_path)


def test_validate_plan_approved_raises_on_none_feature_id(tmp_path):
    """validate_plan_approved raises ValueError when feature_id is None."""
    with pytest.raises(ValueError, match="feature_id"):
        validate_plan_approved(None, workspace=tmp_path)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration: orchestrator path exercised via plan_yaml_gate
# ---------------------------------------------------------------------------


def test_load_plan_yaml_reflects_auto_approve_true(tmp_path):
    """load_plan_yaml returns approved=True when auto_approve=True was passed to write."""
    write_plan_artifact(
        feature_id="test-feat-008",
        name="Auto-approved",
        description="CI path",
        acceptance_criteria=["AC 1"],
        workspace=tmp_path,
        auto_approve=True,
    )
    plan = load_plan_yaml("test-feat-008", workspace=tmp_path)
    assert plan is not None
    assert plan["approved"] is True
    # Also verify gate passes
    validate_plan_approved("test-feat-008", workspace=tmp_path)
