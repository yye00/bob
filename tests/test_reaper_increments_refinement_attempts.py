"""Tests that reap_stuck_feature increments refinement_attempts correctly."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from bob.orchestrator.stuck_executing_reaper import reap_stuck_feature


def _feature(
    *,
    feature_id: str = "incr0000-0000-0000-0000-000000000001",
    name: str = "increment test feature",
    subagent_pid: int | None = 99999,
    subagent_heartbeat_at: datetime | None = None,
    refinement_attempts: int = 0,
    reap_count: int = 0,
    last_reap_at: datetime | None = None,
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = "executing"
    f.subagent_pid = subagent_pid
    f.subagent_heartbeat_at = subagent_heartbeat_at
    f.refinement_attempts = refinement_attempts
    f.reap_count = reap_count
    f.last_reap_at = last_reap_at
    return f


class TestRefinementAttemptsIncrement:
    def test_increments_from_zero(self):
        feature = _feature(refinement_attempts=0)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
            kwargs = mock_db.update_feature.call_args[1]
        assert kwargs["refinement_attempts"] == 1

    def test_increments_from_nonzero(self):
        feature = _feature(refinement_attempts=3)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
            kwargs = mock_db.update_feature.call_args[1]
        assert kwargs["refinement_attempts"] == 4

    def test_reap_count_increments_from_zero(self):
        feature = _feature(reap_count=0)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
            kwargs = mock_db.update_feature.call_args[1]
        assert kwargs["reap_count"] == 1

    def test_reap_count_increments_from_nonzero(self):
        feature = _feature(reap_count=2)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
            kwargs = mock_db.update_feature.call_args[1]
        assert kwargs["reap_count"] == 3

    def test_both_refinement_and_reap_count_increment_together(self):
        feature = _feature(refinement_attempts=5, reap_count=2)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
            kwargs = mock_db.update_feature.call_args[1]
        assert kwargs["refinement_attempts"] == 6
        assert kwargs["reap_count"] == 3

    def test_status_set_to_ready_alongside_increment(self):
        feature = _feature(refinement_attempts=1)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
            kwargs = mock_db.update_feature.call_args[1]
        assert kwargs["status"] == "ready"
        assert kwargs["refinement_attempts"] == 2

    def test_update_feature_called_once(self):
        feature = _feature(refinement_attempts=0)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
        assert mock_db.update_feature.call_count == 1

    def test_feature_id_passed_to_update_feature(self):
        fid = "specific-feature-id-0000-000000000001"
        feature = _feature(feature_id=fid, refinement_attempts=0)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
            args = mock_db.update_feature.call_args[0]
        assert args[0] == fid
