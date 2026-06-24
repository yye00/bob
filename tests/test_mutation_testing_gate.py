"""Tests for bob.mutation_testing_gate.

Covers:
- run_mutation_tests: skips on empty feature_id or pytest_passed=False
- run_mutation_tests: returns gate result dict on success
- run_mutation_tests: returns skipped dict when mutmut unavailable
- run_mutation_tests: rejects when mutation_score < threshold
- run_mutation_tests: persists surviving mutants on failure
- validate_mutation_score: passes at or above threshold
- validate_mutation_score: fails below threshold
- validate_mutation_score: raises on invalid inputs
- type errors on invalid argument types
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from bob.mutation_testing_gate import (
    MUTATION_SCORE_THRESHOLD,
    run_mutation_tests,
    validate_mutation_score,
)
from bob.verification.mutation_gate import MutationReport, MutmutMissingError


# ---------------------------------------------------------------------------
# validate_mutation_score
# ---------------------------------------------------------------------------


def test_validate_mutation_score_above_threshold_passes():
    assert validate_mutation_score(0.9) is True


def test_validate_mutation_score_at_threshold_passes():
    assert validate_mutation_score(MUTATION_SCORE_THRESHOLD) is True


def test_validate_mutation_score_below_threshold_fails():
    assert validate_mutation_score(0.5) is False


def test_validate_mutation_score_zero_fails_with_default_threshold():
    assert validate_mutation_score(0.0) is False


def test_validate_mutation_score_custom_threshold():
    assert validate_mutation_score(0.5, threshold=0.4) is True
    assert validate_mutation_score(0.3, threshold=0.4) is False


def test_validate_mutation_score_non_numeric_raises():
    with pytest.raises(TypeError):
        validate_mutation_score("not-a-number")  # type: ignore[arg-type]


def test_validate_mutation_score_out_of_range_raises():
    with pytest.raises(ValueError):
        validate_mutation_score(1.5)


def test_validate_mutation_score_negative_raises():
    with pytest.raises(ValueError):
        validate_mutation_score(-0.1)


def test_validate_mutation_score_threshold_out_of_range_raises():
    with pytest.raises(ValueError):
        validate_mutation_score(0.8, threshold=1.5)


# ---------------------------------------------------------------------------
# run_mutation_tests: skip conditions
# ---------------------------------------------------------------------------


def test_run_mutation_tests_skips_on_empty_feature_id(tmp_path):
    result = run_mutation_tests(
        feature_id="",
        src_files=[],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=True,
    )
    assert result is None


def test_run_mutation_tests_skips_on_pytest_failed(tmp_path):
    result = run_mutation_tests(
        feature_id="feat-abc",
        src_files=["src/bob/foo.py"],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=False,
    )
    assert result is None


# ---------------------------------------------------------------------------
# run_mutation_tests: success path
# ---------------------------------------------------------------------------


def test_run_mutation_tests_returns_dict_on_success(tmp_path):
    report = MutationReport(
        feature_id="feat-ok",
        total_mutants=10,
        killed=8,
        survived=2,
        timed_out=0,
        mutation_score=0.8,
    )
    with patch(
        "bob.mutation_testing_gate.run_mutation_test", return_value=report
    ):
        result = run_mutation_tests(
            feature_id="feat-ok",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result["passed"] is True
    assert result["mutation_score"] == 0.8
    assert result["feature_id"] == "feat-ok"
    assert result["total_mutants"] == 10
    assert result["killed"] == 8
    assert result["survived"] == 2
    assert result["threshold"] == MUTATION_SCORE_THRESHOLD


def test_run_mutation_tests_fails_when_score_below_threshold(tmp_path):
    report = MutationReport(
        feature_id="feat-low",
        total_mutants=10,
        killed=6,
        survived=4,
        timed_out=0,
        mutation_score=0.6,
    )
    with patch(
        "bob.mutation_testing_gate.run_mutation_test", return_value=report
    ), patch("bob.mutation_testing_gate.persist_surviving_mutants") as mock_persist:
        result = run_mutation_tests(
            feature_id="feat-low",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result["passed"] is False
    mock_persist.assert_called_once()


def test_run_mutation_tests_does_not_persist_on_pass(tmp_path):
    report = MutationReport(
        feature_id="feat-pass",
        total_mutants=4,
        killed=4,
        survived=0,
        timed_out=0,
        mutation_score=1.0,
    )
    with patch(
        "bob.mutation_testing_gate.run_mutation_test", return_value=report
    ), patch("bob.mutation_testing_gate.persist_surviving_mutants") as mock_persist:
        run_mutation_tests(
            feature_id="feat-pass",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    mock_persist.assert_not_called()


# ---------------------------------------------------------------------------
# run_mutation_tests: mutmut unavailable
# ---------------------------------------------------------------------------


def test_run_mutation_tests_returns_skipped_when_mutmut_missing(tmp_path):
    with patch(
        "bob.mutation_testing_gate.run_mutation_test",
        side_effect=MutmutMissingError("mutmut not installed"),
    ):
        result = run_mutation_tests(
            feature_id="feat-missing",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result.get("skipped") is True
    assert "reason" in result
    assert result["reason"]


# ---------------------------------------------------------------------------
# run_mutation_tests: custom threshold
# ---------------------------------------------------------------------------


def test_run_mutation_tests_respects_custom_threshold(tmp_path):
    report = MutationReport(
        feature_id="feat-custom",
        total_mutants=10,
        killed=6,
        survived=4,
        timed_out=0,
        mutation_score=0.6,
    )
    with patch(
        "bob.mutation_testing_gate.run_mutation_test", return_value=report
    ), patch("bob.mutation_testing_gate.persist_surviving_mutants"):
        result = run_mutation_tests(
            feature_id="feat-custom",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=0.5,
        )
    assert result is not None
    assert result["passed"] is True
    assert result["threshold"] == 0.5


# ---------------------------------------------------------------------------
# run_mutation_tests: type validation
# ---------------------------------------------------------------------------


def test_run_mutation_tests_non_string_feature_id_raises(tmp_path):
    with pytest.raises(TypeError):
        run_mutation_tests(
            feature_id=123,  # type: ignore[arg-type]
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )


def test_run_mutation_tests_non_list_src_files_raises(tmp_path):
    with pytest.raises(TypeError):
        run_mutation_tests(
            feature_id="feat",
            src_files="not-a-list",  # type: ignore[arg-type]
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )


def test_run_mutation_tests_non_bool_pytest_passed_raises(tmp_path):
    with pytest.raises(TypeError):
        run_mutation_tests(
            feature_id="feat",
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed="yes",  # type: ignore[arg-type]
        )


def test_run_mutation_tests_invalid_threshold_raises(tmp_path):
    with pytest.raises(ValueError):
        run_mutation_tests(
            feature_id="feat",
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=1.5,
        )


def test_run_mutation_tests_negative_threshold_raises(tmp_path):
    with pytest.raises(ValueError):
        run_mutation_tests(
            feature_id="feat",
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=-0.1,
        )
