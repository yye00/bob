"""Tests for disk_reconciler_verify_fail_promotion in bob3.run_loop.

AC: pytest: tests/test_run_loop_disk_reconciler.py
AC: integration: bob3.run_loop

Verifies that disk_reconciler_verify_fail_promotion is importable from
bob3.run_loop and behaves correctly as the primary entry point for the
verification-fail disk promotion path (companion to F-R7-598).
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from bob3.run_loop import disk_reconciler_verify_fail_promotion


# ---------------------------------------------------------------------------
# Import / integration smoke test
# ---------------------------------------------------------------------------

def test_importable_from_run_loop() -> None:
    """disk_reconciler_verify_fail_promotion must be importable from bob3.run_loop."""
    assert callable(disk_reconciler_verify_fail_promotion)


def test_integration_bob3_run_loop() -> None:
    """Integration: bob3.run_loop exports disk_reconciler_verify_fail_promotion."""
    import bob3.run_loop as rl
    assert hasattr(rl, "disk_reconciler_verify_fail_promotion")
    assert callable(rl.disk_reconciler_verify_fail_promotion)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

def test_returns_bool_on_guard_bypass() -> None:
    """When guard blocks (failed_gate != tests_pass), returns False (bool)."""
    result = disk_reconciler_verify_fail_promotion(
        project_id="proj-rl-001",
        feature_id="feat-rl-001",
        feature_name="Guard bypass test",
        acceptance_criteria_json=json.dumps(["File exists: src/bob3/run_loop.py"]),
        failed_gate="structural",
        passed_gates=[],
    )
    assert isinstance(result, bool)
    assert result is False


# ---------------------------------------------------------------------------
# Guard 1: failed_gate must be "tests_pass"
# ---------------------------------------------------------------------------

def test_returns_false_when_failed_gate_not_tests_pass() -> None:
    """When failed_gate is 'integration', guard blocks and returns False."""
    result = disk_reconciler_verify_fail_promotion(
        project_id="proj-rl-001",
        feature_id="feat-rl-002",
        feature_name="Integration gate test",
        acceptance_criteria_json=json.dumps(["File exists: src/bob3/run_loop.py"]),
        failed_gate="integration",
        passed_gates=[],
    )
    assert result is False


def test_returns_false_when_failed_gate_is_none() -> None:
    """When failed_gate is None, guard blocks and returns False."""
    result = disk_reconciler_verify_fail_promotion(
        project_id="proj-rl-001",
        feature_id="feat-rl-003",
        feature_name="None gate test",
        acceptance_criteria_json=json.dumps(["File exists: src/bob3/run_loop.py"]),
        failed_gate=None,
        passed_gates=[],
    )
    assert result is False


# ---------------------------------------------------------------------------
# Guard 2: structural/behavior AC must be present
# ---------------------------------------------------------------------------

def test_returns_false_when_only_pytest_acs() -> None:
    """When ACs are only pytest: entries, guard blocks and returns False."""
    result = disk_reconciler_verify_fail_promotion(
        project_id="proj-rl-001",
        feature_id="feat-rl-004",
        feature_name="Only pytest ACs",
        acceptance_criteria_json=json.dumps(["pytest: tests/test_foo.py"]),
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_returns_false_for_empty_ac_list() -> None:
    """Empty AC list returns False without raising."""
    result = disk_reconciler_verify_fail_promotion(
        project_id="proj-rl-001",
        feature_id="feat-rl-005",
        feature_name="Empty ACs",
        acceptance_criteria_json="[]",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


# ---------------------------------------------------------------------------
# Guard 3: invalid input raises ValueError
# ---------------------------------------------------------------------------

def test_raises_value_error_for_none_ac_json() -> None:
    """acceptance_criteria_json=None raises ValueError."""
    with pytest.raises(ValueError):
        disk_reconciler_verify_fail_promotion(
            project_id="proj-rl-001",
            feature_id="feat-rl-006",
            feature_name="None AC JSON",
            acceptance_criteria_json=None,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_raises_value_error_for_non_string_ac_json() -> None:
    """acceptance_criteria_json that is not a str raises ValueError."""
    with pytest.raises(ValueError):
        disk_reconciler_verify_fail_promotion(
            project_id="proj-rl-001",
            feature_id="feat-rl-007",
            feature_name="Non-string AC JSON",
            acceptance_criteria_json=123,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


# ---------------------------------------------------------------------------
# Delegation to disk reconciler
# ---------------------------------------------------------------------------

def test_returns_true_when_disk_reconciler_promotes() -> None:
    """When disk_reconciler promotes the feature, returns True."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-rl-001",
            feature_id="feat-rl-008",
            feature_name="Disk promoted",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=["structural", "behavior"],
        )
    assert result is True


def test_returns_false_when_disk_reconciler_does_not_promote() -> None:
    """When disk_reconciler does not promote, returns False."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-rl-001",
            feature_id="feat-rl-009",
            feature_name="Not promoted",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=[],
        )
    assert result is False


# ---------------------------------------------------------------------------
# Log event on promotion
# ---------------------------------------------------------------------------

def test_emits_verify_fail_disk_promoted_log_on_promotion(caplog: pytest.LogCaptureFixture) -> None:
    """On promotion, VERIFY_FAIL_DISK_PROMOTED must appear in log output."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=True,
    ):
        with caplog.at_level(logging.INFO):
            disk_reconciler_verify_fail_promotion(
                project_id="proj-rl-001",
                feature_id="feat-rl-010",
                feature_name="Log test",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=["structural"],
            )
    assert any("VERIFY_FAIL_DISK_PROMOTED" in r.message for r in caplog.records)


def test_no_promo_log_when_not_promoted(caplog: pytest.LogCaptureFixture) -> None:
    """When not promoted, VERIFY_FAIL_DISK_PROMOTED must NOT appear in logs."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        with caplog.at_level(logging.INFO):
            disk_reconciler_verify_fail_promotion(
                project_id="proj-rl-001",
                feature_id="feat-rl-011",
                feature_name="No log test",
                acceptance_criteria_json=acs,
                failed_gate="tests_pass",
                passed_gates=[],
            )
    assert not any("VERIFY_FAIL_DISK_PROMOTED" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Malformed JSON returns False (not raises) for string inputs
# ---------------------------------------------------------------------------

def test_malformed_json_string_returns_false() -> None:
    """Malformed but non-None string AC JSON returns False, does not raise."""
    result = disk_reconciler_verify_fail_promotion(
        project_id="proj-rl-001",
        feature_id="feat-rl-012",
        feature_name="Bad JSON",
        acceptance_criteria_json="{not valid json",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


# ---------------------------------------------------------------------------
# Accepts passed_gates=None (optional argument)
# ---------------------------------------------------------------------------

def test_accepts_none_passed_gates() -> None:
    """passed_gates=None is accepted and returns a well-defined bool."""
    acs = json.dumps(["File exists: src/bob3/run_loop.py"])
    with patch(
        "bob3.orchestrator.disk_reconciler.check_executing_feature_acs",
        return_value=False,
    ):
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-rl-001",
            feature_id="feat-rl-013",
            feature_name="None passed_gates",
            acceptance_criteria_json=acs,
            failed_gate="tests_pass",
            passed_gates=None,
        )
    assert isinstance(result, bool)
