"""Tests for bob.run_loop subagent reaping on terminal-state transitions.

AC: pytest: tests/test_run_loop_reaper.py
Feature: run_loop MUST reap claude subagent process on feature terminal-state transition
         (9bfd41cd-2eb8-4131-86f0-aedcf5786f07)

Covers reap_subagent_on_terminal_state and backstop_reaper_for_orphan_subagents.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch


class TestReapSubagentOnTerminalState(unittest.TestCase):
    """Tests for reap_subagent_on_terminal_state."""

    def test_empty_feature_id_returns_empty_list(self):
        """Empty string feature_id returns [] without raising."""
        from bob.run_loop import reap_subagent_on_terminal_state

        result = reap_subagent_on_terminal_state("")
        self.assertEqual(result, [])

    def test_none_feature_id_raises_value_error(self):
        """None feature_id raises ValueError."""
        from bob.run_loop import reap_subagent_on_terminal_state

        with self.assertRaises(ValueError) as ctx:
            reap_subagent_on_terminal_state(None)  # type: ignore[arg-type]

        self.assertIn("feature_id", str(ctx.exception).lower())

    def test_int_feature_id_raises_value_error(self):
        """Non-string feature_id raises ValueError."""
        from bob.run_loop import reap_subagent_on_terminal_state

        with self.assertRaises(ValueError):
            reap_subagent_on_terminal_state(42)  # type: ignore[arg-type]

    def test_valid_feature_id_calls_reaper(self):
        """Valid UUID feature_id delegates to reap_subagent_for_feature."""
        from bob.run_loop import reap_subagent_on_terminal_state

        fake_fid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [12345]
            result = reap_subagent_on_terminal_state(fake_fid)

        self.assertEqual(result, [12345])

    def test_no_matching_process_returns_empty_list(self):
        """Valid feature_id with no running process returns []."""
        from bob.run_loop import reap_subagent_on_terminal_state

        fake_fid = "00000000-0000-0000-0000-000000000000"
        with patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = []
            result = reap_subagent_on_terminal_state(fake_fid)

        self.assertEqual(result, [])

    def test_returns_list_type(self):
        """Returns a list regardless of outcome."""
        from bob.run_loop import reap_subagent_on_terminal_state

        with patch(
            "bob.orchestrator.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = []
            result = reap_subagent_on_terminal_state("some-feature-id")

        self.assertIsInstance(result, list)


class TestBackstopReaperForOrphanSubagents(unittest.TestCase):
    """Tests for backstop_reaper_for_orphan_subagents."""

    def test_default_call_returns_list(self):
        """Calling with no arguments returns a list."""
        from bob.run_loop import backstop_reaper_for_orphan_subagents

        with patch(
            "bob.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = backstop_reaper_for_orphan_subagents()

        self.assertIsInstance(result, list)

    def test_none_stale_minutes_does_not_raise(self):
        """stale_minutes=None uses default threshold without raising."""
        from bob.run_loop import backstop_reaper_for_orphan_subagents

        with patch(
            "bob.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = backstop_reaper_for_orphan_subagents(None)

        self.assertIsInstance(result, list)

    def test_zero_stale_minutes_does_not_raise(self):
        """stale_minutes=0 is a valid minimum input."""
        from bob.run_loop import backstop_reaper_for_orphan_subagents

        with patch(
            "bob.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = backstop_reaper_for_orphan_subagents(0)

        self.assertIsInstance(result, list)

    def test_positive_stale_minutes_does_not_raise(self):
        """Positive stale_minutes is accepted."""
        from bob.run_loop import backstop_reaper_for_orphan_subagents

        with patch(
            "bob.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = backstop_reaper_for_orphan_subagents(5)

        self.assertIsInstance(result, list)

    def test_negative_stale_minutes_raises_value_error(self):
        """Negative stale_minutes raises ValueError."""
        from bob.run_loop import backstop_reaper_for_orphan_subagents

        with self.assertRaises(ValueError) as ctx:
            backstop_reaper_for_orphan_subagents(-1)

        self.assertIn("stale_minutes", str(ctx.exception).lower())

    def test_no_orphans_returns_empty_list(self):
        """When there are no orphan subagents, returns []."""
        from bob.run_loop import backstop_reaper_for_orphan_subagents

        with patch(
            "bob.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = backstop_reaper_for_orphan_subagents()

        self.assertEqual(result, [])

    def test_orphan_found_returns_tuple_list(self):
        """When orphans are found, returns list of (feature_id, pid) tuples."""
        from bob.run_loop import backstop_reaper_for_orphan_subagents

        fake_fid = "deadbeef-0000-0000-0000-000000000001"
        fake_pid = 99999
        with patch(
            "bob.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = [(fake_fid, fake_pid)]
            result = backstop_reaper_for_orphan_subagents()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], (fake_fid, fake_pid))

    def test_function_is_importable_from_run_loop(self):
        """backstop_reaper_for_orphan_subagents is accessible from bob.run_loop."""
        import bob.run_loop as rl

        self.assertTrue(hasattr(rl, "backstop_reaper_for_orphan_subagents"))
        self.assertTrue(callable(rl.backstop_reaper_for_orphan_subagents))

    def test_function_in_all(self):
        """backstop_reaper_for_orphan_subagents is exported in __all__."""
        import bob.run_loop as rl

        self.assertIn("backstop_reaper_for_orphan_subagents", rl.__all__)


if __name__ == "__main__":
    unittest.main()
