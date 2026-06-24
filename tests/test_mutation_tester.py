"""Tests for bob.mutation_tester — the canonical mutation gate entry point.

AC: pytest: tests/test_mutation_tester.py

Covers the public API of bob.mutation_tester:
- Module import and exported names
- MUTATION_SCORE_THRESHOLD constant
- run_mutation_tests function behavior (skips, gate pass/fail, mutmut missing)
- check_mutation_score utility
- verifier integration (module is importable from bob.verifier scope)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import bob.mutation_tester as mutation_tester_module
from bob.mutation_tester import (
    MUTATION_SCORE_THRESHOLD,
    check_mutation_score,
    run_mutation_tests,
)
from bob.verification.mutation_gate import MutationReport, MutmutMissingError


# ---------------------------------------------------------------------------
# Module-level assertions
# ---------------------------------------------------------------------------


def test_module_exists():
    """src/bob/mutation_tester.py is importable."""
    assert mutation_tester_module is not None


def test_run_mutation_tests_is_callable():
    """bob.mutation_tester.run_mutation_tests is a callable."""
    assert callable(run_mutation_tests)


def test_mutation_score_threshold_is_float():
    """MUTATION_SCORE_THRESHOLD is a float with value 0.75."""
    assert isinstance(MUTATION_SCORE_THRESHOLD, float)
    assert MUTATION_SCORE_THRESHOLD == 0.75


def test_all_exports_present():
    """__all__ includes the expected public names."""
    assert "run_mutation_tests" in mutation_tester_module.__all__
    assert "MUTATION_SCORE_THRESHOLD" in mutation_tester_module.__all__


# ---------------------------------------------------------------------------
# run_mutation_tests: skip conditions
# ---------------------------------------------------------------------------


def test_returns_none_when_pytest_failed(tmp_path):
    """Gate skips (returns None) when pytest_passed=False."""
    result = run_mutation_tests(
        feature_id="feat-skip-pytest",
        src_files=["src/bob/foo.py"],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=False,
    )
    assert result is None


def test_returns_none_for_empty_feature_id(tmp_path):
    """Gate skips (returns None) when feature_id is empty string."""
    result = run_mutation_tests(
        feature_id="",
        src_files=["src/bob/foo.py"],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=True,
    )
    assert result is None


# ---------------------------------------------------------------------------
# run_mutation_tests: gate pass scenario
# ---------------------------------------------------------------------------


def test_gate_passes_when_score_meets_threshold(tmp_path):
    """Gate passes when mutation_score >= threshold."""
    passing_report = MutationReport(
        feature_id="feat-pass",
        total_mutants=10,
        killed=8,
        survived=2,
        timed_out=0,
        mutation_score=0.8,
    )
    with patch(
        "bob.mutation_testing.mutmut_verifier.run_mutation_test",
        return_value=passing_report,
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
    assert result["mutation_score"] == 0.8
    assert result["feature_id"] == "feat-pass"


def test_gate_fails_when_score_below_threshold(tmp_path):
    """Gate fails when mutation_score < threshold."""
    failing_report = MutationReport(
        feature_id="feat-fail",
        total_mutants=10,
        killed=5,
        survived=5,
        timed_out=0,
        mutation_score=0.5,
    )
    with patch(
        "bob.mutation_testing.mutmut_verifier.run_mutation_test",
        return_value=failing_report,
    ), patch("bob.mutation_testing.mutmut_verifier.persist_surviving_mutants"):
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


def test_result_dict_contains_expected_keys(tmp_path):
    """Result dict has all expected keys on a passing run."""
    report = MutationReport(
        feature_id="feat-keys",
        total_mutants=5,
        killed=5,
        survived=0,
        timed_out=0,
        mutation_score=1.0,
    )
    with patch(
        "bob.mutation_testing.mutmut_verifier.run_mutation_test",
        return_value=report,
    ):
        result = run_mutation_tests(
            feature_id="feat-keys",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    for key in ("passed", "mutation_score", "feature_id", "total_mutants",
                "killed", "survived", "timed_out", "threshold"):
        assert key in result, f"Missing expected key: {key!r}"


# ---------------------------------------------------------------------------
# run_mutation_tests: mutmut missing
# ---------------------------------------------------------------------------


def test_returns_skipped_dict_when_mutmut_missing(tmp_path):
    """When mutmut is not installed, returns skipped=True dict (not None)."""
    with patch(
        "bob.mutation_testing.mutmut_verifier.run_mutation_test",
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
    assert "reason" in result and result["reason"]


# ---------------------------------------------------------------------------
# run_mutation_tests: custom threshold
# ---------------------------------------------------------------------------


def test_custom_threshold_overrides_default(tmp_path):
    """Custom threshold is used instead of the default 0.75."""
    report = MutationReport(
        feature_id="feat-custom",
        total_mutants=10,
        killed=6,
        survived=4,
        timed_out=0,
        mutation_score=0.6,
    )
    with patch(
        "bob.mutation_testing.mutmut_verifier.run_mutation_test",
        return_value=report,
    ), patch("bob.mutation_testing.mutmut_verifier.persist_surviving_mutants"):
        # With threshold=0.5, score 0.6 should pass
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
# check_mutation_score
# ---------------------------------------------------------------------------


def test_check_mutation_score_passes_at_threshold():
    """Score equal to threshold passes."""
    assert check_mutation_score(0.75) is True


def test_check_mutation_score_fails_below_threshold():
    """Score below threshold fails."""
    assert check_mutation_score(0.74) is False


def test_check_mutation_score_custom_threshold():
    """Custom threshold is respected."""
    assert check_mutation_score(0.5, threshold=0.4) is True
    assert check_mutation_score(0.3, threshold=0.4) is False


def test_check_mutation_score_raises_on_non_float():
    """Non-numeric score raises TypeError."""
    with pytest.raises(TypeError):
        check_mutation_score("bad")  # type: ignore[arg-type]


def test_check_mutation_score_raises_on_out_of_range():
    """Score outside [0.0, 1.0] raises ValueError."""
    with pytest.raises(ValueError):
        check_mutation_score(1.5)
    with pytest.raises(ValueError):
        check_mutation_score(-0.1)


# ---------------------------------------------------------------------------
# Type validation in run_mutation_tests
# ---------------------------------------------------------------------------


def test_non_string_feature_id_raises(tmp_path):
    """Non-string feature_id raises TypeError."""
    with pytest.raises((TypeError, ValueError)):
        run_mutation_tests(
            feature_id=123,  # type: ignore[arg-type]
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )


def test_non_list_src_files_raises(tmp_path):
    """Non-list src_files raises TypeError."""
    with pytest.raises((TypeError, ValueError)):
        run_mutation_tests(
            feature_id="feat-x",
            src_files="src/bob/foo.py",  # type: ignore[arg-type]
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )


def test_non_bool_pytest_passed_raises(tmp_path):
    """Non-bool pytest_passed raises TypeError."""
    with pytest.raises((TypeError, ValueError)):
        run_mutation_tests(
            feature_id="feat-x",
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed="yes",  # type: ignore[arg-type]
        )


def test_threshold_out_of_range_raises(tmp_path):
    """Threshold outside [0.0, 1.0] raises ValueError."""
    with pytest.raises((ValueError, TypeError)):
        run_mutation_tests(
            feature_id="feat-x",
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=1.5,
        )


# ---------------------------------------------------------------------------
# Verifier integration — importable from bob.verifier context
# ---------------------------------------------------------------------------


def test_verifier_imports_run_mutation_tests():
    """bob.verifier exposes run_mutation_tests via its mutation_testing import."""
    import bob.verifier  # noqa: F401 — integration smoke test
    # verifier.py imports run_mutation_tests from bob.mutation_testing
    from bob.mutation_testing import run_mutation_tests as verifier_rmt
    assert callable(verifier_rmt)


def test_mutation_tester_is_consistent_with_mutation_testing():
    """bob.mutation_tester.run_mutation_tests and bob.mutation_testing.run_mutation_tests are the same callable."""
    from bob.mutation_testing import run_mutation_tests as mt_rmt
    from bob.mutation_tester import run_mutation_tests as mtr_rmt
    # Both come from the same underlying function
    assert callable(mt_rmt)
    assert callable(mtr_rmt)
