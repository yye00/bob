"""Boundary tests for final reaper sweep on orchestrator exit (feature 398757d8).

AC: pytest: tests/test_final_reaper_sweep_on_orchestrator_exit_boundary.py —
empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class TestFinalExitSweepBoundary(unittest.TestCase):
    """Boundary cases for _final_exit_sweep — no input raises, well-defined output."""

    def test_empty_project_id_does_not_raise(self):
        """Passing empty string as project_id must not raise — returns silently."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature"), \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_orphan:
            mock_db.list_features.return_value = []
            mock_orphan.return_value = []
            # Must not raise
            _final_exit_sweep("")

    def test_zero_executing_features_returns_silently(self):
        """When there are zero executing features, _final_exit_sweep returns None."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature"), \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_orphan:
            mock_db.list_features.return_value = []
            mock_orphan.return_value = []
            result = _final_exit_sweep("proj-boundary-zero")

        assert result is None

    def test_minimum_input_single_feature_no_raise(self):
        """Minimum case: one executing feature with missing PID — no exception raised."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        fake_feature = MagicMock()
        fake_feature.id = "feat-boundary-0001-0000-0000-000000000001"
        fake_feature.name = "boundary-test"
        fake_feature.acceptance_criteria = "[]"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_orphan:

            mock_db.list_features.return_value = [fake_feature]
            mock_pids.return_value = []
            mock_disk.return_value = False
            mock_orphan.return_value = []

            # Must not raise
            result = _final_exit_sweep("proj-boundary-one")

        assert result is None

    def test_db_list_features_exception_does_not_raise(self):
        """If db.list_features raises, _final_exit_sweep must handle it gracefully."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_orphan:
            mock_db.list_features.side_effect = RuntimeError("DB unavailable")
            mock_orphan.return_value = []

            # Must not propagate the exception
            result = _final_exit_sweep("proj-boundary-dberror")

        assert result is None

    def test_pid_lookup_exception_continues_to_next_feature(self):
        """If PID lookup raises for one feature, sweep continues to remaining features."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        f1 = MagicMock()
        f1.id = "feat-boundary-err1-0000-0000-000000000001"
        f1.name = "err feature"
        f2 = MagicMock()
        f2.id = "feat-boundary-ok2-0000-0000-000000000002"
        f2.name = "ok feature"
        f2.acceptance_criteria = "[]"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_orphan:

            mock_db.list_features.return_value = [f1, f2]
            mock_pids.side_effect = [RuntimeError("PID lookup failed"), []]
            mock_disk.return_value = False
            mock_orphan.return_value = []

            # Must not raise despite first feature erroring
            _final_exit_sweep("proj-boundary-continue")

        # Second feature (f2) should still be flipped
        updated_ids = [c[0][0] for c in mock_db.update_feature.call_args_list]
        assert f2.id in updated_ids

    def test_sweep_orphan_subagents_boundary_no_stale(self):
        """sweep_orphan_subagents with zero stale features returns empty list, not None."""
        from bob.orchestrator import sweep_orphan_subagents

        with patch("bob.orchestrator.subagent_reaper._query_stale_terminal_features") as mock_q:
            mock_q.return_value = []
            result = sweep_orphan_subagents()

        assert result == []
        assert isinstance(result, list)

    def test_final_exit_sweep_returns_none_not_undefined(self):
        """_final_exit_sweep return value is always None (not undefined/missing)."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature"), \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_orphan:
            mock_db.list_features.return_value = []
            mock_orphan.return_value = []
            ret = _final_exit_sweep("proj-boundary-ret")

        assert ret is None
