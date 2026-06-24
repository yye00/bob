"""Error path tests for mutation-pass check timeout handling in bob.swe_bench_directives (F-R7-609).

Tests that run_mutation_pass_check and check_mutation_pass handle timeout and
subprocess errors gracefully, returning False rather than raising.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from bob.swe_bench_directives import (
    check_mutation_pass,
    handle_mutation_failure,
    run_mutation_pass_check,
)


class TestRunMutationPassCheckTimeout:
    def test_timeout_returns_false(self, tmp_path):
        """TimeoutExpired should return False (mutation check inconclusive)."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=1)):
            result = run_mutation_pass_check(
                ["pytest", "tests/test_foo.py"],
                workspace=str(tmp_path),
                feature_id="feat-timeout-001",
                timeout=1,
            )
        assert result is False

    def test_timeout_does_not_raise(self, tmp_path):
        """TimeoutExpired must not propagate out of run_mutation_pass_check."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=1)):
            try:
                run_mutation_pass_check(
                    ["pytest"],
                    workspace=str(tmp_path),
                    feature_id="feat-timeout-002",
                    timeout=1,
                )
            except subprocess.TimeoutExpired:
                pytest.fail("TimeoutExpired should not propagate from run_mutation_pass_check")

    def test_timeout_with_empty_feature_id(self, tmp_path):
        """Timeout with empty feature_id still returns False without raising."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=1)):
            result = run_mutation_pass_check(
                ["pytest"],
                workspace=str(tmp_path),
                feature_id="",
                timeout=1,
            )
        assert result is False

    def test_nonzero_exit_returns_false(self, tmp_path):
        """A failing test (returncode != 0) should return False."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            result = run_mutation_pass_check(
                ["pytest", "tests/test_bar.py"],
                workspace=str(tmp_path),
                feature_id="feat-fail-001",
            )
        assert result is False

    def test_zero_exit_returns_true(self, tmp_path):
        """A passing test (returncode == 0) should return True (weak test detected)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            result = run_mutation_pass_check(
                ["pytest", "tests/test_baz.py"],
                workspace=str(tmp_path),
                feature_id="feat-weak-001",
            )
        assert result is True

    def test_check_mutation_pass_alias_timeout_returns_false(self, tmp_path):
        """check_mutation_pass alias must also handle TimeoutExpired gracefully."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=1)):
            result = check_mutation_pass(
                ["pytest"],
                workspace=str(tmp_path),
                feature_id="feat-alias-timeout",
                timeout=1,
            )
        assert result is False

    def test_invalid_command_returns_false(self, tmp_path):
        """FileNotFoundError (bad command) should not raise — return False."""
        result = run_mutation_pass_check(
            ["nonexistent_binary_xyzzy_12345"],
            workspace=str(tmp_path),
            feature_id="feat-bad-cmd",
            timeout=5,
        )
        assert result is False

    def test_check_mutation_pass_alias_bad_command_returns_false(self, tmp_path):
        """check_mutation_pass alias: bad command must return False without raising."""
        result = check_mutation_pass(
            ["nonexistent_binary_xyzzy_12345"],
            workspace=str(tmp_path),
            feature_id="feat-bad-cmd-alias",
            timeout=5,
        )
        assert result is False


class TestHandleMutationFailure:
    def test_handle_mutation_failure_returns_dict(self):
        event = handle_mutation_failure("feat-handle-001")
        assert isinstance(event, dict)

    def test_handle_mutation_failure_event_key(self):
        event = handle_mutation_failure("feat-handle-002")
        assert event.get("event") == "WEAK_TEST_DETECTED"

    def test_handle_mutation_failure_includes_feature_id(self):
        event = handle_mutation_failure("feat-handle-003")
        assert event.get("feature_id") == "feat-handle-003"

    def test_handle_mutation_failure_does_not_raise_on_empty_id(self):
        try:
            handle_mutation_failure("")
        except Exception as exc:
            pytest.fail(f"handle_mutation_failure raised unexpectedly: {exc}")

    def test_handle_mutation_failure_with_optional_detail(self):
        event = handle_mutation_failure("feat-handle-004", detail="mutation did not flip result")
        assert "detail" in event or "WEAK_TEST_DETECTED" == event.get("event")
