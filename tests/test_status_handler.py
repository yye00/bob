"""Tests for bob.status_handler — handle_pending_successor_verify (f77b0d51).

Acceptance criteria:
- File exists: src/bob/status_handler.py
- Function defined: bob.status_handler.handle_pending_successor_verify
- pytest: tests/test_status_handler.py
- integration: bob.run_loop
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# AC 1: File exists — src/bob/status_handler.py
# ---------------------------------------------------------------------------


class TestFileExists:
    def test_module_file_exists(self):
        import bob.status_handler

        module_file = Path(bob.status_handler.__file__)
        assert module_file.exists()
        assert module_file.name == "status_handler.py"

    def test_module_importable(self):
        import bob.status_handler  # noqa: F401

    def test_handle_pending_exported(self):
        from bob.status_handler import handle_pending_successor_verify
        assert callable(handle_pending_successor_verify)


# ---------------------------------------------------------------------------
# AC 2: Function defined — bob.status_handler.handle_pending_successor_verify
# ---------------------------------------------------------------------------


class TestFunctionDefined:
    def test_function_is_callable(self):
        from bob.status_handler import handle_pending_successor_verify
        assert callable(handle_pending_successor_verify)

    def test_function_signature_has_required_params(self):
        from bob.status_handler import handle_pending_successor_verify
        sig = inspect.signature(handle_pending_successor_verify)
        params = list(sig.parameters)
        assert "feature_id" in params
        assert "workspace" in params
        assert "structural_ac_passed" in params

    def test_function_returns_bool(self):
        from bob.status_handler import handle_pending_successor_verify
        with patch(
            "bob.status_handler.set_pending_successor_verify",
            return_value=False,
        ):
            result = handle_pending_successor_verify("feat-001", None, False)
        assert isinstance(result, bool)

    def test_raises_value_error_on_none_feature_id(self):
        from bob.status_handler import handle_pending_successor_verify
        with pytest.raises(ValueError):
            handle_pending_successor_verify(None, None, False)

    def test_raises_value_error_on_non_string_feature_id(self):
        from bob.status_handler import handle_pending_successor_verify
        with pytest.raises(ValueError):
            handle_pending_successor_verify(12345, None, False)


# ---------------------------------------------------------------------------
# AC 3: Integration with bob.run_loop
# ---------------------------------------------------------------------------


class TestRunLoopIntegration:
    def test_run_loop_exports_handle_pending_successor_verify(self):
        import bob.run_loop
        assert hasattr(bob.run_loop, "handle_pending_successor_verify")
        assert callable(bob.run_loop.handle_pending_successor_verify)

    def test_run_loop_function_delegates(self):
        from bob.run_loop import handle_pending_successor_verify as rl_handle
        with patch(
            "bob.status_handlers.handle_pending_successor_verify",
            return_value=True,
        ) as mock_fn:
            result = rl_handle("feat-rl", None, True)
        assert result is True
        mock_fn.assert_called_once_with("feat-rl", None, True)


# ---------------------------------------------------------------------------
# Behavioral tests
# ---------------------------------------------------------------------------


class TestBehavior:
    def test_returns_false_when_structural_ac_not_passed(self, tmp_path):
        from bob.status_handler import handle_pending_successor_verify
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        # structural_ac_passed=False — set_pending_successor_verify short-circuits
        result = handle_pending_successor_verify(
            "feat-no-structural", tmp_path, structural_ac_passed=False
        )
        assert result is False

    def test_returns_false_when_not_verifier_extension(self, tmp_path):
        from bob.status_handler import handle_pending_successor_verify
        src = tmp_path / "src"
        src.mkdir()
        (src / "regular_module.py").write_text("# not a verifier")

        # workspace has no verifier-extension module — is_verifier_extension_feature returns False
        result = handle_pending_successor_verify(
            "feat-not-ext", tmp_path, structural_ac_passed=True
        )
        assert result is False

    def test_returns_true_when_both_conditions_met(self, tmp_path):
        from bob.status_handler import handle_pending_successor_verify
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier patched")

        with patch(
            "bob.status_handler.set_pending_successor_verify",
            return_value=True,
        ) as mock_set:
            result = handle_pending_successor_verify(
                "feat-both-met", tmp_path, structural_ac_passed=True
            )
        assert result is True
        mock_set.assert_called_once_with("feat-both-met", tmp_path, True)

    def test_returns_false_when_workspace_is_none_and_structural_passed(self):
        from bob.status_handler import handle_pending_successor_verify
        with patch(
            "bob.status_handler.set_pending_successor_verify",
            return_value=False,
        ):
            result = handle_pending_successor_verify(
                "feat-no-ws", None, structural_ac_passed=True
            )
        assert result is False

    def test_logs_debug_on_invocation(self, tmp_path, caplog):
        from bob.status_handler import handle_pending_successor_verify
        with caplog.at_level(logging.DEBUG, logger="bob.status_handler"):
            handle_pending_successor_verify(
                "feat-log-debug", tmp_path, structural_ac_passed=False
            )
        # handle_pending_successor_verify logs entry debug before delegating
        assert any("feat-log-debug" in r.message for r in caplog.records)
