"""Tests that find_zombie_runs returns 'running' sub_agent_run rows whose target
feature has already reached a terminal state ('completed' in this case)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from bob3.orchestrator.zombie_run_reaper import find_zombie_runs


def _make_run(
    *,
    run_id: str = "run00001-0000-0000-0000-000000000001",
    purpose: str = "feature_research",
    status: str = "running",
    target_id: str | None = "feat0001-0000-0000-0000-000000000001",
) -> MagicMock:
    r = MagicMock()
    r.id = run_id
    r.purpose = purpose
    r.status = status
    r.target_id = target_id
    return r


def _make_feature(
    *,
    feature_id: str = "feat0001-0000-0000-0000-000000000001",
    status: str = "completed",
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.status = status
    return f


class TestFindZombieRunsFeatureCompleted:
    def test_running_run_with_completed_target_is_zombie(self):
        run = _make_run(target_id="feat0001-0000-0000-0000-000000000001")
        feature = _make_feature(
            feature_id="feat0001-0000-0000-0000-000000000001",
            status="completed",
        )
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == "completed" else []
            )
            zombies = find_zombie_runs("proj-1")
        assert len(zombies) == 1
        assert zombies[0].id == run.id

    def test_running_run_with_failed_target_is_zombie(self):
        run = _make_run(target_id="feat0002-0000-0000-0000-000000000001")
        feature = _make_feature(
            feature_id="feat0002-0000-0000-0000-000000000001",
            status="failed",
        )
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == "failed" else []
            )
            zombies = find_zombie_runs("proj-1")
        assert len(zombies) == 1
        assert zombies[0].id == run.id

    def test_running_run_with_needs_human_target_is_zombie(self):
        run = _make_run(target_id="feat0003-0000-0000-0000-000000000001")
        feature = _make_feature(
            feature_id="feat0003-0000-0000-0000-000000000001",
            status="needs_human",
        )
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == "needs_human" else []
            )
            zombies = find_zombie_runs("proj-1")
        assert len(zombies) == 1

    def test_running_run_with_regression_target_is_zombie(self):
        run = _make_run(target_id="feat0004-0000-0000-0000-000000000001")
        feature = _make_feature(
            feature_id="feat0004-0000-0000-0000-000000000001",
            status="regression",
        )
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == "regression" else []
            )
            zombies = find_zombie_runs("proj-1")
        assert len(zombies) == 1

    def test_query_agent_runs_called_with_running_status(self):
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            find_zombie_runs("proj-abc")
            mock_db.query_agent_runs.assert_called_once_with(
                project_id="proj-abc", status="running"
            )
