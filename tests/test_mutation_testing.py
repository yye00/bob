"""Tests for bob.mutation_testing public API.

Acceptance criterion: pytest: tests/test_mutation_testing.py

Covers:
- MUTATION_SCORE_THRESHOLD constant is exported and equals 0.75.
- run_mutation_tests is callable and importable.
- run_mutation_tests returns None when pytest_passed=False.
- run_mutation_tests returns None when feature_id is empty.
- run_mutation_tests returns skipped dict when mutmut is unavailable.
- run_mutation_tests returns a pass/fail dict on success.
- Integration: bob.verifier exports run_mutation_tests and MUTATION_SCORE_THRESHOLD.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import bob.mutation_testing as mod
from bob.mutation_testing import MUTATION_SCORE_THRESHOLD, run_mutation_tests
from bob.verification.mutation_gate import MutationReport, MutmutMissingError


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------


def test_module_exports_threshold():
    assert hasattr(mod, "MUTATION_SCORE_THRESHOLD")
    assert MUTATION_SCORE_THRESHOLD == 0.75


def test_run_mutation_tests_is_callable():
    assert callable(run_mutation_tests)


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------


def test_returns_none_when_pytest_failed(tmp_path):
    result = run_mutation_tests(
        feature_id="feat-x",
        src_files=["src/bob/foo.py"],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=False,
    )
    assert result is None


def test_returns_none_when_feature_id_empty(tmp_path):
    result = run_mutation_tests(
        feature_id="",
        src_files=["src/bob/foo.py"],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=True,
    )
    assert result is None


# ---------------------------------------------------------------------------
# Mutmut unavailable
# ---------------------------------------------------------------------------


def test_returns_skipped_when_mutmut_missing(tmp_path):
    with patch(
        "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        side_effect=MutmutMissingError("mutmut not installed"),
    ):
        result = run_mutation_tests(
            feature_id="feat-no-mutmut",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result.get("skipped") is True
    assert result.get("reason")


# ---------------------------------------------------------------------------
# Gate pass / fail
# ---------------------------------------------------------------------------


def test_returns_passed_true_on_high_score(tmp_path):
    high_score_report = MutationReport(
        feature_id="feat-pass",
        total_mutants=10,
        killed=9,
        survived=1,
        timed_out=0,
        mutation_score=0.9,
    )
    with patch(
        "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=high_score_report,
    ):
        result = run_mutation_tests(
            feature_id="feat-pass",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result["passed"] is True
    assert result["mutation_score"] == 0.9
    assert result["feature_id"] == "feat-pass"


def test_returns_passed_false_on_low_score(tmp_path):
    low_score_report = MutationReport(
        feature_id="feat-fail",
        total_mutants=10,
        killed=5,
        survived=5,
        timed_out=0,
        mutation_score=0.5,
    )
    with patch(
        "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=low_score_report,
    ):
        result = run_mutation_tests(
            feature_id="feat-fail",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result["passed"] is False
    assert result["mutation_score"] == 0.5


# ---------------------------------------------------------------------------
# Integration: bob.verifier re-exports
# ---------------------------------------------------------------------------


def test_verifier_exports_run_mutation_tests():
    import bob.verifier as verifier

    assert hasattr(verifier, "run_mutation_tests")
    assert callable(verifier.run_mutation_tests)


def test_verifier_exports_mutation_score_threshold():
    import bob.verifier as verifier

    assert hasattr(verifier, "MUTATION_SCORE_THRESHOLD")
    assert verifier.MUTATION_SCORE_THRESHOLD == 0.75
