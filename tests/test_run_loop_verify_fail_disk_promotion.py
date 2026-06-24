"""Tests for disk_reconciler_verify_fail_check (F-R7-612 companion).

AC: pytest: tests/test_run_loop_verify_fail_disk_promotion.py
    integration: bob3.run_loop
    Function defined: bob3.run_loop.disk_reconciler_verify_fail_check

Verifies that disk_reconciler_verify_fail_check:
  - is importable from bob3.run_loop
  - returns False when failed_gate != "tests_pass"
  - returns False when no structural/behavior ACs present
  - calls check_executing_feature_acs when guards pass
  - emits VERIFY_FAIL_DISK_PROMOTED event on promotion
  - promotes to True when disk check returns True
  - returns False when disk check returns False
  - raises ValueError for None or non-string acceptance_criteria_json
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from bob3.run_loop import disk_reconciler_verify_fail_check


def test_function_importable() -> None:
    """disk_reconciler_verify_fail_check is importable from bob3.run_loop."""
    assert callable(disk_reconciler_verify_fail_check)


def test_returns_false_when_failed_gate_not_tests_pass() -> None:
    """Returns False immediately when failed_gate is not 'tests_pass'."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test Feature",
        acceptance_criteria_json=acs,
        failed_gate="structural",
        passed_gates=["behavior"],
    )
    assert result is False


def test_returns_false_when_failed_gate_is_none() -> None:
    """Returns False when failed_gate is None (no gate info = don't promote)."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test Feature",
        acceptance_criteria_json=acs,
        failed_gate=None,
        passed_gates=None,
    )
    assert result is False


def test_returns_false_when_no_structural_acs() -> None:
    """Returns False when ACs contain only pytest: entries (no structural/behavior)."""
    acs = json.dumps(["pytest: tests/test_foo.py", "integration: bob3.run_loop"])
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test Feature",
        acceptance_criteria_json=acs,
        failed_gate="tests_pass",
        passed_gates=["structural", "behavior"],
    )
    assert result is False


def test_returns_false_when_ac_json_empty_array() -> None:
    """Returns False when acceptance_criteria_json is an empty array."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test Feature",
        acceptance_criteria_json="[]",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_returns_false_when_ac_json_malformed() -> None:
    """Returns False (not raises) when acceptance_criteria_json is malformed JSON."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test Feature",
        acceptance_criteria_json="{not valid json",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_raises_value_error_when_ac_json_is_none() -> None:
    """Raises ValueError when acceptance_criteria_json is None."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Test Feature",
            acceptance_criteria_json=None,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_raises_value_error_when_ac_json_is_non_string() -> None:
    """Raises ValueError when acceptance_criteria_json is not a string."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Test Feature",
            acceptance_criteria_json=["File exists: x"],  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_calls_disk_check_when_guards_pass_file_exists() -> None:
    """Calls check_executing_feature_acs when 'File exists:' AC is present and guards pass."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ) as mock_check:
        disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Test Feature",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=["structural"],
        )
    mock_check.assert_called_once()


def test_calls_disk_check_when_guards_pass_function_defined() -> None:
    """Calls check_executing_feature_acs when 'Function defined:' AC is present and guards pass."""
    acs = json.dumps(["Function defined: bob3.run_loop.disk_reconciler_verify_fail_check"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ) as mock_check:
        disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Test Feature",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    mock_check.assert_called_once()


def test_returns_true_when_disk_check_promotes() -> None:
    """Returns True when check_executing_feature_acs returns True (disk promotion)."""
    acs = json.dumps([
        "File exists: src/bob3/run_loop.py",
        "Function defined: bob3.run_loop.disk_reconciler_verify_fail_check",
    ])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        result = disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-promote",
            feature_name="Promote Feature",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=["structural", "behavior"],
        )
    assert result is True


def test_returns_false_when_disk_check_fails() -> None:
    """Returns False when check_executing_feature_acs returns False (no promotion)."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        result = disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-no-promote",
            feature_name="No Promote Feature",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert result is False


def test_emits_verify_fail_disk_promoted_event_on_promotion(caplog: pytest.LogCaptureFixture) -> None:
    """Emits VERIFY_FAIL_DISK_PROMOTED event in logs when promotion succeeds."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        with caplog.at_level(logging.INFO, logger="bob3.run_loop"):
            disk_reconciler_verify_fail_check(
                project_id="proj-1",
                feature_id="feat-event",
                feature_name="Event Feature",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=["structural"],
            )
    assert any("VERIFY_FAIL_DISK_PROMOTED" in record.message for record in caplog.records)


def test_does_not_emit_event_when_not_promoted(caplog: pytest.LogCaptureFixture) -> None:
    """Does NOT emit VERIFY_FAIL_DISK_PROMOTED when disk check returns False."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        with caplog.at_level(logging.INFO, logger="bob3.run_loop"):
            disk_reconciler_verify_fail_check(
                project_id="proj-1",
                feature_id="feat-no-event",
                feature_name="No Event Feature",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=[],
            )
    assert not any("VERIFY_FAIL_DISK_PROMOTED" in record.message for record in caplog.records)


def test_mixed_acs_structural_and_pytest() -> None:
    """With mixed ACs (structural + pytest), structural count > 0 so guard passes."""
    acs = json.dumps([
        "File exists: src/bob3/run_loop.py",
        "pytest: tests/test_foo.py",
    ])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        result = disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-mixed",
            feature_name="Mixed ACs",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=["structural"],
        )
    assert result is True


def test_behavior_ac_counts_as_structural_prefix() -> None:
    """'Function defined:' ACs count toward structural_count guard."""
    acs = json.dumps(["Function defined: bob3.run_loop.some_function"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        result = disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-func",
            feature_name="Function AC Feature",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert result is True
