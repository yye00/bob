"""Error path tests for bob.run_loop subagent reaping functions.

AC: pytest: tests/test_run_loop_must_reap_claude_subagent_process_on_feat_error.py
    — invalid input raises ValueError and the function does not silently succeed
    (error path)

Tests that sigterm_subagent_on_terminal_state and sigkill_orphan_subagents_sweeper
reject invalid inputs with ValueError rather than silently succeeding or returning
a misleading result.
"""

from __future__ import annotations

import unittest


class TestSigtermSubagentOnTerminalStateErrorPath(unittest.TestCase):
    """Error-path tests for sigterm_subagent_on_terminal_state."""

    def test_none_feature_id_raises_value_error(self):
        """None feature_id raises ValueError — must not silently succeed."""
        from bob.run_loop import sigterm_subagent_on_terminal_state

        with self.assertRaises(ValueError) as ctx:
            sigterm_subagent_on_terminal_state(None)  # type: ignore[arg-type]

        self.assertIn("feature_id", str(ctx.exception).lower())

    def test_int_feature_id_raises_value_error(self):
        """Integer feature_id raises ValueError."""
        from bob.run_loop import sigterm_subagent_on_terminal_state

        with self.assertRaises(ValueError):
            sigterm_subagent_on_terminal_state(12345)  # type: ignore[arg-type]

    def test_list_feature_id_raises_value_error(self):
        """List feature_id raises ValueError."""
        from bob.run_loop import sigterm_subagent_on_terminal_state

        with self.assertRaises(ValueError):
            sigterm_subagent_on_terminal_state(["a", "b"])  # type: ignore[arg-type]

    def test_dict_feature_id_raises_value_error(self):
        """Dict feature_id raises ValueError."""
        from bob.run_loop import sigterm_subagent_on_terminal_state

        with self.assertRaises(ValueError):
            sigterm_subagent_on_terminal_state({"id": "x"})  # type: ignore[arg-type]

    def test_error_message_names_type(self):
        """ValueError message identifies the bad type."""
        from bob.run_loop import sigterm_subagent_on_terminal_state

        with self.assertRaises(ValueError) as ctx:
            sigterm_subagent_on_terminal_state(42)  # type: ignore[arg-type]

        self.assertIn("int", str(ctx.exception))


class TestSigkillOrphanSubagentsSweeperErrorPath(unittest.TestCase):
    """Error-path tests for sigkill_orphan_subagents_sweeper."""

    def test_negative_stale_minutes_raises_value_error(self):
        """Negative stale_minutes raises ValueError — must not silently succeed."""
        from bob.run_loop import sigkill_orphan_subagents_sweeper

        with self.assertRaises(ValueError) as ctx:
            sigkill_orphan_subagents_sweeper(-1)

        self.assertIn("stale_minutes", str(ctx.exception).lower())

    def test_large_negative_stale_minutes_raises_value_error(self):
        """Large negative stale_minutes raises ValueError."""
        from bob.run_loop import sigkill_orphan_subagents_sweeper

        with self.assertRaises(ValueError):
            sigkill_orphan_subagents_sweeper(-999)

    def test_negative_float_stale_minutes_raises_value_error(self):
        """Negative float stale_minutes raises ValueError."""
        from bob.run_loop import sigkill_orphan_subagents_sweeper

        with self.assertRaises(ValueError):
            sigkill_orphan_subagents_sweeper(-0.1)

    def test_error_message_names_value(self):
        """ValueError message includes the bad value."""
        from bob.run_loop import sigkill_orphan_subagents_sweeper

        with self.assertRaises(ValueError) as ctx:
            sigkill_orphan_subagents_sweeper(-5)

        self.assertIn("-5", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
