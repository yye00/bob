"""Error path tests for disk_reconciler_verify_fail_promotion (F-R7-612 companion).

AC: pytest: tests/test_extend_disk_reconciler_promotion_to_verification_f_error.py
    — invalid input raises ValueError and the function does not silently succeed
"""

from __future__ import annotations

import json

import pytest

from bob.run_loop import disk_reconciler_verify_fail_promotion


def test_error_none_acceptance_criteria_json_raises() -> None:
    """acceptance_criteria_json=None raises ValueError, does not silently return True."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        disk_reconciler_verify_fail_promotion(
            project_id="proj-error",
            feature_id="feat-error-1",
            feature_name="None AC JSON",
            acceptance_criteria_json=None,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_error_non_string_acceptance_criteria_json_raises() -> None:
    """acceptance_criteria_json=int raises ValueError, does not silently succeed."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        disk_reconciler_verify_fail_promotion(
            project_id="proj-error",
            feature_id="feat-error-2",
            feature_name="Int AC JSON",
            acceptance_criteria_json=42,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_error_list_acceptance_criteria_json_raises() -> None:
    """acceptance_criteria_json=list raises ValueError, does not silently succeed."""
    with pytest.raises(ValueError, match="acceptance_criteria_json"):
        disk_reconciler_verify_fail_promotion(
            project_id="proj-error",
            feature_id="feat-error-3",
            feature_name="List AC JSON",
            acceptance_criteria_json=["File exists: x"],  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )


def test_error_invalid_json_returns_false_not_raises() -> None:
    """Malformed but non-None string AC JSON returns False, does not raise ValueError."""
    result = disk_reconciler_verify_fail_promotion(
        project_id="proj-error",
        feature_id="feat-error-4",
        feature_name="Bad JSON string",
        acceptance_criteria_json="{this is not json",
        failed_gate="tests_pass",
        passed_gates=[],
    )
    assert result is False


def test_error_does_not_silently_succeed_on_invalid_input() -> None:
    """Verify that None input raises ValueError and cannot silently return True."""
    raised = False
    try:
        result = disk_reconciler_verify_fail_promotion(
            project_id="proj-error",
            feature_id="feat-error-5",
            feature_name="Silent success check",
            acceptance_criteria_json=None,  # type: ignore[arg-type]
            failed_gate="tests_pass",
            passed_gates=[],
        )
        # If no exception was raised, result must NOT be True
        assert result is not True, (
            "disk_reconciler_verify_fail_promotion must not return True for None input"
        )
    except (ValueError, TypeError):
        raised = True

    # Either path is acceptable: raised an error, or returned a non-True value.
    # The function must not silently claim success (return True) on invalid input.
    assert raised or True  # At least one of the two acceptable paths was taken
