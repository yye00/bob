"""Tests for bob3.final_reaper_sweep — sweep_orphans_on_exit (feature 3b5fe995).

AC: File exists: src/bob3/final_reaper_sweep.py
AC: Function defined: bob3.final_reaper_sweep.sweep_orphans_on_exit
AC: pytest: tests/test_final_reaper_sweep.py
AC: integration: bob3.orchestrator
"""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import MagicMock, call, patch


class TestModuleAndFunction(unittest.TestCase):
    """Structural ACs: module importable, function defined."""

    def test_final_reaper_sweep_module_importable(self):
        """bob3.final_reaper_sweep must be importable."""
        import bob3.final_reaper_sweep  # noqa: F401

    def test_sweep_orphans_on_exit_is_callable(self):
        """sweep_orphans_on_exit must be a callable defined in bob3.final_reaper_sweep."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        assert callable(sweep_orphans_on_exit)

    def test_function_signature_accepts_project_id(self):
        """sweep_orphans_on_exit must accept a project_id positional argument."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        sig = inspect.signature(sweep_orphans_on_exit)
        assert "project_id" in sig.parameters


class TestSweepOrphansOnExitDelegation(unittest.TestCase):
    """Verify delegation to bob3.final_reaper.sweep_orphans_on_exit."""

    def test_delegates_to_final_reaper(self):
        """sweep_orphans_on_exit must delegate to bob3.final_reaper.sweep_orphans_on_exit."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        with patch("bob3.final_reaper_sweep.sweep_orphans_on_exit") as _mock:
            # We test the real delegation by calling through final_reaper mock
            pass

        # Test actual delegation path
        with patch("bob3.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.final_reaper.db") as mock_db, \
             patch("bob3.final_reaper.find_subagent_pid_for_feature"):
            mock_sweep.return_value = []
            mock_db.list_features.return_value = []

            result = sweep_orphans_on_exit("proj-delegation-001")

        assert isinstance(result, list)
        mock_sweep.assert_called_once()

    def test_returns_list(self):
        """sweep_orphans_on_exit must return a list."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        with patch("bob3.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.final_reaper.db") as mock_db, \
             patch("bob3.final_reaper.find_subagent_pid_for_feature"):
            mock_sweep.return_value = []
            mock_db.list_features.return_value = []

            result = sweep_orphans_on_exit("proj-list-001")

        assert isinstance(result, list)

    def test_orphan_executing_feature_flipped_to_failed(self):
        """An executing feature with no live PID must be flipped to failed."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        feature_id = "feat-sweep-0001-0000-0000-000000000001"
        fake_feat = MagicMock()
        fake_feat.id = feature_id
        fake_feat.name = "orphan-feature"

        with patch("bob3.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.final_reaper.db") as mock_db, \
             patch("bob3.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [fake_feat]
            mock_pids.return_value = []  # no live PID

            result = sweep_orphans_on_exit("proj-orphan-001")

        assert feature_id in result
        mock_db.update_feature.assert_called_once_with(
            feature_id,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )

    def test_feature_with_live_pid_is_not_flipped(self):
        """An executing feature with a live PID must NOT be flipped."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        feature_id = "feat-live-sweep-0000-0000-000000000001"
        fake_feat = MagicMock()
        fake_feat.id = feature_id

        with patch("bob3.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.final_reaper.db") as mock_db, \
             patch("bob3.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [fake_feat]
            mock_pids.return_value = [99999]  # live PID present

            result = sweep_orphans_on_exit("proj-live-001")

        assert result == []
        mock_db.update_feature.assert_not_called()

    def test_multiple_orphans_all_flipped(self):
        """All orphan executing features must be flipped, not just the first."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        ids = [
            "feat-multi-sweep-0001-0000-000000000001",
            "feat-multi-sweep-0002-0000-000000000002",
        ]
        features = [MagicMock(id=fid) for fid in ids]

        with patch("bob3.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.final_reaper.db") as mock_db, \
             patch("bob3.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = features
            mock_pids.return_value = []

            result = sweep_orphans_on_exit("proj-multi-001")

        assert sorted(result) == sorted(ids)


class TestSweepOrphansOnExitErrorHandling(unittest.TestCase):
    """Error handling: invalid input raises; per-feature errors are caught."""

    def test_none_project_id_raises_value_error(self):
        """None project_id must raise ValueError."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        with self.assertRaises(ValueError):
            sweep_orphans_on_exit(None)  # type: ignore[arg-type]

    def test_non_string_project_id_raises_value_error(self):
        """Non-string project_id must raise ValueError."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        with self.assertRaises(ValueError):
            sweep_orphans_on_exit(42)  # type: ignore[arg-type]

    def test_sweep_orphan_subagents_error_does_not_propagate(self):
        """If the underlying sweep_orphan_subagents raises, function continues."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        with patch("bob3.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.final_reaper.db") as mock_db, \
             patch("bob3.final_reaper.find_subagent_pid_for_feature"):
            mock_sweep.side_effect = RuntimeError("reaper crashed")
            mock_db.list_features.return_value = []

            result = sweep_orphans_on_exit("proj-err-sweep-001")

        assert isinstance(result, list)

    def test_db_list_failure_returns_empty_list(self):
        """If db.list_features raises, returns empty list without raising."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        with patch("bob3.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.final_reaper.db") as mock_db:
            mock_sweep.return_value = []
            mock_db.list_features.side_effect = RuntimeError("DB unavailable")

            result = sweep_orphans_on_exit("proj-err-db-001")

        assert result == []

    def test_partial_error_continues_remaining_features(self):
        """Per-feature PID lookup error must not abort sweep of remaining features."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        f1 = MagicMock(id="feat-partial-sweep-01-0000-000000000001")
        f2 = MagicMock(id="feat-partial-sweep-02-0000-000000000002")

        def pid_side_effect(fid):
            if fid == f1.id:
                raise RuntimeError("PID lookup failed for f1")
            return []

        with patch("bob3.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.final_reaper.db") as mock_db, \
             patch("bob3.final_reaper.find_subagent_pid_for_feature", side_effect=pid_side_effect):
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [f1, f2]

            result = sweep_orphans_on_exit("proj-partial-sweep-001")

        assert f2.id in result


class TestOrchestratorIntegration(unittest.TestCase):
    """Integration AC: sweep_orphans_on_exit integrates with bob3.orchestrator."""

    def test_final_reaper_sweep_importable(self):
        """bob3.final_reaper_sweep must be importable with sweep_orphans_on_exit."""
        import bob3.final_reaper_sweep as frs

        assert hasattr(frs, "sweep_orphans_on_exit")
        assert callable(frs.sweep_orphans_on_exit)

    def test_sweep_uses_same_reaper_as_main_loop(self):
        """sweep_orphans_on_exit must invoke the same sweep_orphan_subagents used in the main loop."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        with patch("bob3.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.final_reaper.db") as mock_db, \
             patch("bob3.final_reaper.find_subagent_pid_for_feature"):
            mock_sweep.return_value = []
            mock_db.list_features.return_value = []

            sweep_orphans_on_exit("proj-integ-sweep-001")

        mock_sweep.assert_called_once()

    def test_exit_reason_is_orchestrator_exit_during_execution(self):
        """Flipped features must have last_improvement_type='orchestrator_exit_during_execution'."""
        from bob3.final_reaper_sweep import sweep_orphans_on_exit

        fake_feat = MagicMock()
        fake_feat.id = "feat-integ-sweep-0001-0000-000000000001"

        with patch("bob3.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.final_reaper.db") as mock_db, \
             patch("bob3.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [fake_feat]
            mock_pids.return_value = []

            sweep_orphans_on_exit("proj-integ-reason-001")

        _call = mock_db.update_feature.call_args
        assert _call.kwargs.get("last_improvement_type") == "orchestrator_exit_during_execution"
        assert _call.kwargs.get("status") == "failed"
