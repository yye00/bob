"""Tests for bob3.status_pending_successor_verify (c770e876).

Covers:
- Module import and public API availability
- should_defer_to_successor_gen: decision gate logic
- promote_on_successor_verify: successor-gen reconciler entry point
- Integration: functions delegate to pending_successor_verify correctly
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestModuleImport:
    """Module and function availability."""

    def test_module_importable(self):
        import bob3.status_pending_successor_verify  # noqa: F401

    def test_should_defer_to_successor_gen_defined(self):
        from bob3.status_pending_successor_verify import should_defer_to_successor_gen
        assert callable(should_defer_to_successor_gen)

    def test_promote_on_successor_verify_defined(self):
        from bob3.status_pending_successor_verify import promote_on_successor_verify
        assert callable(promote_on_successor_verify)

    def test_pending_successor_verify_status_constant_exported(self):
        from bob3.status_pending_successor_verify import PENDING_SUCCESSOR_VERIFY_STATUS
        assert PENDING_SUCCESSOR_VERIFY_STATUS == "pending_successor_verify"

    def test_verifier_extension_modules_exported(self):
        from bob3.status_pending_successor_verify import VERIFIER_EXTENSION_MODULES
        assert isinstance(VERIFIER_EXTENSION_MODULES, (list, tuple, frozenset, set))


class TestShouldDeferToSuccessorGen:
    """Tests for should_defer_to_successor_gen."""

    def test_none_feature_id_raises_value_error(self):
        from bob3.status_pending_successor_verify import should_defer_to_successor_gen
        with pytest.raises(ValueError, match="feature_id"):
            should_defer_to_successor_gen(None, None, False)

    def test_integer_feature_id_raises_value_error(self):
        from bob3.status_pending_successor_verify import should_defer_to_successor_gen
        with pytest.raises(ValueError):
            should_defer_to_successor_gen(42, None, False)

    def test_structural_ac_false_returns_false_without_touching_db(self, tmp_path):
        from bob3.status_pending_successor_verify import should_defer_to_successor_gen
        result = should_defer_to_successor_gen("feat-x", tmp_path, structural_ac_passed=False)
        assert result is False

    def test_not_verifier_extension_returns_false(self, tmp_path):
        from bob3.status_pending_successor_verify import should_defer_to_successor_gen
        # tmp_path has no verifier-extension modules
        result = should_defer_to_successor_gen("feat-x", tmp_path, structural_ac_passed=True)
        assert result is False

    def test_verifier_extension_feature_with_structural_ac_sets_status(self, tmp_path):
        from bob3.status_pending_successor_verify import should_defer_to_successor_gen
        # Create a verifier-extension module in the workspace
        src = tmp_path / "src" / "bob3"
        src.mkdir(parents=True)
        (src / "enhanced_verification.py").write_text("# patched verifier")

        with patch("bob3.status_pending_successor_verify.set_pending_successor_verify", return_value=True) as mock_set:
            result = should_defer_to_successor_gen("feat-verifier", tmp_path, structural_ac_passed=True)

        assert result is True
        mock_set.assert_called_once_with("feat-verifier", tmp_path, True)

    def test_returns_false_when_set_pending_returns_false(self, tmp_path):
        from bob3.status_pending_successor_verify import should_defer_to_successor_gen
        src = tmp_path / "src" / "bob3"
        src.mkdir(parents=True)
        (src / "enhanced_verification.py").write_text("# verifier")

        with patch("bob3.status_pending_successor_verify.set_pending_successor_verify", return_value=False):
            result = should_defer_to_successor_gen("feat-db-fail", tmp_path, structural_ac_passed=True)

        assert result is False

    def test_none_workspace_with_structural_ac_returns_false(self):
        from bob3.status_pending_successor_verify import should_defer_to_successor_gen
        # No workspace → cannot detect verifier-extension module → False
        result = should_defer_to_successor_gen("feat-no-ws", None, structural_ac_passed=True)
        assert result is False

    def test_return_type_is_always_bool(self, tmp_path):
        from bob3.status_pending_successor_verify import should_defer_to_successor_gen
        result = should_defer_to_successor_gen("feat-type", tmp_path, structural_ac_passed=False)
        assert type(result) is bool


class TestPromoteOnSuccessorVerify:
    """Tests for promote_on_successor_verify."""

    def test_none_feature_id_raises_value_error(self):
        from bob3.status_pending_successor_verify import promote_on_successor_verify
        with pytest.raises(ValueError, match="feature_id"):
            promote_on_successor_verify(None)

    def test_integer_feature_id_raises_value_error(self):
        from bob3.status_pending_successor_verify import promote_on_successor_verify
        with pytest.raises(ValueError):
            promote_on_successor_verify(42)

    def test_delegates_to_promote_from_successor_gen(self):
        from bob3.status_pending_successor_verify import promote_on_successor_verify
        with patch(
            "bob3.status_pending_successor_verify.promote_from_successor_gen",
            return_value="completed",
        ) as mock_promote:
            result = promote_on_successor_verify("feat-ok", acceptance_criteria=None, workspace=None)

        assert result == "completed"
        mock_promote.assert_called_once_with("feat-ok", None, None)

    def test_returns_string_status(self):
        from bob3.status_pending_successor_verify import promote_on_successor_verify
        with patch(
            "bob3.status_pending_successor_verify.promote_from_successor_gen",
            return_value="failed",
        ):
            result = promote_on_successor_verify("feat-fail")

        assert isinstance(result, str)
        assert result == "failed"

    def test_workspace_passed_to_delegate(self, tmp_path):
        from bob3.status_pending_successor_verify import promote_on_successor_verify
        with patch(
            "bob3.status_pending_successor_verify.promote_from_successor_gen",
            return_value="completed",
        ) as mock_promote:
            promote_on_successor_verify("feat-ws", workspace=tmp_path)

        mock_promote.assert_called_once_with("feat-ws", None, tmp_path)

    def test_acceptance_criteria_passed_to_delegate(self):
        from bob3.status_pending_successor_verify import promote_on_successor_verify
        acs = ["File exists: src/bob3/enhanced_verification.py"]
        with patch(
            "bob3.status_pending_successor_verify.promote_from_successor_gen",
            return_value="completed",
        ) as mock_promote:
            promote_on_successor_verify("feat-ac", acceptance_criteria=acs)

        mock_promote.assert_called_once_with("feat-ac", acs, None)

    def test_db_failure_returns_pending_status(self):
        from bob3.status_pending_successor_verify import (
            PENDING_SUCCESSOR_VERIFY_STATUS,
            promote_on_successor_verify,
        )
        with patch(
            "bob3.status_pending_successor_verify.promote_from_successor_gen",
            return_value=PENDING_SUCCESSOR_VERIFY_STATUS,
        ):
            result = promote_on_successor_verify("feat-db-err")

        assert result == PENDING_SUCCESSOR_VERIFY_STATUS

    def test_empty_string_feature_id_calls_delegate(self):
        from bob3.status_pending_successor_verify import promote_on_successor_verify
        # Empty string is a valid str — should NOT raise ValueError
        with patch(
            "bob3.status_pending_successor_verify.promote_from_successor_gen",
            return_value="completed",
        ) as mock_promote:
            result = promote_on_successor_verify("")

        assert isinstance(result, str)
        mock_promote.assert_called_once()


class TestRunLoopIntegration:
    """Integration: functions are importable and wired to pending_successor_verify."""

    def test_should_defer_uses_is_verifier_extension_feature(self, tmp_path):
        from bob3.status_pending_successor_verify import should_defer_to_successor_gen
        src = tmp_path / "src" / "bob3"
        src.mkdir(parents=True)
        (src / "enhanced_verification.py").write_text("# check")

        with patch("bob3.status_pending_successor_verify.set_pending_successor_verify", return_value=True):
            with patch("bob3.status_pending_successor_verify.is_verifier_extension_feature", return_value=True) as mock_is:
                result = should_defer_to_successor_gen("feat-integration", tmp_path, structural_ac_passed=True)

        mock_is.assert_called_once_with("feat-integration", tmp_path)
        assert result is True

    def test_promote_on_successor_verify_accepts_all_keyword_args(self, tmp_path):
        from bob3.status_pending_successor_verify import promote_on_successor_verify
        with patch(
            "bob3.status_pending_successor_verify.promote_from_successor_gen",
            return_value="completed",
        ):
            result = promote_on_successor_verify(
                feature_id="feat-kwargs",
                acceptance_criteria=["File exists: src/bob3/enhanced_verification.py"],
                workspace=tmp_path,
            )
        assert result == "completed"
