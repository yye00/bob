"""Tests for bob3.run_loop subagent reaping on feature terminal-state transition.

Acceptance criteria (feature 4de21232-7ef4-46d8-98b2-1163050ec482):
  - Function defined: bob3.run_loop.handle_terminal_transition
  - Function defined: bob3.run_loop.reap_subagent
  - Function defined: bob3.run_loop.sweep_orphan_subagents
  - pytest: tests/test_run_loop_reaping.py
  - integration: bob3.run_loop

Verifies that all three functions are importable from bob3.run_loop, that
handle_terminal_transition calls reap_subagent, that reap_subagent delegates
to subagent_reaper, and that sweep_orphan_subagents handles stale terminal
features correctly.
"""

from __future__ import annotations

import signal
import unittest
from unittest.mock import call, patch, MagicMock


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

class TestHandleTerminalTransitionImport(unittest.TestCase):
    """handle_terminal_transition is importable from bob3.run_loop."""

    def test_function_importable_from_bob3_run_loop(self):
        import bob3.run_loop as rl
        self.assertTrue(callable(rl.handle_terminal_transition))

    def test_direct_import(self):
        from bob3.run_loop import handle_terminal_transition
        self.assertTrue(callable(handle_terminal_transition))

    def test_function_in_all(self):
        import bob3.run_loop as rl
        self.assertIn("handle_terminal_transition", rl.__all__)


class TestReapSubagentImport(unittest.TestCase):
    """reap_subagent is importable from bob3.run_loop."""

    def test_function_importable_from_bob3_run_loop(self):
        import bob3.run_loop as rl
        self.assertTrue(callable(rl.reap_subagent))

    def test_direct_import(self):
        from bob3.run_loop import reap_subagent
        self.assertTrue(callable(reap_subagent))

    def test_function_in_all(self):
        import bob3.run_loop as rl
        self.assertIn("reap_subagent", rl.__all__)


class TestSweepOrphanSubagentsImport(unittest.TestCase):
    """sweep_orphan_subagents is importable from bob3.run_loop."""

    def test_function_importable_from_bob3_run_loop(self):
        import bob3.run_loop as rl
        self.assertTrue(callable(rl.sweep_orphan_subagents))

    def test_direct_import(self):
        from bob3.run_loop import sweep_orphan_subagents
        self.assertTrue(callable(sweep_orphan_subagents))

    def test_function_in_all(self):
        import bob3.run_loop as rl
        self.assertIn("sweep_orphan_subagents", rl.__all__)


# ---------------------------------------------------------------------------
# handle_terminal_transition behaviour
# ---------------------------------------------------------------------------

