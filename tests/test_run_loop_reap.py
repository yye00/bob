"""Tests for bob3.run_loop.reap_subagent (feature dcb4ffe6).

Acceptance criteria:
  - File exists: src/bob3/run_loop.py
  - Function defined: bob3.run_loop.reap_subagent
  - pytest: tests/test_run_loop_reap.py
  - integration: bob3.run_loop

Verifies that reap_subagent is importable from bob3.run_loop and correctly
delegates to the subagent_reaper for SIGTERM/SIGKILL orchestration on
feature terminal-state transitions.
"""

from __future__ import annotations

import signal
import time
import unittest
from unittest.mock import call, patch


class TestReapSubagentImport(unittest.TestCase):
    """Verifies reap_subagent is importable and callable from bob3.run_loop."""

    def test_function_importable_from_bob3_run_loop(self):
        import bob3.run_loop as rl
        self.assertTrue(callable(rl.reap_subagent))

    def test_function_in_all(self):
        import bob3.run_loop as rl
        self.assertIn("reap_subagent", rl.__all__)

    def test_direct_import(self):
        from bob3.run_loop import reap_subagent
        self.assertTrue(callable(reap_subagent))


class TestReapSubagentBehavior(unittest.TestCase):
    """Tests that reap_subagent correctly orchestrates SIGTERM/SIGKILL."""

    def test_returns_empty_list_when_no_subagent_running(self):
        from bob3.run_loop import reap_subagent

        fake_fid = "00000000-0000-0000-0000-000000000001"
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent(fake_fid)

        self.assertEqual(result, [])

    def test_returns_list_type_always(self):
        from bob3.run_loop import reap_subagent

        fake_fid = "11111111-0000-0000-0000-000000000002"
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent(fake_fid)

        self.assertIsInstance(result, list)

    def test_delegates_to_reap_subagent_for_feature(self):
        from bob3.run_loop import reap_subagent

        fake_fid = "aaaaaaaa-0000-0000-0000-000000000003"
        fake_pid = 55555

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
        ) as mock_audit:
            mock_find.return_value = [fake_pid]
            mock_argv.return_value = ["claude", "--print", "feature", fake_fid]
            mock_wait.return_value = True

            result = reap_subagent(fake_fid)

        self.assertIn(fake_pid, result)
        mock_signal.assert_called_once_with(fake_pid, signal.SIGTERM)
        mock_audit.assert_called_once_with(fake_fid)

    def test_escalates_to_sigkill_after_grace_period(self):
        from bob3.run_loop import reap_subagent

        fake_fid = "bbbbbbbb-0000-0000-0000-000000000004"
        fake_pid = 44444

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
            mock_argv.return_value = ["claude", "--print", "feature", fake_fid]
            # First wait (SIGTERM grace): process did not exit; second wait (SIGKILL): exited
            mock_wait.side_effect = [False, True]

            result = reap_subagent(fake_fid)

        self.assertIn(fake_pid, result)
        sent_sigs = [c[0][1] for c in mock_signal.call_args_list]
        self.assertIn(signal.SIGTERM, sent_sigs)
        self.assertIn(signal.SIGKILL, sent_sigs)

    def test_applies_to_completed_status(self):
        from bob3.run_loop import reap_subagent

        fake_fid = "cccccccc-comp-0000-0000-000000000005"
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent(fake_fid)

        self.assertEqual(result, [])

    def test_applies_to_needs_human_status(self):
        from bob3.run_loop import reap_subagent

        fake_fid = "dddddddd-nh00-0000-0000-000000000006"
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent(fake_fid)

        self.assertEqual(result, [])

    def test_applies_to_regression_status(self):
        from bob3.run_loop import reap_subagent

        fake_fid = "eeeeeeee-regr-0000-0000-000000000007"
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent(fake_fid)

        self.assertEqual(result, [])

    def test_applies_to_failed_status(self):
        from bob3.run_loop import reap_subagent

        fake_fid = "ffffffff-fail-0000-0000-000000000008"
        with patch(
            "bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent(fake_fid)

        self.assertEqual(result, [])

    def test_completes_quickly_when_no_subagent(self):
        from bob3.run_loop import reap_subagent

        fake_fid = "00aabbcc-0000-0000-0000-000000000009"
        start = time.monotonic()
        reap_subagent(fake_fid)
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 1.0)

    def test_returns_pid_in_result_when_reaped(self):
        from bob3.run_loop import reap_subagent

        fake_fid = "11223344-0000-0000-0000-00000000000a"
        fake_pid = 12345

        with patch(
            "bob3.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [fake_pid]
            result = reap_subagent(fake_fid)

        mock_reap.assert_called_once_with(fake_fid)
        self.assertEqual(result, [fake_pid])


class TestReapSubagentOrphanSweep(unittest.TestCase):
    """Tests that the backstop sweeper works via sweep_orphan_subagents."""

    def test_sweep_reaps_stale_terminal_features(self):
        from bob3.run_loop import sweep_orphan_subagents

        stale_fid = "ffffffff-0000-0000-0000-aabbccddeeff"

        with patch(
            "bob3.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob3.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [stale_fid]
            mock_reap.return_value = [99999]

            result = sweep_orphan_subagents()

        self.assertIn((stale_fid, 99999), result)

    def test_sweep_returns_empty_when_no_stale_features(self):
        from bob3.run_loop import sweep_orphan_subagents

        with patch(
            "bob3.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            result = sweep_orphan_subagents()

        self.assertEqual(result, [])


class TestRunLoopIntegration(unittest.TestCase):
    """Integration-level tests: bob3.run_loop wires reap_subagent correctly."""

    def test_reap_subagent_uses_orchestrator_reaper(self):
        import bob3.run_loop as rl

        fake_fid = "aabb1122-0000-0000-0000-000000000001"
        with patch(
            "bob3.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [88888]
            result = rl.reap_subagent(fake_fid)

        mock_reap.assert_called_once_with(fake_fid)
        self.assertEqual(result, [88888])

    def test_audit_sentinel_emitted_on_reap(self):
        from bob3.run_loop import reap_subagent

        fake_fid = "ccdd5566-0000-0000-0000-000000000002"
        fake_pid = 77777

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
            mock_argv.return_value = ["claude", "--print", fake_fid]
            mock_wait.return_value = True

            reap_subagent(fake_fid)

        mock_audit.assert_called_once_with(fake_fid)

    def test_run_loop_module_exports_reap_subagent(self):
        import bob3.run_loop as rl
        self.assertIn("reap_subagent", dir(rl))
        self.assertIn("reap_subagent", rl.__all__)

    def test_existing_exports_not_removed(self):
        import bob3.run_loop as rl
        for name in [
            "classify_subagent_startup_crash",
            "compute_persisted_artifact_count",
            "verify_project_metadata",
            "ProjectMetadataCheckResult",
            "sigterm_subagent_on_terminal_transition",
            "sweep_orphan_subagents",
        ]:
            self.assertIn(name, rl.__all__, f"Pre-existing export {name!r} missing")


if __name__ == "__main__":
    unittest.main()
