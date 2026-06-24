"""Tests the boundary case where there are no 'running' sub_agent_run rows.

scan_and_reap and find_zombie_runs must return empty results gracefully
without hitting the database for feature status lookups."""

from __future__ import annotations

from unittest.mock import patch

from bob3.orchestrator.zombie_run_reaper import find_zombie_runs, scan_and_reap


class TestZombieReaperBoundaryNoRunningRows:
    def test_find_zombie_runs_returns_empty_when_no_running_rows(self):
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            zombies = find_zombie_runs("proj-1")
        assert zombies == []

    def test_list_features_not_called_when_no_running_rows(self):
        """If there are no running rows, we skip the feature lookup entirely."""
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            find_zombie_runs("proj-1")
            mock_db.list_features.assert_not_called()

    def test_scan_and_reap_returns_empty_list_when_no_running_rows(self):
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            result = scan_and_reap("proj-1")
        assert result == []

    def test_scan_and_reap_does_not_call_update_when_nothing_to_reap(self):
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            scan_and_reap("proj-1")
            mock_db.update_agent_run.assert_not_called()

    def test_find_zombie_runs_project_id_passed_to_query_agent_runs(self):
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            find_zombie_runs("my-project-uuid")
            mock_db.query_agent_runs.assert_called_once_with(
                project_id="my-project-uuid", status="running"
            )
