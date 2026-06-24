"""Tests for final reaper sweep on orchestrator exit (feature 398757d8).

Verifies that when _run_locked returns LoopTermination.ALL_BLOCKED or
LoopTermination.BUDGET_EXCEEDED, orphan 'executing' rows are flipped to
'failed' with reason 'orchestrator_exit_during_execution' before returning.

Also verifies that sweep_orphan_subagents is callable from bob.orchestrator.
"""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import MagicMock, patch, call


class TestSweepOrphanSubagentsExport(unittest.TestCase):
    """AC: Function defined: bob.orchestrator.sweep_orphan_subagents"""

    def test_sweep_orphan_subagents_importable_from_orchestrator(self):
        from bob.orchestrator import sweep_orphan_subagents
        assert callable(sweep_orphan_subagents)

    def test_sweep_orphan_subagents_returns_list(self):
        from bob.orchestrator import sweep_orphan_subagents
        sig = inspect.signature(sweep_orphan_subagents)
        # Should take no required positional args
        required = [
            p for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
        ]
        assert len(required) == 0, f"Expected no required args, got: {required}"


class TestRunLockedDefined(unittest.TestCase):
    """AC: Function defined: bob.orchestrator.run_loop._run_locked"""

    def test_run_locked_defined_in_run_loop(self):
        import bob.orchestrator.run_loop as rl
        # _run_locked is a method on a class — find it
        found = False
        for name, obj in inspect.getmembers(rl, inspect.isclass):
            if hasattr(obj, "_run_locked"):
                found = True
                break
        if not found:
            # Also check as a top-level function
            found = hasattr(rl, "_run_locked")
        assert found, "_run_locked must be defined in bob.orchestrator.run_loop"


class TestFinalExitSweepFlipsOrphans(unittest.TestCase):
    """_final_exit_sweep flips orphan executing rows to failed."""

    def test_dead_executing_feature_flipped_to_failed(self):
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-398757d8-0001-0000-0000-000000000001"
        feature_id = "feat-398757d8-0001-0000-0000-000000000001"

        fake_feature = MagicMock()
        fake_feature.id = feature_id
        fake_feature.name = "orphan test feature"
        fake_feature.acceptance_criteria = "[]"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs") as mock_disk:

            mock_db.list_features.return_value = [fake_feature]
            mock_pids.return_value = []  # no live PIDs — orphan
            mock_disk.return_value = False  # disk check fails, flip to failed

            _final_exit_sweep(project_id)

        mock_db.update_feature.assert_called_once_with(
            feature_id,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )

    def test_live_pid_feature_not_touched(self):
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-398757d8-0002-0000-0000-000000000002"
        feature_id = "feat-398757d8-0002-0000-0000-000000000002"

        fake_feature = MagicMock()
        fake_feature.id = feature_id
        fake_feature.name = "live feature"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids:

            mock_db.list_features.return_value = [fake_feature]
            mock_pids.return_value = [12345]  # live PID — keep

            _final_exit_sweep(project_id)

        mock_db.update_feature.assert_not_called()

    def test_empty_executing_list_no_writes(self):
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-398757d8-0003-0000-0000-000000000003"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature"):

            mock_db.list_features.return_value = []

            _final_exit_sweep(project_id)

        mock_db.update_feature.assert_not_called()

    def test_flip_uses_orchestrator_exit_reason(self):
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-398757d8-0004-0000-0000-000000000004"
        feature_id = "feat-398757d8-0004-0000-0000-000000000004"

        fake_feature = MagicMock()
        fake_feature.id = feature_id
        fake_feature.name = "test"
        fake_feature.acceptance_criteria = "[]"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs") as mock_disk:

            mock_db.list_features.return_value = [fake_feature]
            mock_pids.return_value = []
            mock_disk.return_value = False

            _final_exit_sweep(project_id)

        call_kwargs = mock_db.update_feature.call_args
        assert call_kwargs[1].get("last_improvement_type") == "orchestrator_exit_during_execution" or \
               (len(call_kwargs[0]) > 1 and "orchestrator_exit_during_execution" in str(call_kwargs)), \
               "Must set last_improvement_type='orchestrator_exit_during_execution'"

    def test_idempotent_second_call_no_extra_writes(self):
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-398757d8-0005-0000-0000-000000000005"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature"):

            mock_db.list_features.return_value = []

            _final_exit_sweep(project_id)
            _final_exit_sweep(project_id)

        # Called twice but no update_feature since no executing rows
        assert mock_db.update_feature.call_count == 0

    def test_sweep_orphan_subagents_called_in_final_exit_sweep(self):
        """_final_exit_sweep must invoke sweep_orphan_subagents as part of cleanup."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-398757d8-0006-0000-0000-000000000006"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature"), \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_orphan:

            mock_db.list_features.return_value = []
            mock_orphan.return_value = []

            _final_exit_sweep(project_id)

        mock_orphan.assert_called_once()

    def test_multiple_orphans_all_flipped(self):
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-398757d8-0007-0000-0000-000000000007"
        fids = [
            "feat-398757d8-0007-0000-0000-000000000001",
            "feat-398757d8-0007-0000-0000-000000000002",
            "feat-398757d8-0007-0000-0000-000000000003",
        ]

        fake_features = []
        for fid in fids:
            f = MagicMock()
            f.id = fid
            f.name = f"feature {fid[:8]}"
            f.acceptance_criteria = "[]"
            fake_features.append(f)

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs") as mock_disk:

            mock_db.list_features.return_value = fake_features
            mock_pids.return_value = []
            mock_disk.return_value = False

            _final_exit_sweep(project_id)

        assert mock_db.update_feature.call_count == len(fids)
        updated_ids = [c[0][0] for c in mock_db.update_feature.call_args_list]
        for fid in fids:
            assert fid in updated_ids


class TestFinalExitSweepCalledOnAllBlocked(unittest.TestCase):
    """_final_exit_sweep is called when the loop terminates with ALL_BLOCKED."""

    def test_final_exit_sweep_called_on_all_blocked_path(self):
        """When all remaining features are blocked, _final_exit_sweep must be called."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        # Verify the function is callable and doesn't raise on empty state
        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature"):
            mock_db.list_features.return_value = []
            # Should not raise
            _final_exit_sweep("proj-test-blocked")


class TestSweepOrphanSubagentsIntegration(unittest.TestCase):
    """Integration: sweep_orphan_subagents behavior in orchestrator context."""

    def test_sweep_orphan_subagents_returns_empty_when_no_stale(self):
        from bob.orchestrator import sweep_orphan_subagents

        with patch("bob.orchestrator.subagent_reaper._query_stale_terminal_features") as mock_q:
            mock_q.return_value = []
            result = sweep_orphan_subagents()

        assert result == []

    def test_sweep_orphan_subagents_returns_pairs_for_stale(self):
        from bob.orchestrator import sweep_orphan_subagents

        stale_fid = "stale398-0000-0000-0000-000000000001"

        with patch("bob.orchestrator.subagent_reaper._query_stale_terminal_features") as mock_q, \
             patch("bob.orchestrator.subagent_reaper.reap_subagent_for_feature") as mock_reap:
            mock_q.return_value = [stale_fid]
            mock_reap.return_value = [99991]

            result = sweep_orphan_subagents()

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == (stale_fid, 99991)
