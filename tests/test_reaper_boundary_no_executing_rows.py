"""Tests boundary condition: find_stuck_features with no executing rows returns []."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from bob.orchestrator.stuck_executing_reaper import (
    find_stuck_features,
    sweep_stuck_executing,
)


def _feature(
    *,
    feature_id: str = "bound000-0000-0000-0000-000000000001",
    name: str = "boundary feature",
    status: str = "executing",
    subagent_pid: int | None = 99999999,
    subagent_heartbeat_at: datetime | None = None,
    refinement_attempts: int = 0,
    reap_count: int = 0,
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = status
    f.subagent_pid = subagent_pid
    f.subagent_heartbeat_at = subagent_heartbeat_at
    f.refinement_attempts = refinement_attempts
    f.reap_count = reap_count
    f.last_reap_at = None
    return f


class TestNoExecutingRows:
    def test_empty_executing_list_returns_empty(self):
        """When no features are executing, find_stuck_features returns []."""
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = []
            stuck = find_stuck_features("proj-empty", heartbeat_timeout_seconds=300)
        assert stuck == []

    def test_sweep_on_empty_db_returns_empty(self):
        """sweep_stuck_executing returns [] when nothing is stuck."""
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = []
            reaped = sweep_stuck_executing("proj-empty", heartbeat_timeout_seconds=300)
        assert reaped == []

    def test_sweep_does_not_call_update_feature_when_empty(self):
        """No DB writes occur when no features are stuck."""
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = []
            sweep_stuck_executing("proj-empty")
            assert mock_db.update_feature.call_count == 0

    def test_all_executing_features_have_alive_pid(self):
        """All executing features are alive → empty stuck list."""
        import os
        own_pid = os.getpid()
        features = [
            _feature(feature_id=f"alive-{i:03d}", subagent_pid=own_pid)
            for i in range(5)
        ]
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = features
            stuck = find_stuck_features("proj-all-alive", heartbeat_timeout_seconds=300)
        assert stuck == []

    def test_all_executing_features_have_fresh_heartbeat(self):
        """All features have recent heartbeats and no (dead) pids → not stuck."""
        fresh = datetime.now(timezone.utc) - timedelta(seconds=5)
        features = [
            _feature(feature_id=f"fresh-{i:03d}", subagent_pid=None, subagent_heartbeat_at=fresh)
            for i in range(3)
        ]
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = features
            stuck = find_stuck_features("proj-fresh-hb", heartbeat_timeout_seconds=300)
        assert stuck == []

    def test_list_features_called_with_correct_project_id(self):
        """find_stuck_features queries the right project."""
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = []
            find_stuck_features("my-special-project-id", heartbeat_timeout_seconds=300)
        mock_db.list_features.assert_called_once()
        call_kwargs = mock_db.list_features.call_args
        assert "my-special-project-id" in (call_kwargs[0] + tuple(call_kwargs[1].values()))
