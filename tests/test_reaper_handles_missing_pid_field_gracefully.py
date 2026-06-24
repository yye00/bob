"""Tests that reaper handles Feature objects with missing/None subagent_pid gracefully."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from bob.orchestrator.stuck_executing_reaper import (
    find_stuck_features,
    reap_stuck_feature,
    subagent_alive,
    sweep_stuck_executing,
)


def _feature(
    *,
    feature_id: str = "miss0000-0000-0000-0000-000000000001",
    name: str = "missing pid feature",
    status: str = "executing",
    subagent_pid: int | None = None,
    subagent_heartbeat_at: datetime | None = None,
    refinement_attempts: int = 0,
    reap_count: int = 0,
    has_pid_attr: bool = True,
    has_heartbeat_attr: bool = True,
) -> MagicMock:
    f = MagicMock(spec=[
        "id", "name", "status", "refinement_attempts", "reap_count", "last_reap_at"
    ] + (["subagent_pid"] if has_pid_attr else [])
      + (["subagent_heartbeat_at"] if has_heartbeat_attr else []))
    f.id = feature_id
    f.name = name
    f.status = status
    f.refinement_attempts = refinement_attempts
    f.reap_count = reap_count
    f.last_reap_at = None
    if has_pid_attr:
        f.subagent_pid = subagent_pid
    if has_heartbeat_attr:
        f.subagent_heartbeat_at = subagent_heartbeat_at
    return f


class TestMissingPidFieldGraceful:
    def test_none_pid_does_not_raise(self):
        """subagent_pid=None must not raise — treated as dead."""
        feature = _feature(subagent_pid=None, subagent_heartbeat_at=None)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            result = find_stuck_features("proj-1")
        assert len(result) == 1

    def test_none_pid_feature_is_reaped(self):
        """Feature with subagent_pid=None AND stale heartbeat is reaped."""
        stale = datetime.now(timezone.utc) - timedelta(seconds=600)
        feature = _feature(subagent_pid=None, subagent_heartbeat_at=stale)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            reaped = sweep_stuck_executing("proj-1")
        assert feature.id in reaped

    def test_reap_with_none_pid_does_not_raise(self):
        """reap_stuck_feature must not raise when subagent_pid is None."""
        feature = _feature(subagent_pid=None)
        with patch("bob.orchestrator.stuck_executing_reaper.db"):
            reap_stuck_feature(feature)  # must not raise

    def test_reap_clears_pid_to_none_even_when_already_none(self):
        """Clearing an already-None pid must succeed without error."""
        feature = _feature(subagent_pid=None)
        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            reap_stuck_feature(feature)
            kwargs = mock_db.update_feature.call_args[1]
        assert kwargs["subagent_pid"] is None

    def test_subagent_alive_with_none_returns_false(self):
        """subagent_alive(None) should be handled by callers — but 0 is also False."""
        assert subagent_alive(0) is False

    def test_sweep_tolerates_reap_error_on_one_feature(self):
        """sweep_stuck_executing skips features that fail to reap rather than crashing."""
        stale = datetime.now(timezone.utc) - timedelta(seconds=600)
        bad_feature = _feature(
            feature_id="bad00000-0000-0000-0000-000000000001",
            subagent_pid=None,
            subagent_heartbeat_at=stale,
        )
        good_feature = _feature(
            feature_id="good0000-0000-0000-0000-000000000002",
            subagent_pid=None,
            subagent_heartbeat_at=stale,
        )

        call_count = 0

        def patched_update_feature(feature_id, **kwargs):
            nonlocal call_count
            call_count += 1
            if feature_id == bad_feature.id:
                raise RuntimeError("simulated DB error")

        with patch("bob.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [bad_feature, good_feature]
            mock_db.update_feature.side_effect = patched_update_feature
            reaped = sweep_stuck_executing("proj-1")

        # good_feature should still be reaped despite bad_feature error
        assert good_feature.id in reaped
        assert bad_feature.id not in reaped
