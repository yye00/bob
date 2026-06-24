"""Safety tests for subagent_reaper.

Verifies that:
1. reap_subagent_for_feature with a non-matching feature_id returns 0 reaped PIDs
   (no false-positive kills).
2. The bob main orchestrator PID is NEVER in the candidate kill list even if
   its argv accidentally contains a feature id token.
"""

from __future__ import annotations

import os
import signal
import unittest
from unittest.mock import MagicMock, patch

from bob.orchestrator.subagent_reaper import (
    find_subagent_pid_for_feature,
    reap_subagent_for_feature,
)


class TestNoFalsePositiveKills(unittest.TestCase):
    """AC: reap_subagent_for_feature with non-matching feature_id returns 0 reaped PIDs."""

    def test_non_matching_feature_id_returns_empty(self):
        """A feature_id not present in any process argv yields no reaped PIDs."""
        # Use a UUID that is highly unlikely to appear in any real process cmdline
        feature_id = "00000000-0000-0000-0000-cafebabedead"

        with patch("bob.orchestrator.subagent_reaper._iter_candidate_pids") as mock_iter:
            # Only processes with different UUIDs visible (argv as list — NUL-split)
            mock_iter.return_value = [
                (12345, ["claude", "--print", "feature", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee1"]),
                (12346, ["claude", "--print", "feature", "ffffffff-eeee-dddd-cccc-bbbbbbbbbbb1"]),
            ]
            reaped = reap_subagent_for_feature(feature_id)

        self.assertEqual(reaped, [], "Non-matching feature_id must yield 0 reaped PIDs")

    def test_partial_uuid_match_does_not_trigger_reap(self):
        """Partial UUID substring in argv must not match — requires exact token match."""
        feature_id = "abcdef12-0000-0000-0000-000000000001"

        with patch("bob.orchestrator.subagent_reaper._iter_candidate_pids") as mock_iter:
            # Process has a UUID that STARTS with the feature_id prefix but is different
            mock_iter.return_value = [
                (55555, ["claude", "--print", "feature", "abcdef12-0000-0000-0000-999999999999"]),
            ]
            reaped = reap_subagent_for_feature(feature_id)

        self.assertEqual(reaped, [], "Partial UUID match must NOT trigger a reap")

    def test_process_must_have_claude_binary_and_feature_id(self):
        """Both 'claude' binary AND specific feature_id token must be present."""
        feature_id = "12345678-aaaa-bbbb-cccc-ddddeeeeffff"

        with patch("bob.orchestrator.subagent_reaper._iter_candidate_pids") as mock_iter:
            # Has the feature_id but NOT the claude binary name
            mock_iter.return_value = [
                (77777, ["python", "run_agent.py", "feature", feature_id, "--print"]),
            ]
            reaped = reap_subagent_for_feature(feature_id)

        self.assertEqual(reaped, [], "Missing 'claude' binary must prevent match")


class TestOrchestratorPidNeverKilled(unittest.TestCase):
    """AC: bob main orchestrator PID is NEVER in the candidate kill list."""

    def test_own_pid_excluded_from_find(self):
        """find_subagent_pid_for_feature never includes os.getpid() in results."""
        feature_id = "selfprot1-0000-0000-0000-000000000001"
        own_pid = os.getpid()

        with patch("bob.orchestrator.subagent_reaper._iter_candidate_pids") as mock_iter:
            # Adversarially inject own PID as a candidate with feature_id in argv
            mock_iter.return_value = [
                (own_pid, ["claude", "--print", "feature", feature_id])
            ]
            pids = find_subagent_pid_for_feature(feature_id)

        self.assertNotIn(own_pid, pids, "Own PID must NEVER appear in candidate list")

    def test_own_pid_not_signalled_in_reap(self):
        """reap_subagent_for_feature never sends signals to os.getpid()."""
        feature_id = "selfprot2-0000-0000-0000-000000000002"
        own_pid = os.getpid()

        with patch("bob.orchestrator.subagent_reaper._iter_candidate_pids") as mock_iter, \
             patch("bob.orchestrator.subagent_reaper._send_signal") as mock_signal:

            # Even if own PID somehow gets into _iter_candidate_pids output
            mock_iter.return_value = [
                (own_pid, ["claude", "--print", "feature", feature_id])
            ]
            reap_subagent_for_feature(feature_id)

        # No signal should be sent to own PID
        for sig_call in mock_signal.call_args_list:
            killed_pid = sig_call[0][0]
            self.assertNotEqual(killed_pid, own_pid, "Must never signal own PID")

    def test_pid_1_never_signalled(self):
        """PID 1 (init) is never in the kill list even if argv matches."""
        feature_id = "pid1safe1-0000-0000-0000-000000000001"

        with patch("bob.orchestrator.subagent_reaper._iter_candidate_pids") as mock_iter:
            mock_iter.return_value = [
                (1, ["claude", "--print", "feature", feature_id])
            ]
            pids = find_subagent_pid_for_feature(feature_id)

        self.assertNotIn(1, pids, "PID 1 (init) must never appear in candidate list")

    def test_reap_returns_zero_when_only_own_pid_matches(self):
        """reap_subagent_for_feature returns [] when only own PID matches (safety net)."""
        feature_id = "selfprot3-0000-0000-0000-000000000003"
        own_pid = os.getpid()

        with patch("bob.orchestrator.subagent_reaper._iter_candidate_pids") as mock_iter:
            mock_iter.return_value = [
                (own_pid, ["claude", "--print", "feature", feature_id])
            ]
            reaped = reap_subagent_for_feature(feature_id)

        self.assertEqual(reaped, [])

    def test_multiple_safety_exclusions(self):
        """find_subagent_pid_for_feature excludes own PID even with legitimate PIDs present."""
        feature_id = "selfprot4-0000-0000-0000-000000000004"
        own_pid = os.getpid()
        legitimate_pid = 99998

        with patch("bob.orchestrator.subagent_reaper._iter_candidate_pids") as mock_iter:
            mock_iter.return_value = [
                (own_pid, ["claude", "--print", "feature", feature_id]),
                (legitimate_pid, ["claude", "--print", "feature", feature_id]),
            ]
            pids = find_subagent_pid_for_feature(feature_id)

        self.assertNotIn(own_pid, pids)
        self.assertIn(legitimate_pid, pids)


if __name__ == "__main__":
    unittest.main()
