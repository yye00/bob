"""Tests for the verification-fail disk promotion path (F-R7-612 companion).

Extends disk_reconciler promotion to the verification-fail path. Where
F-R7-598 closed the orphan-executing path, this closes the symmetric
verification-fail path: when a feature exhausts retries and would be marked
needs_human due to a failing tests_pass gate, but its structural ACs are
verifiably satisfied on disk, promote it to completed instead.

AC: pytest: tests/test_verify_fail_disk_promotion.py
AC: Function defined: bob.run_loop.reconcile_from_disk
AC: integration: bob.disk_reconciler
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from bob.run_loop import (
    disk_reconciler_verify_fail_promotion,
    reconcile_from_disk,
)


def test_reconcile_from_disk_is_defined() -> None:
    """AC: Function defined: bob.run_loop.reconcile_from_disk."""
    assert callable(reconcile_from_disk)


def test_reconcile_from_disk_delegates_to_orchestrator() -> None:
    """reconcile_from_disk delegates to the orchestrator bulk reconciler."""
    with patch(
        "bob.orchestrator.disk_reconciler.reconcile_from_disk",
        return_value=3,
    ) as mock_bulk:
        result = reconcile_from_disk("proj-1")
    assert result == 3
    mock_bulk.assert_called_once_with("proj-1", None)


def test_integration_bob_disk_reconciler_importable() -> None:
    """AC: integration: bob.disk_reconciler — the facade module imports cleanly."""
    import bob.disk_reconciler as dr

    assert hasattr(dr, "check_executing_feature_acs")
    assert hasattr(dr, "reconcile_from_disk")


def test_promotes_when_structural_acs_satisfied_on_disk() -> None:
    """tests_pass fail + structural AC present + disk satisfied ⇒ promote (True)."""
    acs = json.dumps(
        [
            "File exists: src/bob/run_loop.py",
            "pytest: tests/test_verify_fail_disk_promotion.py",
        ]
    )
    with patch(
        "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ) as mock_check:
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Structural satisfied",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=["structural", "behavior", "integration"],
        )
    assert result is True
    mock_check.assert_called_once()


def test_no_promote_when_disk_check_fails() -> None:
    """tests_pass fail + structural AC present but disk unsatisfied ⇒ no promote."""
    acs = json.dumps(["File exists: src/bob/run_loop.py"])
    with patch(
        "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-2",
            feature_name="Disk unsatisfied",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=["structural"],
        )
    assert result is False


def test_guard_blocks_non_tests_pass_gate() -> None:
    """Guard 1: a failing gate other than tests_pass never promotes."""
    acs = json.dumps(["File exists: src/bob/run_loop.py"])
    with patch(
        "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ) as mock_check:
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-3",
            feature_name="Structural gate failed",
            acceptance_criteria_json=acs,
            failed_gate="structural",
            passed_gates=[],
        )
    assert result is False
    mock_check.assert_not_called()


def test_guard_blocks_when_no_structural_ac() -> None:
    """Guard 2: only pytest ACs (no structural/behavior) ⇒ never promote."""
    acs = json.dumps(
        [
            "pytest: tests/test_verify_fail_disk_promotion.py",
            "pytest: tests/test_something_else.py",
        ]
    )
    with patch(
        "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ) as mock_check:
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-4",
            feature_name="Only pytest ACs",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert result is False
    mock_check.assert_not_called()


def test_function_defined_ac_marker_satisfies_guard_two() -> None:
    """A 'Function defined:' AC counts as structural evidence for guard 2."""
    acs = json.dumps(
        ["Function defined: bob.run_loop.disk_reconciler_verify_fail_promotion"]
    )
    with patch(
        "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ) as mock_check:
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-5",
            feature_name="Function defined AC",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert result is True
    mock_check.assert_called_once()


def test_promotion_emits_verify_fail_disk_promoted_event(caplog) -> None:
    """On promotion, a VERIFY_FAIL_DISK_PROMOTED event is logged."""
    import logging

    acs = json.dumps(["File exists: src/bob/run_loop.py"])
    with patch(
        "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        with caplog.at_level(logging.INFO):
            result = disk_reconciler_verify_fail_promotion(
                project_id="proj-1",
                feature_id="feat-6",
                feature_name="Emits event",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=["structural", "behavior"],
            )
    assert result is True
    assert "VERIFY_FAIL_DISK_PROMOTED" in caplog.text
    assert "feat-6" in caplog.text


def test_none_acceptance_criteria_json_raises() -> None:
    """Invalid input (None AC JSON) raises ValueError, does not silently succeed."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-7",
            feature_name="None AC JSON",
            acceptance_criteria_json=None,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )
