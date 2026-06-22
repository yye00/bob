"""Tests for bob3.zombie_subagentruns_reaper.reap_zombie_subagentruns.

AC: pytest: tests/test_zombie_subagentruns_reaper.py
    Function defined: bob3.zombie_subagentruns_reaper.reap_zombie_subagentruns
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bob3.zombie_subagentruns_reaper import reap_zombie_subagentruns


class TestReapZombieSubagentrunsImport:
    """The module and function must be importable at the canonical path."""

    def test_module_importable(self):
        import bob3.zombie_subagentruns_reaper  # noqa: F401

    def test_function_defined_and_callable(self):
        assert callable(reap_zombie_subagentruns)

    def test_function_name_matches_ac(self):
        assert reap_zombie_subagentruns.__name__ == "reap_zombie_subagentruns"


class TestReapZombieSubagentrunsValidation:
    """Invalid project_id must raise ValueError immediately."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_subagentruns(None)

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_subagentruns("")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_subagentruns("   ")

    def test_tab_only_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_zombie_subagentruns("\t")

    def test_error_message_contains_project_id(self):
        with pytest.raises(ValueError, match="project_id"):
            reap_zombie_subagentruns(None)


class TestReapZombieSubagentrunsHappyPath:
    """Valid project_id delegates to scan_and_reap; returns list of reaped IDs."""

    def test_no_zombies_returns_empty_list(self):
        with patch(
            "bob3.zombie_subagentruns_reaper.scan_and_reap", return_value=[]
        ) as mock:
            result = reap_zombie_subagentruns("proj-abc")
        mock.assert_called_once_with("proj-abc")
        assert result == []

    def test_returns_reaped_ids(self):
        with patch(
            "bob3.zombie_subagentruns_reaper.scan_and_reap",
            return_value=["run-001", "run-002"],
        ) as mock:
            result = reap_zombie_subagentruns("proj-xyz")
        assert result == ["run-001", "run-002"]

    def test_return_type_is_list(self):
        with patch(
            "bob3.zombie_subagentruns_reaper.scan_and_reap", return_value=[]
        ):
            result = reap_zombie_subagentruns("proj-type")
        assert isinstance(result, list)

    def test_minimum_project_id_single_char_accepted(self):
        with patch(
            "bob3.zombie_subagentruns_reaper.scan_and_reap", return_value=[]
        ) as mock:
            result = reap_zombie_subagentruns("x")
        mock.assert_called_once_with("x")
        assert result == []

    def test_delegates_to_scan_and_reap(self):
        """reap_zombie_subagentruns must call scan_and_reap with the project_id."""
        with patch(
            "bob3.zombie_subagentruns_reaper.scan_and_reap",
            return_value=["run-a"],
        ) as mock:
            reap_zombie_subagentruns("my-project")
        mock.assert_called_once_with("my-project")


class TestReapZombieSubagentrunsIntegrationOrchestrator:
    """Integration: bob3.orchestrator already imports from zombie_run_reaper.

    Verify the chain: zombie_subagentruns_reaper -> orchestrator.zombie_run_reaper
    -> scan_and_reap -> db is intact end-to-end (with db mocked).
    """

    def _make_run(self, run_id: str, target_id: str | None = "feat-001"):
        r = MagicMock()
        r.id = run_id
        r.purpose = "feature_research"
        r.status = "running"
        r.target_id = target_id
        return r

    def _make_feature(self, feature_id: str, status: str = "completed"):
        f = MagicMock()
        f.id = feature_id
        f.status = status
        return f

    def test_end_to_end_with_db_mocked(self):
        """Running -> terminal-feature join produces reaped IDs."""
        run = self._make_run("run-zombie-01", target_id="feat-terminal")
        feat = self._make_feature("feat-terminal", status="completed")

        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = (
                lambda project_id, status: [feat] if status == "completed" else []
            )
            mock_db.update_agent_run.return_value = None

            result = reap_zombie_subagentruns("proj-e2e")

        assert result == ["run-zombie-01"]
        mock_db.update_agent_run.assert_called_once()
        call_kwargs = mock_db.update_agent_run.call_args
        assert call_kwargs[0][0] == "run-zombie-01"
        assert call_kwargs[1]["status"] == "timeout"

    def test_active_feature_run_not_reaped(self):
        """A running row whose target feature is still active must not be reaped."""
        run = self._make_run("run-active", target_id="feat-active")

        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.return_value = []  # no terminal features

            result = reap_zombie_subagentruns("proj-active")

        assert result == []
        mock_db.update_agent_run.assert_not_called()

    def test_null_target_id_skipped(self):
        """A running row with target_id=None cannot be a zombie — skipped."""
        run = self._make_run("run-null-target", target_id=None)

        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.return_value = []

            result = reap_zombie_subagentruns("proj-null")

        assert result == []

    def test_all_terminal_statuses_cause_reap(self):
        """Runs targeting features in any terminal state must all be reaped."""
        terminal_statuses = ("completed", "needs_human", "regression", "failed")
        runs = [
            self._make_run(f"run-{s}", target_id=f"feat-{s}")
            for s in terminal_statuses
        ]
        features = [
            self._make_feature(f"feat-{s}", status=s)
            for s in terminal_statuses
        ]

        def list_features_side_effect(project_id, status):
            return [f for f in features if f.status == status]

        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = runs
            mock_db.list_features.side_effect = list_features_side_effect
            mock_db.update_agent_run.return_value = None

            result = reap_zombie_subagentruns("proj-terminal")

        assert len(result) == 4
        assert set(result) == {f"run-{s}" for s in terminal_statuses}
