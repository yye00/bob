"""Error-path tests for the Devin-style editable plan.yaml gate (bcb6a22e).

AC: invalid input raises ValueError and the function does not silently succeed
(error path).
"""
from __future__ import annotations

import pytest

from bob.orchestrator.plan_gate import (
    write_plan_artifact,
)


# ---------------------------------------------------------------------------
# Error: empty feature_id raises ValueError
# ---------------------------------------------------------------------------

def test_write_plan_empty_feature_id_raises(tmp_path):
    """write_plan_artifact must raise ValueError when feature_id is an empty string."""
    with pytest.raises(ValueError, match="feature_id"):
        write_plan_artifact(
            feature_id="",
            name="Some feature",
            description="desc",
            acceptance_criteria=["AC 1"],
            workspace=tmp_path,
        )


# ---------------------------------------------------------------------------
# Error: None feature_id raises ValueError
# ---------------------------------------------------------------------------

def test_write_plan_none_feature_id_raises(tmp_path):
    """write_plan_artifact must raise ValueError when feature_id is None."""
    with pytest.raises(ValueError, match="feature_id"):
        write_plan_artifact(
            feature_id=None,  # type: ignore[arg-type]
            name="Some feature",
            description="desc",
            acceptance_criteria=["AC 1"],
            workspace=tmp_path,
        )


# ---------------------------------------------------------------------------
# Error: empty name raises ValueError
# ---------------------------------------------------------------------------

def test_write_plan_empty_name_raises(tmp_path):
    """write_plan_artifact must raise ValueError when name is an empty string."""
    with pytest.raises(ValueError, match="name"):
        write_plan_artifact(
            feature_id="valid-feature-id",
            name="",
            description="desc",
            acceptance_criteria=["AC 1"],
            workspace=tmp_path,
        )


# ---------------------------------------------------------------------------
# Error: None name raises ValueError
# ---------------------------------------------------------------------------

def test_write_plan_none_name_raises(tmp_path):
    """write_plan_artifact must raise ValueError when name is None."""
    with pytest.raises(ValueError, match="name"):
        write_plan_artifact(
            feature_id="valid-feature-id",
            name=None,  # type: ignore[arg-type]
            description="desc",
            acceptance_criteria=["AC 1"],
            workspace=tmp_path,
        )


# ---------------------------------------------------------------------------
# Error: acceptance_criteria not a list raises ValueError
# ---------------------------------------------------------------------------

def test_write_plan_ac_as_string_raises(tmp_path):
    """write_plan_artifact must raise ValueError when acceptance_criteria is a string."""
    with pytest.raises(ValueError, match="acceptance_criteria"):
        write_plan_artifact(
            feature_id="valid-feature-id",
            name="Valid name",
            description=None,
            acceptance_criteria="not a list",  # type: ignore[arg-type]
            workspace=tmp_path,
        )


def test_write_plan_ac_as_none_raises(tmp_path):
    """write_plan_artifact must raise ValueError when acceptance_criteria is None."""
    with pytest.raises(ValueError, match="acceptance_criteria"):
        write_plan_artifact(
            feature_id="valid-feature-id",
            name="Valid name",
            description=None,
            acceptance_criteria=None,  # type: ignore[arg-type]
            workspace=tmp_path,
        )


def test_write_plan_ac_as_dict_raises(tmp_path):
    """write_plan_artifact must raise ValueError when acceptance_criteria is a dict."""
    with pytest.raises(ValueError, match="acceptance_criteria"):
        write_plan_artifact(
            feature_id="valid-feature-id",
            name="Valid name",
            description=None,
            acceptance_criteria={"ac": "value"},  # type: ignore[arg-type]
            workspace=tmp_path,
        )


# ---------------------------------------------------------------------------
# Verify error cases do not silently succeed (no plan.yaml written)
# ---------------------------------------------------------------------------

def test_empty_feature_id_does_not_create_file(tmp_path):
    """When feature_id is invalid, plan.yaml must NOT be created on disk."""
    try:
        write_plan_artifact(
            feature_id="",
            name="Some feature",
            description=None,
            acceptance_criteria=["AC 1"],
            workspace=tmp_path,
        )
    except ValueError:
        pass  # expected

    # Verify no plan.yaml was written anywhere under tmp_path
    plan_files = list(tmp_path.rglob("plan.yaml"))
    assert len(plan_files) == 0, (
        f"plan.yaml must not be created when feature_id is invalid, but found: {plan_files}"
    )


def test_invalid_ac_type_does_not_create_file(tmp_path):
    """When acceptance_criteria is not a list, plan.yaml must NOT be created on disk."""
    try:
        write_plan_artifact(
            feature_id="valid-id",
            name="Valid name",
            description=None,
            acceptance_criteria="invalid",  # type: ignore[arg-type]
            workspace=tmp_path,
        )
    except ValueError:
        pass  # expected

    plan_files = list(tmp_path.rglob("plan.yaml"))
    assert len(plan_files) == 0, (
        f"plan.yaml must not be created when acceptance_criteria is invalid, but found: {plan_files}"
    )
