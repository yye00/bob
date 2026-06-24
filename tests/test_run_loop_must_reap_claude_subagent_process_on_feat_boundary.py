"""Boundary tests for bob.run_loop subagent reaping functions.

AC: pytest: tests/test_run_loop_must_reap_claude_subagent_process_on_feat_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising
    (boundary case)

Tests boundary inputs to sigterm_subagent_on_terminal_state and
sigkill_orphan_subagents_sweeper: empty string feature_id, zero stale_minutes,
and other minimum inputs must return a well-defined result rather than raising.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch


class TestSigtermSubagentOnTerminalStateBoundary(unittest.TestCase):
    """Boundary tests for sigterm_subagent_on_terminal_state."""

    def test_empty_feature_id_returns_empty_list(self):
        """Empty string feature_id returns [] without raising."""
        from bob.run_loop import sigterm_subagent_on_terminal_state

        result = sigterm_subagent_on_terminal_state("")
        self.assertEqual(result, [])

    def test_empty_feature_id_does_not_call_reaper(self):
        """Empty feature_id short-circuits before calling reap_subagent_for_feature."""
        from bob.run_loop import sigterm_subagent_on_terminal_state

        with patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            result = sigterm_subagent_on_terminal_state("")

        self.assertEqual(result, [])
        mock_reap.assert_not_called()

    def test_feature_id_with_no_matching_process_returns_empty_list(self):
        """Valid feature_id with no running process returns []."""
        from bob.run_loop import sigterm_subagent_on_terminal_state

        fake_fid = "00000000-0000-0000-0000-000000000000"
        with patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = []
            result = sigterm_subagent_on_terminal_state(fake_fid)

        self.assertEqual(result, [])

    def test_returns_list_of_ints_on_success(self):
        """Valid feature_id with matching process returns list of int PIDs."""
        from bob.run_loop import sigterm_subagent_on_terminal_state

        fake_fid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        fake_pid = 12345
        with patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [fake_pid]
            result = sigterm_subagent_on_terminal_state(fake_fid)

        self.assertIsInstance(result, list)
        self.assertIn(fake_pid, result)


class TestSigkillOrphanSubagentsSweeperBoundary(unittest.TestCase):
    """Boundary tests for sigkill_orphan_subagents_sweeper."""

    def test_none_stale_minutes_returns_list(self):
        """stale_minutes=None uses default threshold and returns a list."""
        from bob.run_loop import sigkill_orphan_subagents_sweeper

        with patch(
            "bob.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = sigkill_orphan_subagents_sweeper(None)

        self.assertIsInstance(result, list)

    def test_zero_stale_minutes_does_not_raise(self):
        """stale_minutes=0 is a valid minimum and does not raise."""
        from bob.run_loop import sigkill_orphan_subagents_sweeper

        with patch(
            "bob.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = sigkill_orphan_subagents_sweeper(0)

        self.assertIsInstance(result, list)

    def test_no_args_returns_list(self):
        """Calling with no arguments returns a list (uses default stale_minutes)."""
        from bob.run_loop import sigkill_orphan_subagents_sweeper

        with patch(
            "bob.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = sigkill_orphan_subagents_sweeper()

        self.assertIsInstance(result, list)

    def test_no_orphans_returns_empty_list(self):
        """When there are no orphan subagents, returns an empty list."""
        from bob.run_loop import sigkill_orphan_subagents_sweeper

        with patch(
            "bob.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = sigkill_orphan_subagents_sweeper()

        self.assertEqual(result, [])

    def test_returns_tuples_on_orphan_found(self):
        """When orphans are found, returns list of (feature_id, pid) tuples."""
        from bob.run_loop import sigkill_orphan_subagents_sweeper

        fake_fid = "deadbeef-0000-0000-0000-000000000001"
        fake_pid = 99999
        with patch(
            "bob.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = [(fake_fid, fake_pid)]
            result = sigkill_orphan_subagents_sweeper()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], (fake_fid, fake_pid))


if __name__ == "__main__":
    unittest.main()
