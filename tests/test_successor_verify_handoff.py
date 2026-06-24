"""Tests for bob.status_handler — successor-gen verification handoff (b89c45f9).

Acceptance criteria:
- File exists: src/bob/status_handler.py
- Function defined: bob.status_handler.should_defer_to_successor_verifier
- pytest: tests/test_successor_verify_handoff.py
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

    def test_expected_names_exported(self):
        from bob.status_handler import (
            PENDING_SUCCESSOR_VERIFY_STATUS,
            VERIFIER_EXTENSION_MODULES,
            should_defer_to_successor_verifier,
        )
        assert callable(should_defer_to_successor_verifier)
        assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
        assert PENDING_SUCCESSOR_VERIFY_STATUS == "pending_successor_verify"

    def test_all_contains_expected_names(self):
        from bob.status_handler import __all__
        assert "should_defer_to_successor_verifier" in __all__
        assert "PENDING_SUCCESSOR_VERIFY_STATUS" in __all__
        assert "VERIFIER_EXTENSION_MODULES" in __all__


# ---------------------------------------------------------------------------
# AC 2: Function defined — bob.status_handler.should_defer_to_successor_verifier
# ---------------------------------------------------------------------------


class TestFunctionDefined:
    def test_function_is_callable(self):
        from bob.status_handler import should_defer_to_successor_verifier
        assert callable(should_defer_to_successor_verifier)

    def test_function_signature_has_required_params(self):
        from bob.status_handler import should_defer_to_successor_verifier
        sig = inspect.signature(should_defer_to_successor_verifier)
        params = list(sig.parameters)
        assert "feature_id" in params
        assert "workspace" in params
        assert "structural_ac_passed" in params

    def test_function_returns_bool(self, tmp_path):
        from bob.status_handler import should_defer_to_successor_verifier
        with patch("bob.status_handler.set_pending_successor_verify", return_value=False):
            result = should_defer_to_successor_verifier("feat-001", None, False)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# should_defer_to_successor_verifier — guard conditions
# ---------------------------------------------------------------------------


class TestShouldDeferGuards:
    def test_returns_false_when_structural_ac_not_passed(self, tmp_path):
        from bob.status_handler import should_defer_to_successor_verifier
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.status_handler.set_pending_successor_verify") as mock_set:
            result = should_defer_to_successor_verifier(
                "feat-001", tmp_path, structural_ac_passed=False
            )
        assert result is False
        mock_set.assert_not_called()

    def test_returns_false_when_not_verifier_extension(self, tmp_path):
        from bob.status_handler import should_defer_to_successor_verifier
        src = tmp_path / "src"
        src.mkdir()
        (src / "regular_module.py").write_text("# not a verifier")

        with patch("bob.status_handler.set_pending_successor_verify") as mock_set:
            result = should_defer_to_successor_verifier(
                "feat-001", tmp_path, structural_ac_passed=True
            )
        assert result is False
        mock_set.assert_not_called()

    def test_returns_false_when_workspace_is_none(self):
        from bob.status_handler import should_defer_to_successor_verifier
        with patch("bob.status_handler.set_pending_successor_verify") as mock_set:
            result = should_defer_to_successor_verifier(
                "feat-001", None, structural_ac_passed=True
            )
        assert result is False
        mock_set.assert_not_called()

    def test_returns_false_when_both_conditions_fail(self, tmp_path):
        from bob.status_handler import should_defer_to_successor_verifier
        with patch("bob.status_handler.set_pending_successor_verify") as mock_set:
            result = should_defer_to_successor_verifier(
                "feat-001", None, structural_ac_passed=False
            )
        assert result is False
        mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# should_defer_to_successor_verifier — happy path
# ---------------------------------------------------------------------------


class TestShouldDeferHappyPath:
    def test_returns_true_when_both_conditions_met(self, tmp_path):
        from bob.status_handler import should_defer_to_successor_verifier
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db:
            result = should_defer_to_successor_verifier(
                "feat-abc", tmp_path, structural_ac_passed=True
            )
        assert result is True
        mock_db.update_feature.assert_called_once_with(
            "feat-abc", status="pending_successor_verify"
        )

    def test_delegates_to_set_pending_successor_verify(self, tmp_path):
        from bob.status_handler import should_defer_to_successor_verifier
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.status_handler.set_pending_successor_verify", return_value=True) as mock_set:
            result = should_defer_to_successor_verifier(
                "feat-xyz", tmp_path, structural_ac_passed=True
            )
        assert result is True
        mock_set.assert_called_once_with("feat-xyz", tmp_path, True)

    def test_works_for_verifier_module(self, tmp_path):
        from bob.status_handler import should_defer_to_successor_verifier
        verif_dir = tmp_path / "src" / "bob" / "verification"
        verif_dir.mkdir(parents=True)
        (verif_dir / "verifier.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db:
            result = should_defer_to_successor_verifier(
                "feat-verif", tmp_path, structural_ac_passed=True
            )
        assert result is True

    def test_logs_info_when_deferring(self, tmp_path, caplog):
        from bob.status_handler import should_defer_to_successor_verifier
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db"):
            with caplog.at_level(logging.INFO, logger="bob.status_handler"):
                should_defer_to_successor_verifier(
                    "feat-log", tmp_path, structural_ac_passed=True
                )
        assert any("successor-gen deferral" in r.message for r in caplog.records)

    def test_returns_false_when_set_pending_returns_false(self, tmp_path):
        from bob.status_handler import should_defer_to_successor_verifier
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.status_handler.set_pending_successor_verify", return_value=False):
            result = should_defer_to_successor_verifier(
                "feat-fail", tmp_path, structural_ac_passed=True
            )
        assert result is False


# ---------------------------------------------------------------------------
# Logging behaviour
# ---------------------------------------------------------------------------


class TestLoggingBehaviour:
    def test_logs_debug_when_no_structural_ac(self, tmp_path, caplog):
        from bob.status_handler import should_defer_to_successor_verifier
        with caplog.at_level(logging.DEBUG, logger="bob.status_handler"):
            should_defer_to_successor_verifier("feat-d1", tmp_path, structural_ac_passed=False)
        assert any("no structural AC passed" in r.message for r in caplog.records)

    def test_logs_debug_when_not_verifier_extension(self, tmp_path, caplog):
        from bob.status_handler import should_defer_to_successor_verifier
        src = tmp_path / "src"
        src.mkdir()
        with caplog.at_level(logging.DEBUG, logger="bob.status_handler"):
            should_defer_to_successor_verifier("feat-d2", tmp_path, structural_ac_passed=True)
        assert any("not a verifier-extension" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# AC 4: Integration — bob.run_loop
# ---------------------------------------------------------------------------


class TestRunLoopIntegration:
    def test_run_loop_has_set_pending_successor_verify(self):
        from bob.run_loop import set_pending_successor_verify
        assert callable(set_pending_successor_verify)

    def test_run_loop_set_pending_successor_verify_in_all(self):
        import bob.run_loop as rl
        assert "set_pending_successor_verify" in rl.__all__

    def test_run_loop_delegates_set_pending_to_pending_successor_verify(self, tmp_path):
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

    def test_orchestrator_run_loop_has_private_import(self):
        rl = importlib.import_module("bob.orchestrator.run_loop")
        assert hasattr(rl, "_set_pending_successor_verify")
        assert callable(rl._set_pending_successor_verify)

    def test_status_handler_importable_from_bob(self):
        import bob.status_handler as sh
        assert hasattr(sh, "should_defer_to_successor_verifier")

    def test_should_defer_consistent_with_set_pending(self, tmp_path):
        from bob.status_handler import should_defer_to_successor_verifier
        from bob.pending_successor_verify import set_pending_successor_verify
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db1:
            r1 = should_defer_to_successor_verifier("feat-c1", tmp_path, structural_ac_passed=True)

        with patch("bob.pending_successor_verify.db") as mock_db2:
            r2 = set_pending_successor_verify("feat-c2", tmp_path, structural_ac_passed=True)

        assert r1 == r2 == True
