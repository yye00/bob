"""Tests for bob.status_handlers — successor-gen verification handoff (6ff3ca07).

Acceptance criteria:
- File exists: src/bob/status_handlers.py
- Function defined: bob.status_handlers.handle_pending_successor_verify
- pytest: tests/test_successor_verify.py
- integration: bob.run_loop
"""

from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# AC 1: File exists — src/bob/status_handlers.py
# ---------------------------------------------------------------------------


class TestFileExists:
    def test_module_file_exists(self):
        import bob.status_handlers

        module_file = Path(bob.status_handlers.__file__)
        assert module_file.exists()
        assert module_file.name == "status_handlers.py"

    def test_module_importable(self):
        import bob.status_handlers  # noqa: F401

    def test_expected_names_exported(self):
        from bob.status_handlers import (
            PENDING_SUCCESSOR_VERIFY_STATUS,
            VERIFIER_EXTENSION_MODULES,
            handle_pending_successor_verify,
        )
        assert callable(handle_pending_successor_verify)
        assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
        assert PENDING_SUCCESSOR_VERIFY_STATUS == "pending_successor_verify"

    def test_all_contains_expected_names(self):
        from bob.status_handlers import __all__
        assert "handle_pending_successor_verify" in __all__
        assert "PENDING_SUCCESSOR_VERIFY_STATUS" in __all__
        assert "VERIFIER_EXTENSION_MODULES" in __all__


# ---------------------------------------------------------------------------
# AC 2: Function defined — bob.status_handlers.handle_pending_successor_verify
# ---------------------------------------------------------------------------


class TestFunctionDefined:
    def test_function_is_callable(self):
        from bob.status_handlers import handle_pending_successor_verify
        assert callable(handle_pending_successor_verify)

    def test_function_signature_has_required_params(self):
        from bob.status_handlers import handle_pending_successor_verify
        sig = inspect.signature(handle_pending_successor_verify)
        params = list(sig.parameters)
        assert "feature_id" in params
        assert "workspace" in params
        assert "structural_ac_passed" in params

    def test_function_has_three_params(self):
        from bob.status_handlers import handle_pending_successor_verify
        sig = inspect.signature(handle_pending_successor_verify)
        assert len(sig.parameters) == 3

    def test_function_returns_bool(self):
        from bob.status_handlers import handle_pending_successor_verify
        with patch("bob.status_handlers.set_pending_successor_verify", return_value=True):
            result = handle_pending_successor_verify("feat-123", None, True)
        assert isinstance(result, bool)

    def test_function_returns_false_when_no_structural_ac_passed(self):
        from bob.status_handlers import handle_pending_successor_verify
        with patch("bob.status_handlers.set_pending_successor_verify", return_value=False) as mock_set:
            result = handle_pending_successor_verify("feat-456", None, False)
        assert result is False

    def test_function_delegates_to_set_pending_successor_verify(self):
        from bob.status_handlers import handle_pending_successor_verify
        with patch("bob.status_handlers.set_pending_successor_verify") as mock_set:
            mock_set.return_value = True
            result = handle_pending_successor_verify("feat-789", "/some/workspace", True)
            mock_set.assert_called_once_with("feat-789", "/some/workspace", True)
            assert result is True

    def test_function_passes_workspace_none(self):
        from bob.status_handlers import handle_pending_successor_verify
        with patch("bob.status_handlers.set_pending_successor_verify") as mock_set:
            mock_set.return_value = False
            handle_pending_successor_verify("feat-000", None, True)
            mock_set.assert_called_once_with("feat-000", None, True)


# ---------------------------------------------------------------------------
# AC 3: Behavioral tests for the handler logic
# ---------------------------------------------------------------------------


