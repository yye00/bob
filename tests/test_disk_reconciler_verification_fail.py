"""Tests for disk_reconciler promotion on the verification-fail path (F-R7-612 companion).

Verifies that BEFORE marking a feature needs_human due to verification failure,
bob3 checks disk state via disk_reconciler. If all ACs satisfy on disk with
structural or behavior ACs present and the only failing gate is tests_pass,
the feature is promoted to completed and VERIFY_FAIL_DISK_PROMOTED is emitted.

Companion to F-R7-598 (orphan path). This closes the verification-fail path.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from bob3.disk_reconciler import reconcile_from_disk
from bob3.run_loop import (
    disk_reconciler_verify_fail_check,
    disk_reconciler_verify_fail_promotion,
)


# ---------------------------------------------------------------------------
# reconcile_from_disk is importable from bob3.disk_reconciler (AC check)
# ---------------------------------------------------------------------------


def test_reconcile_from_disk_is_callable() -> None:
    """reconcile_from_disk is importable and callable from bob3.disk_reconciler."""
    assert callable(reconcile_from_disk)


# ---------------------------------------------------------------------------
# disk_reconciler_verify_fail_check guard: tests_pass gate
# ---------------------------------------------------------------------------


def test_verify_fail_check_returns_false_when_failed_gate_is_not_tests_pass() -> None:
    """Guard blocks promotion when failed_gate != 'tests_pass'."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    for gate in ("structural", "behavior", "integration", None, ""):
        result = disk_reconciler_verify_fail_check(
            project_id="proj-test",
            feature_id="feat-001",
            feature_name="Test Feature",
            acceptance_criteria_json=acs,
            failed_gate=gate,
            passed_gates=[],
        )
        assert result is False, f"Expected False for failed_gate={gate!r}, got {result}"


def test_verify_fail_check_returns_false_when_no_structural_acs() -> None:
    """Guard blocks promotion when no structural/behavior ACs are present."""
    acs = json.dumps([
        "pytest: tests/some_test.py",
        "integration: bob3.run_loop",
    ])
    result = disk_reconciler_verify_fail_check(
        project_id="proj-test",
        feature_id="feat-002",
        feature_name="No Structural ACs",
        acceptance_criteria_json=acs,
        failed_gate="tests_pass",
        passed_gates=["structural", "behavior"],
    )
    assert result is False


def test_verify_fail_check_returns_false_for_empty_ac_list() -> None:
    """Empty AC list returns False (no basis for disk promotion)."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-test",
        feature_id="feat-003",
        feature_name="Empty ACs",
        acceptance_criteria_json="[]",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_verify_fail_check_returns_false_for_malformed_json() -> None:
    """Malformed AC JSON returns False, does not raise."""
    result = disk_reconciler_verify_fail_check(
        project_id="proj-test",
        feature_id="feat-004",
        feature_name="Bad JSON",
        acceptance_criteria_json="{not valid json",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_verify_fail_check_raises_for_none_ac_json() -> None:
    """None acceptance_criteria_json raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        disk_reconciler_verify_fail_check(
            project_id="proj-test",
            feature_id="feat-005",
            feature_name="None ACs",
            acceptance_criteria_json=None,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_verify_fail_check_raises_for_non_string_ac_json() -> None:
    """Non-string acceptance_criteria_json raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        disk_reconciler_verify_fail_check(
            project_id="proj-test",
            feature_id="feat-006",
            feature_name="Int ACs",
            acceptance_criteria_json=42,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


# ---------------------------------------------------------------------------
# disk_reconciler_verify_fail_check: successful promotion path
# ---------------------------------------------------------------------------


def test_verify_fail_check_promotes_when_disk_check_succeeds() -> None:
    """Feature is promoted when structural AC present and disk check passes."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ) as mock_check:
        result = disk_reconciler_verify_fail_check(
            project_id="proj-test",
            feature_id="feat-007",
            feature_name="Promoted Feature",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=["structural", "behavior"],
        )
    assert result is True
    mock_check.assert_called_once_with(
        project_id="proj-test",
        feature_id="feat-007",
        feature_name="Promoted Feature",
        acceptance_criteria_json=acs,
    )


def test_verify_fail_check_does_not_promote_when_disk_check_fails() -> None:
    """Feature is NOT promoted when disk check fails even with structural ACs."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        result = disk_reconciler_verify_fail_check(
            project_id="proj-test",
            feature_id="feat-008",
            feature_name="Not Promoted Feature",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=["structural"],
        )
    assert result is False


def test_verify_fail_check_emits_verify_fail_disk_promoted_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VERIFY_FAIL_DISK_PROMOTED event is emitted when promotion succeeds."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        with caplog.at_level(logging.INFO, logger="bob3.run_loop"):
            disk_reconciler_verify_fail_check(
                project_id="proj-test",
                feature_id="feat-emit-001",
                feature_name="Event Emission Test",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=["structural", "behavior"],
            )
    log_text = caplog.text
    assert "VERIFY_FAIL_DISK_PROMOTED" in log_text
    assert "feat-emit-001" in log_text


def test_verify_fail_check_no_event_when_not_promoted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VERIFY_FAIL_DISK_PROMOTED event is NOT emitted when promotion is skipped."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        with caplog.at_level(logging.INFO, logger="bob3.run_loop"):
            disk_reconciler_verify_fail_check(
                project_id="proj-test",
                feature_id="feat-no-event-001",
                feature_name="No Event Test",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=[],
            )
    assert "VERIFY_FAIL_DISK_PROMOTED" not in caplog.text


# ---------------------------------------------------------------------------
# Function defined: AC variant with "Function defined:" prefix
# ---------------------------------------------------------------------------


def test_verify_fail_check_function_defined_ac_satisfies_guard() -> None:
    """'Function defined:' AC counts as structural and satisfies guard 2."""
    acs = json.dumps(["Function defined: bob3.run_loop.disk_reconciler_verify_fail_check"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        result = disk_reconciler_verify_fail_check(
            project_id="proj-test",
            feature_id="feat-009",
            feature_name="Function Defined AC Feature",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert result is True


def test_verify_fail_check_mixed_acs_with_structural() -> None:
    """Mixed ACs (structural + pytest) still satisfy guard 2 via structural."""
    acs = json.dumps([
        "File exists: src/bob3/run_loop.py",
        "Function defined: bob3.disk_reconciler.reconcile_from_disk",
        "pytest: tests/test_disk_reconciler_verification_fail.py",
        "integration: bob3.run_loop",
    ])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        result = disk_reconciler_verify_fail_check(
            project_id="proj-test",
            feature_id="feat-010",
            feature_name="Mixed ACs Feature",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=["structural", "behavior", "integration"],
        )
    assert result is True


# ---------------------------------------------------------------------------
# disk_reconciler_verify_fail_promotion delegates correctly
# ---------------------------------------------------------------------------


def test_verify_fail_promotion_delegates_to_check() -> None:
    """disk_reconciler_verify_fail_promotion delegates to disk_reconciler_verify_fail_check."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ) as mock_check:
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-delegate",
            feature_id="feat-del-001",
            feature_name="Delegate Test",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=["structural"],
        )
    assert result is True
    mock_check.assert_called_once()


