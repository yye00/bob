"""Tests for disk_reconciler_verify_fail_promotion (F-R7-612 companion to F-R7-598).

Verifies that disk_reconciler_promotion_check / disk_reconciler_verify_fail_promotion
intercept the verification-fail→needs_human path and promote to completed when all
ACs satisfy on disk and the failed gate is 'tests_pass'.

AC: pytest: tests/test_disk_reconciler_verify_fail_promotion.py
AC: integration: bob3.run_loop
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from bob3.run_loop import (
    disk_reconciler_promotion_check,
    disk_reconciler_verify_fail_check,
    disk_reconciler_verify_fail_promotion,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _acs(*criteria: str) -> str:
    return json.dumps(list(criteria))


STRUCTURAL_AC = "File exists: src/bob3/run_loop.py"
FUNC_AC = "Function defined: bob3.run_loop.disk_reconciler_verify_fail_promotion"
TESTS_AC = "pytest: tests/test_disk_reconciler_verify_fail_promotion.py"


# ---------------------------------------------------------------------------
# disk_reconciler_verify_fail_promotion — core promotion path
# ---------------------------------------------------------------------------


class TestVerifyFailPromotionGuard:
    """Tests for the guard logic (failed_gate != tests_pass → always False)."""

    def test_wrong_failed_gate_returns_false(self) -> None:
        """Non-tests_pass failed gate should never promote."""
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Guard Test",
            acceptance_criteria_json=_acs(STRUCTURAL_AC),
            failed_gate="structural",
            passed_gates=[],
        )
        assert result is False

    def test_failed_gate_none_returns_false(self) -> None:
        """None failed_gate is not 'tests_pass' so guard fires."""
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Guard None",
            acceptance_criteria_json=_acs(STRUCTURAL_AC),
            failed_gate=None,
            passed_gates=None,
        )
        assert result is False

    def test_empty_failed_gate_returns_false(self) -> None:
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-1",
            feature_name="Guard Empty",
            acceptance_criteria_json=_acs(STRUCTURAL_AC),
            failed_gate="",
            passed_gates=[],
        )
        assert result is False

    def test_no_structural_ac_returns_false(self) -> None:
        """Only pytest ACs → no structural/behavior AC → guard 2 fires."""
        acs = _acs("pytest: tests/test_something.py")
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-2",
            feature_name="No structural ACs",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
        assert result is False

    def test_empty_criteria_list_returns_false(self) -> None:
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-3",
            feature_name="Empty criteria",
            acceptance_criteria_json="[]",
            failed_gate="tests_pass",
            passed_gates=[],
        )
        assert result is False

    def test_malformed_json_returns_false(self) -> None:
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-1",
            feature_id="feat-4",
            feature_name="Malformed JSON",
            acceptance_criteria_json="{not valid json",
            failed_gate="tests_pass",
            passed_gates=[],
        )
        assert result is False


class TestVerifyFailPromotionSuccess:
    """Tests for the happy path: guards pass, disk check succeeds."""

    def test_promotes_when_all_acs_pass_on_disk(self) -> None:
        acs = _acs(STRUCTURAL_AC, TESTS_AC)
        with patch(
            "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=True,
        ) as mock_check:
            result = disk_reconciler_verify_fail_promotion(
                project_id="proj-2",
                feature_id="feat-10",
                feature_name="Promote test",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=["structural", "behavior"],
            )
        assert result is True
        mock_check.assert_called_once()

    def test_does_not_promote_when_disk_check_fails(self) -> None:
        acs = _acs(STRUCTURAL_AC)
        with patch(
            "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=False,
        ):
            result = disk_reconciler_verify_fail_promotion(
                project_id="proj-2",
                feature_id="feat-11",
                feature_name="Disk fail test",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=[],
            )
        assert result is False

    def test_function_ac_counts_as_structural(self) -> None:
        """'Function defined:' AC satisfies guard 2 (structural_count > 0)."""
        acs = _acs(FUNC_AC)
        with patch(
            "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=True,
        ):
            result = disk_reconciler_verify_fail_promotion(
                project_id="proj-2",
                feature_id="feat-12",
                feature_name="Function AC test",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=["structural"],
            )
        assert result is True

    def test_emits_verify_fail_disk_promoted_log(self, caplog) -> None:
        """Successful promotion emits VERIFY_FAIL_DISK_PROMOTED log line."""
        acs = _acs(STRUCTURAL_AC)
        with patch(
            "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=True,
        ):
            with caplog.at_level(logging.INFO, logger="bob3.run_loop"):
                result = disk_reconciler_verify_fail_promotion(
                    project_id="proj-2",
                    feature_id="feat-99",
                    feature_name="Log emit test",
                    acceptance_criteria_json=acs,
                    failed_gate="tests_pass",
                    passed_gates=["structural"],
                )
        assert result is True
        assert "VERIFY_FAIL_DISK_PROMOTED" in caplog.text


class TestVerifyFailPromotionInvalidInput:
    """Invalid input tests — must raise ValueError."""

    def test_none_ac_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="acceptance_criteria_json"):
            disk_reconciler_verify_fail_promotion(
                project_id="proj-3",
                feature_id="feat-20",
                feature_name="None input",
                acceptance_criteria_json=None,  # type: ignore[arg-type]
                failed_gate="tests_pass",
                passed_gates=[],
            )

    def test_non_string_ac_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="acceptance_criteria_json"):
            disk_reconciler_verify_fail_promotion(
                project_id="proj-3",
                feature_id="feat-21",
                feature_name="Int input",
                acceptance_criteria_json=123,  # type: ignore[arg-type]
                failed_gate="tests_pass",
                passed_gates=[],
            )


# ---------------------------------------------------------------------------
# disk_reconciler_promotion_check — companion function (same logic)
# ---------------------------------------------------------------------------


class TestPromotionCheck:
    """Verifies disk_reconciler_promotion_check has the same guard and promotion logic."""

    def test_wrong_gate_returns_false(self) -> None:
        result = disk_reconciler_promotion_check(
            project_id="proj-5",
            feature_id="feat-30",
            feature_name="Wrong gate",
            acceptance_criteria_json=_acs(STRUCTURAL_AC),
            failed_gate="integration",
            passed_gates=[],
        )
        assert result is False

    def test_no_structural_ac_returns_false(self) -> None:
        acs = _acs("integration: bob3.run_loop")
        result = disk_reconciler_promotion_check(
            project_id="proj-5",
            feature_id="feat-31",
            feature_name="No structural",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
        assert result is False

    def test_promotes_when_acs_pass(self) -> None:
        acs = _acs(STRUCTURAL_AC)
        with patch(
            "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
            return_value=True,
        ):
            result = disk_reconciler_promotion_check(
                project_id="proj-5",
                feature_id="feat-32",
                feature_name="Promotes OK",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=["structural"],
            )
        assert result is True

    def test_none_raises(self) -> None:
        with pytest.raises(ValueError):
            disk_reconciler_promotion_check(
                project_id="proj-5",
                feature_id="feat-33",
                feature_name="None raises",
                acceptance_criteria_json=None,  # type: ignore[arg-type]
                failed_gate="tests_pass",
                passed_gates=[],
            )


# ---------------------------------------------------------------------------
# Integration: bob3.run_loop imports are accessible
# ---------------------------------------------------------------------------


def test_integration_bob3_run_loop_importable() -> None:
    """Verify the functions are importable from bob3.run_loop (integration AC)."""
    from bob3 import run_loop as rl

    assert callable(getattr(rl, "disk_reconciler_verify_fail_promotion", None))
    assert callable(getattr(rl, "disk_reconciler_promotion_check", None))
    assert callable(getattr(rl, "disk_reconciler_verify_fail_check", None))


def test_integration_disk_reconciler_reconcile_from_disk_importable() -> None:
    """AC: Function defined: bob3.disk_reconciler.reconcile_from_disk."""
    from bob3.disk_reconciler import reconcile_from_disk

    assert callable(reconcile_from_disk)
