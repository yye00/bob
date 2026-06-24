"""Tests for successor-gen verification handoff in bob.run_loop (3682d2e7).

Acceptance criteria:
- File exists: src/bob/enhanced_verification.py
- Function defined: bob.run_loop.handle_pending_successor_verify
- pytest: tests/test_successor_verification_handoff.py
- integration: bob.run_loop
"""

from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# AC 1: File exists — src/bob/enhanced_verification.py
# ---------------------------------------------------------------------------


class TestFileExists:
    def test_enhanced_verification_file_exists(self):
        import bob.enhanced_verification

        module_file = Path(bob.enhanced_verification.__file__)
        assert module_file.exists()
        assert module_file.name == "enhanced_verification.py"

    def test_enhanced_verification_importable(self):
        import bob.enhanced_verification  # noqa: F401

    def test_enhanced_verification_is_python_file(self):
        import bob.enhanced_verification

        module_file = Path(bob.enhanced_verification.__file__)
        assert module_file.suffix == ".py"


# ---------------------------------------------------------------------------
# AC 2: Function defined — bob.run_loop.handle_pending_successor_verify
# ---------------------------------------------------------------------------


class TestFunctionDefined:
    def test_function_exists_in_run_loop(self):
        from bob.run_loop import handle_pending_successor_verify
        assert callable(handle_pending_successor_verify)

    def test_function_in_run_loop_all(self):
        import bob.run_loop as rl
        assert "handle_pending_successor_verify" in rl.__all__

    def test_function_has_required_parameters(self):
        from bob.run_loop import handle_pending_successor_verify
        sig = inspect.signature(handle_pending_successor_verify)
        params = list(sig.parameters)
        assert "feature_id" in params
        assert "workspace" in params
        assert "structural_ac_passed" in params

    def test_function_returns_bool_when_structural_ac_false(self):
        from bob.run_loop import handle_pending_successor_verify
        result = handle_pending_successor_verify("feat-001", None, False)
        assert isinstance(result, bool)
        assert result is False

    def test_function_returns_false_for_empty_workspace(self, tmp_path):
        from bob.run_loop import handle_pending_successor_verify
        result = handle_pending_successor_verify("feat-001", tmp_path, True)
        assert isinstance(result, bool)
        assert result is False

    def test_function_returns_false_for_none_workspace(self):
        from bob.run_loop import handle_pending_successor_verify
        result = handle_pending_successor_verify("feat-002", None, True)
        assert isinstance(result, bool)
        assert result is False


# ---------------------------------------------------------------------------
# handle_pending_successor_verify — guard conditions
# ---------------------------------------------------------------------------


class TestGuardConditions:
    def test_structural_ac_false_prevents_status_update(self, tmp_path):
        """structural_ac_passed=False must short-circuit before any DB call."""
        from bob.run_loop import handle_pending_successor_verify

        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db:
            result = handle_pending_successor_verify("feat-003", tmp_path, False)

        assert result is False
        mock_db.update_feature.assert_not_called()

    def test_workspace_without_verifier_module_returns_false(self, tmp_path):
        """Workspace with no verifier-extension module must return False."""
        from bob.run_loop import handle_pending_successor_verify

        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "something_else.py").write_text("# unrelated")

        with patch("bob.pending_successor_verify.db") as mock_db:
            result = handle_pending_successor_verify("feat-004", tmp_path, True)

        assert result is False
        mock_db.update_feature.assert_not_called()

    def test_workspace_with_verifier_module_and_structural_ac_sets_status(self, tmp_path):
        """Feature with verifier-extension module and structural AC passed must set status."""
        from bob.run_loop import handle_pending_successor_verify

        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db:
            result = handle_pending_successor_verify("feat-005", tmp_path, True)

        assert result is True
        mock_db.update_feature.assert_called_once_with(
            "feat-005", status="pending_successor_verify"
        )

    def test_none_workspace_returns_false_not_raise(self):
        """None workspace must return False, not raise any exception."""
        from bob.run_loop import handle_pending_successor_verify
        result = handle_pending_successor_verify("feat-006", None, True)
        assert result is False

    def test_return_type_is_always_bool(self, tmp_path):
        from bob.run_loop import handle_pending_successor_verify
        result = handle_pending_successor_verify("feat-007", tmp_path, False)
        assert type(result) is bool


# ---------------------------------------------------------------------------
# AC 4: Integration — bob.run_loop
# ---------------------------------------------------------------------------


class TestRunLoopIntegration:
    def test_run_loop_has_handle_pending_successor_verify(self):
        from bob.run_loop import handle_pending_successor_verify
        assert callable(handle_pending_successor_verify)

    def test_run_loop_has_set_pending_successor_verify(self):
        from bob.run_loop import set_pending_successor_verify
        assert callable(set_pending_successor_verify)

    def test_handle_pending_delegates_to_status_handlers(self):
        """handle_pending_successor_verify delegates to bob.status_handlers."""
        from bob.run_loop import handle_pending_successor_verify
        with patch("bob.status_handlers.handle_pending_successor_verify") as mock_handler:
            mock_handler.return_value = False
            handle_pending_successor_verify("feat-int-1", None, False)
        mock_handler.assert_called_once_with("feat-int-1", None, False)

    def test_set_pending_delegates_to_pending_successor_verify(self, tmp_path):
        """set_pending_successor_verify delegates to bob.pending_successor_verify."""
        from bob.run_loop import set_pending_successor_verify

        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db:
            result = set_pending_successor_verify("feat-rl", tmp_path, structural_ac_passed=True)
        assert result is True
        mock_db.update_feature.assert_called_once_with(
            "feat-rl", status="pending_successor_verify"
        )

    def test_handle_and_set_consistent_for_valid_verifier_workspace(self, tmp_path):
        """handle_pending_successor_verify and set_pending_successor_verify agree."""
        from bob.run_loop import handle_pending_successor_verify, set_pending_successor_verify

        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db1:
            mock_db1.update_feature.return_value = None
            r1 = handle_pending_successor_verify("feat-a", tmp_path, structural_ac_passed=True)

        tmp_path2 = tmp_path.parent / "ws2"
        src2 = tmp_path2 / "src" / "bob"
        src2.mkdir(parents=True)
        (src2 / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db2:
            mock_db2.update_feature.return_value = None
            r2 = set_pending_successor_verify("feat-b", tmp_path2, structural_ac_passed=True)

        assert r1 == r2 == True

    def test_orchestrator_run_loop_has_private_import(self):
        rl = importlib.import_module("bob.orchestrator.run_loop")
        assert hasattr(rl, "_set_pending_successor_verify")
        assert callable(rl._set_pending_successor_verify)

    def test_status_handlers_has_handle_pending_successor_verify(self):
        import bob.status_handlers as sh
        assert hasattr(sh, "handle_pending_successor_verify")
        assert callable(sh.handle_pending_successor_verify)

    def test_pending_successor_verify_status_constant(self):
        from bob.run_loop import set_pending_successor_verify
        from bob.pending_successor_verify import PENDING_SUCCESSOR_VERIFY_STATUS
        assert PENDING_SUCCESSOR_VERIFY_STATUS == "pending_successor_verify"