def test_verify_fail_promotion_returns_false_on_wrong_gate() -> None:
    """disk_reconciler_verify_fail_promotion returns False when failed_gate is not tests_pass."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    result = disk_reconciler_verify_fail_promotion(
        project_id="proj-gate-test",
        feature_id="feat-gate-001",
        feature_name="Wrong Gate",
        acceptance_criteria_json=acs,
        failed_gate="structural",
        passed_gates=[],
    )
    assert result is False


def test_verify_fail_promotion_raises_on_none_ac_json() -> None:
    """disk_reconciler_verify_fail_promotion raises ValueError for None ACs."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        disk_reconciler_verify_fail_promotion(
            project_id="proj-err",
            feature_id="feat-err-001",
            feature_name="Error Test",
            acceptance_criteria_json=None,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


# ---------------------------------------------------------------------------
# Integration: bob3.run_loop exports are all present
# ---------------------------------------------------------------------------


def test_run_loop_exports_verify_fail_functions() -> None:
    """All required disk_reconciler verify-fail functions are accessible from bob3.run_loop."""
    import bob3.run_loop as rl
    assert hasattr(rl, "disk_reconciler_verify_fail_check")
    assert hasattr(rl, "disk_reconciler_verify_fail_promotion")
    assert callable(rl.disk_reconciler_verify_fail_check)
    assert callable(rl.disk_reconciler_verify_fail_promotion)


def test_disk_reconciler_module_exports_reconcile_from_disk() -> None:
    """bob3.disk_reconciler exports reconcile_from_disk as required by AC."""
    import bob3.disk_reconciler as dr
    assert hasattr(dr, "reconcile_from_disk")
    assert callable(dr.reconcile_from_disk)


# ---------------------------------------------------------------------------
# Guard logic: only promote when (structural_count + behavior_count) > 0
# AND failed gate is tests_pass
# ---------------------------------------------------------------------------


def test_guard_rejects_all_pytest_acs() -> None:
    """Features with only pytest: ACs (no structural) are NOT promoted."""
    acs = json.dumps([
        "pytest: tests/test_foo.py",
        "pytest: tests/test_bar.py",
    ])
    result = disk_reconciler_verify_fail_check(
        project_id="proj-guard",
        feature_id="feat-g-001",
        feature_name="Pytest Only Feature",
        acceptance_criteria_json=acs,
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False, "pytest-only features must NOT be promoted via disk reconciler"


def test_guard_rejects_integration_only_acs() -> None:
    """Features with only integration: ACs (no structural) are NOT promoted."""
    acs = json.dumps([
        "integration: bob3.run_loop",
    ])
    result = disk_reconciler_verify_fail_check(
        project_id="proj-guard",
        feature_id="feat-g-002",
        feature_name="Integration Only Feature",
        acceptance_criteria_json=acs,
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_guard_accepts_file_exists_with_tests_pass_gate() -> None:
    """'File exists:' AC with tests_pass gate passes both guards."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        result = disk_reconciler_verify_fail_check(
            project_id="proj-guard",
            feature_id="feat-g-003",
            feature_name="File Exists Feature",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
        )
    assert result is True
