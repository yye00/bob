"""Tests for bob.zombie_subagent_reaper.reap_zombie_subagent_runs.

AC:
  - File exists: src/bob/zombie_subagent_reaper.py
  - Function defined: bob.zombie_subagent_reaper.reap_zombie_subagent_runs
  - integration: bob.db

The reaper joins sub_agent_runs (status='running') against features and marks
any row whose target feature is in a terminal state as status='timeout' with a
completion timestamp.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from bob.zombie_subagent_reaper import reap_zombie_subagent_runs


def _make_run(*, run_id="run-0001", target_id="feat-0001", purpose="feature_research"):
    r = MagicMock()
    r.id = run_id
    r.purpose = purpose
    r.status = "running"
    r.target_id = target_id
    return r


def _make_feature(*, feature_id="feat-0001", status="completed"):
    f = MagicMock()
    f.id = feature_id
    f.status = status
    return f


class TestFunctionContract:
    def test_function_is_defined_and_callable(self):
        """AC: Function defined: bob.zombie_subagent_reaper.reap_zombie_subagent_runs."""
        assert callable(reap_zombie_subagent_runs)

    def test_integration_bob_db_importable(self):
        """AC: integration: bob.db — the module joins runs against features via db."""
        import bob.db as db

        assert hasattr(db, "query_agent_runs")
        assert hasattr(db, "list_features")
        assert hasattr(db, "update_agent_run")


class TestHappyPath:
    def test_single_zombie_run_reaped(self):
        run = _make_run()
        feature = _make_feature()
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == "completed" else []
            )
            mock_db.update_agent_run.return_value = None
            result = reap_zombie_subagent_runs("proj-1")

        assert result == ["run-0001"]

    def test_run_marked_timeout_with_completion_timestamp(self):
        run = _make_run()
        feature = _make_feature()
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == "completed" else []
            )
            reap_zombie_subagent_runs("proj-1")

        mock_db.update_agent_run.assert_called_once()
        args, kwargs = mock_db.update_agent_run.call_args
        assert args[0] == "run-0001"
        assert kwargs["status"] == "timeout"
        assert isinstance(kwargs["completed_at"], datetime)

    @pytest.mark.parametrize("terminal", ["completed", "needs_human", "regression", "failed"])
    def test_all_terminal_states_trigger_reap(self, terminal):
        run = _make_run()
        feature = _make_feature(status=terminal)
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == terminal else []
            )
            result = reap_zombie_subagent_runs("proj-1")

        assert result == ["run-0001"]


class TestNonReapCases:
    def test_running_against_active_feature_not_reaped(self):
        run = _make_run()
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.return_value = []  # no terminal features
            result = reap_zombie_subagent_runs("proj-1")

        assert result == []
        mock_db.update_agent_run.assert_not_called()

    def test_null_target_id_skipped(self):
        run = _make_run(target_id=None)
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.return_value = []
            result = reap_zombie_subagent_runs("proj-1")

        assert result == []

    def test_no_running_rows_returns_empty(self):
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            mock_db.list_features.return_value = []
            result = reap_zombie_subagent_runs("proj-1")

        assert result == []


class TestErrorPath:
    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="project_id"):
            reap_zombie_subagent_runs(None)

    def test_empty_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_subagent_runs("")

    def test_whitespace_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_subagent_runs("   ")

    def test_non_string_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_subagent_runs(123)
