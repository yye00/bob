"""Tests boundary condition: _resume_interrupted_work_periodic on empty DB.

When the project has no features at all, the function must return []
without errors and without making any DB writes.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bob3.orchestrator.run_loop import _resume_interrupted_work_periodic


class TestPeriodicResumeBoundaryEmptyDb:
    def test_empty_db_returns_empty_list(self):
        """Empty DB → returns []."""
        with patch("bob3.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.return_value = []
            result = _resume_interrupted_work_periodic("proj-empty")

        assert result == []

    def test_empty_db_no_update_calls(self):
        """Empty DB → no update_feature calls."""
        with patch("bob3.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.return_value = []
            _resume_interrupted_work_periodic("proj-empty")

        mock_db.update_feature.assert_not_called()

    def test_list_features_is_called_with_interrupted_status(self):
        """The function queries for 'interrupted' status from the DB."""
        with patch("bob3.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.return_value = []
            _resume_interrupted_work_periodic("proj-empty")

        # Should have made at least one call with status="interrupted"
        calls_with_interrupted = [
            c for c in mock_db.list_features.call_args_list
            if "interrupted" in (list(c.args) + list(c.kwargs.values()))
        ]
        assert len(calls_with_interrupted) >= 1

    def test_returns_list_type_always(self):
        """Return type is always a list, even for empty case."""
        with patch("bob3.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.return_value = []
            result = _resume_interrupted_work_periodic("proj-empty")

        assert isinstance(result, list)

    def test_does_not_raise_on_empty_db(self):
        """No exception is raised when DB is empty."""
        with patch("bob3.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.return_value = []
            try:
                _resume_interrupted_work_periodic("proj-empty")
            except Exception as exc:
                pytest.fail(f"Unexpected exception: {exc}")
