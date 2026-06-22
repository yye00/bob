"""Boundary tests for bob3.zombie_reaper.reap_zombie_runs.

AC: pytest: tests/test_zombie_sub_agent_runs_reaper_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bob3.zombie_reaper import reap_zombie_runs


class TestBoundaryEmptyProject:
    """Zero running rows — function must return an empty list, not raise."""

    def test_empty_project_returns_empty_list(self):
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_runs("proj-empty")
        assert result == []

    def test_project_with_no_sub_agent_runs_at_all(self):
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            mock_db.list_features.return_value = []
            from bob3.orchestrator.zombie_run_reaper import scan_and_reap

            result = scan_and_reap("proj-no-runs")
        assert result == []
        assert isinstance(result, list)

    def test_no_running_rows_returns_empty_list(self):
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            mock_db.list_features.return_value = []
            from bob3.orchestrator.zombie_run_reaper import find_zombie_runs

            zombies = find_zombie_runs("proj-no-running")
        assert zombies == []

    def test_only_non_running_rows_are_ignored(self):
        from unittest.mock import MagicMock

        non_running = MagicMock()
        non_running.id = "run-completed"
        non_running.status = "completed"
        non_running.target_id = "feat-001"

        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            # query_agent_runs(status='running') returns nothing
            mock_db.query_agent_runs.return_value = []
            mock_db.list_features.return_value = []
            from bob3.orchestrator.zombie_run_reaper import scan_and_reap

            result = scan_and_reap("proj-x")
        assert result == []


class TestBoundaryMinimumInput:
    """Minimum valid input: one run, one feature — function must behave correctly."""

    def _make_run(self, *, run_id="run-0001", target_id="feat-0001", status="running"):
        from unittest.mock import MagicMock

        r = MagicMock()
        r.id = run_id
        r.purpose = "feature_research"
        r.status = status
        r.target_id = target_id
        return r

    def _make_feature(self, *, feature_id="feat-0001", status="completed"):
        from unittest.mock import MagicMock

        f = MagicMock()
        f.id = feature_id
        f.status = status
        return f

    def test_single_zombie_run_is_reaped(self):
        run = self._make_run()
        feature = self._make_feature()
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == "completed" else []
            )
            mock_db.update_agent_run.return_value = None
            from bob3.orchestrator.zombie_run_reaper import scan_and_reap

            result = scan_and_reap("proj-single")
        assert result == ["run-0001"]

    def test_single_run_with_null_target_id_returns_empty(self):
        run = self._make_run(target_id=None)
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.return_value = []
            from bob3.orchestrator.zombie_run_reaper import scan_and_reap

            result = scan_and_reap("proj-null-target")
        assert result == []

    def test_running_row_against_active_feature_returns_empty(self):
        run = self._make_run()
        # No terminal features — active/executing features don't match
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.return_value = []
            from bob3.orchestrator.zombie_run_reaper import scan_and_reap

            result = scan_and_reap("proj-active")
        assert result == []

    def test_return_type_is_always_list(self):
        """Even when nothing is reaped, the return type must be list."""
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_runs("proj-type-check")
        assert isinstance(result, list)

    def test_reap_zombie_runs_function_defined_and_callable(self):
        """AC: Function defined: bob3.zombie_reaper.reap_zombie_runs."""
        from bob3.zombie_reaper import reap_zombie_runs as fn

        assert callable(fn)

    def test_minimum_project_id_single_char(self):
        """Single-character project_id is accepted (minimum non-empty string)."""
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_runs("x")
        assert result == []
