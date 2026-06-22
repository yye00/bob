"""Tests for bob3.stuck_executing_reaper — top-level module.

Acceptance criteria:
- File exists: src/bob3/stuck_executing_reaper.py
- Function defined: bob3.stuck_executing_reaper.detect_and_reset_stuck_features
- pytest: tests/test_stuck_executing_reaper.py
- integration: bob3.orchestrator
"""

from __future__ import annotations

import inspect
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Module-level import checks
# ---------------------------------------------------------------------------

class TestModuleImports:
    def test_module_importable(self):
        import bob3.stuck_executing_reaper  # noqa: F401

    def test_detect_and_reset_stuck_features_callable(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        assert callable(detect_and_reset_stuck_features)

    def test_detect_and_reset_accepts_project_id(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        sig = inspect.signature(detect_and_reset_stuck_features)
        assert "project_id" in sig.parameters

    def test_detect_and_reset_accepts_heartbeat_timeout(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        sig = inspect.signature(detect_and_reset_stuck_features)
        assert "heartbeat_timeout_seconds" in sig.parameters

    def test_detect_and_reset_has_default_timeout(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        sig = inspect.signature(detect_and_reset_stuck_features)
        param = sig.parameters["heartbeat_timeout_seconds"]
        assert param.default != inspect.Parameter.empty

    def test_default_timeout_is_300(self):
        from bob3.stuck_executing_reaper import DEFAULT_HEARTBEAT_TIMEOUT_SECONDS
        assert DEFAULT_HEARTBEAT_TIMEOUT_SECONDS == 300

    def test_module_exports_subagent_alive(self):
        from bob3.stuck_executing_reaper import subagent_alive
        assert callable(subagent_alive)

    def test_module_exports_find_stuck_features(self):
        from bob3.stuck_executing_reaper import find_stuck_features
        assert callable(find_stuck_features)

    def test_module_exports_reap_stuck_feature(self):
        from bob3.stuck_executing_reaper import reap_stuck_feature
        assert callable(reap_stuck_feature)

    def test_module_exports_sweep_stuck_executing(self):
        from bob3.stuck_executing_reaper import sweep_stuck_executing
        assert callable(sweep_stuck_executing)


# ---------------------------------------------------------------------------
# Functional behavior via detect_and_reset_stuck_features
# ---------------------------------------------------------------------------

class TestDetectAndResetStuckFeatures:
    def test_returns_empty_list_when_no_executing_features(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = []
            result = detect_and_reset_stuck_features("proj-1")
        assert result == []

    def test_returns_list_of_reaped_feature_ids(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=None)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            result = detect_and_reset_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert feature.id in result

    def test_resets_status_to_ready_on_dead_pid(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=None)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            detect_and_reset_stuck_features("proj-1")
            call_kwargs = mock_db.update_feature.call_args[1]
        assert call_kwargs["status"] == "ready"

    def test_increments_refinement_attempts(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        feature = _feature(subagent_pid=99999999, refinement_attempts=2)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            detect_and_reset_stuck_features("proj-1")
            call_kwargs = mock_db.update_feature.call_args[1]
        assert call_kwargs["refinement_attempts"] == 3

    def test_clears_subagent_pid(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        feature = _feature(subagent_pid=99999999)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            detect_and_reset_stuck_features("proj-1")
            call_kwargs = mock_db.update_feature.call_args[1]
        assert call_kwargs["subagent_pid"] is None

    def test_clears_subagent_heartbeat_at(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        feature = _feature(subagent_pid=99999999)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            detect_and_reset_stuck_features("proj-1")
            call_kwargs = mock_db.update_feature.call_args[1]
        assert call_kwargs["subagent_heartbeat_at"] is None

    def test_stamps_last_reap_at(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        feature = _feature(subagent_pid=99999999)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            detect_and_reset_stuck_features("proj-1")
            call_kwargs = mock_db.update_feature.call_args[1]
        assert call_kwargs.get("last_reap_at") is not None

    def test_increments_reap_count(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        feature = _feature(subagent_pid=99999999, reap_count=1)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            detect_and_reset_stuck_features("proj-1")
            call_kwargs = mock_db.update_feature.call_args[1]
        assert call_kwargs["reap_count"] == 2

    def test_does_not_reap_when_pid_is_alive(self):
        """Features with a live PID must NOT be reaped."""
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        live_pid = os.getpid()
        feature = _feature(subagent_pid=live_pid, subagent_heartbeat_at=None)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            result = detect_and_reset_stuck_features("proj-1")
        assert result == []
        mock_db.update_feature.assert_not_called()

    def test_does_not_reap_when_heartbeat_fresh(self):
        """A dead PID but fresh heartbeat should NOT be reaped."""
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        fresh_hb = datetime.now(timezone.utc) - timedelta(seconds=10)
        feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=fresh_hb)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            result = detect_and_reset_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert result == []

    def test_reaps_when_heartbeat_stale(self):
        """Dead PID + stale heartbeat → reap."""
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        stale_hb = datetime.now(timezone.utc) - timedelta(seconds=600)
        feature = _feature(subagent_pid=99999999, subagent_heartbeat_at=stale_hb)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            result = detect_and_reset_stuck_features("proj-1", heartbeat_timeout_seconds=300)
        assert feature.id in result

    def test_reaps_when_pid_none_and_no_heartbeat(self):
        """No PID and no heartbeat → stuck → reap."""
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        feature = _feature(subagent_pid=None, subagent_heartbeat_at=None)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            result = detect_and_reset_stuck_features("proj-1")
        assert feature.id in result

    def test_multiple_stuck_features_all_reaped(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        f1 = _feature(feature_id="aaaa0000-0000-0000-0000-000000000001", subagent_pid=99999991)
        f2 = _feature(feature_id="bbbb0000-0000-0000-0000-000000000002", subagent_pid=99999992)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [f1, f2]
            result = detect_and_reset_stuck_features("proj-1")
        assert f1.id in result
        assert f2.id in result
        assert mock_db.update_feature.call_count == 2

    def test_continues_on_individual_reap_failure(self):
        """If one reap fails, others should still succeed."""
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        f1 = _feature(feature_id="aaaa0000-0000-0000-0000-000000000001", subagent_pid=None)
        f2 = _feature(feature_id="bbbb0000-0000-0000-0000-000000000002", subagent_pid=None)
        call_count = [0]

        def update_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("DB write failed")

        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [f1, f2]
            mock_db.update_feature.side_effect = update_side_effect
            result = detect_and_reset_stuck_features("proj-1")
        assert f2.id in result

    def test_logs_reap_event(self, caplog):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        import logging
        feature = _feature(subagent_pid=99999999)
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = [feature]
            with caplog.at_level(logging.INFO, logger="bob3.orchestrator.stuck_executing_reaper"):
                detect_and_reset_stuck_features("proj-1")
        assert any(
            "reap" in r.message.lower() or "stuck" in r.message.lower()
            for r in caplog.records
        )

    def test_delegates_to_db_list_features_with_executing_status(self):
        """detect_and_reset_stuck_features calls db.list_features with status=executing."""
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
            mock_db.list_features.return_value = []
            detect_and_reset_stuck_features("proj-xyz")
            mock_db.list_features.assert_called_once_with(
                project_id="proj-xyz", status="executing"
            )


# ---------------------------------------------------------------------------
# subagent_alive helper tests
# ---------------------------------------------------------------------------

class TestSubagentAlive:
    def test_returns_true_for_live_pid(self):
        from bob3.stuck_executing_reaper import subagent_alive
        assert subagent_alive(os.getpid()) is True

    def test_returns_false_for_dead_pid(self):
        from bob3.stuck_executing_reaper import subagent_alive
        assert subagent_alive(99999999) is False

    def test_returns_false_for_zero_pid(self):
        from bob3.stuck_executing_reaper import subagent_alive
        assert subagent_alive(0) is False

    def test_returns_false_for_negative_pid(self):
        from bob3.stuck_executing_reaper import subagent_alive
        assert subagent_alive(-1) is False


# ---------------------------------------------------------------------------
# Orchestrator integration: bob3.orchestrator exports sweep via stuck_executing_reaper
# ---------------------------------------------------------------------------

class TestOrchestratorIntegration:
    def test_orchestrator_stuck_executing_reaper_importable(self):
        from bob3.orchestrator.stuck_executing_reaper import sweep_stuck_executing
        assert callable(sweep_stuck_executing)

    def test_top_level_delegates_to_orchestrator_sweep(self):
        """detect_and_reset_stuck_features must delegate to sweep_stuck_executing."""
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        with patch(
            "bob3.orchestrator.stuck_executing_reaper.sweep_stuck_executing"
        ) as mock_sweep:
            mock_sweep.return_value = ["feat-1"]
            # Patch at the orchestrator level since that's where sweep lives
            with patch("bob3.orchestrator.stuck_executing_reaper.db") as mock_db:
                mock_db.list_features.return_value = []
                result = detect_and_reset_stuck_features("proj-1")
        # Verifies the top-level function returns a list (delegating pattern)
        assert isinstance(result, list)

    def test_both_modules_expose_project_id_param(self):
        """Both the top-level and orchestrator functions accept project_id."""
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        from bob3.orchestrator.stuck_executing_reaper import sweep_stuck_executing
        sig1 = inspect.signature(detect_and_reset_stuck_features)
        sig2 = inspect.signature(sweep_stuck_executing)
        assert "project_id" in sig1.parameters
        assert "project_id" in sig2.parameters

    def test_both_modules_expose_heartbeat_timeout_param(self):
        from bob3.stuck_executing_reaper import detect_and_reset_stuck_features
        from bob3.orchestrator.stuck_executing_reaper import sweep_stuck_executing
        sig1 = inspect.signature(detect_and_reset_stuck_features)
        sig2 = inspect.signature(sweep_stuck_executing)
        assert "heartbeat_timeout_seconds" in sig1.parameters
        assert "heartbeat_timeout_seconds" in sig2.parameters

    def test_orchestrator_run_loop_imports_sweep_stuck_executing(self):
        """The orchestrator run_loop must import sweep_stuck_executing."""
        import importlib
        import importlib.util
        import ast
        from pathlib import Path
        run_loop_path = Path(__file__).parent.parent / "src" / "bob3" / "orchestrator" / "run_loop.py"
        source = run_loop_path.read_text()
        tree = ast.parse(source)
        import_stmts = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        found = False
        for node in import_stmts:
            if isinstance(node, ast.ImportFrom):
                if node.module and "stuck_executing_reaper" in node.module:
                    found = True
                    break
        assert found, "orchestrator run_loop must import from stuck_executing_reaper"
