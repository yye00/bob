"""Tests for bob.orchestrator.subagent_reaper.reap_subagent_on_terminal.

AC: pytest: tests/test_subagent_reaper_terminal.py
AC: Function defined: bob.orchestrator.subagent_reaper.reap_subagent_on_terminal

reap_subagent_on_terminal is the named terminal-transition entry point. It
validates its input, delegates to reap_subagent_for_feature, and returns the
list of reaped PIDs. Invalid input must raise ValueError rather than silently
succeed.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from bob.orchestrator import subagent_reaper


class TestReapSubagentOnTerminalDefined(unittest.TestCase):
    """The named entry point exists and is callable."""

    def test_function_is_defined(self):
        self.assertTrue(hasattr(subagent_reaper, "reap_subagent_on_terminal"))
        self.assertTrue(callable(subagent_reaper.reap_subagent_on_terminal))


class TestReapSubagentOnTerminalHappyPath(unittest.TestCase):
    """Valid inputs delegate to reap_subagent_for_feature."""

    def test_returns_reaped_pids(self):
        fake_fid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch.object(
            subagent_reaper, "reap_subagent_for_feature", return_value=[4242]
        ) as mock_reap:
            result = subagent_reaper.reap_subagent_on_terminal(fake_fid)

        self.assertEqual(result, [4242])
        mock_reap.assert_called_once_with(fake_fid)

    def test_no_matching_process_returns_empty_list(self):
        fake_fid = "00000000-0000-0000-0000-000000000000"
        with patch.object(
            subagent_reaper, "reap_subagent_for_feature", return_value=[]
        ):
            result = subagent_reaper.reap_subagent_on_terminal(fake_fid)

        self.assertEqual(result, [])


class TestReapSubagentOnTerminalBoundary(unittest.TestCase):
    """Empty / minimum input returns a well-defined result without raising."""

    def test_empty_feature_id_returns_empty_list(self):
        result = subagent_reaper.reap_subagent_on_terminal("")
        self.assertEqual(result, [])

    def test_empty_feature_id_does_not_call_reaper(self):
        with patch.object(
            subagent_reaper, "reap_subagent_for_feature"
        ) as mock_reap:
            result = subagent_reaper.reap_subagent_on_terminal("")

        self.assertEqual(result, [])
        mock_reap.assert_not_called()


class TestReapSubagentOnTerminalErrorPath(unittest.TestCase):
    """Invalid-typed input raises ValueError, does not silently succeed."""

    def test_none_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            subagent_reaper.reap_subagent_on_terminal(None)  # type: ignore[arg-type]
        self.assertIn("feature_id", str(ctx.exception).lower())

    def test_int_raises_value_error(self):
        with self.assertRaises(ValueError):
            subagent_reaper.reap_subagent_on_terminal(123)  # type: ignore[arg-type]

    def test_list_raises_value_error(self):
        with self.assertRaises(ValueError):
            subagent_reaper.reap_subagent_on_terminal(["x"])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
