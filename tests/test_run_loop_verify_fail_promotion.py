"""Tests for disk_reconciler_verify_fail_check in bob.run_loop.

Verifies the F-R7-612 companion: before marking a feature needs_human due to
a verification failure, check disk state. If all ACs satisfy on disk, promote
to completed. Only triggers when failed_gate == "tests_pass" and at least one
structural/behavior AC is present.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from bob.run_loop import disk_reconciler_verify_fail_check


# ---------------------------------------------------------------------------
# Existence and signature
# ---------------------------------------------------------------------------

def test_function_is_importable():
    """disk_reconciler_verify_fail_check must be importable from bob.run_loop."""
    assert callable(disk_reconciler_verify_fail_check)


def test_function_in_all():
    """disk_reconciler_verify_fail_check must appear in bob.run_loop.__all__."""
    import bob.run_loop as m
    assert "disk_reconciler_verify_fail_check" in m.__all__


# ---------------------------------------------------------------------------
# ValueError for invalid input (boundary / rejection ACs)
# ---------------------------------------------------------------------------

def test_raises_value_error_when_acs_json_is_none():
    """Raises ValueError when acceptance_criteria_json is None."""
    with pytest.raises(ValueError, match="must not be None"):
        disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Test",
            acceptance_criteria_json=None,
        )


def test_raises_value_error_when_acs_json_is_not_string():
    """Raises ValueError when acceptance_criteria_json is not a string."""
    with pytest.raises(ValueError, match="must be a str"):
        disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Test",
            acceptance_criteria_json=["File exists: src/foo.py"],
        )


def test_raises_value_error_when_acs_json_is_integer():
    """Raises ValueError when acceptance_criteria_json is an int."""
    with pytest.raises(ValueError, match="must be a str"):
        disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Test",
            acceptance_criteria_json=42,
        )


# ---------------------------------------------------------------------------
# Guard 1: failed_gate must be "tests_pass"
# ---------------------------------------------------------------------------

def test_returns_false_when_failed_gate_is_none():
    """Returns False without calling disk check when failed_gate is None."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate=None,
    )
    assert result is False


def test_returns_false_when_failed_gate_is_structural():
    """Returns False when failed_gate is 'structural' (not tests_pass)."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="structural",
    )
    assert result is False


def test_returns_false_when_failed_gate_is_behavior():
    """Returns False when failed_gate is 'behavior' (not tests_pass)."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="behavior",
    )
    assert result is False


def test_returns_false_when_failed_gate_is_integration():
    """Returns False when failed_gate is 'integration' (not tests_pass)."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="integration",
    )
    assert result is False


# ---------------------------------------------------------------------------
# Guard 2: AC JSON must be parseable and non-empty
# ---------------------------------------------------------------------------

def test_returns_false_when_acs_json_is_empty_list():
    """Returns False when acceptance_criteria_json is '[]'."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json="[]",
        failed_gate="tests_pass",
    )
    assert result is False


def test_returns_false_when_acs_json_is_malformed():
    """Returns False when acceptance_criteria_json is not valid JSON."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json="not-valid-json",
        failed_gate="tests_pass",
    )
    assert result is False


# ---------------------------------------------------------------------------
# Guard 3: must have at least one structural/behavior AC
# ---------------------------------------------------------------------------

def test_returns_false_when_only_pytest_acs():
    """Returns False when ACs are only pytest: entries (no structural/behavior)."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["pytest: tests/test_foo.py::test_bar"]',
        failed_gate="tests_pass",
    )
    assert result is False


def test_returns_false_when_only_integration_acs():
    """Returns False when ACs are only integration: entries."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["integration: bob.some_module"]',
        failed_gate="tests_pass",
    )
    assert result is False


# ---------------------------------------------------------------------------
# Happy path: delegates to check_executing_feature_acs when guards pass
# ---------------------------------------------------------------------------

@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs", return_value=True)
def test_returns_true_when_disk_check_succeeds(mock_check):
    """Returns True when guards pass and check_executing_feature_acs returns True."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="tests_pass",
        passed_gates=["structural", "behavior"],
    )
    assert result is True
    mock_check.assert_called_once_with(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
    )


