"""Tests that _resume_interrupted_work_periodic is a no-op when no interrupted rows exist.

When everything is either 'ready', 'executing', 'completed', or 'failed',
the periodic scan must not modify any feature and must return an empty list.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bob.orchestrator.run_loop import _resume_interrupted_work_periodic


class TestPeriodicResumeNoOpWhenNoInterrupted:
    def test_returns_empty_list_when_no_interrupted_features(self):
        """No interrupted rows → returns []."""
        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.return_value = []
            result = _resume_interrupted_work_periodic("proj-1")

        assert result == []

    def test_no_db_writes_when_no_interrupted_features(self):
        """No interrupted rows → update_feature must never be called."""
        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.return_value = []
            _resume_interrupted_work_periodic("proj-1")

        mock_db.update_feature.assert_not_called()

    def test_ready_features_are_ignored(self):
        """Features already in 'ready' status are not touched."""
        ready_feat = MagicMock()
        ready_feat.id = "rdy00001-0000-0000-0000-000000000001"
        ready_feat.status = "ready"

        with patch("bob.orchestrator.run_loop.db") as mock_db:
            # list_features for "interrupted" returns empty; "ready" is not queried here
            mock_db.list_features.side_effect = lambda project_id, status: (
                [] if status == "interrupted" else [ready_feat]
            )
            result = _resume_interrupted_work_periodic("proj-1")

        assert result == []
        mock_db.update_feature.assert_not_called()

    def test_completed_features_are_ignored(self):
        """Features in 'completed' status are not touched."""
        completed_feat = MagicMock()
        completed_feat.id = "comp0001-0000-0000-0000-000000000001"
        completed_feat.status = "completed"

        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = lambda project_id, status: (
                [] if status == "interrupted" else [completed_feat]
            )
            result = _resume_interrupted_work_periodic("proj-1")

        assert result == []
        mock_db.update_feature.assert_not_called()

    def test_failed_features_are_ignored(self):
        """Features in 'failed' status are not touched."""
        failed_feat = MagicMock()
        failed_feat.id = "fail0001-0000-0000-0000-000000000001"
        failed_feat.status = "failed"

        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = lambda project_id, status: (
                [] if status == "interrupted" else [failed_feat]
            )
            result = _resume_interrupted_work_periodic("proj-1")

        assert result == []
        mock_db.update_feature.assert_not_called()
