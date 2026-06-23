"""Tests for bob3.stuck_executing_reaper_detect_reset_features_whose_subagent.

Acceptance criteria:
- File exists: src/bob3/stuck_executing_reaper_detect_reset_features_whose_subagent.py
- pytest: tests/test_stuck_executing_reaper_detect_reset_features_whose_subagent.py::test_stuck_executing_reaper_detect_reset_features_whose_subagent
- Function defined: bob3.stuck_executing_reaper_detect_reset_features_whose_subagent.stuck_executing_reaper_detect_reset_features_whose_subagent
"""

from __future__ import annotations

import inspect
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


def _feature(
    *,
    feature_id: str = "dead0000-0000-0000-0000-000000000001",
    name: str = "test feature",
    status: str = "executing",
    subagent_pid: int | None = 99999999,
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


def test_stuck_executing_reaper_detect_reset_features_whose_subagent():
    """Primary AC test — verifies the module and function exist and are callable."""
    import bob3.stuck_executing_reaper_detect_reset_features_whose_subagent as mod
    fn = mod.stuck_executing_reaper_detect_reset_features_whose_subagent
    assert callable(fn), "Function must be callable"

    sig = inspect.signature(fn)
    assert "project_id" in sig.parameters, "Must accept project_id"
    assert "heartbeat_timeout_seconds" in sig.parameters, "Must accept heartbeat_timeout_seconds"

    param = sig.parameters["heartbeat_timeout_seconds"]
    assert param.default != inspect.Parameter.empty, "heartbeat_timeout_seconds must have a default"
    assert param.default == 300, "Default timeout must be 300 seconds"

    # Call with a mocked db and a dead PID — must return a list of reaped IDs
    feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=None)
    with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
        mock_db.list_features.return_value = [feature]
        result = fn("test-project-id")

    assert isinstance(result, list), "Must return a list"
    assert feature.id in result, "Stuck feature must be reaped"


def test_module_importable():
    import bob3.stuck_executing_reaper_detect_reset_features_whose_subagent  # noqa: F401


def test_function_defined():
    from bob3.stuck_executing_reaper_detect_reset_features_whose_subagent import (
        stuck_executing_reaper_detect_reset_features_whose_subagent,
    )
    assert callable(stuck_executing_reaper_detect_reset_features_whose_subagent)


def test_returns_empty_list_when_no_executing():
    from bob3.stuck_executing_reaper_detect_reset_features_whose_subagent import (
        stuck_executing_reaper_detect_reset_features_whose_subagent as fn,
    )
    with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
        mock_db.list_features.return_value = []
        result = fn("proj-1")
    assert result == []


def test_does_not_reap_live_pid():
    from bob3.stuck_executing_reaper_detect_reset_features_whose_subagent import (
        stuck_executing_reaper_detect_reset_features_whose_subagent as fn,
    )
    live_pid = os.getpid()
    feature = _feature(subagent_pid=live_pid, subagent_heartbeat_at=None)
    with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
        mock_db.list_features.return_value = [feature]
        result = fn("proj-1")
    assert result == []
    mock_db.update_feature.assert_not_called()


def test_does_not_reap_fresh_heartbeat():
    from bob3.stuck_executing_reaper_detect_reset_features_whose_subagent import (
        stuck_executing_reaper_detect_reset_features_whose_subagent as fn,
    )
    fresh_hb = datetime.now(timezone.utc) - timedelta(seconds=10)
    feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=fresh_hb)
    with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
        mock_db.list_features.return_value = [feature]
        result = fn("proj-1", heartbeat_timeout_seconds=300)
    assert result == []


def test_reaps_stale_heartbeat():
    from bob3.stuck_executing_reaper_detect_reset_features_whose_subagent import (
        stuck_executing_reaper_detect_reset_features_whose_subagent as fn,
    )
    stale_hb = datetime.now(timezone.utc) - timedelta(seconds=600)
    feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=stale_hb)
    with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
        mock_db.list_features.return_value = [feature]
        result = fn("proj-1", heartbeat_timeout_seconds=300)
    assert feature.id in result


def test_resets_status_to_ready():
    from bob3.stuck_executing_reaper_detect_reset_features_whose_subagent import (
        stuck_executing_reaper_detect_reset_features_whose_subagent as fn,
    )
    feature = _feature(subagent_pid=99999999)
    with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
        mock_db.list_features.return_value = [feature]
        fn("proj-1")
        call_kwargs = mock_db.update_feature.call_args[1]
    assert call_kwargs["status"] == "ready"


def test_increments_refinement_attempts():
    from bob3.stuck_executing_reaper_detect_reset_features_whose_subagent import (
        stuck_executing_reaper_detect_reset_features_whose_subagent as fn,
    )
    feature = _feature(subagent_pid=99999999, refinement_attempts=2)
    with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
        mock_db.list_features.return_value = [feature]
        fn("proj-1")
        call_kwargs = mock_db.update_feature.call_args[1]
    assert call_kwargs["refinement_attempts"] == 3


def test_clears_subagent_pid():
    from bob3.stuck_executing_reaper_detect_reset_features_whose_subagent import (
        stuck_executing_reaper_detect_reset_features_whose_subagent as fn,
    )
    feature = _feature(subagent_pid=99999999)
    with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
        mock_db.list_features.return_value = [feature]
        fn("proj-1")
        call_kwargs = mock_db.update_feature.call_args[1]
    assert call_kwargs["subagent_pid"] is None


def test_multiple_stuck_features_all_reaped():
    from bob3.stuck_executing_reaper_detect_reset_features_whose_subagent import (
        stuck_executing_reaper_detect_reset_features_whose_subagent as fn,
    )
    f1 = _feature(feature_id="aaaa0000-0000-0000-0000-000000000001", subagent_pid=99999991)
    f2 = _feature(feature_id="bbbb0000-0000-0000-0000-000000000002", subagent_pid=99999992)
    with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
        mock_db.list_features.return_value = [f1, f2]
        result = fn("proj-1")
    assert f1.id in result
    assert f2.id in result
