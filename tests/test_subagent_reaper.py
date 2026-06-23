"""Tests for bob3.subagent_reaper — feature terminal-state process cleanup.

AC: pytest: tests/test_subagent_reaper.py
    Verifies that bob3.subagent_reaper exposes the required public functions
    and that they behave correctly.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch


class TestSubagentReaperPublicInterface(unittest.TestCase):
    """Verify the public API of bob3.subagent_reaper."""

    def test_reap_subagent_on_terminal_state_importable(self):
        """reap_subagent_on_terminal_state is importable from bob3.subagent_reaper."""
        from bob3.subagent_reaper import reap_subagent_on_terminal_state  # noqa: F401

        self.assertTrue(callable(reap_subagent_on_terminal_state))

    def test_sweep_orphan_subagents_importable(self):
        """sweep_orphan_subagents is importable from bob3.subagent_reaper."""
        from bob3.subagent_reaper import sweep_orphan_subagents  # noqa: F401

        self.assertTrue(callable(sweep_orphan_subagents))

    def test_reap_subagent_for_feature_importable(self):
        """reap_subagent_for_feature is importable from bob3.subagent_reaper."""
        from bob3.subagent_reaper import reap_subagent_for_feature  # noqa: F401

        self.assertTrue(callable(reap_subagent_for_feature))

    def test_find_subagent_pid_for_feature_importable(self):
        """find_subagent_pid_for_feature is importable from bob3.subagent_reaper."""
        from bob3.subagent_reaper import find_subagent_pid_for_feature  # noqa: F401

        self.assertTrue(callable(find_subagent_pid_for_feature))


class TestReapSubagentOnTerminalState(unittest.TestCase):
    """Tests for reap_subagent_on_terminal_state."""

    def test_empty_feature_id_returns_empty_list(self):
        """Empty string feature_id returns [] without raising."""
        from bob3.subagent_reaper import reap_subagent_on_terminal_state

        result = reap_subagent_on_terminal_state("")
        self.assertEqual(result, [])

    def test_none_feature_id_raises_value_error(self):
        """None feature_id raises ValueError."""
        from bob3.subagent_reaper import reap_subagent_on_terminal_state

        with self.assertRaises(ValueError) as ctx:
            reap_subagent_on_terminal_state(None)  # type: ignore[arg-type]

        self.assertIn("feature_id", str(ctx.exception).lower())

    def test_int_feature_id_raises_value_error(self):
        """Integer feature_id raises ValueError."""
        from bob3.subagent_reaper import reap_subagent_on_terminal_state

        with self.assertRaises(ValueError):
            reap_subagent_on_terminal_state(42)  # type: ignore[arg-type]

    def test_valid_feature_id_no_matching_process_returns_empty(self):
        """Valid feature_id with no running process returns []."""
        from bob3.subagent_reaper import reap_subagent_on_terminal_state

        fake_fid = "00000000-0000-0000-0000-000000000000"
        with patch(
            "bob3.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = []
            result = reap_subagent_on_terminal_state(fake_fid)

        self.assertEqual(result, [])
        mock_reap.assert_called_once_with(fake_fid)

    def test_valid_feature_id_with_process_returns_pid_list(self):
        """Valid feature_id with matching process returns list of int PIDs."""
        from bob3.subagent_reaper import reap_subagent_on_terminal_state

        fake_fid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        fake_pid = 12345
        with patch(
            "bob3.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [fake_pid]
            result = reap_subagent_on_terminal_state(fake_fid)

        self.assertIsInstance(result, list)
        self.assertIn(fake_pid, result)
        mock_reap.assert_called_once_with(fake_fid)

    def test_error_message_names_type_for_int(self):
        """ValueError message mentions the bad type."""
        from bob3.subagent_reaper import reap_subagent_on_terminal_state

        with self.assertRaises(ValueError) as ctx:
            reap_subagent_on_terminal_state(42)  # type: ignore[arg-type]

        self.assertIn("int", str(ctx.exception))


class TestSweepOrphanSubagents(unittest.TestCase):
    """Tests for sweep_orphan_subagents."""

    def test_returns_list(self):
        """sweep_orphan_subagents returns a list."""
        from bob3.subagent_reaper import sweep_orphan_subagents

        with patch(
            "bob3.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = sweep_orphan_subagents()

        self.assertIsInstance(result, list)

    def test_no_orphans_returns_empty_list(self):
        """When no orphan subagents exist, returns empty list."""
        from bob3.subagent_reaper import sweep_orphan_subagents

        with patch(
            "bob3.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = sweep_orphan_subagents()

        self.assertEqual(result, [])

    def test_orphans_found_returns_tuples(self):
        """sweep_orphan_subagents returns list of (feature_id, pid) tuples."""
        # The function is imported at module level from orchestrator; test that
        # the real call path returns a list (no exceptions, right shape).
        from bob3.subagent_reaper import sweep_orphan_subagents

        # patch the underlying orchestrator function via its module
        import bob3.orchestrator.subagent_reaper as _orch_reaper

        fake_fid = "deadbeef-0000-0000-0000-000000000001"
        fake_pid = 99999
        original = _orch_reaper.sweep_orphan_subagents
        try:
            _orch_reaper.sweep_orphan_subagents = lambda: [(fake_fid, fake_pid)]
            result = sweep_orphan_subagents()
        finally:
            _orch_reaper.sweep_orphan_subagents = original

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], (fake_fid, fake_pid))


class TestReapOnTerminalTransition(unittest.TestCase):
    """Tests for reap_on_terminal_transition — AC-required function name."""

    def test_importable(self):
        """reap_on_terminal_transition is importable from bob3.subagent_reaper."""
        from bob3.subagent_reaper import reap_on_terminal_transition  # noqa: F401

        self.assertTrue(callable(reap_on_terminal_transition))

    def test_empty_feature_id_returns_empty_list(self):
        """Empty string feature_id returns [] without raising."""
        from bob3.subagent_reaper import reap_on_terminal_transition

        result = reap_on_terminal_transition("")
        self.assertEqual(result, [])

    def test_none_feature_id_raises_value_error(self):
        """None feature_id raises ValueError."""
        from bob3.subagent_reaper import reap_on_terminal_transition

        with self.assertRaises(ValueError) as ctx:
            reap_on_terminal_transition(None)  # type: ignore[arg-type]

        self.assertIn("feature_id", str(ctx.exception).lower())

    def test_valid_feature_id_no_matching_process_returns_empty(self):
        """Valid feature_id with no running process returns []."""
        from bob3.subagent_reaper import reap_on_terminal_transition

        fake_fid = "00000000-0000-0000-0000-111111111111"
        with patch(
            "bob3.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = []
            result = reap_on_terminal_transition(fake_fid)

        self.assertEqual(result, [])

    def test_valid_feature_id_with_process_returns_pid_list(self):
        """Valid feature_id with matching process returns list of int PIDs."""
        from bob3.subagent_reaper import reap_on_terminal_transition

        fake_fid = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
        fake_pid = 54321
        with patch(
            "bob3.subagent_reaper.reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [fake_pid]
            result = reap_on_terminal_transition(fake_fid)

        self.assertIsInstance(result, list)
        self.assertIn(fake_pid, result)


class TestReapStaleOrphans(unittest.TestCase):
    """Tests for reap_stale_orphans — AC-required function name."""

    def test_importable(self):
        """reap_stale_orphans is importable from bob3.subagent_reaper."""
        from bob3.subagent_reaper import reap_stale_orphans  # noqa: F401

        self.assertTrue(callable(reap_stale_orphans))

    def test_returns_list(self):
        """reap_stale_orphans returns a list."""
        from bob3.subagent_reaper import reap_stale_orphans

        with patch(
            "bob3.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = reap_stale_orphans()

        self.assertIsInstance(result, list)

    def test_no_orphans_returns_empty_list(self):
        """When no orphan subagents exist, returns empty list."""
        from bob3.subagent_reaper import reap_stale_orphans

        with patch(
            "bob3.orchestrator.subagent_reaper.sweep_orphan_subagents"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = reap_stale_orphans()

        self.assertEqual(result, [])

    def test_orphans_found_returns_tuples(self):
        """reap_stale_orphans returns list of (feature_id, pid) tuples."""
        from bob3.subagent_reaper import reap_stale_orphans

        import bob3.orchestrator.subagent_reaper as _orch_reaper

        fake_fid = "deadbeef-1111-2222-3333-444444444444"
        fake_pid = 77777
        original = _orch_reaper.sweep_orphan_subagents
        try:
            _orch_reaper.sweep_orphan_subagents = lambda: [(fake_fid, fake_pid)]
            result = reap_stale_orphans()
        finally:
            _orch_reaper.sweep_orphan_subagents = original

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], (fake_fid, fake_pid))


class TestRunLoopIntegration(unittest.TestCase):
    """Integration tests verifying run_loop uses subagent reaper functions."""

    def test_run_loop_has_sigterm_subagent_on_terminal_state(self):
        """run_loop exposes sigterm_subagent_on_terminal_state."""
        from bob3 import run_loop

        self.assertTrue(hasattr(run_loop, "sigterm_subagent_on_terminal_state"))
        self.assertTrue(callable(run_loop.sigterm_subagent_on_terminal_state))

    def test_run_loop_has_sigkill_orphan_subagents_sweeper(self):
        """run_loop exposes sigkill_orphan_subagents_sweeper."""
        from bob3 import run_loop

        self.assertTrue(hasattr(run_loop, "sigkill_orphan_subagents_sweeper"))
        self.assertTrue(callable(run_loop.sigkill_orphan_subagents_sweeper))

    def test_run_loop_has_sweep_orphan_subagents(self):
        """run_loop exposes sweep_orphan_subagents."""
        from bob3 import run_loop

        self.assertTrue(hasattr(run_loop, "sweep_orphan_subagents"))
        self.assertTrue(callable(run_loop.sweep_orphan_subagents))

    def test_run_loop_has_reap_subagent_on_terminal_state(self):
        """run_loop exposes reap_subagent_on_terminal_state."""
        from bob3 import run_loop

        self.assertTrue(hasattr(run_loop, "reap_subagent_on_terminal_state"))
        self.assertTrue(callable(run_loop.reap_subagent_on_terminal_state))


if __name__ == "__main__":
    unittest.main()
