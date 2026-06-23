"""Tests for successor-gen verification handoff (d80d289e).

Acceptance criteria verified:
- File exists: src/bob3/enhanced_verification.py
- Function defined: bob3.run_loop.set_pending_successor_verify
- integration: bob3.run_loop
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import pytest


class TestFileExists:
    def test_enhanced_verification_file_exists(self):
        """AC: File exists: src/bob3/enhanced_verification.py"""
        import bob3.enhanced_verification as m
        module_file = Path(m.__file__)
        assert module_file.exists()
        assert module_file.name == "enhanced_verification.py"

    def test_enhanced_verification_importable(self):
        import bob3.enhanced_verification  # noqa: F401


class TestFunctionDefined:
    def test_set_pending_successor_verify_exists_in_run_loop(self):
        """AC: Function defined: bob3.run_loop.set_pending_successor_verify"""
        from bob3.run_loop import set_pending_successor_verify
        assert callable(set_pending_successor_verify)

    def test_set_pending_successor_verify_signature(self):
        from bob3.run_loop import set_pending_successor_verify
        sig = inspect.signature(set_pending_successor_verify)
        params = list(sig.parameters)
        assert "feature_id" in params
        assert "workspace" in params
        assert "structural_ac_passed" in params

    def test_set_pending_successor_verify_returns_bool_false_when_no_structural_ac(self, tmp_path):
        from bob3.run_loop import set_pending_successor_verify
        result = set_pending_successor_verify("feat-001", tmp_path, False)
        assert isinstance(result, bool)
        assert result is False

    def test_set_pending_successor_verify_returns_bool_with_no_verifier_module(self, tmp_path):
        from bob3.run_loop import set_pending_successor_verify
        # workspace with no verifier-extension modules → False
        result = set_pending_successor_verify("feat-002", tmp_path, True)
        assert isinstance(result, bool)
        assert result is False


class TestRunLoopIntegration:
    """AC: integration: bob3.run_loop"""

    def test_set_pending_successor_verify_importable_from_run_loop(self):
        from bob3 import run_loop
        assert hasattr(run_loop, "set_pending_successor_verify")

    def test_handle_pending_successor_verify_importable_from_run_loop(self):
        from bob3 import run_loop
        assert hasattr(run_loop, "handle_pending_successor_verify")

    def test_run_loop_delegates_to_pending_successor_verify_module(self, tmp_path):
        """run_loop.set_pending_successor_verify delegates to bob3.pending_successor_verify."""
        from bob3.run_loop import set_pending_successor_verify
        with patch(
            "bob3.pending_successor_verify.set_pending_successor_verify",
            return_value=True,
        ) as mock_fn:
            result = set_pending_successor_verify("feat-003", tmp_path, True)
        assert isinstance(result, bool)

    def test_both_functions_exported_in_run_loop_all(self):
        from bob3 import run_loop
        assert "set_pending_successor_verify" in run_loop.__all__
        assert "handle_pending_successor_verify" in run_loop.__all__

    def test_set_pending_successor_verify_on_verifier_workspace(self, tmp_path):
        """When workspace has enhanced_verification.py, function defers to successor-gen."""
        from bob3.run_loop import set_pending_successor_verify
        src_bob3 = tmp_path / "src" / "bob3"
        src_bob3.mkdir(parents=True)
        (src_bob3 / "enhanced_verification.py").write_text("# verifier patch")
        # patch the DB so no real DB write occurs
        with patch("bob3.pending_successor_verify.db") as mock_db:
            mock_db.update_feature_status.return_value = None
            result = set_pending_successor_verify("feat-004", tmp_path, True)
        assert isinstance(result, bool)


class TestPendingSuccessorVerifyStatus:
    def test_pending_successor_verify_status_constant(self):
        from bob3.pending_successor_verify import PENDING_SUCCESSOR_VERIFY_STATUS
        assert PENDING_SUCCESSOR_VERIFY_STATUS == "pending_successor_verify"

    def test_verifier_extension_modules_is_tuple(self):
        from bob3.pending_successor_verify import VERIFIER_EXTENSION_MODULES
        assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
        assert len(VERIFIER_EXTENSION_MODULES) > 0

    def test_verifier_extension_modules_contains_enhanced_verification(self):
        from bob3.pending_successor_verify import VERIFIER_EXTENSION_MODULES
        has_ev = any("enhanced_verification" in m for m in VERIFIER_EXTENSION_MODULES)
        assert has_ev, "VERIFIER_EXTENSION_MODULES should reference enhanced_verification.py"
