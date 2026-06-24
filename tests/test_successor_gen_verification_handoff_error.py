"""Error-path tests for bob3.status_handler.handle_pending_successor_verify (f77b0d51).

Error AC: invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest


class TestErrorPaths:
    """Invalid input must raise ValueError, not silently succeed."""

    def test_none_feature_id_raises_value_error(self):
        from bob3.status_handler import handle_pending_successor_verify
        with pytest.raises(ValueError):
            handle_pending_successor_verify(None, None, False)

    def test_integer_feature_id_raises_value_error(self):
        from bob3.status_handler import handle_pending_successor_verify
        with pytest.raises(ValueError):
            handle_pending_successor_verify(42, None, False)

    def test_list_feature_id_raises_value_error(self):
        from bob3.status_handler import handle_pending_successor_verify
        with pytest.raises(ValueError):
            handle_pending_successor_verify(["feat-x"], None, False)

    def test_dict_feature_id_raises_value_error(self):
        from bob3.status_handler import handle_pending_successor_verify
        with pytest.raises(ValueError):
            handle_pending_successor_verify({"id": "feat-x"}, None, False)

    def test_float_feature_id_raises_value_error(self):
        from bob3.status_handler import handle_pending_successor_verify
        with pytest.raises(ValueError):
            handle_pending_successor_verify(3.14, None, True)

    def test_error_message_mentions_feature_id(self):
        from bob3.status_handler import handle_pending_successor_verify
        with pytest.raises(ValueError, match="feature_id"):
            handle_pending_successor_verify(None, None, False)

    def test_none_feature_id_does_not_silently_return_true(self):
        from bob3.status_handler import handle_pending_successor_verify
        raised = False
        try:
            result = handle_pending_successor_verify(None, None, True)
            # If it didn't raise, it must not have silently returned True
            assert result is not True, "Function silently returned True for None feature_id"
        except ValueError:
            raised = True
        assert raised, "Expected ValueError for None feature_id"

    def test_non_string_does_not_write_to_db(self):
        from bob3.status_handler import handle_pending_successor_verify
        from unittest.mock import patch
        with patch("bob3.pending_successor_verify.db") as mock_db:
            with pytest.raises(ValueError):
                handle_pending_successor_verify(999, None, True)
        mock_db.update_feature.assert_not_called()

    def test_true_integer_feature_id_raises_not_accepts(self):
        from bob3.status_handler import handle_pending_successor_verify
        with pytest.raises(ValueError):
            handle_pending_successor_verify(True, None, True)
