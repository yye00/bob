"""Tests that find_zombie_runs skips sub_agent_run rows with null target_id.

Runs with no target_id cannot be joined against a feature and must not be
classified as zombies — they may be utility or diagnostic runs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from bob.orchestrator.zombie_run_reaper import find_zombie_runs


def _make_run(
    *,
    run_id: str = "run00001-0000-0000-0000-000000000001",
    purpose: str = "diagnostics",
    status: str = "running",
    target_id: str | None = None,
) -> MagicMock:
    r = MagicMock()
    r.id = run_id
    r.purpose = purpose
    r.status = status
    r.target_id = target_id
    return r


class TestFindZombieRunsNullTargetId:
    def test_run_with_null_target_id_is_not_zombie(self):
        run = _make_run(target_id=None)
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.return_value = []
            zombies = find_zombie_runs("proj-1")
        assert zombies == []

    def test_null_target_id_skipped_even_when_terminal_features_exist(self):
        """Even if there are terminal features in the project, a run with
        null target_id must not be classified as a zombie."""
        run = _make_run(target_id=None)
        terminal_feature = MagicMock()
        terminal_feature.id = "feat0001-0000-0000-0000-000000000001"
        terminal_feature.status = "completed"

        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [terminal_feature] if status == "completed" else []
            )
            zombies = find_zombie_runs("proj-1")

        assert zombies == []

    def test_list_features_not_queried_when_all_runs_have_null_target_id(self):
        """Optimization: if no candidates have a target_id, skip the feature query."""
        run1 = _make_run(run_id="run00001-0000-0000-0000-000000000001", target_id=None)
        run2 = _make_run(run_id="run00002-0000-0000-0000-000000000001", target_id=None)

        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run1, run2]
            find_zombie_runs("proj-1")
            mock_db.list_features.assert_not_called()

    def test_mixed_null_and_non_null_target_ids(self):
        """Only the run with a non-null target_id pointing to a terminal feature
        should be returned; the null-target-id run must be skipped."""
        run_null = _make_run(
            run_id="run-null-00000000000000000000001",
            target_id=None,
        )
        run_with_target = _make_run(
            run_id="run-with-00000000000000000000001",
            target_id="feat0001-0000-0000-0000-000000000001",
        )
        terminal_feature = MagicMock()
        terminal_feature.id = "feat0001-0000-0000-0000-000000000001"
        terminal_feature.status = "completed"

        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run_null, run_with_target]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [terminal_feature] if status == "completed" else []
            )
            zombies = find_zombie_runs("proj-1")

        assert len(zombies) == 1
        assert zombies[0].id == run_with_target.id
