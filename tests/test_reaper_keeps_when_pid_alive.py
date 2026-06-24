"""Tests that find_stuck_features does NOT reap features whose subagent PID
is still alive in the OS process table."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from bob.orchestrator.stuck_executing_reaper import (
    find_stuck_features,
    subagent_alive,
)


def _feature(
    *,
    feature_id: str = "alive000-0000-0000-0000-000000000001",
    name: str = "alive feature",
    subagent_pid: int | None = None,
    subagent_heartbeat_at: datetime | None = None,
    refinement_attempts: int = 0,
    reap_count: int = 0,
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = "executing"
    f.subagent_pid = subagent_pid
    f.subagent_heartbeat_at = subagent_heartbeat_at
    f.refinement_attempts = refinement_attempts
    f.reap_count = reap_count
    f.last_reap_at = None
    return f


class TestSubagentAliveWithLivePid:
    def test_own_pid_is_alive(self):
        assert subagent_alive(os.getpid()) is True

    def test_init_pid_1_is_alive(self):
        # PID 1 (init/systemd) is always alive on Linux.
        assert subagent_alive(1) is True


class TestFindStuckFeaturesWithAlivePid:
    def test_alive_pid_not_in_stuck_list(self):
        own_pid = os.getpid()
        feature = _feature(subagent_pid=own_pid, subagent_heartbeat_at=None)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 0

    def test_alive_pid_with_fresh_heartbeat_not_stuck(self):
        own_pid = os.getpid()
        fresh_hb = datetime.now(timezone.utc) - timedelta(seconds=10)
        feature = _feature(subagent_pid=own_pid, subagent_heartbeat_at=fresh_hb)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 0

    def test_alive_pid_with_stale_heartbeat_not_stuck(self):
        # Even if the heartbeat is stale, a live PID means the subagent is running.
        own_pid = os.getpid()
        stale_hb = datetime.now(timezone.utc) - timedelta(seconds=9999)
        feature = _feature(subagent_pid=own_pid, subagent_heartbeat_at=stale_hb)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 0

    def test_mixed_dead_and_alive_only_dead_returned(self):
        own_pid = os.getpid()
        dead_pid = 99999999
        alive_feat = _feature(
            feature_id="alive000-0000-0000-0000-000000000001",
            subagent_pid=own_pid,
        )
        dead_feat = _feature(
            feature_id="dead0000-0000-0000-0000-000000000002",
            subagent_pid=dead_pid,
            subagent_heartbeat_at=None,
        )
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [alive_feat, dead_feat]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 1
        assert stuck[0].id == dead_feat.id
