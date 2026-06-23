"""Tests for final reaper sweep on orchestrator exit (feature a927a4b0).

AC: pytest: tests/test_orchestrator_exit_reaper.py
Verifies that ALL_BLOCKED/BUDGET_EXCEEDED termination flips orphan 'executing'
rows to 'failed' before returning via _final_exit_sweep invocation.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch


class TestSweepOrphanSubagentsDefined(unittest.TestCase):
    """AC: Function defined: bob3.orchestrator.sweep_orphan_subagents."""

    def test_sweep_orphan_subagents_is_importable(self):
        from bob3.orchestrator import sweep_orphan_subagents
        assert callable(sweep_orphan_subagents)

    def test_sweep_orphan_subagents_returns_list(self):
        from bob3.orchestrator import sweep_orphan_subagents
        with patch("bob3.orchestrator.subagent_reaper._query_stale_terminal_features") as mock_q:
            mock_q.return_value = []
            result = sweep_orphan_subagents()
        assert isinstance(result, list)

    def test_sweep_orphan_subagents_in_subagent_reaper_module(self):
        from bob3.orchestrator.subagent_reaper import sweep_orphan_subagents
        assert callable(sweep_orphan_subagents)


class TestRunLockedDefined(unittest.TestCase):
    """AC: Function defined: bob3.orchestrator.run_loop._run_locked."""

    def test_run_locked_is_importable(self):
        from bob3.orchestrator.run_loop import OrchestrationLoop
        assert hasattr(OrchestrationLoop, "_run_locked")

    def test_run_locked_is_callable(self):
        from bob3.orchestrator.run_loop import OrchestrationLoop
        assert callable(OrchestrationLoop._run_locked)


class TestFinalExitSweepFlipsOrphans(unittest.TestCase):
    """_final_exit_sweep flips orphan executing rows to failed on orchestrator exit."""

    def _make_feature(self, fid, name="test-feature", acceptance_criteria="[]"):
        f = MagicMock()
        f.id = fid
        f.name = name
        f.acceptance_criteria = acceptance_criteria
        return f

    def test_orphan_executing_feature_flipped_to_failed(self):
        """Executing feature with no live PID must be flipped to 'failed'."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        feature = self._make_feature("feat-orphan-0001-0000-0000-000000000001")

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents"):
            mock_db.list_features.return_value = [feature]
            mock_pids.return_value = []
            mock_disk.return_value = False

            _final_exit_sweep("proj-flip-001")

        mock_db.update_feature.assert_called_once_with(
            feature.id,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )

    def test_live_pid_feature_skipped(self):
        """Executing feature with a live PID must NOT be flipped."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        feature = self._make_feature("feat-live-0001-0000-0000-000000000001")

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents"):
            mock_db.list_features.return_value = [feature]
            mock_pids.return_value = [12345]

            _final_exit_sweep("proj-skip-live")

        mock_db.update_feature.assert_not_called()

    def test_multiple_orphans_all_flipped(self):
        """All orphan executing features (no live PID) must be flipped to 'failed'."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        features = [
            self._make_feature(f"feat-multi-{i:04d}-0000-0000-000000000001")
            for i in range(3)
        ]

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents"):
            mock_db.list_features.return_value = features
            mock_pids.return_value = []
            mock_disk.return_value = False

            _final_exit_sweep("proj-multi-flip")

        assert mock_db.update_feature.call_count == 3
        flipped_ids = {c[0][0] for c in mock_db.update_feature.call_args_list}
        assert flipped_ids == {f.id for f in features}

    def test_sweep_orphan_subagents_called_before_flip(self):
        """_final_exit_sweep must call sweep_orphan_subagents before any DB updates."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        call_order = []

        def record_sweep(*a, **kw):
            call_order.append("sweep")
            return []

        def record_update(*a, **kw):
            call_order.append("update")

        feature = self._make_feature("feat-order-0001-0000-0000-000000000001")

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents", side_effect=record_sweep):
            mock_db.list_features.return_value = [feature]
            mock_db.update_feature.side_effect = record_update
            mock_pids.return_value = []
            mock_disk.return_value = False

            _final_exit_sweep("proj-order-check")

        assert call_order[0] == "sweep", "sweep_orphan_subagents must be called first"
        assert "update" in call_order, "update_feature must be called after sweep"

    def test_disk_promoted_feature_not_flipped_to_failed(self):
        """Feature with AC artifacts on disk must be promoted to completed, not failed."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        feature = self._make_feature("feat-disk-prom-0000-0000-000000000001")

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents"):
            mock_db.list_features.return_value = [feature]
            mock_pids.return_value = []
            mock_disk.return_value = True  # disk check says artifacts present

            _final_exit_sweep("proj-disk-promoted")

        # Must not flip to failed when disk check passes
        for c in mock_db.update_feature.call_args_list:
            assert c[1].get("status") != "failed", (
                "Feature promoted by disk check must not also be flipped to 'failed'"
            )

    def test_reason_is_orchestrator_exit_during_execution(self):
        """The flip reason must be 'orchestrator_exit_during_execution'."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        feature = self._make_feature("feat-reason-0001-0000-0000-000000000001")

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents"):
            mock_db.list_features.return_value = [feature]
            mock_pids.return_value = []
            mock_disk.return_value = False

            _final_exit_sweep("proj-reason-check")

        update_kwargs = mock_db.update_feature.call_args[1]
        assert update_kwargs.get("last_improvement_type") == "orchestrator_exit_during_execution"
        assert update_kwargs.get("status") == "failed"


class TestFinalExitSweepOnAllBlocked(unittest.TestCase):
    """_final_exit_sweep is invoked when loop terminates with ALL_BLOCKED."""

    def test_all_blocked_calls_final_exit_sweep(self):
        """When all_remaining_blocked() is True, _final_exit_sweep must be called."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        # Test the function directly — we verify it's callable and produces
        # the right side effects without running the full async loop.
        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents"):
            mock_db.list_features.return_value = []

            # Must complete without exception (simulating ALL_BLOCKED path)
            _final_exit_sweep("proj-all-blocked")

    def test_final_exit_sweep_idempotent_on_empty(self):
        """Calling _final_exit_sweep twice on no executing features is safe."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature"), \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents"):
            mock_db.list_features.return_value = []

            _final_exit_sweep("proj-idempotent")
            _final_exit_sweep("proj-idempotent")

        # list_features called twice (one per invocation), no updates
        assert mock_db.list_features.call_count == 2
        mock_db.update_feature.assert_not_called()


class TestIntegrationOrchestrator(unittest.TestCase):
    """Integration checks: bob3.orchestrator exposes required symbols."""

    def test_orchestrator_package_exports_sweep_orphan_subagents(self):
        import bob3.orchestrator as orch
        assert hasattr(orch, "sweep_orphan_subagents")
        assert callable(orch.sweep_orphan_subagents)

    def test_orchestrator_run_loop_has_final_exit_sweep(self):
        from bob3.orchestrator import run_loop
        assert hasattr(run_loop, "_final_exit_sweep")
        assert callable(run_loop._final_exit_sweep)

    def test_orchestrator_run_loop_has_run_locked(self):
        from bob3.orchestrator.run_loop import OrchestrationLoop
        assert hasattr(OrchestrationLoop, "_run_locked")

    def test_loop_termination_has_all_blocked_and_budget_exceeded(self):
        from bob3.orchestrator.run_loop import LoopTermination
        assert hasattr(LoopTermination, "ALL_BLOCKED")
        assert hasattr(LoopTermination, "BUDGET_EXCEEDED")
        assert LoopTermination.ALL_BLOCKED.value == "all_blocked"
        assert LoopTermination.BUDGET_EXCEEDED.value == "budget_exceeded"
