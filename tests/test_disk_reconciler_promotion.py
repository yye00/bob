"""Tests for bob.run_loop.disk_reconciler_promotion_check (b255ed0f).

Acceptance criteria verified:
  - Function defined: bob.run_loop.disk_reconciler_promotion_check
  - integration: bob.run_loop
  - pytest: tests/test_disk_reconciler_promotion.py
  - File exists: src/bob/run_loop.py
  - Boundary case: empty/zero input returns well-defined result (not crash)
  - Invalid input: raises ValueError or returns rejection, no silent success
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from bob.run_loop import disk_reconciler_promotion_check


# ---------------------------------------------------------------------------
# AC: Function defined and importable
# ---------------------------------------------------------------------------

def test_function_exists():
    """disk_reconciler_promotion_check must be importable from bob.run_loop."""
    assert callable(disk_reconciler_promotion_check)


# ---------------------------------------------------------------------------
# AC: Boundary case — empty or zero input returns well-defined result
# ---------------------------------------------------------------------------

def test_empty_ac_list_returns_false():
    """Empty AC list is a boundary: must return False, not crash."""
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json="[]",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_empty_string_ac_returns_false():
    """Empty JSON string '""' is unparseable as list — must return False."""
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='""',
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_no_structural_acs_returns_false():
    """ACs with only pytest: entries and no structural ACs — returns False."""
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["pytest: tests/test_foo.py"]',
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_failed_gate_none_returns_false_without_crash():
    """failed_gate=None is a boundary: must return False, not crash."""
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate=None,
        passed_gates=[],
    )
    assert result is False


def test_failed_gate_not_tests_pass_returns_false():
    """Guard: failed_gate != 'tests_pass' must short-circuit to False."""
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="structural",
        passed_gates=[],
    )
    assert result is False


def test_failed_gate_behavior_returns_false():
    """Guard: failed_gate='behavior' must return False (not tests_pass)."""
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="behavior",
        passed_gates=[],
    )
    assert result is False


# ---------------------------------------------------------------------------
# AC: Invalid input — raises ValueError or returns rejection, no silent success
# ---------------------------------------------------------------------------

def test_raises_value_error_on_none_ac_json():
    """None as acceptance_criteria_json must raise ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        disk_reconciler_promotion_check(
            project_id="proj-001",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json=None,
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_raises_value_error_on_list_ac_json():
    """A list (non-string) as acceptance_criteria_json must raise ValueError."""
    with pytest.raises(ValueError, match="str"):
        disk_reconciler_promotion_check(
            project_id="proj-001",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json=["File exists: src/bob/foo.py"],
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_raises_value_error_on_integer_ac_json():
    """An integer as acceptance_criteria_json must raise ValueError."""
    with pytest.raises(ValueError):
        disk_reconciler_promotion_check(
            project_id="proj-001",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json=42,
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_malformed_json_returns_false_not_crash():
    """Malformed JSON string must return False, not raise or crash."""
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json="not-valid-json{{{",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


# ---------------------------------------------------------------------------
# AC: Integration — delegates to disk reconciler when guards pass
# ---------------------------------------------------------------------------

@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs")
def test_delegates_to_disk_reconciler_when_guard_passes(mock_check):
    """When all guards pass, must call check_executing_feature_acs."""
    mock_check.return_value = True
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="tests_pass",
        passed_gates=["structural", "behavior"],
    )
    mock_check.assert_called_once_with(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
    )
    assert result is True


@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs")
def test_returns_false_when_disk_check_fails(mock_check):
    """When disk check returns False, must return False (no promotion)."""
    mock_check.return_value = False
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="tests_pass",
        passed_gates=["structural"],
    )
    assert result is False


@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs")
def test_no_disk_check_when_no_structural_acs(mock_check):
    """Guard must block disk check when no structural/behavior ACs exist."""
    disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["pytest: tests/test_foo.py"]',
        failed_gate="tests_pass",
        passed_gates=[],
    )
    mock_check.assert_not_called()


@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs")
def test_function_defined_ac_satisfies_structural_guard(mock_check):
    """'Function defined:' AC must pass the structural guard."""
    mock_check.return_value = False
    disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["Function defined: bob.foo.bar"]',
        failed_gate="tests_pass",
        passed_gates=[],
    )
    mock_check.assert_called_once()


@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs")
def test_mixed_acs_with_structural_passes_guard(mock_check):
    """Mixed ACs with at least one structural entry must pass the guard."""
    mock_check.return_value = True
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json=json.dumps([
            "File exists: src/bob/foo.py",
            "pytest: tests/test_foo.py",
            "Function defined: bob.foo.bar",
        ]),
        failed_gate="tests_pass",
        passed_gates=["structural", "behavior"],
    )
    mock_check.assert_called_once()
    assert result is True


# ---------------------------------------------------------------------------
# AC: Return type is bool
# ---------------------------------------------------------------------------

@patch("bob.orchestrator.disk_reconciler.check_executing_feature_acs")
def test_return_type_is_bool_on_promotion(mock_check):
    """Return type must be bool (True) when promoted."""
    mock_check.return_value = True
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert isinstance(result, bool)
    assert result is True


def test_return_type_is_bool_on_guard_bypass():
    """Return type must be bool (False) when guards block."""
    result = disk_reconciler_promotion_check(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json="[]",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert isinstance(result, bool)
    assert result is False
