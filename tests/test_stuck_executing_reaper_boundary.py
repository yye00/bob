"""Boundary-case tests for bob.reaper.detect_stuck_executing / reset_stuck_feature.

AC: pytest: tests/test_stuck_executing_reaper_boundary.py — empty, zero, or
minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from bob.reaper import detect_stuck_executing, reset_stuck_feature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# detect_stuck_executing boundary cases
# ---------------------------------------------------------------------------


class TestDetectStuckExecutingBoundary:
    def test_empty_executing_list_returns_empty_list(self):
        """No executing features → empty list, not an error."""
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = []
            result = detect_stuck_executing("proj-empty")
        assert result == []
        assert isinstance(result, list)

    def test_zero_heartbeat_timeout_reaps_all_dead_pid_features(self):
        """heartbeat_timeout_seconds=0 treats any heartbeat as stale."""
        feature = _feature(subagent_pid=None, subagent_heartbeat_at=None)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            result = detect_stuck_executing("proj-zero-timeout", heartbeat_timeout_seconds=0)
        assert isinstance(result, list)
        assert feature in result

    def test_single_alive_pid_feature_not_stuck(self):
        """When the sole executing feature has an alive PID, nothing is reaped."""
        own_pid = os.getpid()
        feature = _feature(subagent_pid=own_pid)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            result = detect_stuck_executing("proj-alive")
        assert result == []

    def test_single_feature_no_pid_no_heartbeat_is_stuck(self):
        """Single feature with no PID and no heartbeat → stuck."""
        feature = _feature(subagent_pid=None, subagent_heartbeat_at=None)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            result = detect_stuck_executing("proj-no-pid")
        assert feature in result

    def test_fresh_heartbeat_no_pid_not_stuck_within_timeout(self):
        """Feature with no PID but a fresh heartbeat is not stuck when within timeout."""
        fresh = datetime.now(timezone.utc) - timedelta(seconds=5)
        feature = _feature(subagent_pid=None, subagent_heartbeat_at=fresh)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            result = detect_stuck_executing("proj-fresh-hb", heartbeat_timeout_seconds=300)
        assert feature not in result

    def test_multiple_features_mixed_aliveness(self):
        """Mix of alive and dead features — only dead ones returned."""
        own_pid = os.getpid()
        alive = _feature(feature_id="alive000-0000-0000-0000-000000000001", subagent_pid=own_pid)
        dead = _feature(feature_id="dead0000-0000-0000-0000-000000000001", subagent_pid=None)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [alive, dead]
            result = detect_stuck_executing("proj-mixed")
        assert alive not in result
        assert dead in result

    def test_returns_list_type_always(self):
        """Return type is always list, never None."""
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = []
            result = detect_stuck_executing("proj-type-check")
        assert isinstance(result, list)

    def test_large_heartbeat_timeout_does_not_raise(self):
        """Very large timeout is valid and does not raise."""
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = []
            result = detect_stuck_executing("proj-large-timeout", heartbeat_timeout_seconds=86400)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# reset_stuck_feature boundary cases
# ---------------------------------------------------------------------------


class TestResetStuckFeatureBoundary:
    def test_reset_feature_with_zero_reap_count(self):
        """Feature with reap_count=0 is reset without error."""
        feature = _feature(reap_count=0, refinement_attempts=0)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.update_feature.return_value = None
            reset_stuck_feature(feature)
        mock_db.update_feature.assert_called_once()

    def test_reset_feature_increments_reap_count(self):
        """After reset, update_feature is called with reap_count=1 for a first reap."""
        feature = _feature(reap_count=0, refinement_attempts=0, subagent_pid=None)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.update_feature.return_value = None
            reset_stuck_feature(feature)
        call_kwargs = mock_db.update_feature.call_args[1]
        assert call_kwargs.get("reap_count") == 1

    def test_reset_feature_sets_status_ready(self):
        """reset_stuck_feature always sets the status to 'ready'."""
        feature = _feature(reap_count=0, refinement_attempts=2, subagent_pid=None)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.update_feature.return_value = None
            reset_stuck_feature(feature)
        call_kwargs = mock_db.update_feature.call_args[1]
        assert call_kwargs.get("status") == "ready"

    def test_reset_feature_increments_refinement_attempts(self):
        """reset_stuck_feature increments refinement_attempts by 1."""
        feature = _feature(reap_count=0, refinement_attempts=3, subagent_pid=None)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.update_feature.return_value = None
            reset_stuck_feature(feature)
        call_kwargs = mock_db.update_feature.call_args[1]
        assert call_kwargs.get("refinement_attempts") == 4

    def test_reset_feature_accepts_explicit_now(self):
        """reset_stuck_feature accepts an explicit 'now' timestamp."""
        feature = _feature(reap_count=0)
        explicit_now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.update_feature.return_value = None
            reset_stuck_feature(feature, now=explicit_now)
        call_kwargs = mock_db.update_feature.call_args[1]
        assert "2025-01-01" in call_kwargs.get("last_reap_at", "")

    def test_reset_feature_with_large_reap_count(self):
        """Feature with a large reap_count can still be reset without error."""
        feature = _feature(reap_count=999, refinement_attempts=999)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.update_feature.return_value = None
            reset_stuck_feature(feature)
        call_kwargs = mock_db.update_feature.call_args[1]
        assert call_kwargs.get("reap_count") == 1000
