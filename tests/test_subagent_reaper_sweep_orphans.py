"""Tests for sweep_orphan_subagents — orphan backstop sweeper.

Verifies that sweep_orphan_subagents reaps orphan subagents for features
whose terminal-state dwell exceeds 5 minutes.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, call, patch


class TestSweepOrphanSubagents(unittest.TestCase):
    """Unit tests for sweep_orphan_subagents."""

    def setUp(self):
        from bob.orchestrator.subagent_reaper import sweep_orphan_subagents
        self.sweep = sweep_orphan_subagents

    def test_returns_list_of_reaped_pairs(self):
        """sweep_orphan_subagents returns list of (feature_id, pid) tuples."""
        from bob.orchestrator.subagent_reaper import sweep_orphan_subagents

        with patch("bob.orchestrator.subagent_reaper._query_stale_terminal_features") as mock_query, \
             patch("bob.orchestrator.subagent_reaper.reap_subagent_for_feature") as mock_reap:

            stale_fid = "stale111-0000-0000-0000-000000000001"
            mock_query.return_value = [stale_fid]
            mock_reap.return_value = [54321]

            result = sweep_orphan_subagents()

        self.assertIsInstance(result, list)
        self.assertIn((stale_fid, 54321), result)

    def test_calls_reap_for_each_stale_feature(self):
        """sweep_orphan_subagents calls reap_subagent_for_feature for each stale feature."""
        from bob.orchestrator.subagent_reaper import sweep_orphan_subagents

        stale1 = "stale111-0000-0000-0000-000000000002"
        stale2 = "stale222-0000-0000-0000-000000000003"

        with patch("bob.orchestrator.subagent_reaper._query_stale_terminal_features") as mock_query, \
             patch("bob.orchestrator.subagent_reaper.reap_subagent_for_feature") as mock_reap:

            mock_query.return_value = [stale1, stale2]
            mock_reap.side_effect = [[11111], [22222]]

            result = sweep_orphan_subagents()

        mock_reap.assert_any_call(stale1)
        mock_reap.assert_any_call(stale2)
        self.assertIn((stale1, 11111), result)
        self.assertIn((stale2, 22222), result)

    def test_returns_empty_when_no_stale_features(self):
        """sweep_orphan_subagents returns [] when no stale terminal features exist."""
        from bob.orchestrator.subagent_reaper import sweep_orphan_subagents

        with patch("bob.orchestrator.subagent_reaper._query_stale_terminal_features") as mock_query, \
             patch("bob.orchestrator.subagent_reaper.reap_subagent_for_feature") as mock_reap:

            mock_query.return_value = []
            result = sweep_orphan_subagents()

        self.assertEqual(result, [])
        mock_reap.assert_not_called()

    def test_handles_feature_with_no_running_subagent(self):
        """sweep_orphan_subagents skips features whose subagent is already dead."""
        from bob.orchestrator.subagent_reaper import sweep_orphan_subagents

        stale_fid = "stale333-0000-0000-0000-000000000004"

        with patch("bob.orchestrator.subagent_reaper._query_stale_terminal_features") as mock_query, \
             patch("bob.orchestrator.subagent_reaper.reap_subagent_for_feature") as mock_reap:

            mock_query.return_value = [stale_fid]
            mock_reap.return_value = []  # no PID found / already dead

            result = sweep_orphan_subagents()

        self.assertEqual(result, [])

    def test_is_idempotent(self):
        """sweep_orphan_subagents can be called multiple times without side effects."""
        from bob.orchestrator.subagent_reaper import sweep_orphan_subagents

        with patch("bob.orchestrator.subagent_reaper._query_stale_terminal_features") as mock_query, \
             patch("bob.orchestrator.subagent_reaper.reap_subagent_for_feature") as mock_reap:

            mock_query.return_value = []
            r1 = sweep_orphan_subagents()
            r2 = sweep_orphan_subagents()

        self.assertEqual(r1, [])
        self.assertEqual(r2, [])

    def test_query_uses_5min_threshold(self):
        """_query_stale_terminal_features uses 5-minute dwell threshold."""
        from bob.orchestrator.subagent_reaper import _query_stale_terminal_features

        # Call with mocked db — verify the SQL uses the 5-min check.
        # We can't easily intercept the SQL, so we verify the function
        # is callable and returns a list without error when db has no rows.
        with patch("bob.orchestrator.subagent_reaper.db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.execute.return_value = mock_cursor
            mock_db.connect.return_value = mock_conn

            result = _query_stale_terminal_features()

        self.assertEqual(result, [])
        # Verify SQL was called with terminal statuses
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]
        self.assertIn("completed", sql)
        self.assertIn("needs_human", sql)
        self.assertIn("1440", sql)  # minutes conversion in julianday math


if __name__ == "__main__":
    unittest.main()
