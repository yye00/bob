"""Tests for mutation_testing_post_impl_quality_gate_mutmut.

Acceptance criteria:
- File exists: src/bob/mutation_testing_post_impl_quality_gate_mutmut.py
- Function defined: bob.mutation_testing_post_impl_quality_gate_mutmut
  .mutation_testing_post_impl_quality_gate_mutmut
- pytest: tests/test_mutation_testing_post_impl_quality_gate_mutmut.py
  ::test_mutation_testing_post_impl_quality_gate_mutmut
- integration: bob.orchestrator.run_loop
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import bob.mutation_testing_post_impl_quality_gate_mutmut as mod
from bob.mutation_testing_post_impl_quality_gate_mutmut import (
    MUTATION_SCORE_THRESHOLD,
    mutation_testing_post_impl_quality_gate_mutmut,
)
from bob.verification.mutation_gate import MutationReport


# ---------------------------------------------------------------------------
# AC test — must be named exactly as in the acceptance criterion
# ---------------------------------------------------------------------------


def test_mutation_testing_post_impl_quality_gate_mutmut():
    """AC test: function importable and expresses core gate behaviour."""
    assert callable(mutation_testing_post_impl_quality_gate_mutmut)

    # Module exposes the threshold constant
    assert hasattr(mod, "MUTATION_SCORE_THRESHOLD")
    assert MUTATION_SCORE_THRESHOLD == 0.75

    # Module docstring mentions mutation or mutmut
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "mutation" in doc or "mutmut" in doc

    # Function returns None for empty feature_id (no-op)
    result = mutation_testing_post_impl_quality_gate_mutmut(
        feature_id="",
        src_files=[],
        test_dir="/tmp",
        workspace="/tmp",
        pytest_passed=False,
    )
    assert result is None

    # When pytest_passed=False, the gate must be skipped (returns None)
    result2 = mutation_testing_post_impl_quality_gate_mutmut(
        feature_id="abc",
        src_files=["src/bob/foo.py"],
        test_dir="tests",
        workspace="/tmp",
        pytest_passed=False,
    )
    assert result2 is None

    # run_loop integration: function exists in run_loop namespace
    import bob.orchestrator.run_loop as rl

    assert hasattr(rl, "mutation_testing_post_impl_quality_gate_mutmut") or hasattr(
        rl, "_run_mutation_gate_if_enabled"
    ), (
        "run_loop must expose mutation_testing_post_impl_quality_gate_mutmut "
        "or _run_mutation_gate_if_enabled"
    )


# ---------------------------------------------------------------------------
# Gate logic tests
# ---------------------------------------------------------------------------


class TestGatePassCondition:
    """Verify the gate accepts implementations with score >= 0.75."""

    def test_passes_on_high_score(self, tmp_path):
        good_report = MutationReport(
            feature_id="feat-pass",
            total_mutants=10,
            killed=8,
            survived=2,
            timed_out=0,
            mutation_score=0.80,
        )
        with patch(
            "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
            return_value=good_report,
        ):
            result = mutation_testing_post_impl_quality_gate_mutmut(
                feature_id="feat-pass",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=True,
            )

        assert result is not None
        assert result["passed"] is True
        assert result["mutation_score"] == 0.80

    def test_passes_exactly_at_threshold(self, tmp_path):
        boundary_report = MutationReport(
            feature_id="feat-boundary",
            total_mutants=4,
            killed=3,
            survived=1,
            timed_out=0,
            mutation_score=0.75,
        )
        with patch(
            "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
            return_value=boundary_report,
        ):
            result = mutation_testing_post_impl_quality_gate_mutmut(
                feature_id="feat-boundary",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=True,
            )

        assert result is not None
        assert result["passed"] is True


class TestGateRejectCondition:
    """Verify the gate rejects implementations with score < 0.75."""

    def test_rejects_on_low_score(self, tmp_path):
        bad_report = MutationReport(
            feature_id="feat-fail",
            total_mutants=10,
            killed=5,
            survived=5,
            timed_out=0,
            mutation_score=0.50,
        )
        with patch(
            "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
            return_value=bad_report,
        ):
            result = mutation_testing_post_impl_quality_gate_mutmut(
                feature_id="feat-fail",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=True,
            )

        assert result is not None
        assert result["passed"] is False
        assert result["mutation_score"] == 0.50

    def test_rejects_just_below_threshold(self, tmp_path):
        borderline_report = MutationReport(
            feature_id="feat-border",
            total_mutants=100,
            killed=74,
            survived=26,
            timed_out=0,
            mutation_score=0.74,
        )
        with patch(
            "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
            return_value=borderline_report,
        ):
            result = mutation_testing_post_impl_quality_gate_mutmut(
                feature_id="feat-border",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=True,
            )

        assert result is not None
        assert result["passed"] is False


class TestMutationReportPersistence:
    """Verify that surviving mutants are persisted when score < 0.75."""

    def test_mutation_report_written_on_failure(self, tmp_path):
        failing_report = MutationReport(
            feature_id="feat-persist",
            total_mutants=10,
            killed=6,
            survived=4,
            timed_out=0,
            mutation_score=0.60,
            surviving_mutant_diffs=[{"mutant_id": "m1", "diff": "--- a\n+++ b\n"}],
        )
        with patch(
            "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
            return_value=failing_report,
        ):
            mutation_testing_post_impl_quality_gate_mutmut(
                feature_id="feat-persist",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=True,
            )

        report_path = tmp_path / "runs" / "feat-persist" / "mutation_report.json"
        assert report_path.exists(), "mutation_report.json must be written on failure"

        data = json.loads(report_path.read_text())
        assert data["mutation_score"] == 0.60
        assert "surviving_mutant_diffs" in data
        assert "message" in data
        assert "strengthen assertions" in data["message"]

    def test_report_contains_next_implementer_message(self, tmp_path):
        failing_report = MutationReport(
            feature_id="feat-msg",
            total_mutants=4,
            killed=2,
            survived=2,
            timed_out=0,
            mutation_score=0.50,
            surviving_mutant_diffs=[],
        )
        with patch(
            "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
            return_value=failing_report,
        ):
            mutation_testing_post_impl_quality_gate_mutmut(
                feature_id="feat-msg",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=True,
            )

        report_path = tmp_path / "runs" / "feat-msg" / "mutation_report.json"
        data = json.loads(report_path.read_text())
        assert "cannot distinguish" in data["message"].lower() or "strengthen" in data["message"].lower()


class TestPytestPassedGuard:
    """Verify the gate only runs after pytest passes."""

    def test_skips_when_pytest_failed(self, tmp_path):
        with patch(
            "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test"
        ) as mock_run:
            result = mutation_testing_post_impl_quality_gate_mutmut(
                feature_id="feat-skip",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=False,
            )

        mock_run.assert_not_called()
        assert result is None

    def test_runs_when_pytest_passed(self, tmp_path):
        ok_report = MutationReport(
            feature_id="feat-run",
            total_mutants=4,
            killed=4,
            survived=0,
            timed_out=0,
            mutation_score=1.0,
        )
        with patch(
            "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
            return_value=ok_report,
        ) as mock_run:
            mutation_testing_post_impl_quality_gate_mutmut(
                feature_id="feat-run",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=True,
            )

        mock_run.assert_called_once()


class TestMutmutUnavailable:
    """Verify graceful handling when mutmut is not installed."""

    def test_returns_skipped_result_when_mutmut_missing(self, tmp_path):
        from bob.verification.mutation_gate import MutmutMissingError

        with patch(
            "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
            side_effect=MutmutMissingError("mutmut not installed"),
        ):
            result = mutation_testing_post_impl_quality_gate_mutmut(
                feature_id="feat-miss",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=True,
            )

        assert result is not None
        assert result.get("skipped") is True
        assert "mutmut" in result.get("reason", "").lower()


class TestRunLoopIntegration:
    """Verify that run_loop imports or exposes the mutation gate helper."""

    def test_run_loop_has_mutation_gate_symbol(self):
        import bob.orchestrator.run_loop as rl

        has_facade = hasattr(rl, "mutation_testing_post_impl_quality_gate_mutmut")
        has_helper = hasattr(rl, "_run_mutation_gate_if_enabled")
        assert has_facade or has_helper, (
            "run_loop must import mutation_testing_post_impl_quality_gate_mutmut "
            "or define _run_mutation_gate_if_enabled"
        )

    def test_mutation_gate_importable_from_module(self):
        from bob.mutation_testing_post_impl_quality_gate_mutmut import (
            mutation_testing_post_impl_quality_gate_mutmut,
        )

        assert callable(mutation_testing_post_impl_quality_gate_mutmut)
