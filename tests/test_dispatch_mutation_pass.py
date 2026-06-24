"""Tests for mutation-pass check (WEAK_TEST_DETECTED) in bob3.dispatch (F-R7-609).

Covers run_mutation_pass_check, check_mutation_pass, apply_mutation_check,
and emit_weak_test_event. ICSE 2026: 12-22% of "passing" patches are
logically wrong because tests under-specify the behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.dispatch import (
    apply_mutation_check,
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

    def test_feature_id_present(self):
        event = emit_weak_test_event("feat-abc")
        assert event["feature_id"] == "feat-abc"

    def test_detail_included_when_provided(self):
        event = emit_weak_test_event("feat-001", detail="mutation did not flip")
        assert event["detail"] == "mutation did not flip"

    def test_detail_absent_when_none(self):
        event = emit_weak_test_event("feat-001", detail=None)
        assert "detail" not in event

    def test_detail_absent_when_not_passed(self):
        event = emit_weak_test_event("feat-001")
        assert "detail" not in event

    def test_event_is_json_serializable(self):
        event = emit_weak_test_event("feat-123", detail="test info")
        json.dumps(event)  # must not raise

    def test_empty_feature_id_returns_dict(self):
        event = emit_weak_test_event("")
        assert isinstance(event, dict)
        assert event["feature_id"] == ""


class TestRunMutationPassCheck:
    def test_returns_false_when_test_fails_after_mutation(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED")
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is False

    def test_returns_true_when_test_passes_after_mutation(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is True

    def test_returns_bool(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = run_mutation_pass_check(["pytest"], tmp_path, "feat-001")
        assert isinstance(result, bool)

    def test_timeout_returns_false(self, tmp_path):
        import subprocess
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=120)
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is False

    def test_emits_weak_test_event_when_still_passes(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock, \
             patch("bob3.dispatch.emit_weak_test_event") as mock_emit:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            mock_emit.return_value = {"event": "WEAK_TEST_DETECTED", "feature_id": "feat-001"}
            run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
            mock_emit.assert_called_once()

    def test_does_not_emit_weak_test_event_when_test_fails(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock, \
             patch("bob3.dispatch.emit_weak_test_event") as mock_emit:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED")
            run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
            mock_emit.assert_not_called()

    def test_string_workspace_accepted(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = run_mutation_pass_check(["pytest"], str(tmp_path), "feat-001")
        assert isinstance(result, bool)

    def test_passes_env_to_subprocess(self, tmp_path):
        custom_env = {"MY_VAR": "my_val"}
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            run_mutation_pass_check(["pytest"], tmp_path, "feat-001", env=custom_env)
            call_kwargs = mock.call_args[1]
            assert "MY_VAR" in call_kwargs["env"]

    def test_uses_workspace_as_cwd(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            run_mutation_pass_check(["pytest"], tmp_path, "feat-001")
            call_kwargs = mock.call_args[1]
            assert call_kwargs["cwd"] == str(tmp_path)


class TestCheckMutationPass:
    def test_returns_false_when_test_fails(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = check_mutation_pass(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is False

    def test_returns_true_when_test_still_passes(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = check_mutation_pass(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is True

    def test_returns_bool(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = check_mutation_pass(["pytest"], tmp_path, "feat-001")
        assert isinstance(result, bool)

    def test_delegates_to_run_mutation_pass_check(self, tmp_path):
        with patch("bob3.dispatch.run_mutation_pass_check") as mock_inner:
            mock_inner.return_value = False
            check_mutation_pass(["pytest"], tmp_path, "feat-001")
            mock_inner.assert_called_once()


class TestApplyMutationCheck:
    def test_returns_false_when_test_fails(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = apply_mutation_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is False

    def test_returns_true_when_test_still_passes(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = apply_mutation_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is True

    def test_returns_bool(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = apply_mutation_check(["pytest"], tmp_path, "feat-001")
        assert isinstance(result, bool)
