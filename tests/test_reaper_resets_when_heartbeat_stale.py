"""Tests that find_stuck_features reaps a feature whose heartbeat is stale,
even when no PID is recorded."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from bob3.orchestrator.stuck_executing_reaper import (
    find_stuck_features,
    reap_stuck_feature,
)


def _feature(
    *,
    feature_id: str = "stale000-0000-0000-0000-000000000001",
    name: str = "stale feature",
    status: str = "executing",
    subagent_pid: int | None = None,
    subagent_heartbeat_at: datetime | None = None,
    refinement_attempts: int = 0,
    reap_count: int = 0,
    last_reap_at: datetime | None = None,
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = status
    f.subagent_pid = subagent_pid
    f.subagent_heartbeat_at = subagent_heartbeat_at
    f.refinement_attempts = refinement_attempts
    f.reap_count = reap_count
    f.last_reap_at = last_reap_at
    return f


class TestStaleHeartbeatNoAliveProcess:
    def test_stale_heartbeat_no_pid_is_stuck(self):
        """No PID + heartbeat older than timeout → stuck."""
        stale = datetime.now(timezone.utc) - timedelta(seconds=600)
        feature = _feature(subagent_pid=None, subagent_heartbeat_at=stale)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 1
        assert stuck[0].id == feature.id

    def test_heartbeat_exactly_at_threshold_is_stuck(self):
        """Heartbeat age == timeout → treat as stuck (>= comparison)."""
        exactly_at_threshold = datetime.now(timezone.utc) - timedelta(seconds=300)
        feature = _feature(subagent_pid=None, subagent_heartbeat_at=exactly_at_threshold)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 1

    def test_fresh_heartbeat_no_pid_is_not_stuck(self):
        """No PID but heartbeat is recent → still executing (e.g. PID not yet recorded)."""
        fresh = datetime.now(timezone.utc) - timedelta(seconds=10)
        feature = _feature(subagent_pid=None, subagent_heartbeat_at=fresh)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 0

    def test_dead_pid_fresh_heartbeat_is_not_stuck(self):
        """Dead PID + fresh heartbeat → do NOT reap (heartbeat within window)."""
        fresh = datetime.now(timezone.utc) - timedelta(seconds=5)
        feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=fresh)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 0

    def test_dead_pid_stale_heartbeat_is_stuck(self):
        """Dead PID + stale heartbeat → reap."""
        stale = datetime.now(timezone.utc) - timedelta(seconds=400)
        feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=stale)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 1

    def test_reap_logs_heartbeat_age(self, caplog):
        """reap_stuck_feature logs the heartbeat age in its output."""
        import logging
        stale = datetime.now(timezone.utc) - timedelta(seconds=600)
        feature = _feature(subagent_pid=None, subagent_heartbeat_at=stale)
        now = datetime.now(timezone.utc)
        with patch("bob3.orchestrator.stuck_executing_reaper.db"):
            with caplog.at_level(logging.INFO, logger="bob3.orchestrator.stuck_executing_reaper"):
                reap_stuck_feature(feature, now=now)
        assert any("STUCK_REAPER" in r.message for r in caplog.records)
