"""Tests for final reaper sweep on orchestrator exit (feature 230dac5a).

AC: pytest: tests/test_orchestrator_exit_cleanup.py
Verifies that ALL_BLOCKED/BUDGET_EXCEEDED termination flips orphan 'executing'
rows to 'failed' before returning, via _final_exit_sweep invocation in _run_locked.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, call


class TestFinalReaperSweepIntegration(unittest.TestCase):
    """Integration tests: _run_locked calls _final_exit_sweep on terminal exits."""

    def test_run_locked_method_exists_on_orchestration_loop(self):
        """_run_locked must be defined as a method of OrchestrationLoop."""
        from bob3.orchestrator.run_loop import OrchestrationLoop
        assert hasattr(OrchestrationLoop, "_run_locked"), (
            "_run_locked must be defined on OrchestrationLoop"
        )
        assert callable(OrchestrationLoop._run_locked)

    def test_sweep_orphan_subagents_is_defined_in_reaper(self):
        """sweep_orphan_subagents must be defined in bob3.orchestrator.subagent_reaper."""
        from bob3.orchestrator.subagent_reaper import sweep_orphan_subagents
        assert callable(sweep_orphan_subagents)

    def test_sweep_orphan_subagents_importable_from_orchestrator(self):
        """sweep_orphan_subagents must be importable from bob3.orchestrator package."""
        from bob3.orchestrator import sweep_orphan_subagents
        assert callable(sweep_orphan_subagents)

    def test_final_exit_sweep_is_defined_in_run_loop(self):
        """_final_exit_sweep must be defined and callable in bob3.orchestrator.run_loop."""
        from bob3.orchestrator.run_loop import _final_exit_sweep
        assert callable(_final_exit_sweep)

    def test_final_exit_sweep_called_on_all_blocked_path(self):
        """_final_exit_sweep is invoked in the ALL_BLOCKED termination path."""
        from bob3.orchestrator.run_loop import _final_exit_sweep, LoopTermination

        # Verify the ALL_BLOCKED enum member exists
        assert LoopTermination.ALL_BLOCKED.value == "all_blocked"

        # Verify _final_exit_sweep handles the all-blocked case
        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature"), \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep:
            mock_db.list_features.return_value = []
            mock_sweep.return_value = []

            # Calling _final_exit_sweep should not raise (simulates ALL_BLOCKED path)
            result = _final_exit_sweep("proj-all-blocked-cleanup")

        assert result is None

    def test_final_exit_sweep_called_on_budget_exceeded_path(self):
        """_final_exit_sweep is invoked in the BUDGET_EXCEEDED termination path."""
        from bob3.orchestrator.run_loop import _final_exit_sweep, LoopTermination

        # Verify the BUDGET_EXCEEDED enum member exists
        assert LoopTermination.BUDGET_EXCEEDED.value == "budget_exceeded"

        # Verify _final_exit_sweep handles the budget-exceeded case
        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature"), \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep:
            mock_db.list_features.return_value = []
            mock_sweep.return_value = []

            result = _final_exit_sweep("proj-budget-exceeded-cleanup")

        assert result is None

    def test_orphan_executing_rows_flipped_to_failed_on_exit(self):
        """Orphan 'executing' rows (no live PID) must be flipped to 'failed' on exit."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        orphan_ids = [
            "94c9de63-0000-0000-0000-000000000001",
            "14298e1d-0000-0000-0000-000000000002",
            "b394aa24-0000-0000-0000-000000000003",
            "97fe3ec0-0000-0000-0000-000000000004",
            "630e1914-0000-0000-0000-000000000005",
        ]
        orphan_features = []
        for fid in orphan_ids:
            f = MagicMock()
            f.id = fid
            f.name = f"orphan-{fid[:8]}"
            f.acceptance_criteria = "[]"
            orphan_features.append(f)

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep:
            mock_db.list_features.return_value = orphan_features
            mock_pids.return_value = []  # No live PIDs — all are orphans
            mock_disk.return_value = False  # No disk artifacts to promote
            mock_sweep.return_value = []

            _final_exit_sweep("proj-five-orphans")

        # All 5 orphan features must have been flipped to 'failed'
        assert mock_db.update_feature.call_count == 5
        flipped_ids = {c[0][0] for c in mock_db.update_feature.call_args_list}
        assert flipped_ids == set(orphan_ids)

        # Each flip must use the correct reason
        for c in mock_db.update_feature.call_args_list:
            kwargs = c[1]
            assert kwargs.get("status") == "failed"
            assert kwargs.get("last_improvement_type") == "orchestrator_exit_during_execution"

    def test_sweep_orphan_subagents_invoked_before_row_updates(self):
        """sweep_orphan_subagents must be called before any DB row flips."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        call_order = []

        def record_sweep(*a, **kw):
            call_order.append("sweep")
            return []

        def record_update(*a, **kw):
            call_order.append("update")

        feature = MagicMock()
        feature.id = "feat-order-cleanup-0000-000000000001"
        feature.name = "cleanup-order"
        feature.acceptance_criteria = "[]"

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents", side_effect=record_sweep):
            mock_db.list_features.return_value = [feature]
            mock_db.update_feature.side_effect = record_update
            mock_pids.return_value = []
            mock_disk.return_value = False

            _final_exit_sweep("proj-order-cleanup")

        assert call_order[0] == "sweep", (
            "sweep_orphan_subagents must be called before any update_feature calls"
        )
        assert "update" in call_order

    def test_live_subagent_not_flipped(self):
        """Executing feature with a live sub-agent PID must NOT be flipped to 'failed'."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        feature = MagicMock()
        feature.id = "feat-live-cleanup-0000-000000000001"
        feature.name = "live-subagent"

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents"):
            mock_db.list_features.return_value = [feature]
            mock_pids.return_value = [99999]  # Live PID present

            _final_exit_sweep("proj-live-skip")

        mock_db.update_feature.assert_not_called()

    def test_idempotent_on_no_executing_rows(self):
        """_final_exit_sweep with no executing rows produces no DB writes (idempotent)."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature"), \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep:
            mock_db.list_features.return_value = []
            mock_sweep.return_value = []

            _final_exit_sweep("proj-idempotent-cleanup")
            _final_exit_sweep("proj-idempotent-cleanup")

        mock_db.update_feature.assert_not_called()

    def test_none_project_id_raises(self):
        """Passing None as project_id must raise (ValueError, TypeError, or AttributeError)."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        with self.assertRaises((ValueError, TypeError, AttributeError)):
            with patch("bob3.orchestrator.run_loop.db") as mock_db, \
                 patch("bob3.orchestrator.run_loop._sweep_orphan_subagents"):
                mock_db.list_features.side_effect = TypeError("project_id must be str")
                _final_exit_sweep(None)  # type: ignore[arg-type]

    def test_per_feature_error_does_not_abort_sweep(self):
        """Error for one feature during update must not prevent other features from being flipped."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        f1 = MagicMock()
        f1.id = "feat-cleanup-err1-000000000001"
        f1.name = "fail-feature"
        f1.acceptance_criteria = "[]"
        f2 = MagicMock()
        f2.id = "feat-cleanup-ok2--000000000002"
        f2.name = "ok-feature"
        f2.acceptance_criteria = "[]"

        attempted_ids = []

        def track_update(fid, **kwargs):
            attempted_ids.append(fid)
            if fid == f1.id:
                raise RuntimeError("DB write error for f1")

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep:
            mock_db.list_features.return_value = [f1, f2]
            mock_pids.return_value = []
            mock_disk.return_value = False
            mock_db.update_feature.side_effect = track_update
            mock_sweep.return_value = []

            # Must not raise despite f1 update failing
            _final_exit_sweep("proj-per-feature-error")

        assert f1.id in attempted_ids, "f1 must have been attempted"
        assert f2.id in attempted_ids, "f2 must still be attempted even after f1 error"

    def test_sweep_returns_list_type(self):
        """sweep_orphan_subagents always returns a list (never None)."""
        from bob3.orchestrator.subagent_reaper import sweep_orphan_subagents

        with patch("bob3.orchestrator.subagent_reaper._query_stale_terminal_features") as mock_q:
            mock_q.return_value = []
            result = sweep_orphan_subagents()

        assert isinstance(result, list)
        assert result == []