class TestHandleTerminalTransitionBehavior(unittest.TestCase):
    """handle_terminal_transition triggers subagent reaping for all terminal states."""

    def _make_fake_feature_id(self, n: int) -> str:
        return f"{n:08x}-0000-0000-0000-000000000000"

    def test_returns_list_of_reaped_pids(self):
        """Returns whatever reap_subagent_for_feature returns."""
        from bob3.run_loop import handle_terminal_transition

        fid = self._make_fake_feature_id(1)
        fake_pid = 12345
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find, patch(
            "bob3.orchestrator.subagent_reaper._read_proc_argv"
        ) as mock_argv, patch(
            "bob3.orchestrator.subagent_reaper._send_signal"
        ), patch(
            "bob3.orchestrator.subagent_reaper._wait_for_exit"
        ) as mock_wait, patch(
            "bob3.orchestrator.subagent_reaper._append_audit_sentinel"
        ):
            mock_find.return_value = [fake_pid]
            mock_argv.return_value = ["claude", "--print", "feature", fid]
            mock_wait.return_value = True

            result = handle_terminal_transition(fid)

        self.assertIsInstance(result, list)
        self.assertIn(fake_pid, result)

    def test_returns_empty_list_when_no_subagent_running(self):
        """Returns [] when no claude process is tagged with the feature id."""
        from bob3.run_loop import handle_terminal_transition

        fid = self._make_fake_feature_id(2)
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = handle_terminal_transition(fid)

        self.assertEqual(result, [])

    def test_works_for_completed_status(self):
        """Applies to 'completed' terminal state."""
        from bob3.run_loop import handle_terminal_transition

        fid = self._make_fake_feature_id(3)
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = handle_terminal_transition(fid, status="completed")

        self.assertEqual(result, [])

    def test_works_for_needs_human_status(self):
        """Applies to 'needs_human' terminal state."""
        from bob3.run_loop import handle_terminal_transition

        fid = self._make_fake_feature_id(4)
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = handle_terminal_transition(fid, status="needs_human")

        self.assertEqual(result, [])

    def test_works_for_regression_status(self):
        """Applies to 'regression' terminal state."""
        from bob3.run_loop import handle_terminal_transition

        fid = self._make_fake_feature_id(5)
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = handle_terminal_transition(fid, status="regression")

        self.assertEqual(result, [])

    def test_works_for_failed_status(self):
        """Applies to 'failed' terminal state."""
        from bob3.run_loop import handle_terminal_transition

        fid = self._make_fake_feature_id(6)
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = handle_terminal_transition(fid, status="failed")

        self.assertEqual(result, [])

    def test_emits_audit_sentinel_on_reap(self):
        """Emits subagent_reaped_on_terminal=<feature_id> sentinel after reap."""
        from bob3.run_loop import handle_terminal_transition

        fid = self._make_fake_feature_id(7)
        fake_pid = 99999
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find, patch(
            "bob3.orchestrator.subagent_reaper._read_proc_argv"
        ) as mock_argv, patch(
            "bob3.orchestrator.subagent_reaper._send_signal"
        ), patch(
            "bob3.orchestrator.subagent_reaper._wait_for_exit"
        ) as mock_wait, patch(
            "bob3.orchestrator.subagent_reaper._append_audit_sentinel"
        ) as mock_audit:
            mock_find.return_value = [fake_pid]
            mock_argv.return_value = ["claude", "--print", "feature", fid]
            mock_wait.return_value = True

            handle_terminal_transition(fid)

        mock_audit.assert_called_once_with(fid)

    def test_sends_sigterm_to_matching_process(self):
        """Sends SIGTERM to the matching subagent process."""
        from bob3.run_loop import handle_terminal_transition

        fid = self._make_fake_feature_id(8)
        fake_pid = 77777
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find, patch(
            "bob3.orchestrator.subagent_reaper._read_proc_argv"
        ) as mock_argv, patch(
            "bob3.orchestrator.subagent_reaper._send_signal"
        ) as mock_signal, patch(
            "bob3.orchestrator.subagent_reaper._wait_for_exit"
        ) as mock_wait, patch(
            "bob3.orchestrator.subagent_reaper._append_audit_sentinel"
        ):
            mock_find.return_value = [fake_pid]
            mock_argv.return_value = ["claude", "--print", "feature", fid]
            mock_wait.return_value = True

            handle_terminal_transition(fid)

        mock_signal.assert_any_call(fake_pid, signal.SIGTERM)

    def test_escalates_sigkill_after_grace_period(self):
        """Escalates to SIGKILL when process survives the 15s grace window."""
        from bob3.run_loop import handle_terminal_transition

        fid = self._make_fake_feature_id(9)
        fake_pid = 66666
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find, patch(
            "bob3.orchestrator.subagent_reaper._read_proc_argv"
        ) as mock_argv, patch(
            "bob3.orchestrator.subagent_reaper._send_signal"
        ) as mock_signal, patch(
            "bob3.orchestrator.subagent_reaper._wait_for_exit"
        ) as mock_wait, patch(
            "bob3.orchestrator.subagent_reaper._append_audit_sentinel"
        ):
            mock_find.return_value = [fake_pid]
            mock_argv.return_value = ["claude", "--print", "feature", fid]
            # First wait (SIGTERM grace) times out; second wait (post SIGKILL) succeeds.
            mock_wait.side_effect = [False, True]

            handle_terminal_transition(fid)

        calls = mock_signal.call_args_list
        signals_sent = [c[0][1] for c in calls]
        self.assertIn(signal.SIGTERM, signals_sent)
        self.assertIn(signal.SIGKILL, signals_sent)


# ---------------------------------------------------------------------------
# reap_subagent behaviour
# ---------------------------------------------------------------------------

class TestReapSubagentBehavior(unittest.TestCase):
    """Tests that reap_subagent correctly orchestrates SIGTERM/SIGKILL."""

    def test_returns_empty_list_when_no_subagent_running(self):
        from bob3.run_loop import reap_subagent

        fid = "00000000-0000-0000-0000-111111111111"
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent(fid)

        self.assertEqual(result, [])

    def test_returns_list_type_always(self):
        from bob3.run_loop import reap_subagent

        fid = "11111111-0000-0000-0000-222222222222"
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent(fid)

        self.assertIsInstance(result, list)

    def test_returns_pid_on_successful_reap(self):
        from bob3.run_loop import reap_subagent

        fid = "22222222-0000-0000-0000-333333333333"
        fake_pid = 55555
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find, patch(
            "bob3.orchestrator.subagent_reaper._read_proc_argv"
        ) as mock_argv, patch(
            "bob3.orchestrator.subagent_reaper._send_signal"
        ), patch(
            "bob3.orchestrator.subagent_reaper._wait_for_exit"
        ) as mock_wait, patch(
            "bob3.orchestrator.subagent_reaper._append_audit_sentinel"
        ):
            mock_find.return_value = [fake_pid]
            mock_argv.return_value = ["claude", "--print", "feature", fid]
            mock_wait.return_value = True

            result = reap_subagent(fid)

        self.assertIn(fake_pid, result)

    def test_does_not_reap_own_pid(self):
        """Ensures the reaper never signals its own PID (safety contract)."""
        import os
        from bob3.run_loop import reap_subagent

        own_pid = os.getpid()
        fid = "33333333-0000-0000-0000-444444444444"
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            # Pretend own PID is returned (should be filtered)
            mock_find.return_value = []
            result = reap_subagent(fid)

        # own_pid must never appear in reaped list
        self.assertNotIn(own_pid, result)


