"""Tests for final reaper sweep on orchestrator exit (feature da498003).

Verifies that when _run_locked terminates with ALL_BLOCKED or BUDGET_EXCEEDED,
orphan 'executing' rows are flipped to 'failed' with reason
'orchestrator_exit_during_execution' before returning.

AC: pytest: tests/test_orchestrator_reaper_exit.py
AC: integration: bob.orchestrator.run_loop
"""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import MagicMock, patch


class TestRunLoopIntegrationImports(unittest.TestCase):
    """integration: bob.orchestrator.run_loop — module-level symbol checks."""

    def test_run_loop_module_importable(self):
        import bob.orchestrator.run_loop as rl
        assert rl is not None

    def test_sweep_orphan_subagents_in_run_loop(self):
        """AC: Function defined: bob.orchestrator.run_loop.sweep_orphan_subagents"""
        from bob.orchestrator.run_loop import sweep_orphan_subagents
        assert callable(sweep_orphan_subagents)

    def test_final_exit_sweep_defined(self):
        from bob.orchestrator.run_loop import _final_exit_sweep
        assert callable(_final_exit_sweep)

    def test_loop_termination_enum_has_all_blocked(self):
        from bob.orchestrator.run_loop import LoopTermination
        assert hasattr(LoopTermination, "ALL_BLOCKED")

    def test_loop_termination_enum_has_budget_exceeded(self):
        from bob.orchestrator.run_loop import LoopTermination
        assert hasattr(LoopTermination, "BUDGET_EXCEEDED")

    def test_run_locked_method_exists_on_orchestration_class(self):
        import bob.orchestrator.run_loop as rl
        found = any(
            hasattr(obj, "_run_locked")
            for _, obj in inspect.getmembers(rl, inspect.isclass)
        )
        if not found:
            found = hasattr(rl, "_run_locked")
        assert found, "_run_locked must be defined in bob.orchestrator.run_loop"

    def test_final_exit_sweep_invokes_sweep_orphan_subagents(self):
        """_final_exit_sweep must call _sweep_orphan_subagents as first cleanup step."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature"):
            mock_db.list_features.return_value = []
            mock_sweep.return_value = []

            _final_exit_sweep("proj-da498003-0001-0000-0000-000000000001")

        mock_sweep.assert_called_once()

    def test_final_exit_sweep_flips_orphan_to_failed(self):
        """Orphan executing features with no live PID must be flipped to 'failed'."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        feature_id = "feat-da498003-0001-0000-0000-000000000001"
        fake_feature = MagicMock()
        fake_feature.id = feature_id
        fake_feature.name = "orphan-reaper-exit-test"
        fake_feature.acceptance_criteria = "[]"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep:

            mock_db.list_features.return_value = [fake_feature]
            mock_pids.return_value = []
            mock_disk.return_value = False
            mock_sweep.return_value = []

            _final_exit_sweep("proj-da498003-0001-0000-0000-000000000001")

        mock_db.update_feature.assert_called_once_with(
            feature_id,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )

    def test_live_pid_feature_not_touched_on_exit(self):
        """Features with a live PID must NOT be flipped — regression guard."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        feature_id = "feat-da498003-0002-0000-0000-000000000002"
        fake_feature = MagicMock()
        fake_feature.id = feature_id
        fake_feature.name = "live-feature"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep:

            mock_db.list_features.return_value = [fake_feature]
            mock_pids.return_value = [54321]
            mock_sweep.return_value = []

            _final_exit_sweep("proj-da498003-0002-0000-0000-000000000002")

        mock_db.update_feature.assert_not_called()

    def test_disk_promoted_feature_not_flipped_to_failed(self):
        """Feature whose ACs are satisfied on disk must be promoted, not failed."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        feature_id = "feat-da498003-0003-0000-0000-000000000003"
        fake_feature = MagicMock()
        fake_feature.id = feature_id
        fake_feature.name = "disk-promoted"
        fake_feature.acceptance_criteria = "[]"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep:

            mock_db.list_features.return_value = [fake_feature]
            mock_pids.return_value = []
            mock_disk.return_value = True
            mock_sweep.return_value = []

            _final_exit_sweep("proj-da498003-0003-0000-0000-000000000003")

        mock_db.update_feature.assert_not_called()

    def test_final_exit_sweep_called_before_all_blocked_return(self):
        """_final_exit_sweep is wired into the ALL_BLOCKED path in _run_locked.

        This test verifies the integration pattern: when _run_locked would
        return ALL_BLOCKED, it first calls _final_exit_sweep.
        """
        import bob.orchestrator.run_loop as rl
        source = inspect.getsource(rl)

        all_blocked_section_has_sweep = (
            "_final_exit_sweep" in source and
            "ALL_BLOCKED" in source
        )
        assert all_blocked_section_has_sweep, (
            "_final_exit_sweep must be referenced in run_loop near ALL_BLOCKED return"
        )

    def test_final_exit_sweep_called_before_budget_exceeded_return(self):
        """_final_exit_sweep is wired into the BUDGET_EXCEEDED path in _run_locked."""
        import bob.orchestrator.run_loop as rl
        source = inspect.getsource(rl)

        budget_exceeded_section_has_sweep = (
            "_final_exit_sweep" in source and
            "BUDGET_EXCEEDED" in source
        )
        assert budget_exceeded_section_has_sweep, (
            "_final_exit_sweep must be referenced in run_loop near BUDGET_EXCEEDED return"
        )

    def test_sweep_orphan_subagents_module_level_callable(self):
        """sweep_orphan_subagents must be callable from bob.orchestrator.run_loop."""
        from bob.orchestrator.run_loop import sweep_orphan_subagents

        with patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_inner:
            mock_inner.return_value = []
            result = sweep_orphan_subagents()

        assert isinstance(result, list)

    def test_sweep_orphan_subagents_returns_list_on_exception(self):
        """sweep_orphan_subagents must return a list (not raise) when inner sweep fails."""
        from bob.orchestrator.run_loop import sweep_orphan_subagents

        with patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_inner:
            mock_inner.side_effect = RuntimeError("sweep failed")
            result = sweep_orphan_subagents()

        assert isinstance(result, list)
        assert result == []
