"""Tests for extend_disk_reconciler_promotion_verification_fail_path (b161fced).

Verifies the companion to F-R7-598: before marking a feature needs_human due
to a verification failure, check disk state. If all ACs satisfy on disk,
promote to completed instead of needs_human.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch, call

import pytest

from bob.extend_disk_reconciler_promotion_verification_fail_path import (
    extend_disk_reconciler_promotion_verification_fail_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_feature(
    feature_id: str = "feat-001",
    name: str = "Test Feature",
    acceptance_criteria: str = '["File exists: src/bob/foo.py"]',
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.acceptance_criteria = acceptance_criteria
    return f


# ---------------------------------------------------------------------------
# AC: Function signature and return type
# ---------------------------------------------------------------------------

def test_extend_disk_reconciler_promotion_verification_fail_path():
    """Module-level smoke test — function exists and returns a dict."""
    result = extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="tests_pass",
        passed_gates=["structural", "behavior"],
    )
    # Always returns a dict (promoted or not)
    assert isinstance(result, dict)
    assert "promoted" in result
    assert isinstance(result["promoted"], bool)


# ---------------------------------------------------------------------------
# AC: Guard — only promote when failed_gate is tests_pass
# ---------------------------------------------------------------------------

def test_returns_not_promoted_when_no_failed_gate():
    """When failed_gate is None, skip promotion and return promoted=False."""
    result = extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate=None,
        passed_gates=[],
    )
    assert result["promoted"] is False


def test_returns_not_promoted_when_failed_gate_is_structural():
    """When failed_gate is 'structural' (not tests_pass), do not promote."""
    result = extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="structural",
        passed_gates=[],
    )
    assert result["promoted"] is False


def test_returns_not_promoted_when_failed_gate_is_behavior():
    """When failed_gate is 'behavior' (not tests_pass), do not promote."""
    result = extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="behavior",
        passed_gates=[],
    )
    assert result["promoted"] is False


# ---------------------------------------------------------------------------
# AC: Guard — only promote when structural_count + behavior_count > 0
# ---------------------------------------------------------------------------

def test_returns_not_promoted_when_no_structural_or_behavior_acs():
    """When ACs have no structural/behavior entries, do not promote."""
    result = extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["pytest: tests/test_foo.py::test_bar"]',
        failed_gate="tests_pass",
        passed_gates=["structural", "behavior"],
    )
    assert result["promoted"] is False


def test_returns_not_promoted_when_empty_acs():
    """Empty AC list should not trigger promotion."""
    result = extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json="[]",
        failed_gate="tests_pass",
        passed_gates=["structural"],
    )
    assert result["promoted"] is False


def test_returns_not_promoted_when_acs_unparseable():
    """Malformed AC JSON should not trigger promotion."""
    result = extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json="not-valid-json",
        failed_gate="tests_pass",
        passed_gates=["structural"],
    )
    assert result["promoted"] is False


# ---------------------------------------------------------------------------
# AC: Delegates to disk_reconciler check_executing_feature_acs when guard passes
# ---------------------------------------------------------------------------

@patch("bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs")
def test_delegates_to_check_executing_feature_acs_when_guard_passes(mock_check):
    """When guards pass, calls check_executing_feature_acs and promotes if True."""
    mock_check.return_value = True
    result = extend_disk_reconciler_promotion_verification_fail_path(
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
    assert result["promoted"] is True


@patch("bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs")
def test_returns_not_promoted_when_disk_check_fails(mock_check):
    """When check_executing_feature_acs returns False, promoted=False."""
    mock_check.return_value = False
    result = extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="tests_pass",
        passed_gates=["structural"],
    )
    assert result["promoted"] is False


@patch("bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs")
def test_returns_not_promoted_when_disk_check_raises(mock_check):
    """When check_executing_feature_acs raises, promoted=False (no crash)."""
    mock_check.side_effect = RuntimeError("unexpected error")
    result = extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="tests_pass",
        passed_gates=["structural"],
    )
    assert result["promoted"] is False


# ---------------------------------------------------------------------------
# AC: Emits VERIFY_FAIL_DISK_PROMOTED log event on promotion
# ---------------------------------------------------------------------------

@patch("bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs")
def test_emits_verify_fail_disk_promoted_log_on_promotion(mock_check, caplog):
    """On promotion, log line must contain VERIFY_FAIL_DISK_PROMOTED."""
    mock_check.return_value = True
    with caplog.at_level(logging.INFO):
        extend_disk_reconciler_promotion_verification_fail_path(
            project_id="proj-001",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json='["File exists: src/bob/foo.py"]',
            failed_gate="tests_pass",
            passed_gates=["structural", "behavior"],
        )
    assert any("VERIFY_FAIL_DISK_PROMOTED" in r.message for r in caplog.records)


@patch("bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs")
def test_log_contains_feature_id_on_promotion(mock_check, caplog):
    """The VERIFY_FAIL_DISK_PROMOTED log line must include the feature_id."""
    mock_check.return_value = True
    with caplog.at_level(logging.INFO):
        extend_disk_reconciler_promotion_verification_fail_path(
            project_id="proj-001",
            feature_id="feat-abc-123",
            feature_name="Test Feature",
            acceptance_criteria_json='["File exists: src/bob/foo.py"]',
            failed_gate="tests_pass",
            passed_gates=["structural"],
        )
    promo_lines = [r.message for r in caplog.records if "VERIFY_FAIL_DISK_PROMOTED" in r.message]
    assert len(promo_lines) >= 1
    assert "feat-abc-123" in promo_lines[0]


@patch("bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs")
def test_log_contains_failed_gate_on_promotion(mock_check, caplog):
    """The VERIFY_FAIL_DISK_PROMOTED log line must include the failed_gate."""
    mock_check.return_value = True
    with caplog.at_level(logging.INFO):
        extend_disk_reconciler_promotion_verification_fail_path(
            project_id="proj-001",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json='["File exists: src/bob/foo.py"]',
            failed_gate="tests_pass",
            passed_gates=["structural", "behavior"],
        )
    promo_lines = [r.message for r in caplog.records if "VERIFY_FAIL_DISK_PROMOTED" in r.message]
    assert len(promo_lines) >= 1
    assert "tests_pass" in promo_lines[0]


@patch("bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs")
def test_no_promotion_log_when_not_promoted(mock_check, caplog):
    """When not promoted, VERIFY_FAIL_DISK_PROMOTED must NOT appear in logs."""
    mock_check.return_value = False
    with caplog.at_level(logging.INFO):
        extend_disk_reconciler_promotion_verification_fail_path(
            project_id="proj-001",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json='["File exists: src/bob/foo.py"]',
            failed_gate="tests_pass",
            passed_gates=["structural"],
        )
    assert not any("VERIFY_FAIL_DISK_PROMOTED" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# AC: Result dict includes failed_gate and passed_gates
# ---------------------------------------------------------------------------

@patch("bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs")
def test_result_includes_failed_gate(mock_check):
    """Result dict must include the failed_gate that was provided."""
    mock_check.return_value = True
    result = extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="tests_pass",
        passed_gates=["structural"],
    )
    assert result["failed_gate"] == "tests_pass"


@patch("bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs")
def test_result_includes_passed_gates(mock_check):
    """Result dict must include the passed_gates list."""
    mock_check.return_value = True
    result = extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="tests_pass",
        passed_gates=["structural", "behavior"],
    )
    assert result["passed_gates"] == ["structural", "behavior"]


# ---------------------------------------------------------------------------
# AC: Guard check — structural/behavior AC counting
# ---------------------------------------------------------------------------

def test_structural_ac_file_exists_counts_as_structural():
    """A 'File exists:' AC is structural and satisfies the guard condition."""
    # When check_executing_feature_acs would be called (no mock), we only test
    # that it doesn't short-circuit due to the guard. We verify by patching.
    with patch(
        "bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs",
        return_value=False,
    ) as mock_check:
        extend_disk_reconciler_promotion_verification_fail_path(
            project_id="proj-001",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json='["File exists: src/bob/foo.py"]',
            failed_gate="tests_pass",
            passed_gates=[],
        )
        # Guard should NOT block — check_executing_feature_acs must be called
        mock_check.assert_called_once()


def test_function_defined_ac_counts_as_structural():
    """A 'Function defined:' AC is structural and satisfies the guard condition."""
    with patch(
        "bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs",
        return_value=False,
    ) as mock_check:
        extend_disk_reconciler_promotion_verification_fail_path(
            project_id="proj-001",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json='["Function defined: bob.foo.bar"]',
            failed_gate="tests_pass",
            passed_gates=[],
        )
        mock_check.assert_called_once()


def test_mixed_acs_structural_and_pytest_passes_guard():
    """Mixed ACs with at least one structural entry should pass the guard."""
    with patch(
        "bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs",
        return_value=True,
    ) as mock_check:
        result = extend_disk_reconciler_promotion_verification_fail_path(
            project_id="proj-001",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json=json.dumps([
                "File exists: src/bob/foo.py",
                "pytest: tests/test_foo.py::test_bar",
            ]),
            failed_gate="tests_pass",
            passed_gates=["structural"],
        )
        mock_check.assert_called_once()
        assert result["promoted"] is True


# ---------------------------------------------------------------------------
# AC: Does not call disk check when guard is bypassed (efficiency)
# ---------------------------------------------------------------------------

@patch("bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs")
def test_no_disk_check_when_failed_gate_is_not_tests_pass(mock_check):
    """When failed_gate != 'tests_pass', disk check must NOT be called."""
    extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["File exists: src/bob/foo.py"]',
        failed_gate="integration",
        passed_gates=["structural"],
    )
    mock_check.assert_not_called()


@patch("bob.extend_disk_reconciler_promotion_verification_fail_path.check_executing_feature_acs")
def test_no_disk_check_when_only_pytest_acs(mock_check):
    """When ACs are only pytest: entries, disk check must NOT be called."""
    extend_disk_reconciler_promotion_verification_fail_path(
        project_id="proj-001",
        feature_id="feat-001",
        feature_name="Test Feature",
        acceptance_criteria_json='["pytest: tests/test_foo.py::test_bar"]',
        failed_gate="tests_pass",
        passed_gates=[],
    )
    mock_check.assert_not_called()
