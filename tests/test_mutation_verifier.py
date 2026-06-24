"""Tests for bob.mutation_verifier.run_mutation_testing.

Acceptance criteria:
- File exists: src/bob/mutation_verifier.py
- Function defined: bob.mutation_verifier.run_mutation_testing
- pytest: tests/test_mutation_verifier.py
- integration: bob.orchestrator
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import bob.mutation_verifier as mod
from bob.mutation_verifier import (
    MUTATION_SCORE_THRESHOLD,
    run_mutation_testing,
)
from bob.verification.mutation_gate import MutationReport, MutmutMissingError


# ---------------------------------------------------------------------------
# Basic importability and API surface
# ---------------------------------------------------------------------------


def test_module_importable():
    """Module bob.mutation_verifier imports without error."""
    assert mod is not None


def test_function_defined():
    """run_mutation_testing is callable and exposed in the module."""
    assert callable(run_mutation_testing)
    assert hasattr(mod, "run_mutation_testing")


def test_threshold_constant():
    """MUTATION_SCORE_THRESHOLD is 0.75."""
    assert MUTATION_SCORE_THRESHOLD == 0.75


def test_module_docstring_mentions_mutation():
    """Module docstring references mutation."""
    assert mod.__doc__ is not None
    assert "mutation" in mod.__doc__.lower()


# ---------------------------------------------------------------------------
# Skip conditions — returns None
# ---------------------------------------------------------------------------


def test_empty_feature_id_returns_none(tmp_path):
    """Empty feature_id causes gate to skip (returns None)."""
    result = run_mutation_testing(
        feature_id="",
        src_files=[],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=True,
    )
    assert result is None


def test_pytest_failed_returns_none(tmp_path):
    """pytest_passed=False causes gate to skip (returns None)."""
    result = run_mutation_testing(
        feature_id="feat-x",
        src_files=["src/bob/foo.py"],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=False,
    )
    assert result is None


# ---------------------------------------------------------------------------
# Gate pass/fail logic
# ---------------------------------------------------------------------------


def test_passes_when_score_above_threshold(tmp_path):
    """Gate passes when mutation_score >= threshold."""
    good_report = MutationReport(
        feature_id="feat-pass",
        total_mutants=10,
        killed=8,
        survived=2,
        timed_out=0,
        mutation_score=0.80,
    )
    with patch(
        "bob.mutation_verifier.run_mutation_test",
        return_value=good_report,
    ):
        result = run_mutation_testing(
            feature_id="feat-pass",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result["passed"] is True
    assert result["mutation_score"] == 0.80


def test_fails_when_score_below_threshold(tmp_path):
    """Gate fails when mutation_score < threshold."""
    bad_report = MutationReport(
        feature_id="feat-fail",
        total_mutants=10,
        killed=6,
        survived=4,
        timed_out=0,
        mutation_score=0.60,
    )
    with patch(
        "bob.mutation_verifier.run_mutation_test",
        return_value=bad_report,
    ), patch(
        "bob.mutation_verifier.persist_surviving_mutants"
    ) as mock_persist:
        result = run_mutation_testing(
            feature_id="feat-fail",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result["passed"] is False
    assert result["mutation_score"] == 0.60
    mock_persist.assert_called_once()


def test_result_contains_expected_keys(tmp_path):
    """Gate result dict contains all expected keys."""
    report = MutationReport(
        feature_id="feat-keys",
        total_mutants=8,
        killed=7,
        survived=1,
        timed_out=0,
        mutation_score=0.875,
    )
    with patch(
        "bob.mutation_verifier.run_mutation_test",
        return_value=report,
    ):
        result = run_mutation_testing(
            feature_id="feat-keys",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    expected_keys = {
        "passed", "mutation_score", "feature_id", "total_mutants",
        "killed", "survived", "timed_out", "threshold",
    }
    assert expected_keys.issubset(result.keys())


def test_result_feature_id_matches_input(tmp_path):
    """Result feature_id matches the input feature_id."""
    report = MutationReport(
        feature_id="my-feature-123",
        total_mutants=4,
        killed=4,
        survived=0,
        timed_out=0,
        mutation_score=1.0,
    )
    with patch(
        "bob.mutation_verifier.run_mutation_test",
        return_value=report,
    ):
        result = run_mutation_testing(
            feature_id="my-feature-123",
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result["feature_id"] == "my-feature-123"


# ---------------------------------------------------------------------------
# Custom threshold
# ---------------------------------------------------------------------------


def test_custom_threshold_is_respected(tmp_path):
    """A custom threshold overrides the default."""
    report = MutationReport(
        feature_id="feat-custom",
        total_mutants=10,
        killed=6,
        survived=4,
        timed_out=0,
        mutation_score=0.60,
    )
    with patch(
        "bob.mutation_verifier.run_mutation_test",
        return_value=report,
    ), patch("bob.mutation_verifier.persist_surviving_mutants"):
        result = run_mutation_testing(
            feature_id="feat-custom",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=0.50,  # lower than score 0.60 → should pass
        )
    assert result is not None
    assert result["passed"] is True
    assert result["threshold"] == 0.50


# ---------------------------------------------------------------------------
# mutmut unavailable — returns skipped dict, not None
# ---------------------------------------------------------------------------


def test_mutmut_missing_returns_skipped_dict(tmp_path):
    """When mutmut is missing, gate returns skipped dict with reason."""
    with patch(
        "bob.mutation_verifier.run_mutation_test",
        side_effect=MutmutMissingError("mutmut not installed"),
    ):
        result = run_mutation_testing(
            feature_id="feat-missing",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result.get("skipped") is True
    assert result.get("reason")


# ---------------------------------------------------------------------------
# Type validation (raises TypeError)
# ---------------------------------------------------------------------------


def test_non_string_feature_id_raises_type_error(tmp_path):
    """Non-string feature_id raises TypeError."""
    with pytest.raises(TypeError):
        run_mutation_testing(
            feature_id=123,  # type: ignore[arg-type]
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )


def test_non_list_src_files_raises_type_error(tmp_path):
    """Non-list src_files raises TypeError."""
    with pytest.raises(TypeError):
        run_mutation_testing(
            feature_id="feat-x",
            src_files="src/bob/foo.py",  # type: ignore[arg-type]
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )


def test_non_bool_pytest_passed_raises_type_error(tmp_path):
    """Non-bool pytest_passed raises TypeError."""
    with pytest.raises(TypeError):
        run_mutation_testing(
            feature_id="feat-x",
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed="yes",  # type: ignore[arg-type]
        )


def test_threshold_above_1_raises_value_error(tmp_path):
    """threshold > 1.0 raises ValueError."""
    with pytest.raises(ValueError):
        run_mutation_testing(
            feature_id="feat-x",
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=1.5,
        )


def test_negative_threshold_raises_value_error(tmp_path):
    """threshold < 0.0 raises ValueError."""
    with pytest.raises(ValueError):
        run_mutation_testing(
            feature_id="feat-x",
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=-0.1,
        )


# ---------------------------------------------------------------------------
# Integration: bob.orchestrator imports run_mutation_testing
# ---------------------------------------------------------------------------


def test_orchestrator_integration():
    """bob.orchestrator exposes run_mutation_testing (integration AC)."""
    import bob.orchestrator as orch

    assert hasattr(orch, "run_mutation_testing"), (
        "bob.orchestrator must expose run_mutation_testing "
        "(add: from bob.mutation_verifier import run_mutation_testing)"
    )
    assert callable(orch.run_mutation_testing)
