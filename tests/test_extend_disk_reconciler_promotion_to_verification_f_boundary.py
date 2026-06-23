"""Boundary tests for disk_reconciler_verify_fail_promotion (F-R7-612 companion).

AC: pytest: tests/test_extend_disk_reconciler_promotion_to_verification_f_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from bob3.run_loop import disk_reconciler_verify_fail_promotion


def test_boundary_empty_ac_json_string() -> None:
    """Empty JSON array returns False, does not raise."""
    result = disk_reconciler_verify_fail_promotion(
        project_id="proj-boundary",
        feature_id="feat-boundary-1",
        feature_name="Boundary Empty ACs",
        acceptance_criteria_json="[]",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_boundary_none_failed_gate() -> None:
    """failed_gate=None returns False, does not raise."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    result = disk_reconciler_verify_fail_promotion(
        project_id="proj-boundary",
        feature_id="feat-boundary-2",
        feature_name="None failed_gate",
        acceptance_criteria_json=acs,
        failed_gate=None,
        passed_gates=None,
    )
    assert result is False


def test_boundary_empty_passed_gates() -> None:
    """passed_gates=[] (minimum input) is accepted and returns a defined result."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-boundary",
            feature_id="feat-boundary-3",
            feature_name="Empty passed_gates",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert isinstance(result, bool)


def test_boundary_none_passed_gates() -> None:
    """passed_gates=None (omitted) returns a well-defined result, does not raise."""
    acs = json.dumps(["Function defined: bob3.run_loop.disk_reconciler_verify_fail_promotion"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-boundary",
            feature_id="feat-boundary-4",
            feature_name="None passed_gates",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=None,
        )
    assert isinstance(result, bool)


def test_boundary_minimal_structural_ac() -> None:
    """Single minimal structural AC satisfies guard 2 and reaches the disk check."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ) as mock_check:
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-boundary",
            feature_id="feat-boundary-5",
            feature_name="Single structural AC",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert result is True
    mock_check.assert_called_once()


def test_boundary_whitespace_ac_json() -> None:
    """AC JSON with only whitespace returns False, does not raise."""
    result = disk_reconciler_verify_fail_promotion(
        project_id="proj-boundary",
        feature_id="feat-boundary-6",
        feature_name="Whitespace AC JSON",
        acceptance_criteria_json="   ",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_boundary_empty_feature_id() -> None:
    """Empty feature_id with valid ACs returns a well-defined bool (not raises)."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-boundary",
            feature_id="",
            feature_name="Empty feature_id",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert isinstance(result, bool)