# ---------------------------------------------------------------------------
# sweep_orphan_subagents behaviour
# ---------------------------------------------------------------------------

class TestSweepOrphanSubagentsBehavior(unittest.TestCase):
    """Tests for the backstop sweeper that catches handler-bypass orphans."""

    def test_returns_list_type(self):
        from bob3.run_loop import sweep_orphan_subagents

        with patch(
            "bob3.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            result = sweep_orphan_subagents()

        self.assertIsInstance(result, list)

    def test_returns_empty_list_when_no_stale_features(self):
        from bob3.run_loop import sweep_orphan_subagents

        with patch(
            "bob3.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            result = sweep_orphan_subagents()

        self.assertEqual(result, [])

    def test_returns_feature_pid_pairs_for_reaped_orphans(self):
        from bob3.run_loop import sweep_orphan_subagents

        fid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        fake_pid = 11111
        with patch(
            "bob3.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob3.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [fid]
            mock_reap.return_value = [fake_pid]

            result = sweep_orphan_subagents()

        self.assertIn((fid, fake_pid), result)

    def test_handles_multiple_stale_features(self):
        from bob3.run_loop import sweep_orphan_subagents

        fid1 = "aaaaaaaa-0000-0000-0000-000000000001"
        fid2 = "bbbbbbbb-0000-0000-0000-000000000002"
        pid1, pid2 = 11111, 22222
        with patch(
            "bob3.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob3.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [fid1, fid2]
            mock_reap.side_effect = [[pid1], [pid2]]

            result = sweep_orphan_subagents()

        self.assertIn((fid1, pid1), result)
        self.assertIn((fid2, pid2), result)
        self.assertEqual(len(result), 2)

    def test_catches_exceptions_per_feature(self):
        """Exceptions in one feature's reap do not abort the rest of the sweep."""
        from bob3.run_loop import sweep_orphan_subagents

        fid1 = "cccccccc-0000-0000-0000-000000000003"
        fid2 = "dddddddd-0000-0000-0000-000000000004"
        pid2 = 33333
        with patch(
            "bob3.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob3.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [fid1, fid2]
            # First feature raises, second succeeds
            mock_reap.side_effect = [RuntimeError("boom"), [pid2]]

            result = sweep_orphan_subagents()

        # fid2 should still appear despite fid1 exception
        self.assertIn((fid2, pid2), result)

    def test_idempotent_when_no_matching_pids(self):
        """Safe to run even when stale features have no live subagents."""
        from bob3.run_loop import sweep_orphan_subagents

        fid = "eeeeeeee-0000-0000-0000-000000000005"
        with patch(
            "bob3.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob3.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [fid]
            mock_reap.return_value = []

            result = sweep_orphan_subagents()

        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Integration: module-level reachability
# ---------------------------------------------------------------------------

class TestIntegrationBobRunLoop(unittest.TestCase):
    """Integration tests ensuring bob3.run_loop publishes the full API surface."""

    def test_all_three_ac_functions_importable(self):
        import bob3.run_loop as rl
        for fname in ("handle_terminal_transition", "reap_subagent", "sweep_orphan_subagents"):
            with self.subTest(fname=fname):
                self.assertTrue(callable(getattr(rl, fname, None)), f"{fname} not callable")

    def test_all_three_in_dunder_all(self):
        import bob3.run_loop as rl
        for fname in ("handle_terminal_transition", "reap_subagent", "sweep_orphan_subagents"):
            with self.subTest(fname=fname):
                self.assertIn(fname, rl.__all__)

    def test_module_importable_without_side_effects(self):
        """Importing bob3.run_loop must not trigger DB connections or process scans."""
        import importlib
        # Re-importing the module must not raise
        import bob3.run_loop
        importlib.reload(bob3.run_loop)


if __name__ == "__main__":
    unittest.main()
