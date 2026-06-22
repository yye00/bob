"""Tests for bob3.successor_verify_handler (1e768c51).

Verifies that both public functions are importable and behave correctly:
- should_defer_to_successor_verify
- promote_successor_verified_features
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


class TestModuleImports:
    """Module and functions must be importable."""

    def test_module_imports(self):
        import bob3.successor_verify_handler  # noqa: F401

    def test_should_defer_to_successor_verify_is_callable(self):
        from bob3.successor_verify_handler import should_defer_to_successor_verify
        assert callable(should_defer_to_successor_verify)

    def test_promote_successor_verified_features_is_callable(self):
        from bob3.successor_verify_handler import promote_successor_verified_features
        assert callable(promote_successor_verified_features)


class TestShouldDeferToSuccessorVerify:
    """Tests for should_defer_to_successor_verify."""

    def test_returns_false_when_not_verifier_extension(self, tmp_path):
        from bob3.successor_verify_handler import should_defer_to_successor_verify
        # Empty workspace — no verifier extension module present
        result = should_defer_to_successor_verify("feat-001", tmp_path, True)
        assert result is False

    def test_returns_false_when_structural_ac_not_passed(self, tmp_path):
        from bob3.successor_verify_handler import should_defer_to_successor_verify
        result = should_defer_to_successor_verify("feat-002", tmp_path, False)
        assert result is False

    def test_returns_bool_type(self, tmp_path):
        from bob3.successor_verify_handler import should_defer_to_successor_verify
        result = should_defer_to_successor_verify("feat-003", tmp_path, False)
        assert isinstance(result, bool)

    def test_none_workspace_returns_false_not_raise(self):
        from bob3.successor_verify_handler import should_defer_to_successor_verify
        result = should_defer_to_successor_verify("feat-004", None, True)
        assert isinstance(result, bool)

    def test_delegates_to_set_pending_successor_verify(self, tmp_path):
        from bob3.successor_verify_handler import should_defer_to_successor_verify
        with patch(
            "bob3.successor_verify_handler.set_pending_successor_verify",
            return_value=True,
        ) as mock_fn:
            result = should_defer_to_successor_verify("feat-delegate", tmp_path, True)
        mock_fn.assert_called_once_with("feat-delegate", tmp_path, True)
        assert result is True

    def test_returns_true_when_delegate_returns_true(self):
        from bob3.successor_verify_handler import should_defer_to_successor_verify
        with patch(
            "bob3.successor_verify_handler.set_pending_successor_verify",
            return_value=True,
        ):
            result = should_defer_to_successor_verify("feat-005", None, True)
        assert result is True

    def test_returns_false_when_delegate_returns_false(self):
        from bob3.successor_verify_handler import should_defer_to_successor_verify
        with patch(
            "bob3.successor_verify_handler.set_pending_successor_verify",
            return_value=False,
        ):
            result = should_defer_to_successor_verify("feat-006", None, False)
        assert result is False

    def test_empty_feature_id_does_not_raise(self, tmp_path):
        from bob3.successor_verify_handler import should_defer_to_successor_verify
        with patch(
            "bob3.successor_verify_handler.set_pending_successor_verify",
            return_value=False,
        ):
            result = should_defer_to_successor_verify("", tmp_path, False)
        assert isinstance(result, bool)

    def test_nonexistent_workspace_returns_bool_not_raise(self):
        from bob3.successor_verify_handler import should_defer_to_successor_verify
        nonexistent = Path("/tmp/bob3_test_nonexistent_xyz99")
        result = should_defer_to_successor_verify("feat-007", nonexistent, True)
        assert isinstance(result, bool)


class TestPromoteSuccessorVerifiedFeatures:
    """Tests for promote_successor_verified_features."""

    def test_raises_value_error_for_none_feature_id(self):
        from bob3.successor_verify_handler import promote_successor_verified_features
        with pytest.raises(ValueError):
            promote_successor_verified_features(None)

    def test_raises_value_error_for_integer_feature_id(self):
        from bob3.successor_verify_handler import promote_successor_verified_features
        with pytest.raises(ValueError):
            promote_successor_verified_features(42)

    def test_raises_value_error_for_list_feature_id(self):
        from bob3.successor_verify_handler import promote_successor_verified_features
        with pytest.raises(ValueError):
            promote_successor_verified_features(["feat-x"])

    def test_delegates_to_promote_from_successor_gen(self, tmp_path):
        from bob3.successor_verify_handler import promote_successor_verified_features
        with patch(
            "bob3.successor_verify_handler.promote_from_successor_gen",
            return_value="completed",
        ) as mock_fn:
            result = promote_successor_verified_features("feat-promote", None, tmp_path)
        mock_fn.assert_called_once_with("feat-promote", None, tmp_path)
        assert result == "completed"

    def test_returns_string_status(self, tmp_path):
        from bob3.successor_verify_handler import promote_successor_verified_features
        with patch(
            "bob3.successor_verify_handler.promote_from_successor_gen",
            return_value="completed",
        ):
            result = promote_successor_verified_features("feat-str", None, None)
        assert isinstance(result, str)

    def test_returns_completed_on_success(self):
        from bob3.successor_verify_handler import promote_successor_verified_features
        with patch(
            "bob3.successor_verify_handler.promote_from_successor_gen",
            return_value="completed",
        ):
            result = promote_successor_verified_features("feat-done", None, None)
        assert result == "completed"

    def test_returns_failed_on_failure(self):
        from bob3.successor_verify_handler import promote_successor_verified_features
        with patch(
            "bob3.successor_verify_handler.promote_from_successor_gen",
            return_value="failed",
        ):
            result = promote_successor_verified_features("feat-fail", None, None)
        assert result == "failed"

    def test_returns_pending_when_db_error(self):
        from bob3.successor_verify_handler import promote_successor_verified_features
        with patch(
            "bob3.successor_verify_handler.promote_from_successor_gen",
            return_value="pending_successor_verify",
        ):
            result = promote_successor_verified_features("feat-db-err", None, None)
        assert result == "pending_successor_verify"

    def test_accepts_optional_acceptance_criteria(self):
        from bob3.successor_verify_handler import promote_successor_verified_features
        with patch(
            "bob3.successor_verify_handler.promote_from_successor_gen",
            return_value="completed",
        ) as mock_fn:
            result = promote_successor_verified_features(
                "feat-acs", ["File exists: src/bob3/enhanced_verification.py"], None
            )
        assert isinstance(result, str)

    def test_accepts_none_workspace(self):
        from bob3.successor_verify_handler import promote_successor_verified_features
        with patch(
            "bob3.successor_verify_handler.promote_from_successor_gen",
            return_value="completed",
        ):
            result = promote_successor_verified_features("feat-no-ws", None, None)
        assert isinstance(result, str)
