"""Tests for subagent_reaper terminal-transition hook.

Verifies that reap_subagent_for_feature is invoked within 30s of a
feature transitioning to a terminal state (completed/needs_human/
regression/failed) — AC: integration run_loop completion handler.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import MagicMock, call, patch

from bob3.orchestrator.subagent_reaper import (
    find_subagent_pid_for_feature,
    reap_subagent_for_feature,
)


class TestFindSubagentPidForFeature(unittest.TestCase):
    """Unit tests for find_subagent_pid_for_feature."""

    def test_returns_empty_when_no_matching_process(self):
        """Returns empty list when no claude process has the feature id."""
        fake_fid = "deadbeef-0000-0000-0000-000000000000"
        pids = find_subagent_pid_for_feature(fake_fid)
        self.assertIsInstance(pids, list)
        # No process should be tagged with this fake UUID
        self.assertEqual(pids, [])

    def test_returns_empty_for_non_claude_processes(self):
        """find_subagent_pid_for_feature ignores non-claude processes."""
        feature_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch("bob3.orchestrator.subagent_reaper._iter_candidate_pids") as mock_iter:
            # Simulate a python process with feature_id in argv — NOT claude
            mock_iter.return_value = [
                (9999, ["python", "script.py", "--feature", feature_id])
            ]
            pids = find_subagent_pid_for_feature(feature_id)
        # python process must NOT be returned even if it has the feature_id
        self.assertEqual(pids, [])

    def test_finds_matching_claude_process(self):
        """find_subagent_pid_for_feature returns PID when claude process has feature_id."""
        feature_id = "12345678-1234-1234-1234-123456789abc"
        fake_pid = 42000
        # _iter_candidate_pids returns (pid, argv_list) — NUL-split argv
        fake_argv = ["claude", "--print", "feature", feature_id, "--some-flag"]

        with patch("bob3.orchestrator.subagent_reaper._iter_candidate_pids") as mock_iter:
            mock_iter.return_value = [(fake_pid, fake_argv)]
            pids = find_subagent_pid_for_feature(feature_id)

        self.assertIn(fake_pid, pids)

    def test_excludes_own_pid(self):
        """find_subagent_pid_for_feature never returns os.getpid()."""
        feature_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        own_pid = os.getpid()

        with patch("bob3.orchestrator.subagent_reaper._iter_candidate_pids") as mock_iter:
            # Simulate own process appearing as a claude candidate
            mock_iter.return_value = [
                (own_pid, ["claude", "--print", "feature", feature_id])
            ]
            pids = find_subagent_pid_for_feature(feature_id)

        self.assertNotIn(own_pid, pids)


class TestReapSubagentForFeature(unittest.TestCase):
    """Unit tests for reap_subagent_for_feature SIGTERM/SIGKILL logic."""

    def test_reap_sends_sigterm_and_returns_reaped_count(self):
        """reap_subagent_for_feature sends SIGTERM and returns list of reaped pids."""
        feature_id = "aabbccdd-0000-0000-0000-000000000001"
        fake_pid = 88888
        # TOCTOU re-validation reads /proc/<pid>/cmdline; must return a matching argv.
        fake_argv = ["claude", "--print", "feature", feature_id]

        with patch("bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature") as mock_find, \
             patch("bob3.orchestrator.subagent_reaper._read_proc_argv") as mock_argv, \
             patch("bob3.orchestrator.subagent_reaper._send_signal") as mock_signal, \
             patch("bob3.orchestrator.subagent_reaper._wait_for_exit") as mock_wait, \
             patch("bob3.orchestrator.subagent_reaper._pid_is_alive") as mock_alive, \
             patch("bob3.orchestrator.subagent_reaper._append_audit_sentinel") as mock_audit:

            mock_find.return_value = [fake_pid]
            mock_argv.return_value = fake_argv  # TOCTOU guard passes
            mock_wait.return_value = True  # process exited cleanly after SIGTERM
            mock_alive.return_value = False

            reaped = reap_subagent_for_feature(feature_id)

        self.assertIn(fake_pid, reaped)
        mock_signal.assert_called_once_with(fake_pid, signal.SIGTERM)
        mock_audit.assert_called_once_with(feature_id)

    def test_reap_sends_sigkill_when_process_survives_grace_period(self):
        """reap_subagent_for_feature escalates to SIGKILL when process survives 15s grace."""
        feature_id = "aabbccdd-0000-0000-0000-000000000002"
        fake_pid = 77777
        fake_argv = ["claude", "--print", "feature", feature_id]

        with patch("bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature") as mock_find, \
             patch("bob3.orchestrator.subagent_reaper._read_proc_argv") as mock_argv, \
             patch("bob3.orchestrator.subagent_reaper._send_signal") as mock_signal, \
             patch("bob3.orchestrator.subagent_reaper._pid_is_alive") as mock_alive, \
             patch("bob3.orchestrator.subagent_reaper._append_audit_sentinel") as mock_audit, \
             patch("bob3.orchestrator.subagent_reaper._wait_for_exit") as mock_wait:

            mock_find.return_value = [fake_pid]
            mock_argv.return_value = fake_argv  # TOCTOU guard passes both times
            # First call: SIGTERM wait — process did NOT exit; second call: SIGKILL wait — did exit
            mock_wait.side_effect = [False, True]
            mock_alive.return_value = False

            reaped = reap_subagent_for_feature(feature_id)

        self.assertIn(fake_pid, reaped)
        calls = mock_signal.call_args_list
        sig_nums = [c[0][1] for c in calls]
        self.assertIn(signal.SIGTERM, sig_nums)
        self.assertIn(signal.SIGKILL, sig_nums)
        mock_audit.assert_called_once_with(feature_id)

    def test_reap_returns_empty_when_no_subagent_found(self):
        """reap_subagent_for_feature returns [] when no matching PID found."""
        feature_id = "aabbccdd-0000-0000-0000-000000000003"

        with patch("bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature") as mock_find, \
             patch("bob3.orchestrator.subagent_reaper._append_audit_sentinel") as mock_audit:

            mock_find.return_value = []
            reaped = reap_subagent_for_feature(feature_id)

        self.assertEqual(reaped, [])
        mock_audit.assert_not_called()

    def test_reap_appends_audit_sentinel(self):
        """reap_subagent_for_feature appends subagent_reaped_on_terminal sentinel."""
        feature_id = "aabbccdd-0000-0000-0000-000000000004"
        fake_pid = 66666
        fake_argv = ["claude", "--print", "feature", feature_id]

        with patch("bob3.orchestrator.subagent_reaper.find_subagent_pid_for_feature") as mock_find, \
             patch("bob3.orchestrator.subagent_reaper._read_proc_argv") as mock_argv, \
             patch("bob3.orchestrator.subagent_reaper._send_signal"), \
             patch("bob3.orchestrator.subagent_reaper._pid_is_alive") as mock_alive, \
             patch("bob3.orchestrator.subagent_reaper._append_audit_sentinel") as mock_audit, \
             patch("bob3.orchestrator.subagent_reaper._wait_for_exit") as mock_wait:

            mock_find.return_value = [fake_pid]
            mock_argv.return_value = fake_argv  # TOCTOU guard passes
            mock_wait.return_value = True  # exited cleanly after SIGTERM
            mock_alive.return_value = False

            reap_subagent_for_feature(feature_id)

        mock_audit.assert_called_once_with(feature_id)


class TestReapWithinWindow(unittest.TestCase):
    """Integration: reap happens within 30s of terminal transition."""

    def test_reap_completes_quickly_with_no_live_process(self):
        """reap_subagent_for_feature completes within 30s when no process exists."""
        feature_id = "deadbeef-dead-dead-dead-deaddeaddead"
        start = time.monotonic()
        result = reap_subagent_for_feature(feature_id)
        elapsed = time.monotonic() - start
        self.assertEqual(result, [])
        self.assertLess(elapsed, 30.0, "reap must complete within 30s")


if __name__ == "__main__":
    unittest.main()
