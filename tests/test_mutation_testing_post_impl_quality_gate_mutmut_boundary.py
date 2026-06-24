"""Boundary-case tests for mutation_testing_post_impl_quality_gate_mutmut.

AC: pytest: tests/test_mutation_testing_post_impl_quality_gate_mutmut_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than
    raising (boundary case)

Covers:
- Empty feature_id (boundary: returns None, not an error).
- Empty src_files list with valid inputs.
- pytest_passed=False (boundary: gate skips gracefully).
- Zero total_mutants (score defaults to 1.0, gate passes).
- Threshold at exact minimum boundary (0.0).
- Threshold at exact maximum boundary (1.0).
- Minimum viable feature_id (single character).
- Score exactly at gate threshold (0.75).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.mutation_testing_post_impl_quality_gate_mutmut import (
    MUTATION_SCORE_THRESHOLD,
    mutation_testing_post_impl_quality_gate_mutmut,
)
from bob3.verification.mutation_gate import MutationReport


# ---------------------------------------------------------------------------
# Boundary: empty / zero inputs return well-defined results, not exceptions
# ---------------------------------------------------------------------------


def test_empty_feature_id_returns_none(tmp_path):
    """Empty string feature_id is a documented skip — returns None, not an error."""
    result = mutation_testing_post_impl_quality_gate_mutmut(
        feature_id="",
        src_files=[],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=True,
    )
    assert result is None


def test_pytest_failed_returns_none(tmp_path):
    """pytest_passed=False is a boundary skip — returns None, not an error."""
    result = mutation_testing_post_impl_quality_gate_mutmut(
        feature_id="feat-boundary",
        src_files=["src/bob3/foo.py"],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=False,
    )
    assert result is None


def test_empty_src_files_list_does_not_raise(tmp_path):
    """Empty src_files list is valid — gate runs (or skips) without raising."""
    ok_report = MutationReport(
        feature_id="feat-empty-src",
        total_mutants=0,
        killed=0,
        survived=0,
        timed_out=0,
        mutation_score=1.0,
    )
    with patch(
        "bob3.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=ok_report,
    ):
        result = mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="feat-empty-src",
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert isinstance(result, dict)


def test_zero_total_mutants_score_defaults_to_1_0(tmp_path):
    """When zero mutants are generated, score defaults to 1.0 (gate passes)."""
    zero_report = MutationReport(
        feature_id="feat-zero",
        total_mutants=0,
        killed=0,
        survived=0,
        timed_out=0,
        mutation_score=1.0,
    )
    with patch(
        "bob3.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=zero_report,
    ):
        result = mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="feat-zero",
            src_files=[],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result["mutation_score"] == 1.0
    assert result["passed"] is True


# ---------------------------------------------------------------------------
# Boundary: threshold at minimum (0.0) and maximum (1.0)
# ---------------------------------------------------------------------------


def test_threshold_zero_always_passes(tmp_path):
    """Any non-negative score passes when threshold is 0.0."""
    low_report = MutationReport(
        feature_id="feat-thresh-0",
        total_mutants=10,
        killed=0,
        survived=10,
        timed_out=0,
        mutation_score=0.0,
    )
    with patch(
        "bob3.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=low_report,
    ):
        result = mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="feat-thresh-0",
            src_files=["src/bob3/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=0.0,
        )
    assert result is not None
    assert result["passed"] is True


def test_threshold_one_requires_perfect_score(tmp_path):
    """Only a perfect score (1.0) passes when threshold is 1.0."""
    perfect_report = MutationReport(
        feature_id="feat-thresh-1",
        total_mutants=4,
        killed=4,
        survived=0,
        timed_out=0,
        mutation_score=1.0,
    )
    with patch(
        "bob3.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=perfect_report,
    ):
        result = mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="feat-thresh-1",
            src_files=["src/bob3/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=1.0,
        )
    assert result is not None
    assert result["passed"] is True


def test_threshold_one_rejects_below_perfect(tmp_path):
    """A score below 1.0 is rejected when threshold is 1.0."""
    imperfect_report = MutationReport(
        feature_id="feat-thresh-1-fail",
        total_mutants=10,
        killed=9,
        survived=1,
        timed_out=0,
        mutation_score=0.9,
    )
    with patch(
        "bob3.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=imperfect_report,
    ):
        result = mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="feat-thresh-1-fail",
            src_files=["src/bob3/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=1.0,
        )
    assert result is not None
    assert result["passed"] is False


# ---------------------------------------------------------------------------
# Boundary: minimum viable feature_id (single character)
# ---------------------------------------------------------------------------


def test_single_char_feature_id_is_valid(tmp_path):
    """A single-character feature_id is a valid boundary input."""
    ok_report = MutationReport(
        feature_id="x",
        total_mutants=2,
        killed=2,
        survived=0,
        timed_out=0,
        mutation_score=1.0,
    )
    with patch(
        "bob3.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=ok_report,
    ):
        result = mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="x",
            src_files=["src/bob3/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result["feature_id"] == "x"


# ---------------------------------------------------------------------------
# Boundary: score exactly at the default gate threshold (0.75)
# ---------------------------------------------------------------------------


def test_score_exactly_at_threshold_passes(tmp_path):
    """Score exactly equal to the threshold is a boundary pass (>=, not >)."""
    boundary_report = MutationReport(
        feature_id="feat-exact-boundary",
        total_mutants=4,
        killed=3,
        survived=1,
        timed_out=0,
        mutation_score=MUTATION_SCORE_THRESHOLD,
    )
    with patch(
        "bob3.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=boundary_report,
    ):
        result = mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="feat-exact-boundary",
            src_files=["src/bob3/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result["passed"] is True
    assert result["mutation_score"] == MUTATION_SCORE_THRESHOLD


# ---------------------------------------------------------------------------
# Boundary: both empty feature_id and pytest_passed=False together
# ---------------------------------------------------------------------------


def test_empty_feature_id_and_pytest_failed_returns_none(tmp_path):
    """Doubly-skipped gate (empty id + failed pytest) returns None gracefully."""
    result = mutation_testing_post_impl_quality_gate_mutmut(
        feature_id="",
        src_files=[],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=False,
    )
    assert result is None
