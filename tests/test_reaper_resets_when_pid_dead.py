"""Tests that find_stuck_features and reap_stuck_feature reset a feature
whose recorded subagent PID no longer exists in the OS process table."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from bob3.orchestrator.stuck_executing_reaper import (
    find_stuck_features,
    reap_stuck_feature,
    subagent_alive,
)


def _feature(
    *,
    feature_id: str = "dead0000-0000-0000-0000-000000000001",
    name: str = "test feature",
    status: str = "executing",
    subagent_pid: int | None = 99999,
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


class TestSubagentAliveDeadPid:
    def test_dead_pid_returns_false(self):
        # PID 99999999 is almost certainly not running.
        assert subagent_alive(99999999) is False

    def test_zero_pid_returns_false(self):
        assert subagent_alive(0) is False

    def test_negative_pid_returns_false(self):
        assert subagent_alive(-1) is False

    def test_own_pid_returns_true(self):
        import os
        assert subagent_alive(os.getpid()) is True


class TestFindStuckFeaturesWithDeadPid:
    def test_executing_feature_with_dead_pid_and_no_heartbeat_is_stuck(self):
        feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=None)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 1
        assert stuck[0].id == feature.id

    def test_executing_feature_with_dead_pid_and_stale_heartbeat_is_stuck(self):
        stale_hb = datetime.now(timezone.utc) - timedelta(seconds=600)
        feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=stale_hb)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 1

    def test_feature_with_none_pid_and_no_heartbeat_is_stuck(self):
        feature = _feature(subagent_pid=None, subagent_heartbeat_at=None)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            stuck = find_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert len(stuck) == 1


class TestReapStuckFeatureWithDeadPid:
    def test_reap_sets_status_to_ready(self):
        feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=None)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
            call_kwargs = mock_db.update_feature.call_args
        assert call_kwargs[1]["status"] == "ready"

    def test_reap_clears_subagent_pid(self):
        feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=None)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
            call_kwargs = mock_db.update_feature.call_args
        assert call_kwargs[1]["subagent_pid"] is None

    def test_reap_clears_subagent_heartbeat_at(self):
        feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=None)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
            call_kwargs = mock_db.update_feature.call_args
        assert call_kwargs[1]["subagent_heartbeat_at"] is None

    def test_reap_stamps_last_reap_at(self):
        feature = _feature(subagent_pid=99999999)
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature, now=now)
            call_kwargs = mock_db.update_feature.call_args
        assert call_kwargs[1]["last_reap_at"] == now.isoformat()
