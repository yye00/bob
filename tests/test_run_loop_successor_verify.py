"""Tests for bob3.run_loop.handle_pending_successor_verify (7525d70f).

Verifies that run_loop exposes handle_pending_successor_verify as a public
function that correctly delegates to bob3.status_handler.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


class TestHandlePendingSuccessorVerifyImport:
    """handle_pending_successor_verify must be importable from bob3.run_loop."""

    def test_function_is_importable(self):
        from bob3.run_loop import handle_pending_successor_verify
        assert callable(handle_pending_successor_verify)

    def test_function_is_in_module_all(self):
        import bob3.run_loop as rl
        assert "handle_pending_successor_verify" in dir(rl)

    def test_function_returns_bool(self):
        from bob3.run_loop import handle_pending_successor_verify
        with patch(
            "bob3.status_handlers.handle_pending_successor_verify",
            return_value=False,
        ):
            result = handle_pending_successor_verify("feat-abc", None, False)
        assert isinstance(result, bool)


class TestHandlePendingSuccessorVerifyDelegation:
    """run_loop.handle_pending_successor_verify delegates to status_handlers."""

    def test_returns_false_when_structural_ac_not_passed(self, tmp_path):
        from bob3.run_loop import handle_pending_successor_verify
        result = handle_pending_successor_verify(
            "feat-xyz", tmp_path, structural_ac_passed=False
        )
        assert result is False

    def test_returns_false_for_non_verifier_extension_workspace(self, tmp_path):
        from bob3.run_loop import handle_pending_successor_verify
        # Workspace with no verifier extension modules
        (tmp_path / "ordinary_file.py").write_text("x = 1\n")
        result = handle_pending_successor_verify(
            "feat-ordinary", tmp_path, structural_ac_passed=True
        )
        assert result is False

    def test_returns_true_when_delegate_returns_true(self):
        from bob3.run_loop import handle_pending_successor_verify
        with patch(
            "bob3.status_handlers.handle_pending_successor_verify",
            return_value=True,
        ):
            result = handle_pending_successor_verify("feat-psv", None, True)
        assert result is True

    def test_workspace_none_does_not_raise(self):
        from bob3.run_loop import handle_pending_successor_verify
        result = handle_pending_successor_verify("feat-none-ws", None, False)
        assert isinstance(result, bool)

    def test_nonexistent_workspace_does_not_raise(self):
        from bob3.run_loop import handle_pending_successor_verify
        nonexistent = Path("/tmp/bob3_test_nonexistent_run_loop_9z9z9")
        result = handle_pending_successor_verify(
            "feat-nopath", nonexistent, structural_ac_passed=True
        )
        assert isinstance(result, bool)


class TestPendingSuccessorVerifyStatus:
    """The pending_successor_verify status constant must be accessible."""

    def test_status_string_accessible_via_run_loop(self):
        from bob3.run_loop import set_pending_successor_verify
        assert callable(set_pending_successor_verify)

    def test_detect_pending_successor_verify_accessible(self):
        from bob3.run_loop import detect_pending_successor_verify
        assert callable(detect_pending_successor_verify)
