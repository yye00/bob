"""Tests for disk_reconciler promotion on the verification-fail path (F-R7-612 companion to F-R7-598).

Verifies that when a feature's verification fails with failed_gate='tests_pass'
but structural/behavior ACs are satisfied on disk, the feature is promoted to
completed and emits VERIFY_FAIL_DISK_PROMOTED instead of escalating to needs_human.

AC: pytest: tests/test_verify_fail_disk_promoted.py
AC: integration: bob.run_loop
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from bob.run_loop import (
    disk_reconciler_verify_fail_check,
    disk_reconciler_verify_fail_gate,
    disk_reconciler_verify_fail_promotion,
)


def _acs(*criteria: str) -> str:
    return json.dumps(list(criteria))


STRUCTURAL_AC = "File exists: src/bob/run_loop.py"
FUNC_AC = "Function defined: bob.run_loop.disk_reconciler_verify_fail_gate"
TESTS_AC = "pytest: tests/test_verify_fail_disk_promoted.py"


class TestVerifyFailDiskPromoted:
    """Core tests for VERIFY_FAIL_DISK_PROMOTED promotion path."""

    def test_promotes_to_completed_when_all_acs_pass_on_disk(self) -> None:
        """When disk check passes all ACs and failed_gate=tests_pass, returns True."""
        acs = _acs(STRUCTURAL_AC, FUNC_AC)
        with patch(
            "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=True,
        ):
            result = disk_reconciler_verify_fail_promotion(
                project_id="proj-promoted",
                feature_id="feat-promoted-1",
                feature_name="Promoted Feature",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=["structural", "behavior"],
            )
        assert result is True

    def test_does_not_promote_when_disk_check_fails(self) -> None:
        """When disk check fails at least one AC, returns False (no promotion)."""
        acs = _acs(STRUCTURAL_AC)
        with patch(
            "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=False,
        ):
            result = disk_reconciler_verify_fail_promotion(
                project_id="proj-promoted",
                feature_id="feat-promoted-2",
                feature_name="Disk Fail Feature",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=["structural"],
            )
        assert result is False

    def test_guard_wrong_failed_gate_blocks_promotion(self) -> None:
        """failed_gate != 'tests_pass' prevents promotion even if disk check would pass."""
        acs = _acs(STRUCTURAL_AC)
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-promoted",
            feature_id="feat-promoted-3",
            feature_name="Wrong Gate",
            acceptance_criteria_json=acs,
            failed_gate="structural",
            passed_gates=[],
        )
        assert result is False

    def test_guard_no_structural_ac_blocks_promotion(self) -> None:
        """No structural/behavior ACs (only pytest:) means guard 2 blocks promotion."""
        acs = _acs("pytest: tests/some_test.py")
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-promoted",
            feature_id="feat-promoted-4",
            feature_name="No Structural",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
        assert result is False

    def test_emits_verify_fail_disk_promoted_event_on_success(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Successful promotion emits a VERIFY_FAIL_DISK_PROMOTED log event."""
        acs = _acs(STRUCTURAL_AC)
        with patch(
            "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=True,
        ):
            with caplog.at_level(logging.INFO, logger="bob.run_loop"):
                disk_reconciler_verify_fail_check(
                    project_id="proj-log",
                    feature_id="feat-log-1",
                    feature_name="Log Event Feature",
                    acceptance_criteria_json=acs,
                    failed_gate="tests_pass",
                    passed_gates=["structural"],
                )
        assert "VERIFY_FAIL_DISK_PROMOTED" in caplog.text

    def test_function_defined_ac_satisfies_guard_2(self) -> None:
        """'Function defined:' AC counts as structural for guard 2."""
        acs = _acs("Function defined: bob.run_loop.disk_reconciler_verify_fail_gate")
        with patch(
            "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=True,
        ):
            result = disk_reconciler_verify_fail_promotion(
                project_id="proj-promoted",
                feature_id="feat-promoted-5",
                feature_name="Function AC",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=[],
            )
        assert result is True

    def test_disk_reconciler_verify_fail_gate_delegates_correctly(self) -> None:
        """disk_reconciler_verify_fail_gate returns True when disk check passes."""
        acs = _acs(STRUCTURAL_AC)
        with patch(
            "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=True,
        ):
            result = disk_reconciler_verify_fail_gate(
                project_id="proj-gate",
                feature_id="feat-gate-1",
                feature_name="Gate Function",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=["structural", "behavior"],
            )
        assert result is True

    def test_mixed_acs_with_structural_and_pytest(self) -> None:
        """Mixed AC list (structural + pytest) passes guard 2 and reaches disk check."""
        acs = _acs(STRUCTURAL_AC, TESTS_AC)
        with patch(
            "bob.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=True,
        ):
            result = disk_reconciler_verify_fail_promotion(
                project_id="proj-promoted",
                feature_id="feat-promoted-6",
                feature_name="Mixed ACs",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=[],
            )
        assert result is True

    def test_invalid_json_returns_false(self) -> None:
        """Malformed AC JSON returns False, does not raise."""
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-promoted",
            feature_id="feat-promoted-7",
            feature_name="Bad JSON",
            acceptance_criteria_json="{bad json",
            failed_gate="tests_pass",
            passed_gates=[],
        )
        assert result is False
