"""Tests for bob3.zombie_subruns_reaper.reap_zombie_subruns.

AC: File exists: src/bob3/zombie_subruns_reaper.py
AC: Function defined: bob3.zombie_subruns_reaper.reap_zombie_subruns
AC: pytest: tests/test_zombie_subruns_reaper.py
AC: integration: bob3.orchestrator
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bob3.zombie_subruns_reaper import reap_zombie_subruns


class TestImport:
    """The module and function must be importable at the canonical path."""

    def test_module_importable(self):
        import bob3.zombie_subruns_reaper  # noqa: F401

    def test_function_defined_and_callable(self):
        assert callable(reap_zombie_subruns)

    def test_function_name_matches_ac(self):
        assert reap_zombie_subruns.__name__ == "reap_zombie_subruns"


class TestValidation:
    """Invalid project_id must raise ValueError immediately."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_subruns(None)

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_subruns("")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_subruns("   ")

    def test_tab_only_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_subruns("\t")

    def test_error_message_contains_project_id(self):
        with pytest.raises(ValueError, match="project_id"):
            reap_zombie_subruns(None)


class TestReaping:
    """Reaping logic: zombies are identified and closed as 'timeout'."""

    def _make_run(self, *, run_id="run-abc1", target_id="feat-abc1"):
        r = MagicMock()
        r.id = run_id
        r.purpose = "feature_research"
        r.target_id = target_id
        return r

    def _make_feature(self, *, feature_id="feat-abc1", status="completed"):
        f = MagicMock()
        f.id = feature_id
        f.status = status
        return f

    def test_no_running_rows_returns_empty_list(self):
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            mock_db.list_features.return_value = []
            result = reap_zombie_subruns("proj-1234")
        assert result == []

    def test_zombie_run_is_reaped(self):
        run = self._make_run()
        feature = self._make_feature()
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == "completed" else []
            )
            mock_db.update_agent_run.return_value = None
            result = reap_zombie_subruns("proj-1234")
        assert result == ["run-abc1"]

    def test_run_targeting_active_feature_not_reaped(self):
        run = self._make_run()
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.return_value = []
            result = reap_zombie_subruns("proj-active")
        assert result == []

    def test_run_with_null_target_id_not_reaped(self):
        run = self._make_run(target_id=None)
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.return_value = []
            result = reap_zombie_subruns("proj-null-target")
        assert result == []

    def test_all_terminal_statuses_trigger_reap(self):
        for terminal_status in ("completed", "needs_human", "regression", "failed"):
            run = self._make_run(run_id=f"run-{terminal_status}", target_id=f"feat-{terminal_status}")
            feature = self._make_feature(feature_id=f"feat-{terminal_status}", status=terminal_status)
            with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
                mock_db.query_agent_runs.return_value = [run]
                mock_db.list_features.side_effect = lambda project_id, status, _s=terminal_status: (
                    [feature] if status == _s else []
                )
                mock_db.update_agent_run.return_value = None
                result = reap_zombie_subruns("proj-terminal")
            assert f"run-{terminal_status}" in result, f"Expected run with status={terminal_status} to be reaped"

    def test_return_type_is_list(self):
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = []
            mock_db.list_features.return_value = []
            result = reap_zombie_subruns("proj-type-check")
        assert isinstance(result, list)

    def test_multiple_zombies_all_reaped(self):
        runs = [
            self._make_run(run_id="run-001", target_id="feat-001"),
            self._make_run(run_id="run-002", target_id="feat-002"),
        ]
        features = [
            self._make_feature(feature_id="feat-001"),
            self._make_feature(feature_id="feat-002"),
        ]
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = runs
            mock_db.list_features.side_effect = lambda project_id, status: (
                features if status == "completed" else []
            )
            mock_db.update_agent_run.return_value = None
            result = reap_zombie_subruns("proj-multi")
        assert sorted(result) == ["run-001", "run-002"]


class TestOrchestratorIntegration:
    """The module integrates with bob3.orchestrator via zombie_run_reaper."""

    def test_scan_and_reap_is_callable_from_orchestrator(self):
        from bob3.orchestrator.zombie_run_reaper import scan_and_reap
        assert callable(scan_and_reap)

    def test_find_zombie_runs_is_callable_from_orchestrator(self):
        from bob3.orchestrator.zombie_run_reaper import find_zombie_runs
        assert callable(find_zombie_runs)

    def test_reap_zombie_run_is_callable_from_orchestrator(self):
        from bob3.orchestrator.zombie_run_reaper import reap_zombie_run
        assert callable(reap_zombie_run)

    def test_reap_zombie_subruns_delegates_to_scan_and_reap(self):
        with patch("bob3.zombie_subruns_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = ["run-xyz"]
            result = reap_zombie_subruns("proj-delegate")
        mock_sar.assert_called_once_with("proj-delegate")
        assert result == ["run-xyz"]
