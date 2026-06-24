"""Tests for bob.mutmut_gate — mutmut 3.x post-impl quality gate.

Acceptance criteria:
- File exists: src/bob/mutmut_gate.py
- Function defined: bob.mutmut_gate.run_mutation_tests
- pytest: tests/test_mutmut_gate.py
- CLI command: verify mutmut
- integration: bob.verifier
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import bob.mutmut_gate as mod
from bob.mutmut_gate import MUTATION_SCORE_THRESHOLD, run_mutation_tests
from bob.verification.mutation_gate import MutationReport, MutmutMissingError


# ---------------------------------------------------------------------------
# AC 1 & 2: File and function presence
# ---------------------------------------------------------------------------


def test_module_importable():
    """bob.mutmut_gate must be importable."""
    assert mod is not None


def test_run_mutation_tests_callable():
    """bob.mutmut_gate.run_mutation_tests must be a callable."""
    assert callable(run_mutation_tests)


def test_threshold_constant():
    """Module must expose MUTATION_SCORE_THRESHOLD = 0.75."""
    assert MUTATION_SCORE_THRESHOLD == 0.75


# ---------------------------------------------------------------------------
# AC 5: Integration with bob.verifier
# ---------------------------------------------------------------------------


def test_verifier_imports_run_mutation_tests():
    """bob.verifier must import run_mutation_tests from bob.mutmut_gate."""
    import bob.verifier as verifier

    # verifier should have the mutmut gate integration (imported at module level)
    assert hasattr(verifier, "run_mutation_tests") or hasattr(
        verifier, "check_mutation_score"
    ), "bob.verifier must expose run_mutation_tests or check_mutation_score"


def test_verifier_imports_check_mutation_score():
    """bob.verifier re-exports check_mutation_score from mutmut_gate."""
    import bob.verifier as verifier

    assert hasattr(verifier, "check_mutation_score"), (
        "bob.verifier must re-export check_mutation_score from bob.mutmut_gate"
    )


# ---------------------------------------------------------------------------
# AC 4: CLI command `verify mutmut`
# ---------------------------------------------------------------------------


def test_verify_mutmut_cli_command_exists():
    """bob verify mutmut CLI command must exist."""
    from bob.cli import main

    # The 'verify' group or direct command must exist
    commands = list(main.commands.keys())
    assert "verify" in commands, (
        f"'verify' command/group missing from bob CLI; available: {commands}"
    )


def test_verify_mutmut_subcommand_exists():
    """bob verify mutmut subcommand must be registered."""
    from bob.cli import main

    verify_group = main.commands.get("verify")
    assert verify_group is not None, "'verify' group not registered in bob CLI"
    sub_cmds = list(verify_group.commands.keys()) if hasattr(verify_group, "commands") else []
    assert "mutmut" in sub_cmds, (
        f"'mutmut' subcommand missing from 'verify' group; available: {sub_cmds}"
    )


# ---------------------------------------------------------------------------
# Gate logic: skip conditions
# ---------------------------------------------------------------------------


def test_returns_none_when_pytest_not_passed(tmp_path):
    """Gate must return None when pytest_passed=False."""
    result = run_mutation_tests(
        feature_id="feat-x",
        src_files=["src/bob/dummy.py"],
        test_dir="tests",
        workspace=str(tmp_path),
        pytest_passed=False,
    )
    assert result is None


def test_returns_none_for_empty_feature_id(tmp_path):
    """Gate must return None for empty feature_id."""
    result = run_mutation_tests(
        feature_id="",
        src_files=[],
        test_dir="tests",
        workspace=str(tmp_path),
        pytest_passed=True,
    )
    assert result is None


# ---------------------------------------------------------------------------
# Gate logic: mutmut unavailable → skipped result
# ---------------------------------------------------------------------------


def test_skips_gracefully_when_mutmut_missing(tmp_path):
    """When mutmut is not installed, gate returns skipped=True dict."""
    with patch(
        "bob.mutmut_gate.run_mutation_test",
        side_effect=MutmutMissingError("mutmut not found on PATH"),
    ):
        result = run_mutation_tests(
            feature_id="feat-skip",
            src_files=["src/bob/foo.py"],
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result.get("skipped") is True
    assert "reason" in result


# ---------------------------------------------------------------------------
# Gate logic: pass / fail conditions
# ---------------------------------------------------------------------------


def test_passes_on_high_mutation_score(tmp_path):
    """Gate must return passed=True when mutation_score >= threshold."""
    good_report = MutationReport(
        feature_id="feat-pass",
        total_mutants=10,
        killed=8,
        survived=2,
        timed_out=0,
        mutation_score=0.80,
    )
    with patch("bob.mutmut_gate.run_mutation_test", return_value=good_report):
        result = run_mutation_tests(
            feature_id="feat-pass",
            src_files=["src/bob/foo.py"],
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    assert result["passed"] is True
    assert result["mutation_score"] == 0.80


def test_rejects_on_low_mutation_score(tmp_path):
    """Gate must return passed=False when mutation_score < threshold."""
    bad_report = MutationReport(
        feature_id="feat-fail",
        total_mutants=10,
        killed=4,
        survived=6,
        timed_out=0,
        mutation_score=0.40,
    )
    with patch("bob.mutmut_gate.run_mutation_test", return_value=bad_report):
        with patch("bob.mutmut_gate.persist_surviving_mutants") as mock_persist:
            result = run_mutation_tests(
                feature_id="feat-fail",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=True,
            )
    assert result is not None
    assert result["passed"] is False
    assert result["mutation_score"] == 0.40
    mock_persist.assert_called_once()


def test_surviving_mutants_persisted_on_failure(tmp_path):
    """Surviving mutants must be persisted when gate rejects."""
    bad_report = MutationReport(
        feature_id="feat-mutants",
        total_mutants=8,
        killed=3,
        survived=5,
        timed_out=0,
        mutation_score=0.375,
        surviving_mutant_diffs=[{"id": 1, "diff": "--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y"}],
    )
    with patch("bob.mutmut_gate.run_mutation_test", return_value=bad_report):
        with patch("bob.mutmut_gate.persist_surviving_mutants") as mock_persist:
            run_mutation_tests(
                feature_id="feat-mutants",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=True,
            )
    mock_persist.assert_called_once_with(bad_report, tmp_path)


def test_custom_threshold_respected(tmp_path):
    """Gate must use custom threshold when provided."""
    report = MutationReport(
        feature_id="feat-custom",
        total_mutants=10,
        killed=6,
        survived=4,
        timed_out=0,
        mutation_score=0.60,
    )
    with patch("bob.mutmut_gate.run_mutation_test", return_value=report):
        with patch("bob.mutmut_gate.persist_surviving_mutants"):
            # With default threshold (0.75), score 0.60 should fail
            result_default = run_mutation_tests(
                feature_id="feat-custom",
                src_files=["src/bob/foo.py"],
                test_dir="tests",
                workspace=str(tmp_path),
                pytest_passed=True,
            )
    assert result_default["passed"] is False

    with patch("bob.mutmut_gate.run_mutation_test", return_value=report):
        # With threshold=0.50, score 0.60 should pass
        result_low = run_mutation_tests(
            feature_id="feat-custom",
            src_files=["src/bob/foo.py"],
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=0.50,
        )
    assert result_low["passed"] is True
    assert result_low["threshold"] == 0.50


# ---------------------------------------------------------------------------
# Type validation
# ---------------------------------------------------------------------------


def test_invalid_feature_id_type_raises(tmp_path):
    """Non-string feature_id must raise TypeError."""
    with pytest.raises(TypeError):
        run_mutation_tests(
            feature_id=42,  # type: ignore[arg-type]
            src_files=[],
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=True,
        )


def test_invalid_src_files_type_raises(tmp_path):
    """Non-list src_files must raise TypeError."""
    with pytest.raises(TypeError):
        run_mutation_tests(
            feature_id="feat-x",
            src_files="not-a-list",  # type: ignore[arg-type]
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=True,
        )


def test_invalid_threshold_raises(tmp_path):
    """Out-of-range threshold must raise ValueError."""
    with pytest.raises(ValueError):
        run_mutation_tests(
            feature_id="feat-x",
            src_files=[],
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=False,
            threshold=1.5,
        )


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


def test_result_contains_expected_keys(tmp_path):
    """Gate result dict must contain standard keys."""
    report = MutationReport(
        feature_id="feat-keys",
        total_mutants=4,
        killed=4,
        survived=0,
        timed_out=0,
        mutation_score=1.0,
    )
    with patch("bob.mutmut_gate.run_mutation_test", return_value=report):
        result = run_mutation_tests(
            feature_id="feat-keys",
            src_files=["src/bob/foo.py"],
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=True,
        )
    assert result is not None
    for key in ("passed", "mutation_score", "feature_id", "total_mutants", "killed", "survived"):
        assert key in result, f"Key '{key}' missing from gate result"
