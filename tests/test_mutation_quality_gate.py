"""Tests for mutation_testing.verify_mutation_score (AC: pytest: tests/test_mutation_quality_gate.py).

Covers the mutation_testing module public API:
- mutation_testing.verify_mutation_score is callable
- delegates correctly to the underlying gate logic
- CLI command quality-gate mutmut is registered on the bob CLI
- integration: spec_quality_gate (verify_mutation_score referenced in gate context)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import mutation_testing
from mutation_testing import verify_mutation_score
from bob.verification.mutation_gate import MutationReport, MutmutMissingError


# ---------------------------------------------------------------------------
# AC: Function defined: mutation_testing.verify_mutation_score
# ---------------------------------------------------------------------------


def test_verify_mutation_score_is_callable():
    """mutation_testing.verify_mutation_score must be importable and callable."""
    assert callable(verify_mutation_score)


def test_mutation_testing_module_exports_verify_mutation_score():
    """mutation_testing module must export verify_mutation_score in __all__."""
    assert "verify_mutation_score" in mutation_testing.__all__


def test_verify_mutation_score_skips_when_pytest_failed(tmp_path):
    """verify_mutation_score returns None when pytest_passed=False."""
    result = verify_mutation_score(
        feature_id="feat-abc",
        src_files=["src/bob/foo.py"],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=False,
    )
    assert result is None


def test_verify_mutation_score_skips_empty_feature_id(tmp_path):
    """verify_mutation_score returns None for empty feature_id."""
    result = verify_mutation_score(
        feature_id="",
        src_files=[],
        test_dir=str(tmp_path),
        workspace=str(tmp_path),
        pytest_passed=True,
    )
    assert result is None


def test_verify_mutation_score_passes_gate_on_high_score(tmp_path):
    """verify_mutation_score returns passed=True when score >= threshold."""
    good_report = MutationReport(
        feature_id="feat-high",
        total_mutants=10,
        killed=9,
        survived=1,
        timed_out=0,
        mutation_score=0.90,
    )
    with patch(
        "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=good_report,
    ):
        result = verify_mutation_score(
            feature_id="feat-high",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )

    assert result is not None
    assert result["passed"] is True
    assert result["mutation_score"] == 0.90
    assert result["feature_id"] == "feat-high"


def test_verify_mutation_score_rejects_gate_on_low_score(tmp_path):
    """verify_mutation_score returns passed=False when score < threshold."""
    bad_report = MutationReport(
        feature_id="feat-low",
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
        result = verify_mutation_score(
            feature_id="feat-low",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )

    assert result is not None
    assert result["passed"] is False


def test_verify_mutation_score_returns_skipped_when_mutmut_missing(tmp_path):
    """verify_mutation_score returns skipped dict when mutmut not installed."""
    with patch(
        "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        side_effect=MutmutMissingError("not installed"),
    ):
        result = verify_mutation_score(
            feature_id="feat-miss",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )

    assert result is not None
    assert result.get("skipped") is True


def test_verify_mutation_score_persists_report_on_failure(tmp_path):
    """verify_mutation_score writes mutation_report.json when gate fails."""
    failing_report = MutationReport(
        feature_id="feat-write",
        total_mutants=8,
        killed=4,
        survived=4,
        timed_out=0,
        mutation_score=0.50,
        surviving_mutant_diffs=[{"mutant_id": "m1", "diff": "--- a\n+++ b\n"}],
    )
    with patch(
        "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=failing_report,
    ):
        verify_mutation_score(
            feature_id="feat-write",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
        )

    report_path = tmp_path / "runs" / "feat-write" / "mutation_report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text())
    assert data["mutation_score"] == 0.50


def test_verify_mutation_score_custom_threshold(tmp_path):
    """verify_mutation_score accepts a custom threshold parameter."""
    report = MutationReport(
        feature_id="feat-thresh",
        total_mutants=10,
        killed=8,
        survived=2,
        timed_out=0,
        mutation_score=0.80,
    )
    with patch(
        "bob.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        return_value=report,
    ):
        # With threshold=0.90, score 0.80 should fail
        result = verify_mutation_score(
            feature_id="feat-thresh",
            src_files=["src/bob/foo.py"],
            test_dir=str(tmp_path),
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=0.90,
        )

    assert result is not None
    assert result["passed"] is False
    assert result["threshold"] == 0.90


# ---------------------------------------------------------------------------
# AC: CLI command: quality-gate mutmut
# ---------------------------------------------------------------------------


def test_quality_gate_mutmut_cli_registered():
    """The bob CLI must expose 'quality-gate mutmut' as a registered command."""
    from click.testing import CliRunner
    from bob.cli import main

    runner = CliRunner()
    # Invoke 'quality-gate --help' to verify the group is registered
    result = runner.invoke(main, ["quality-gate", "--help"])
    assert result.exit_code == 0, (
        f"'bob quality-gate --help' failed with exit code {result.exit_code}:\n"
        f"{result.output}"
    )
    assert "mutmut" in result.output.lower(), (
        f"'mutmut' subcommand not listed in 'quality-gate --help':\n{result.output}"
    )


def test_quality_gate_mutmut_help():
    """'bob quality-gate mutmut --help' must succeed and describe the command."""
    from click.testing import CliRunner
    from bob.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["quality-gate", "mutmut", "--help"])
    assert result.exit_code == 0, (
        f"'bob quality-gate mutmut --help' failed:\n{result.output}"
    )
    # Must mention key options
    assert "--feature-id" in result.output or "feature" in result.output.lower()


# ---------------------------------------------------------------------------
# AC: integration: spec_quality_gate
# ---------------------------------------------------------------------------


def test_spec_quality_gate_integration_symbol():
    """verify_mutation_score must be importable from mutation_testing module
    (spec_quality_gate integration: mutation gate is a verifier-stage gate)."""
    from mutation_testing import verify_mutation_score as vms

    assert callable(vms)
    # The gate threshold must match the spec requirement
    from mutation_testing import MUTATION_SCORE_THRESHOLD

    assert MUTATION_SCORE_THRESHOLD == 0.75


def test_spec_quality_gate_threshold_constant_exported():
    """MUTATION_SCORE_THRESHOLD is exported from mutation_testing for integration."""
    assert hasattr(mutation_testing, "MUTATION_SCORE_THRESHOLD")
    assert mutation_testing.MUTATION_SCORE_THRESHOLD == 0.75
