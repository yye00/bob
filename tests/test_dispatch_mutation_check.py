"""Tests for mutation-pass check in bob.dispatch (F-R7-609).

Covers run_mutation_pass_check, check_mutation_pass, and emit_weak_test_event.

ICSE 2026 finding: 12-22% of "passing" patches are logically wrong because
tests under-specify behaviour. The mutation-pass check detects this by
running the test after flipping a constant/boolean in the edited region.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob.dispatch import (
    check_mutation_pass,
    emit_weak_test_event,
    run_mutation_pass_check,
)


class TestEmitWeakTestEvent:
    def test_returns_dict(self):
        event = emit_weak_test_event("feat-001")
        assert isinstance(event, dict)

    def test_event_key_is_weak_test_detected(self):
        event = emit_weak_test_event("feat-001")
        assert event["event"] == "WEAK_TEST_DETECTED"

    def test_feature_id_in_event(self):
        event = emit_weak_test_event("feat-abc")
        assert event["feature_id"] == "feat-abc"

    def test_detail_included_when_provided(self):
        event = emit_weak_test_event("feat-001", detail="mutation did not flip")
        assert event["detail"] == "mutation did not flip"

    def test_detail_absent_when_none(self):
        event = emit_weak_test_event("feat-001", detail=None)
        assert "detail" not in event

    def test_event_is_json_serializable(self):
        event = emit_weak_test_event("feat-001", detail="some detail")
        json.dumps(event)  # must not raise

    def test_empty_feature_id_accepted(self):
        event = emit_weak_test_event("")
        assert event["feature_id"] == ""


class TestRunMutationPassCheck:
    def test_returns_false_when_test_fails(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED")
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is False

    def test_returns_true_when_test_still_passes(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="passed", stderr="")
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is True

    def test_emits_weak_test_event_when_passes(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch("bob.dispatch.emit_weak_test_event") as mock_emit:
                run_mutation_pass_check(["pytest"], tmp_path, "feat-001")
                mock_emit.assert_called_once()

    def test_does_not_emit_event_when_test_fails(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            with patch("bob.dispatch.emit_weak_test_event") as mock_emit:
                run_mutation_pass_check(["pytest"], tmp_path, "feat-001")
                mock_emit.assert_not_called()

    def test_accepts_string_workspace(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = run_mutation_pass_check(["pytest"], str(tmp_path), "feat-001")
        assert isinstance(result, bool)

    def test_returns_false_on_timeout(self, tmp_path):
        import subprocess
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=1)
            result = run_mutation_pass_check(["pytest"], tmp_path, "feat-001", timeout=1)
        assert result is False

    def test_passes_env_to_subprocess(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            run_mutation_pass_check(["pytest"], tmp_path, "feat-001", env={"FOO": "bar"})
            _, kwargs = mock_run.call_args
            assert "FOO" in kwargs["env"]

    def test_command_passed_as_first_arg(self, tmp_path):
        cmd = ["pytest", "-x", "test_foo.py"]
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            run_mutation_pass_check(cmd, tmp_path, "feat-001")
            args, _ = mock_run.call_args
            assert args[0] == cmd


class TestCheckMutationPass:
    def test_delegates_to_run_mutation_pass_check(self, tmp_path):
        with patch("bob.dispatch.run_mutation_pass_check") as mock_inner:
            mock_inner.return_value = False
            result = check_mutation_pass(["pytest"], tmp_path, "feat-001")
        mock_inner.assert_called_once()
        assert result is False

    def test_returns_true_for_weak_test(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = check_mutation_pass(["pytest"], tmp_path, "feat-001")
        assert result is True

    def test_returns_false_for_adequate_test(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = check_mutation_pass(["pytest"], tmp_path, "feat-001")
        assert result is False

    def test_passes_through_env_parameter(self, tmp_path):
        with patch("bob.dispatch.run_mutation_pass_check") as mock_inner:
            mock_inner.return_value = False
            check_mutation_pass(["pytest"], tmp_path, "feat-001", env={"X": "1"})
            _, kwargs = mock_inner.call_args
            assert kwargs.get("env") == {"X": "1"}

    def test_passes_through_timeout_parameter(self, tmp_path):
        with patch("bob.dispatch.run_mutation_pass_check") as mock_inner:
            mock_inner.return_value = False
            check_mutation_pass(["pytest"], tmp_path, "feat-001", timeout=60)
            _, kwargs = mock_inner.call_args
            assert kwargs.get("timeout") == 60
