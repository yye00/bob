"""Tests for promote_on_verify_fail_from_disk (F-R7-598 companion).

AC: pytest: tests/test_verify_fail_disk_promote.py

Verifies that the verification-fail disk-promotion path:
  - promotes to completed when all ACs satisfy on disk (tests_pass gate failed)
  - emits VERIFY_FAIL_DISK_PROMOTED on promotion
  - refuses to promote when the failed gate is not tests_pass
  - refuses to promote when no structural/behavior AC is present (guard 2)
  - raises ValueError on invalid (None / non-str) AC JSON
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from bob.run_loop import promote_on_verify_fail_from_disk


def test_function_defined() -> None:
    """AC: Function defined: bob.run_loop.promote_on_verify_fail_from_disk."""
    assert callable(promote_on_verify_fail_from_disk)


def test_promotes_when_acs_satisfied_on_disk() -> None:
    """tests_pass failed + structural AC present + disk check passes -> promote (True)."""
    acs = json.dumps(["File exists: src/bob/run_loop.py"])
    with patch(
        "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ) as mock_check:
        result = promote_on_verify_fail_from_disk(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Promote me",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=["structural", "behavior", "integration"],
        )
    assert result is True
    mock_check.assert_called_once()


def test_emits_verify_fail_disk_promoted_event(caplog) -> None:
    """On promotion, VERIFY_FAIL_DISK_PROMOTED is logged with the feature id."""
    acs = json.dumps(["Function defined: bob.run_loop.promote_on_verify_fail_from_disk"])
    with patch(
        "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        with caplog.at_level(logging.INFO):
            result = promote_on_verify_fail_from_disk(
                project_id="proj-2",
                feature_id="feat-2",
                feature_name="Emit event",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=["structural"],
            )
    assert result is True
    assert "VERIFY_FAIL_DISK_PROMOTED" in caplog.text
    assert "feat-2" in caplog.text


def test_no_promote_when_failed_gate_not_tests_pass() -> None:
    """Guard 1: a non-tests_pass failed gate blocks promotion."""
    acs = json.dumps(["File exists: src/bob/run_loop.py"])
    with patch(
        "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ) as mock_check:
        result = promote_on_verify_fail_from_disk(
            project_id="proj-3",
            feature_id="feat-3",
            feature_name="Wrong gate",
            acceptance_criteria_json=acs,
            failed_gate="structural",
            passed_gates=[],
        )
    assert result is False
    mock_check.assert_not_called()


def test_no_promote_when_no_structural_ac() -> None:
    """Guard 2: only pytest ACs present -> no disk evidence -> no promotion."""
    acs = json.dumps(["pytest: tests/test_foo.py"])
    with patch(
        "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ) as mock_check:
        result = promote_on_verify_fail_from_disk(
            project_id="proj-4",
            feature_id="feat-4",
            feature_name="No structural",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert result is False
    mock_check.assert_not_called()


def test_no_promote_when_disk_check_fails() -> None:
    """Disk check returns False (an AC not satisfied) -> no promotion."""
    acs = json.dumps(["File exists: src/bob/run_loop.py"])
    with patch(
        "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        result = promote_on_verify_fail_from_disk(
            project_id="proj-5",
            feature_id="feat-5",
            feature_name="Disk fails",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert result is False


def test_none_ac_json_raises_value_error() -> None:
    """Invalid input (None AC JSON) raises ValueError, does not silently succeed."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        promote_on_verify_fail_from_disk(
            project_id="proj-6",
            feature_id="feat-6",
            feature_name="None AC",
            acceptance_criteria_json=None,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_non_string_ac_json_raises_value_error() -> None:
    """Invalid input (non-str AC JSON) raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        promote_on_verify_fail_from_disk(
            project_id="proj-7",
            feature_id="feat-7",
            feature_name="Int AC",
            acceptance_criteria_json=123,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_empty_ac_json_returns_false() -> None:
    """Empty AC list returns False, does not raise."""
    result = promote_on_verify_fail_from_disk(
        project_id="proj-8",
        feature_id="feat-8",
        feature_name="Empty ACs",
        acceptance_criteria_json="[]",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False
