"""Tests that find_zombie_runs does NOT return runs whose target feature is
still active (non-terminal), preserving legitimately in-flight work."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from bob.orchestrator.zombie_run_reaper import find_zombie_runs


def _make_run(
    *,
    run_id: str = "run00001-0000-0000-0000-000000000001",
    purpose: str = "feature_implement",
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
    status: str = "executing",
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.status = status
    return f


class TestFindZombieRunsLeavesLegitRunningAlone:
    def _find_with_feature_status(self, feature_status: str) -> list:
        run = _make_run(target_id="feat0001-0000-0000-0000-000000000001")
        feature = _make_feature(
            feature_id="feat0001-0000-0000-0000-000000000001",
            status=feature_status,
        )
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            # No terminal features returned for any status.
            mock_db.list_features.return_value = []
            return find_zombie_runs("proj-1")

    def test_run_with_executing_target_is_not_zombie(self):
        zombies = self._find_with_feature_status("executing")
        assert zombies == []

    def test_run_with_pending_target_is_not_zombie(self):
        zombies = self._find_with_feature_status("pending")
        assert zombies == []

    def test_run_with_ready_target_is_not_zombie(self):
        zombies = self._find_with_feature_status("ready")
        assert zombies == []

    def test_run_with_reviewing_target_is_not_zombie(self):
        zombies = self._find_with_feature_status("reviewing")
        assert zombies == []

    def test_mixed_runs_only_zombie_reaped(self):
        """Only the run whose target is terminal should be returned."""
        run_zombie = _make_run(
            run_id="run-zombie-000000000000000000000001",
            target_id="feat-terminal-000000000000000000001",
        )
        run_legit = _make_run(
            run_id="run-legit-0000000000000000000000001",
            target_id="feat-executing-00000000000000000001",
        )
        terminal_feature = _make_feature(
            feature_id="feat-terminal-000000000000000000001",
            status="completed",
        )

        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run_zombie, run_legit]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [terminal_feature] if status == "completed" else []
            )
            zombies = find_zombie_runs("proj-1")

        assert len(zombies) == 1
        assert zombies[0].id == run_zombie.id
