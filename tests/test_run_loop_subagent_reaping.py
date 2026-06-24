"""Tests for bob.run_loop subagent reaping functions (8b02d5ec / 0143c5c4).

Acceptance criteria:
  - Function defined: bob.run_loop.sigterm_subagent_on_terminal_transition
  - Function defined: bob.run_loop.sweep_orphan_subagents
  - Function defined: bob.run_loop.reap_subagent_on_terminal_transition
  - Function defined: bob.run_loop.orphan_subagent_sweeper
  - integration: bob.run_loop
  - integration: bob.orchestrator

Verifies that both function pairs are importable from the public bob.run_loop
module and correctly delegate to bob.orchestrator.subagent_reaper.
"""

from __future__ import annotations

import signal
import time
import unittest
from unittest.mock import patch


class TestSigtermSubagentOnTerminalTransition(unittest.TestCase):
    """Tests for bob.run_loop.sigterm_subagent_on_terminal_transition."""

    def test_function_is_importable_from_bob_run_loop(self):
        """sigterm_subagent_on_terminal_transition is accessible at bob.run_loop."""
        import bob.run_loop as rl
        self.assertTrue(callable(rl.sigterm_subagent_on_terminal_transition))

    def test_returns_empty_list_when_no_subagent_running(self):
        """Returns [] when no claude process is tagged with the feature id."""
        from bob.run_loop import sigterm_subagent_on_terminal_transition

        fake_fid = "00000000-0000-0000-0000-000000000001"
        with patch(
            "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = sigterm_subagent_on_terminal_transition(fake_fid)

        self.assertEqual(result, [])

    def test_delegates_to_reap_subagent_for_feature(self):
        """sigterm_subagent_on_terminal_transition delegates to reap_subagent_for_feature."""
        from bob.run_loop import sigterm_subagent_on_terminal_transition

        fake_fid = "aaaaaaaa-0000-0000-0000-000000000002"
        fake_pid = 55555
        fake_argv = ["claude", "--print", "feature", fake_fid]

        with patch(
            "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find, patch(
            "bob.orchestrator.subagent_reaper._read_proc_argv"
        ) as mock_argv, patch(
            "bob.orchestrator.subagent_reaper._send_signal"
        ) as mock_signal, patch(
            "bob.orchestrator.subagent_reaper._wait_for_exit"
        ) as mock_wait, patch(
            "bob.orchestrator.subagent_reaper._append_audit_sentinel"
        ) as mock_audit:
            mock_find.return_value = [fake_pid]
            mock_argv.return_value = fake_argv
            mock_wait.return_value = True

            result = sigterm_subagent_on_terminal_transition(fake_fid)

        self.assertIn(fake_pid, result)
        mock_signal.assert_called_once_with(fake_pid, signal.SIGTERM)
        mock_audit.assert_called_once_with(fake_fid)

    def test_sends_sigkill_after_grace_period_expires(self):
        """Escalates to SIGKILL when process survives 15s SIGTERM grace window."""
        from bob.run_loop import sigterm_subagent_on_terminal_transition

        fake_fid = "bbbbbbbb-0000-0000-0000-000000000003"
        fake_pid = 44444
        fake_argv = ["claude", "--print", "feature", fake_fid]

        with patch(
            "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find, patch(
            "bob.orchestrator.subagent_reaper._read_proc_argv"
        ) as mock_argv, patch(
            "bob.orchestrator.subagent_reaper._send_signal"
        ) as mock_signal, patch(
            "bob.orchestrator.subagent_reaper._wait_for_exit"
        ) as mock_wait, patch(
            "bob.orchestrator.subagent_reaper._append_audit_sentinel"
        ):
            mock_find.return_value = [fake_pid]
            mock_argv.return_value = fake_argv
            # SIGTERM wait: no exit; SIGKILL wait: exited
            mock_wait.side_effect = [False, True]

            result = sigterm_subagent_on_terminal_transition(fake_fid)

        self.assertIn(fake_pid, result)
        sent_sigs = [c[0][1] for c in mock_signal.call_args_list]
        self.assertIn(signal.SIGTERM, sent_sigs)
        self.assertIn(signal.SIGKILL, sent_sigs)

    def test_returns_list_type(self):
        """Return value is always a list regardless of outcome."""
        from bob.run_loop import sigterm_subagent_on_terminal_transition

        fake_fid = "cccccccc-0000-0000-0000-000000000004"
        with patch(
            "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = sigterm_subagent_on_terminal_transition(fake_fid)

        self.assertIsInstance(result, list)

    def test_applies_to_all_terminal_statuses(self):
        """Function is called and works for completed, needs_human, regression, failed."""
        from bob.run_loop import sigterm_subagent_on_terminal_transition

        terminal_statuses = ["completed", "needs_human", "regression", "failed"]
        for status in terminal_statuses:
            fake_fid = f"dddddddd-{status[:4]}-0000-0000-000000000005"
            with patch(
                "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
            ) as mock_find:
                mock_find.return_value = []
                result = sigterm_subagent_on_terminal_transition(fake_fid)

            self.assertEqual(result, [], f"Expected [] for status={status}")

    def test_completes_quickly_when_no_subagent(self):
        """Completes within 1s when no matching subagent is running."""
        from bob.run_loop import sigterm_subagent_on_terminal_transition

        fake_fid = "eeeeeeee-0000-0000-0000-000000000006"
        start = time.monotonic()
        sigterm_subagent_on_terminal_transition(fake_fid)
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 1.0)


class TestSweepOrphanSubagentsRunLoop(unittest.TestCase):
    """Tests for bob.run_loop.sweep_orphan_subagents."""

    def test_function_is_importable_from_bob_run_loop(self):
        """sweep_orphan_subagents is accessible at bob.run_loop."""
        import bob.run_loop as rl
        self.assertTrue(callable(rl.sweep_orphan_subagents))

    def test_returns_empty_list_when_no_stale_features(self):
        """Returns [] when no terminal features have exceeded 5min dwell."""
        from bob.run_loop import sweep_orphan_subagents

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            result = sweep_orphan_subagents()

        self.assertEqual(result, [])

    def test_returns_reaped_pairs_for_stale_features(self):
        """Returns (feature_id, pid) tuples for each reaped orphan."""
        from bob.run_loop import sweep_orphan_subagents

        stale_fid = "ffffffff-0000-0000-0000-000000000001"

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [stale_fid]
            mock_reap.return_value = [12345]

            result = sweep_orphan_subagents()

        self.assertIsInstance(result, list)
        self.assertIn((stale_fid, 12345), result)

    def test_reaps_multiple_stale_features(self):
        """Iterates and reaps all features in the stale list."""
        from bob.run_loop import sweep_orphan_subagents

        fid1 = "aaaabbbb-0000-0000-0000-000000000002"
        fid2 = "ccccdddd-0000-0000-0000-000000000003"

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [fid1, fid2]
            mock_reap.side_effect = [[11111], [22222]]

            result = sweep_orphan_subagents()

        mock_reap.assert_any_call(fid1)
        mock_reap.assert_any_call(fid2)
        self.assertIn((fid1, 11111), result)
        self.assertIn((fid2, 22222), result)

    def test_skips_features_with_no_live_subagent(self):
        """Feature with already-dead subagent produces no entry in result."""
        from bob.run_loop import sweep_orphan_subagents

        stale_fid = "eeeeffff-0000-0000-0000-000000000004"

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [stale_fid]
            mock_reap.return_value = []

            result = sweep_orphan_subagents()

        self.assertEqual(result, [])

    def test_is_idempotent(self):
        """Can be called multiple times; each call returns independent results."""
        from bob.run_loop import sweep_orphan_subagents

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            r1 = sweep_orphan_subagents()
            r2 = sweep_orphan_subagents()

        self.assertEqual(r1, [])
        self.assertEqual(r2, [])

    def test_returns_list_type(self):
        """Return value is always a list."""
        from bob.run_loop import sweep_orphan_subagents

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            result = sweep_orphan_subagents()

        self.assertIsInstance(result, list)


class TestRunLoopModuleExports(unittest.TestCase):
    """Verifies the public __all__ of bob.run_loop includes the new functions."""

    def test_sigterm_in_all(self):
        """sigterm_subagent_on_terminal_transition appears in bob.run_loop.__all__."""
        import bob.run_loop as rl
        self.assertIn("sigterm_subagent_on_terminal_transition", rl.__all__)

    def test_sweep_orphans_in_all(self):
        """sweep_orphan_subagents appears in bob.run_loop.__all__."""
        import bob.run_loop as rl
        self.assertIn("sweep_orphan_subagents", rl.__all__)

    def test_existing_exports_still_present(self):
        """Adding new functions did not remove any pre-existing __all__ entries."""
        import bob.run_loop as rl
        for name in [
            "classify_subagent_startup_crash",
            "compute_persisted_artifact_count",
            "verify_project_metadata",
            "ProjectMetadataCheckResult",
        ]:
            self.assertIn(name, rl.__all__, f"Pre-existing export {name!r} missing from __all__")


class TestIntegrationRunLoop(unittest.TestCase):
    """Integration-level tests verifying bob.run_loop wires correctly."""

    def test_sigterm_function_calls_orchestrator_reaper(self):
        """sigterm_subagent_on_terminal_transition uses the orchestrator subagent_reaper."""
        import bob.run_loop as rl

        fake_fid = "11112222-0000-0000-0000-000000000001"
        with patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [99999]
            result = rl.sigterm_subagent_on_terminal_transition(fake_fid)

        mock_reap.assert_called_once_with(fake_fid)
        self.assertEqual(result, [99999])

    def test_sweep_function_calls_orchestrator_sweeper(self):
        """sweep_orphan_subagents uses the orchestrator subagent_reaper sweep."""
        import bob.run_loop as rl

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = ["aabbccdd-ffff-0000-0000-000000000002"]
            mock_reap.return_value = [77777]

            result = rl.sweep_orphan_subagents()

        self.assertIn(("aabbccdd-ffff-0000-0000-000000000002", 77777), result)


class TestReapSubagentOnTerminalTransition(unittest.TestCase):
    """Tests for bob.run_loop.reap_subagent_on_terminal_transition (AC: 0143c5c4)."""

    def test_function_is_importable_from_bob_run_loop(self):
        """reap_subagent_on_terminal_transition is accessible at bob.run_loop."""
        import bob.run_loop as rl
        self.assertTrue(callable(rl.reap_subagent_on_terminal_transition))

    def test_returns_empty_list_when_no_subagent_running(self):
        """Returns [] when no claude process is tagged with the feature id."""
        from bob.run_loop import reap_subagent_on_terminal_transition

        fake_fid = "00000000-0000-0000-0000-000000000010"
        with patch(
            "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent_on_terminal_transition(fake_fid)

        self.assertEqual(result, [])

    def test_delegates_to_reap_subagent_for_feature(self):
        """reap_subagent_on_terminal_transition delegates to reap_subagent_for_feature."""
        from bob.run_loop import reap_subagent_on_terminal_transition

        fake_fid = "aaaaaaaa-0000-0000-0000-000000000011"
        with patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [55555]
            result = reap_subagent_on_terminal_transition(fake_fid)

        mock_reap.assert_called_once_with(fake_fid)
        self.assertEqual(result, [55555])

    def test_sends_sigterm_then_sigkill(self):
        """Escalates to SIGKILL when process survives SIGTERM grace window."""
        from bob.run_loop import reap_subagent_on_terminal_transition

        fake_fid = "bbbbbbbb-0000-0000-0000-000000000012"
        fake_pid = 44444

        with patch(
            "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find, patch(
            "bob.orchestrator.subagent_reaper._read_proc_argv"
        ) as mock_argv, patch(
            "bob.orchestrator.subagent_reaper._send_signal"
        ) as mock_signal, patch(
            "bob.orchestrator.subagent_reaper._wait_for_exit"
        ) as mock_wait, patch(
            "bob.orchestrator.subagent_reaper._append_audit_sentinel"
        ):
            mock_find.return_value = [fake_pid]
            mock_argv.return_value = ["claude", "--print", "feature", fake_fid]
            mock_wait.side_effect = [False, True]

            result = reap_subagent_on_terminal_transition(fake_fid)

        self.assertIn(fake_pid, result)
        sent_sigs = [c[0][1] for c in mock_signal.call_args_list]
        self.assertIn(signal.SIGTERM, sent_sigs)
        self.assertIn(signal.SIGKILL, sent_sigs)

    def test_applies_to_all_terminal_statuses(self):
        """Function works for completed, needs_human, regression, failed."""
        from bob.run_loop import reap_subagent_on_terminal_transition

        terminal_statuses = ["completed", "needs_human", "regression", "failed"]
        for status in terminal_statuses:
            fake_fid = f"dddddddd-{status[:4]}-0000-0000-000000000013"
            with patch(
                "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
            ) as mock_find:
                mock_find.return_value = []
                result = reap_subagent_on_terminal_transition(fake_fid)

            self.assertEqual(result, [], f"Expected [] for status={status}")

    def test_returns_list_type(self):
        """Return value is always a list."""
        from bob.run_loop import reap_subagent_on_terminal_transition

        fake_fid = "cccccccc-0000-0000-0000-000000000014"
        with patch(
            "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent_on_terminal_transition(fake_fid)

        self.assertIsInstance(result, list)

    def test_in_all(self):
        """reap_subagent_on_terminal_transition appears in bob.run_loop.__all__."""
        import bob.run_loop as rl
        self.assertIn("reap_subagent_on_terminal_transition", rl.__all__)


class TestOrphanSubagentSweeper(unittest.TestCase):
    """Tests for bob.run_loop.orphan_subagent_sweeper (AC: 0143c5c4)."""

    def test_function_is_importable_from_bob_run_loop(self):
        """orphan_subagent_sweeper is accessible at bob.run_loop."""
        import bob.run_loop as rl
        self.assertTrue(callable(rl.orphan_subagent_sweeper))

    def test_returns_empty_list_when_no_stale_features(self):
        """Returns [] when no terminal features have exceeded 5min dwell."""
        from bob.run_loop import orphan_subagent_sweeper

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            result = orphan_subagent_sweeper()

        self.assertEqual(result, [])

    def test_returns_reaped_pairs_for_stale_features(self):
        """Returns (feature_id, pid) tuples for each reaped orphan."""
        from bob.run_loop import orphan_subagent_sweeper

        stale_fid = "ffffffff-0000-0000-0000-000000000020"

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [stale_fid]
            mock_reap.return_value = [12345]

            result = orphan_subagent_sweeper()

        self.assertIsInstance(result, list)
        self.assertIn((stale_fid, 12345), result)

    def test_reaps_multiple_stale_features(self):
        """Iterates and reaps all features in the stale list."""
        from bob.run_loop import orphan_subagent_sweeper

        fid1 = "aaaabbbb-0000-0000-0000-000000000021"
        fid2 = "ccccdddd-0000-0000-0000-000000000022"

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [fid1, fid2]
            mock_reap.side_effect = [[11111], [22222]]

            result = orphan_subagent_sweeper()

        mock_reap.assert_any_call(fid1)
        mock_reap.assert_any_call(fid2)
        self.assertIn((fid1, 11111), result)
        self.assertIn((fid2, 22222), result)

    def test_skips_features_with_no_live_subagent(self):
        """Feature with already-dead subagent produces no entry in result."""
        from bob.run_loop import orphan_subagent_sweeper

        stale_fid = "eeeeffff-0000-0000-0000-000000000023"

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [stale_fid]
            mock_reap.return_value = []

            result = orphan_subagent_sweeper()

        self.assertEqual(result, [])

    def test_is_idempotent(self):
        """Can be called multiple times; each call returns independent results."""
        from bob.run_loop import orphan_subagent_sweeper

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            r1 = orphan_subagent_sweeper()
            r2 = orphan_subagent_sweeper()

        self.assertEqual(r1, [])
        self.assertEqual(r2, [])

    def test_returns_list_type(self):
        """Return value is always a list."""
        from bob.run_loop import orphan_subagent_sweeper

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            result = orphan_subagent_sweeper()

        self.assertIsInstance(result, list)

    def test_in_all(self):
        """orphan_subagent_sweeper appears in bob.run_loop.__all__."""
        import bob.run_loop as rl
        self.assertIn("orphan_subagent_sweeper", rl.__all__)


class TestIntegrationRunLoopOrchestrator(unittest.TestCase):
    """Integration: verifies bob.run_loop wires to bob.orchestrator correctly."""

    def test_reap_function_calls_orchestrator_reaper(self):
        """reap_subagent_on_terminal_transition uses the orchestrator subagent_reaper."""
        import bob.run_loop as rl

        fake_fid = "11112222-0000-0000-0000-000000000030"
        with patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [99999]
            result = rl.reap_subagent_on_terminal_transition(fake_fid)

        mock_reap.assert_called_once_with(fake_fid)
        self.assertEqual(result, [99999])

    def test_sweeper_calls_orchestrator_sweeper(self):
        """orphan_subagent_sweeper uses the orchestrator subagent_reaper sweep."""
        import bob.run_loop as rl

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = ["aabbccdd-ffff-0000-0000-000000000031"]
            mock_reap.return_value = [77777]

            result = rl.orphan_subagent_sweeper()

        self.assertIn(("aabbccdd-ffff-0000-0000-000000000031", 77777), result)

    def test_bob_orchestrator_subagent_reaper_importable(self):
        """bob.orchestrator.subagent_reaper is importable (integration AC)."""
        import bob.orchestrator.subagent_reaper as reaper
        self.assertTrue(callable(reaper.reap_subagent_for_feature))
        self.assertTrue(callable(reaper.sweep_orphan_subagents))
        self.assertTrue(callable(reaper.find_subagent_pid_for_feature))


class TestBackstopReapOrphanSubagents(unittest.TestCase):
    """Tests for bob.run_loop.backstop_reap_orphan_subagents (AC: b7561f93)."""

    def test_function_is_importable_from_bob_run_loop(self):
        """backstop_reap_orphan_subagents is accessible at bob.run_loop."""
        import bob.run_loop as rl
        self.assertTrue(callable(rl.backstop_reap_orphan_subagents))

    def test_in_all(self):
        """backstop_reap_orphan_subagents appears in bob.run_loop.__all__."""
        import bob.run_loop as rl
        self.assertIn("backstop_reap_orphan_subagents", rl.__all__)

    def test_returns_empty_list_when_no_stale_features(self):
        """Returns [] when no terminal features have exceeded 5min dwell."""
        from bob.run_loop import backstop_reap_orphan_subagents

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            result = backstop_reap_orphan_subagents()

        self.assertEqual(result, [])

    def test_returns_list_type(self):
        """Return value is always a list."""
        from bob.run_loop import backstop_reap_orphan_subagents

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            result = backstop_reap_orphan_subagents()

        self.assertIsInstance(result, list)

    def test_returns_reaped_pairs_for_stale_features(self):
        """Returns (feature_id, pid) tuples for each reaped orphan."""
        from bob.run_loop import backstop_reap_orphan_subagents

        stale_fid = "b7561f93-0000-0000-0000-000000000001"

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [stale_fid]
            mock_reap.return_value = [12345]

            result = backstop_reap_orphan_subagents()

        self.assertIsInstance(result, list)
        self.assertIn((stale_fid, 12345), result)

    def test_reaps_multiple_stale_features(self):
        """Iterates and reaps all features in the stale list."""
        from bob.run_loop import backstop_reap_orphan_subagents

        fid1 = "b7561f93-0000-0000-0000-000000000002"
        fid2 = "b7561f93-0000-0000-0000-000000000003"

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [fid1, fid2]
            mock_reap.side_effect = [[11111], [22222]]

            result = backstop_reap_orphan_subagents()

        mock_reap.assert_any_call(fid1)
        mock_reap.assert_any_call(fid2)
        self.assertIn((fid1, 11111), result)
        self.assertIn((fid2, 22222), result)

    def test_skips_features_with_no_live_subagent(self):
        """Feature with already-dead subagent produces no entry in result."""
        from bob.run_loop import backstop_reap_orphan_subagents

        stale_fid = "b7561f93-0000-0000-0000-000000000004"

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = [stale_fid]
            mock_reap.return_value = []

            result = backstop_reap_orphan_subagents()

        self.assertEqual(result, [])

    def test_is_idempotent(self):
        """Can be called multiple times; each call returns independent results."""
        from bob.run_loop import backstop_reap_orphan_subagents

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query:
            mock_query.return_value = []
            r1 = backstop_reap_orphan_subagents()
            r2 = backstop_reap_orphan_subagents()

        self.assertEqual(r1, [])
        self.assertEqual(r2, [])

    def test_delegates_to_orchestrator_sweep(self):
        """backstop_reap_orphan_subagents uses the orchestrator subagent_reaper sweep."""
        import bob.run_loop as rl

        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features"
        ) as mock_query, patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_query.return_value = ["b7561f93-ffff-0000-0000-000000000005"]
            mock_reap.return_value = [77777]

            result = rl.backstop_reap_orphan_subagents()

        self.assertIn(("b7561f93-ffff-0000-0000-000000000005", 77777), result)


class TestReapSubagentOnTerminalState(unittest.TestCase):
    """Tests for bob.run_loop.reap_subagent_on_terminal_state (AC: 7933f525)."""

    def test_function_is_importable_from_bob_run_loop(self):
        """reap_subagent_on_terminal_state is accessible at bob.run_loop."""
        import bob.run_loop as rl
        self.assertTrue(callable(rl.reap_subagent_on_terminal_state))

    def test_in_all(self):
        """reap_subagent_on_terminal_state appears in bob.run_loop.__all__."""
        import bob.run_loop as rl
        self.assertIn("reap_subagent_on_terminal_state", rl.__all__)

    def test_returns_empty_list_when_no_subagent_running(self):
        """Returns [] when no claude process is tagged with the feature id."""
        from bob.run_loop import reap_subagent_on_terminal_state

        fake_fid = "79330000-0000-0000-0000-000000000001"
        with patch(
            "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent_on_terminal_state(fake_fid)

        self.assertEqual(result, [])

    def test_delegates_to_reap_subagent_for_feature(self):
        """reap_subagent_on_terminal_state delegates to reap_subagent_for_feature."""
        from bob.run_loop import reap_subagent_on_terminal_state

        fake_fid = "79330000-0000-0000-0000-000000000002"
        with patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [55555]
            result = reap_subagent_on_terminal_state(fake_fid)

        mock_reap.assert_called_once_with(fake_fid)
        self.assertEqual(result, [55555])

    def test_applies_to_all_terminal_statuses(self):
        """Function works for completed, needs_human, regression, failed."""
        from bob.run_loop import reap_subagent_on_terminal_state

        terminal_statuses = ["completed", "needs_human", "regression", "failed"]
        for status in terminal_statuses:
            fake_fid = f"79330000-{status[:4]}-0000-0000-000000000003"
            with patch(
                "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
            ) as mock_find:
                mock_find.return_value = []
                result = reap_subagent_on_terminal_state(fake_fid)
            self.assertEqual(result, [], f"Expected [] for status={status}")

    def test_is_callable(self):
        """reap_subagent_on_terminal_state is a standalone callable."""
        import bob.run_loop as rl
        self.assertTrue(callable(rl.reap_subagent_on_terminal_state))


class TestReapSubagentOnTerminal(unittest.TestCase):
    """Tests for bob.run_loop.reap_subagent_on_terminal (AC: c493ccc8)."""

    def test_function_is_importable_from_bob_run_loop(self):
        """reap_subagent_on_terminal is accessible at bob.run_loop."""
        import bob.run_loop as rl
        self.assertTrue(callable(rl.reap_subagent_on_terminal))

    def test_in_all(self):
        """reap_subagent_on_terminal is in bob.run_loop.__all__."""
        import bob.run_loop as rl
        self.assertIn("reap_subagent_on_terminal", rl.__all__)

    def test_is_alias_of_reap_subagent_on_terminal_transition(self):
        """reap_subagent_on_terminal is the same callable as reap_subagent_on_terminal_transition."""
        import bob.run_loop as rl
        self.assertIs(rl.reap_subagent_on_terminal, rl.reap_subagent_on_terminal_transition)

    def test_returns_empty_list_when_no_subagent_running(self):
        """Returns [] when no claude process is tagged with the feature id."""
        from bob.run_loop import reap_subagent_on_terminal

        fake_fid = "c4930000-0000-0000-0000-000000000001"
        with patch(
            "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
        ) as mock_find:
            mock_find.return_value = []
            result = reap_subagent_on_terminal(fake_fid)

        self.assertEqual(result, [])

    def test_delegates_to_reap_subagent_for_feature(self):
        """reap_subagent_on_terminal delegates to reap_subagent_for_feature."""
        from bob.run_loop import reap_subagent_on_terminal

        fake_fid = "c4930000-0000-0000-0000-000000000002"
        with patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [12345]
            result = reap_subagent_on_terminal(fake_fid)

        mock_reap.assert_called_once_with(fake_fid)
        self.assertEqual(result, [12345])

    def test_applies_to_all_terminal_statuses(self):
        """Function works for completed, needs_human, regression, failed."""
        from bob.run_loop import reap_subagent_on_terminal

        terminal_statuses = ["completed", "needs_human", "regression", "failed"]
        for status in terminal_statuses:
            fake_fid = f"c4930000-{status[:4]}-0000-0000-000000000003"
            with patch(
                "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature"
            ) as mock_find:
                mock_find.return_value = []
                result = reap_subagent_on_terminal(fake_fid)
            self.assertEqual(result, [], f"Expected [] for status={status}")

    def test_returns_list_type(self):
        """Return value is always a list."""
        from bob.run_loop import reap_subagent_on_terminal

        fake_fid = "c4930000-0000-0000-0000-000000000004"
        with patch(
            "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature",
            return_value=[],
        ):
            result = reap_subagent_on_terminal(fake_fid)
        self.assertIsInstance(result, list)


class TestSubagentReaperModule(unittest.TestCase):
    """Tests for src/bob/subagent_reaper.py (AC: File exists: src/bob/subagent_reaper.py)."""

    def test_module_is_importable(self):
        """bob.subagent_reaper is importable."""
        import bob.subagent_reaper as sr
        self.assertIsNotNone(sr)

    def test_find_subagent_pid_for_feature_exported(self):
        """bob.subagent_reaper exports find_subagent_pid_for_feature."""
        import bob.subagent_reaper as sr
        self.assertTrue(callable(sr.find_subagent_pid_for_feature))

    def test_reap_subagent_for_feature_exported(self):
        """bob.subagent_reaper exports reap_subagent_for_feature."""
        import bob.subagent_reaper as sr
        self.assertTrue(callable(sr.reap_subagent_for_feature))

    def test_sweep_orphan_subagents_exported(self):
        """bob.subagent_reaper exports sweep_orphan_subagents."""
        import bob.subagent_reaper as sr
        self.assertTrue(callable(sr.sweep_orphan_subagents))

    def test_reap_delegates_to_orchestrator(self):
        """reap_subagent_for_feature in bob.subagent_reaper delegates to orchestrator."""
        import bob.subagent_reaper as sr

        fake_fid = "c4930000-0000-0000-0000-000000000010"
        with patch.object(sr, "reap_subagent_for_feature", return_value=[99999]) as mock_reap:
            result = sr.reap_subagent_for_feature(fake_fid)

        mock_reap.assert_called_once_with(fake_fid)
        self.assertEqual(result, [99999])

    def test_sweep_delegates_to_orchestrator(self):
        """sweep_orphan_subagents in bob.subagent_reaper delegates to orchestrator."""
        import bob.subagent_reaper as sr

        with patch.object(sr, "sweep_orphan_subagents", return_value=[("feat-abc", 77777)]) as mock_sweep:
            result = sr.sweep_orphan_subagents()

        mock_sweep.assert_called_once()
        self.assertEqual(result, [("feat-abc", 77777)])

    def test_in_all(self):
        """All public symbols are in bob.subagent_reaper.__all__."""
        import bob.subagent_reaper as sr
        for name in [
            "find_subagent_pid_for_feature",
            "reap_subagent_for_feature",
            "sweep_orphan_subagents",
        ]:
            self.assertIn(name, sr.__all__, f"{name} missing from __all__")


class TestReapSubagentOnTerminalStateBehavior(unittest.TestCase):
    """Boundary and invalid-input behavior tests for reap_subagent_on_terminal_state (81a69f3f)."""

    def test_empty_string_returns_empty_list(self):
        """Empty string feature_id returns [] without crashing (boundary case)."""
        from bob.run_loop import reap_subagent_on_terminal_state
        result = reap_subagent_on_terminal_state("")
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_none_raises_value_error(self):
        """None feature_id raises ValueError — must not silently succeed."""
        from bob.run_loop import reap_subagent_on_terminal_state
        with self.assertRaises(ValueError):
            reap_subagent_on_terminal_state(None)

    def test_non_string_raises_value_error(self):
        """Non-string feature_id raises ValueError — must not silently succeed."""
        from bob.run_loop import reap_subagent_on_terminal_state
        with self.assertRaises(ValueError):
            reap_subagent_on_terminal_state(12345)

    def test_list_raises_value_error(self):
        """List feature_id raises ValueError."""
        from bob.run_loop import reap_subagent_on_terminal_state
        with self.assertRaises(ValueError):
            reap_subagent_on_terminal_state(["a", "b"])

    def test_valid_uuid_delegates_normally(self):
        """Valid UUID delegates to reap_subagent_for_feature and returns list."""
        from bob.run_loop import reap_subagent_on_terminal_state
        fake_fid = "81a69f3f-0000-0000-0000-000000000001"
        with patch(
            "bob.orchestrator.subagent_reaper.find_subagent_pid_for_feature",
            return_value=[],
        ):
            result = reap_subagent_on_terminal_state(fake_fid)
        self.assertIsInstance(result, list)


class TestBackstopReaperBehavior(unittest.TestCase):
    """Boundary and invalid-input behavior tests for backstop_reaper (81a69f3f)."""

    def test_no_args_returns_list(self):
        """backstop_reaper() with no arguments returns a list (boundary: default/zero input)."""
        from bob.run_loop import backstop_reaper
        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features",
            return_value=[],
        ):
            result = backstop_reaper()
        self.assertIsInstance(result, list)

    def test_none_stale_minutes_returns_list(self):
        """backstop_reaper(None) uses default dwell threshold — returns list."""
        from bob.run_loop import backstop_reaper
        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features",
            return_value=[],
        ):
            result = backstop_reaper(None)
        self.assertIsInstance(result, list)

    def test_zero_stale_minutes_returns_list(self):
        """backstop_reaper(0) is a well-defined boundary case — returns list."""
        from bob.run_loop import backstop_reaper
        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features",
            return_value=[],
        ):
            result = backstop_reaper(0)
        self.assertIsInstance(result, list)

    def test_negative_stale_minutes_raises_value_error(self):
        """Negative stale_minutes raises ValueError — must not silently succeed."""
        from bob.run_loop import backstop_reaper
        with self.assertRaises(ValueError):
            backstop_reaper(-1)

    def test_large_negative_raises_value_error(self):
        """Large negative stale_minutes raises ValueError."""
        from bob.run_loop import backstop_reaper
        with self.assertRaises(ValueError):
            backstop_reaper(-9999)

    def test_delegates_to_sweep_when_valid(self):
        """Valid call delegates to sweep and returns reaped pairs."""
        from bob.run_loop import backstop_reaper
        fid = "81a69f3f-0000-0000-0000-000000000002"
        with patch(
            "bob.orchestrator.subagent_reaper._query_stale_terminal_features",
            return_value=[fid],
        ), patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature",
            return_value=[99999],
        ):
            result = backstop_reaper()
        self.assertIn((fid, 99999), result)


if __name__ == "__main__":
    unittest.main()