class TestHandlerBehavior:
    def test_returns_true_when_verifier_extension_with_structural_ac_passed(self, tmp_path):
        """When workspace has a verifier-extension module and structural AC passed, return True."""
        verifier_src = tmp_path / "src" / "bob"
        verifier_src.mkdir(parents=True)
        (verifier_src / "enhanced_verification.py").write_text("# patched verifier\n")

        from bob.status_handlers import handle_pending_successor_verify
        with patch("bob.pending_successor_verify.db") as mock_db:
            mock_db.update_feature.return_value = None
            result = handle_pending_successor_verify(
                "feat-aaa", str(tmp_path), True
            )
        assert result is True

    def test_returns_false_when_structural_ac_not_passed(self, tmp_path):
        """When structural_ac_passed is False, always return False regardless of workspace."""
        verifier_src = tmp_path / "src" / "bob"
        verifier_src.mkdir(parents=True)
        (verifier_src / "enhanced_verification.py").write_text("# patched verifier\n")

        from bob.status_handlers import handle_pending_successor_verify
        result = handle_pending_successor_verify("feat-bbb", str(tmp_path), False)
        assert result is False

    def test_returns_false_when_no_verifier_extension_in_workspace(self, tmp_path):
        """When workspace does not touch a verifier-extension module, return False."""
        src = tmp_path / "src" / "bob"
        src.mkdir(parents=True)
        (src / "some_unrelated_module.py").write_text("# unrelated\n")

        from bob.status_handlers import handle_pending_successor_verify
        result = handle_pending_successor_verify("feat-ccc", str(tmp_path), True)
        assert result is False

    def test_returns_false_when_workspace_is_none(self):
        """When workspace is None, return False (cannot detect verifier-extension)."""
        from bob.status_handlers import handle_pending_successor_verify
        result = handle_pending_successor_verify("feat-ddd", None, True)
        assert result is False

    def test_returns_false_when_workspace_does_not_exist(self, tmp_path):
        """When workspace path does not exist, return False safely."""
        from bob.status_handlers import handle_pending_successor_verify
        nonexistent = tmp_path / "no_such_dir"
        result = handle_pending_successor_verify("feat-eee", str(nonexistent), True)
        assert result is False

    def test_logs_debug_on_call(self, tmp_path, caplog):
        """Logs a debug message when called."""
        from bob.status_handlers import handle_pending_successor_verify
        with caplog.at_level(logging.DEBUG, logger="bob.status_handlers"):
            handle_pending_successor_verify("feat-fff", None, False)
        assert "feat-fff" in caplog.text

    def test_verifier_extension_module_verified_src_path(self, tmp_path):
        """Verify other VERIFIER_EXTENSION_MODULES are also detected."""
        verifier_src = tmp_path / "src" / "bob" / "verification"
        verifier_src.mkdir(parents=True)
        (verifier_src / "verifier.py").write_text("# patched secondary verifier\n")

        from bob.status_handlers import handle_pending_successor_verify
        with patch("bob.pending_successor_verify.db") as mock_db:
            mock_db.update_feature.return_value = None
            result = handle_pending_successor_verify(
                "feat-ggg", str(tmp_path), True
            )
        assert result is True


# ---------------------------------------------------------------------------
# AC 4: Integration — bob.run_loop
# ---------------------------------------------------------------------------


class TestRunLoopIntegration:
    def test_handle_pending_successor_verify_in_run_loop(self):
        """handle_pending_successor_verify must be accessible from bob.run_loop."""
        from bob.run_loop import handle_pending_successor_verify
        assert callable(handle_pending_successor_verify)

    def test_run_loop_all_includes_handler(self):
        """run_loop.__all__ must include handle_pending_successor_verify."""
        import bob.run_loop as rl
        assert "handle_pending_successor_verify" in rl.__all__

    def test_run_loop_function_delegates_to_status_handlers(self):
        """run_loop.handle_pending_successor_verify delegates to status_handlers."""
        from bob.run_loop import handle_pending_successor_verify
        with patch("bob.status_handlers.set_pending_successor_verify") as mock_set:
            mock_set.return_value = True
            result = handle_pending_successor_verify("feat-hhh", "/workspace", True)
        assert result is True

    def test_run_loop_function_signature_matches(self):
        """run_loop.handle_pending_successor_verify has the same signature as the handler."""
        from bob.run_loop import handle_pending_successor_verify
        sig = inspect.signature(handle_pending_successor_verify)
        params = list(sig.parameters)
        assert "feature_id" in params
        assert "workspace" in params
        assert "structural_ac_passed" in params

    def test_set_pending_successor_verify_still_in_run_loop(self):
        """Existing set_pending_successor_verify remains accessible after adding new handler."""
        from bob.run_loop import set_pending_successor_verify
        assert callable(set_pending_successor_verify)

    def test_status_handlers_module_importable_from_run_loop_context(self):
        """bob.status_handlers can be imported (round-trip check from run_loop)."""
        import bob.status_handlers as sh
        import bob.run_loop as rl
        assert hasattr(sh, "handle_pending_successor_verify")
        assert hasattr(rl, "handle_pending_successor_verify")
