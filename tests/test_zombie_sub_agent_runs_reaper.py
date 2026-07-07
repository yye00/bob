"""Tests for bob.zombie_sub_agent_runs_reaper.reap_zombie_sub_agent_runs.

AC: pytest: tests/test_zombie_sub_agent_runs_reaper.py

The reaper closes sub_agent_runs rows with status='running' whose target feature
is already in a terminal state ('completed', 'needs_human', 'regression',
'failed'), marking them status='timeout' with a completion timestamp.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bob.zombie_sub_agent_runs_reaper import reap_zombie_sub_agent_runs


def _make_run(*, run_id="run-1", target_id="feat-1", purpose="feature_research"):
    r = MagicMock()
    r.id = run_id
    r.purpose = purpose
    r.status = "running"
    r.target_id = target_id
    return r


def _make_feature(*, feature_id="feat-1", status="completed"):
    f = MagicMock()
    f.id = feature_id
    f.status = status
    return f


class TestApiContract:
    def test_function_defined_and_callable(self):
        assert callable(reap_zombie_sub_agent_runs)

    def test_file_exists(self):
        import bob.zombie_sub_agent_runs_reaper as mod

        assert mod.__file__.endswith("zombie_sub_agent_runs_reaper.py")


class TestReaping:
    def test_zombie_run_against_terminal_feature_is_reaped(self):
        run = _make_run()
        feat = _make_feature()
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feat] if status == "completed" else []
            )
            result = reap_zombie_sub_agent_runs("proj-1")
        assert result == ["run-1"]

    def test_run_against_active_feature_not_reaped(self):
        run = _make_run()
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.return_value = []
            result = reap_zombie_sub_agent_runs("proj-active")
        assert result == []

    def test_run_marked_timeout_with_completed_at(self):
        run = _make_run()
        feat = _make_feature()
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feat] if status == "completed" else []
            )
            reap_zombie_sub_agent_runs("proj-1")
            mock_db.update_agent_run.assert_called_once()
            _, kwargs = mock_db.update_agent_run.call_args
            assert kwargs["status"] == "timeout"
            assert kwargs["completed_at"] is not None

    @pytest.mark.parametrize(
        "terminal_status", ["completed", "needs_human", "regression", "failed"]
    )
    def test_all_terminal_statuses_trigger_reap(self, terminal_status):
        run = _make_run()
        feat = _make_feature(status=terminal_status)
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feat] if status == terminal_status else []
            )
            result = reap_zombie_sub_agent_runs("proj-1")
        assert result == ["run-1"]

    def test_null_target_id_skipped(self):
        run = _make_run(target_id=None)
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.return_value = []
            result = reap_zombie_sub_agent_runs("proj-1")
        assert result == []

    def test_returns_list_type(self):
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            mock_db.list_features.return_value = []
            result = reap_zombie_sub_agent_runs("proj-1")
        assert isinstance(result, list)


class TestInvalidInput:
    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="project_id"):
            reap_zombie_sub_agent_runs(None)

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_sub_agent_runs("")

    def test_whitespace_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_sub_agent_runs("   ")
