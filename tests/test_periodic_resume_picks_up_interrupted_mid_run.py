"""Tests that _resume_interrupted_work_periodic picks up 'interrupted' features mid-run.

This covers the core scenario: a feature is cancelled mid-run (max_turns hit,
async timeout, etc.) and marked 'interrupted'. The periodic scan should
detect it and promote it back to 'ready' so the orchestrator loop picks it up
without needing a restart.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from bob3.orchestrator.run_loop import _resume_interrupted_work_periodic


def _feature(
    *,
    feature_id: str = "feat0001-0000-0000-0000-000000000001",
    name: str = "interrupted feature",
    status: str = "interrupted",
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = status
    return f


class TestPeriodicResumePicksUpInterrupted:
    def test_interrupted_feature_is_promoted_to_ready(self):
        """A single 'interrupted' feature must be reset to 'ready'."""
        feat = _feature()
        with patch("bob3.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feat] if status == "interrupted" else []
            )
            promoted = _resume_interrupted_work_periodic("proj-1")

        assert promoted == [feat.id]
        mock_db.update_feature.assert_called_once_with(feat.id, status="ready")

    def test_multiple_interrupted_features_all_promoted(self):
        """All interrupted features are reset to 'ready'."""
        feats = [
            _feature(feature_id=f"feat{i:04d}-0000-0000-0000-000000000001", name=f"feat-{i}")
            for i in range(3)
        ]
        with patch("bob3.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = lambda project_id, status: (
                feats if status == "interrupted" else []
            )
            promoted = _resume_interrupted_work_periodic("proj-1")

        assert len(promoted) == 3
        assert set(promoted) == {f.id for f in feats}
        assert mock_db.update_feature.call_count == 3

    def test_return_value_contains_promoted_feature_ids(self):
        """Return value is a list of the promoted feature IDs."""
        feat = _feature(feature_id="aabbccdd-0000-0000-0000-000000000001")
        with patch("bob3.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feat] if status == "interrupted" else []
            )
            promoted = _resume_interrupted_work_periodic("proj-x")

        assert promoted == ["aabbccdd-0000-0000-0000-000000000001"]

    def test_correct_project_id_passed_to_db(self):
        """The function queries only the given project_id."""
        with patch("bob3.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.return_value = []
            _resume_interrupted_work_periodic("my-project-99")

        for c in mock_db.list_features.call_args_list:
            args, kwargs = c
            project_passed = args[0] if args else kwargs.get("project_id")
            assert project_passed == "my-project-99"

    def test_status_set_to_ready_not_pending(self):
        """Promoted features are set to 'ready', not 'pending'."""
        feat = _feature()
        with patch("bob3.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feat] if status == "interrupted" else []
            )
            _resume_interrupted_work_periodic("proj-1")

        call_args = mock_db.update_feature.call_args
        assert call_args[1].get("status") == "ready" or call_args[0][1] == "ready"