@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs", return_value=False)
def test_returns_false_when_disk_check_returns_false(mock_check):
    """Returns False when check_executing_feature_acs returns False."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="tests_pass",
    )
    assert result is False


# ---------------------------------------------------------------------------
# Structural AC types that pass Guard 3
# ---------------------------------------------------------------------------

@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs", return_value=False)
def test_file_exists_ac_is_recognized_as_structural(mock_check):
    """'File exists:' AC passes Guard 3 and causes disk check to be called."""
    disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="tests_pass",
    )
    mock_check.assert_called_once()


@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs", return_value=False)
def test_function_defined_ac_is_recognized_as_structural(mock_check):
    """'Function defined:' AC passes Guard 3 and causes disk check to be called."""
    disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["Function defined: bob.run_loop.disk_reconciler_verify_fail_check"]',
        failed_gate="tests_pass",
    )
    mock_check.assert_called_once()


@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs", return_value=True)
def test_mixed_structural_and_pytest_acs_passes_guard(mock_check):
    """Mixed ACs with at least one 'File exists:' entry pass Guard 3."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json=json.dumps([
            "File exists: src/bob/foo.py",
            "pytest: tests/test_foo.py::test_bar",
        ]),
        failed_gate="tests_pass",
    )
    assert result is True
    mock_check.assert_called_once()


# ---------------------------------------------------------------------------
# VERIFY_FAIL_DISK_PROMOTED log event on promotion
# ---------------------------------------------------------------------------

@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs", return_value=True)
def test_emits_verify_fail_disk_promoted_log_on_promotion(mock_check, caplog):
    """On promotion, a log line containing VERIFY_FAIL_DISK_PROMOTED must appear."""
    with caplog.at_level(logging.INFO, logger="bob.run_loop"):
        disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-xyz",
            feature_name="Test Feature",
            acceptance_criteria_json='["File exists: src/bob/foo.py"]',
            failed_gate="tests_pass",
            passed_gates=["structural"],
        )
    assert any("VERIFY_FAIL_DISK_PROMOTED" in r.message for r in caplog.records)


@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs", return_value=True)
def test_promotion_log_contains_feature_id(mock_check, caplog):
    """The VERIFY_FAIL_DISK_PROMOTED log line must include the feature_id."""
    with caplog.at_level(logging.INFO, logger="bob.run_loop"):
        disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-abc-123",
            feature_name="Test Feature",
            acceptance_criteria_json='["File exists: src/bob/foo.py"]',
            failed_gate="tests_pass",
            passed_gates=[],
        )
    promo_lines = [r.message for r in caplog.records if "VERIFY_FAIL_DISK_PROMOTED" in r.message]
    assert len(promo_lines) >= 1
    assert "feat-abc-123" in promo_lines[0]


@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs", return_value=True)
def test_promotion_log_contains_failed_gate(mock_check, caplog):
    """The VERIFY_FAIL_DISK_PROMOTED log line must include 'tests_pass'."""
    with caplog.at_level(logging.INFO, logger="bob.run_loop"):
        disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json='["File exists: src/bob/foo.py"]',
            failed_gate="tests_pass",
            passed_gates=["structural", "behavior"],
        )
    promo_lines = [r.message for r in caplog.records if "VERIFY_FAIL_DISK_PROMOTED" in r.message]
    assert len(promo_lines) >= 1
    assert "tests_pass" in promo_lines[0]


@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs", return_value=False)
def test_no_promotion_log_when_disk_check_fails(mock_check, caplog):
    """No VERIFY_FAIL_DISK_PROMOTED log when disk check returns False."""
    with caplog.at_level(logging.INFO, logger="bob.run_loop"):
        disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json='["File exists: src/bob/foo.py"]',
            failed_gate="tests_pass",
        )
    assert not any("VERIFY_FAIL_DISK_PROMOTED" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# No disk check call when guards are bypassed (efficiency)
# ---------------------------------------------------------------------------

@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs")
def test_no_disk_check_when_failed_gate_not_tests_pass(mock_check):
    """Disk check must NOT be called when failed_gate != 'tests_pass'."""
    disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="integration",
    )
    mock_check.assert_not_called()


@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs")
def test_no_disk_check_when_only_pytest_acs_present(mock_check):
    """Disk check must NOT be called when only pytest: ACs are present."""
    disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["pytest: tests/test_foo.py::test_bar"]',
        failed_gate="tests_pass",
    )
    mock_check.assert_not_called()


# ---------------------------------------------------------------------------
# Boundary: empty or zero-input cases
# ---------------------------------------------------------------------------

def test_empty_acs_json_returns_false_not_crash():
    """Empty AC list returns False without raising."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json="[]",
        failed_gate="tests_pass",
    )
    assert result is False


def test_none_failed_gate_returns_false_not_crash():
    """None failed_gate returns False without raising."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-1",
        feature_id="feat-1",
        feature_name="Test",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate=None,
        passed_gates=[],
    )
    assert result is False


def test_empty_passed_gates_list_is_valid():
    """empty passed_gates list is valid and returns False (no real disk)."""
    with patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs", return_value=False):
        result = disk_reconciler_verify_fail_check(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Test",
            acceptance_criteria_json='["File exists: src/bob/foo.py"]',
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert result is False
