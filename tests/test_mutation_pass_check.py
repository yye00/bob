"""Tests for mutation-pass check (F-R7-609 component D).

AC: Function defined: bob3.dispatch.check_mutation_pass
    pytest: tests/test_mutation_pass_check.py

ICSE 2026: 12-22% of "passing" patches are logically wrong because tests
under-specify. After worker reports test-pass, flip one constant or negate
one boolean; if test still passes, emit WEAK_TEST_DETECTED.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.dispatch import (
    check_mutation_pass,
    emit_weak_test_event,
    run_mutation_pass_check,
)


class TestCheckMutationPassExists:
    def test_check_mutation_pass_callable(self):
        assert callable(check_mutation_pass)

    def test_run_mutation_pass_check_callable(self):
        assert callable(run_mutation_pass_check)

    def test_emit_weak_test_event_callable(self):
        assert callable(emit_weak_test_event)


class TestRunMutationPassCheck:
    def test_returns_false_when_test_fails(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="FAILED", stderr="")
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is False

    def test_returns_true_when_test_passes_after_mutation(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="passed", stderr="")
            result = run_mutation_pass_check(["pytest", "test.py"], tmp_path, "feat-001")
        assert result is True

    def test_returns_bool_type(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = run_mutation_pass_check(["echo"], tmp_path, "feat-002")
        assert isinstance(result, bool)

    def test_timeout_returns_false(self, tmp_path):
        import subprocess as sp
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.side_effect = sp.TimeoutExpired(cmd=["pytest"], timeout=1)
            result = run_mutation_pass_check(["pytest"], tmp_path, "feat-003", timeout=1)
        assert result is False

    def test_accepts_extra_env(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = run_mutation_pass_check(
                ["pytest"], tmp_path, "feat-004", env={"MY_VAR": "1"}
            )
        assert isinstance(result, bool)
        call_kwargs = mock.call_args[1]
        assert "MY_VAR" in call_kwargs["env"]

    def test_accepts_string_workspace(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = run_mutation_pass_check(["pytest"], str(tmp_path), "feat-005")
        assert isinstance(result, bool)

    def test_workspace_used_as_cwd(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            run_mutation_pass_check(["pytest", "t.py"], tmp_path, "feat-006")
        assert mock.call_args[1]["cwd"] == str(tmp_path)


class TestCheckMutationPass:
    def test_delegates_to_run_mutation_pass_check_pass(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = check_mutation_pass(["pytest"], tmp_path, "feat-007")
        assert result is True

    def test_delegates_to_run_mutation_pass_check_fail(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = check_mutation_pass(["pytest"], tmp_path, "feat-008")
        assert result is False

    def test_returns_bool(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = check_mutation_pass(["echo"], tmp_path, "feat-009")
        assert isinstance(result, bool)


class TestEmitWeakTestEvent:
    def test_returns_dict(self):
        event = emit_weak_test_event("feat-010")
        assert isinstance(event, dict)

    def test_event_key_is_weak_test_detected(self):
        event = emit_weak_test_event("feat-011")
        assert event["event"] == "WEAK_TEST_DETECTED"

    def test_feature_id_stored(self):
        event = emit_weak_test_event("feat-xyz")
        assert event["feature_id"] == "feat-xyz"

    def test_detail_included_when_provided(self):
        event = emit_weak_test_event("feat-012", detail="mutation did not flip")
        assert event["detail"] == "mutation did not flip"

    def test_detail_absent_when_none(self):
        event = emit_weak_test_event("feat-013", detail=None)
        assert "detail" not in event

    def test_emit_when_test_passes_after_mutation(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="passed", stderr="")
            with patch("bob3.dispatch.emit_weak_test_event") as mock_emit:
                mock_emit.return_value = {"event": "WEAK_TEST_DETECTED", "feature_id": "f"}
                run_mutation_pass_check(["pytest"], tmp_path, "f")
            mock_emit.assert_called_once()

    def test_no_emit_when_test_fails_after_mutation(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            with patch("bob3.dispatch.emit_weak_test_event") as mock_emit:
                run_mutation_pass_check(["pytest"], tmp_path, "f")
            mock_emit.assert_not_called()
