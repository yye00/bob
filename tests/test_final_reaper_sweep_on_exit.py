"""Tests for the final reaper sweep on orchestrator exit (feature ef89f7ca).

When the orchestrator loop terminates on ALL_BLOCKED or BUDGET_EXCEEDED, any
rows still in status='executing' whose sub-agent has already died must be
flipped to 'failed' with reason 'orchestrator_exit_during_execution' before the
loop returns its LoopTermination. Otherwise the stale rows pollute inter-gen
status reports ("5 executing" forever).

AC coverage:
- Function defined: bob.run_loop.sweep_orphan_subagents
- Function defined: bob.run_loop._run_locked
- integration: bob.run_loop
- pytest: tests/test_final_reaper_sweep_on_exit.py
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bob import final_reaper
from bob.final_reaper import sweep_orphans_on_exit


def _feature(fid: str, status: str = "executing"):
    return SimpleNamespace(id=fid, status=status, name=f"feat-{fid[:8]}")


class TestFunctionsDefined(unittest.TestCase):
    """AC: named entry points exist on bob.run_loop."""

    def test_sweep_orphan_subagents_defined_on_run_loop(self):
        from bob.run_loop import sweep_orphan_subagents
        self.assertTrue(callable(sweep_orphan_subagents))

    def test_run_locked_defined_on_run_loop(self):
        from bob.run_loop import _run_locked
        self.assertTrue(callable(_run_locked))

    def test_run_locked_delegates_to_sweep_orphans_on_exit(self):
        """_run_locked must invoke the final-exit sweep for the project."""
        with patch("bob.final_reaper.sweep_orphans_on_exit") as mock_sweep:
            mock_sweep.return_value = ["feat-1"]
            from bob.run_loop import _run_locked
            result = _run_locked("proj-123")
        mock_sweep.assert_called_once_with("proj-123")
        self.assertEqual(result, ["feat-1"])


class TestSweepFlipsOrphans(unittest.TestCase):
    """Core behavior: orphan executing rows (no live PID) are flipped to failed."""

    def test_orphan_with_no_pid_is_flipped_to_failed(self):
        orphan = _feature("94c9de63-0000-0000-0000-000000000001")
        with patch.object(final_reaper, "sweep_orphan_subagents", return_value=[]), \
             patch.object(final_reaper, "find_subagent_pid_for_feature", return_value=[]), \
             patch.object(final_reaper.db, "list_features", return_value=[orphan]) as mock_list, \
             patch.object(final_reaper.db, "update_feature") as mock_update:
            flipped = sweep_orphans_on_exit("proj-x")

        self.assertEqual(flipped, [orphan.id])
        mock_list.assert_called_once_with(project_id="proj-x", status="executing")
        mock_update.assert_called_once_with(
            orphan.id,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )

    def test_feature_with_live_pid_is_left_alone(self):
        live = _feature("14298e1d-0000-0000-0000-000000000002")
        with patch.object(final_reaper, "sweep_orphan_subagents", return_value=[]), \
             patch.object(final_reaper, "find_subagent_pid_for_feature", return_value=[4242]), \
             patch.object(final_reaper.db, "list_features", return_value=[live]), \
             patch.object(final_reaper.db, "update_feature") as mock_update:
            flipped = sweep_orphans_on_exit("proj-x")

        self.assertEqual(flipped, [])
        mock_update.assert_not_called()

    def test_multiple_orphans_all_flipped(self):
        orphans = [
            _feature("94c9de63-0000-0000-0000-000000000001"),
            _feature("b394aa24-0000-0000-0000-000000000003"),
            _feature("97fe3ec0-0000-0000-0000-000000000004"),
        ]
        with patch.object(final_reaper, "sweep_orphan_subagents", return_value=[]), \
             patch.object(final_reaper, "find_subagent_pid_for_feature", return_value=[]), \
             patch.object(final_reaper.db, "list_features", return_value=orphans), \
             patch.object(final_reaper.db, "update_feature") as mock_update:
            flipped = sweep_orphans_on_exit("proj-x")

        self.assertEqual(flipped, [o.id for o in orphans])
        self.assertEqual(mock_update.call_count, 3)

    def test_mixed_live_and_orphan_only_orphan_flipped(self):
        orphan = _feature("94c9de63-0000-0000-0000-000000000001")
        live = _feature("14298e1d-0000-0000-0000-000000000002")

        def pid_lookup(fid):
            return [999] if fid == live.id else []

        with patch.object(final_reaper, "sweep_orphan_subagents", return_value=[]), \
             patch.object(final_reaper, "find_subagent_pid_for_feature", side_effect=pid_lookup), \
             patch.object(final_reaper.db, "list_features", return_value=[orphan, live]), \
             patch.object(final_reaper.db, "update_feature") as mock_update:
            flipped = sweep_orphans_on_exit("proj-x")

        self.assertEqual(flipped, [orphan.id])
        mock_update.assert_called_once()


class TestIdempotentAndResilient(unittest.TestCase):
    """The sweep must be idempotent and never abort on a single broken row."""

    def test_no_executing_rows_returns_empty(self):
        with patch.object(final_reaper, "sweep_orphan_subagents", return_value=[]), \
             patch.object(final_reaper.db, "list_features", return_value=[]), \
             patch.object(final_reaper.db, "update_feature") as mock_update:
            flipped = sweep_orphans_on_exit("proj-x")

        self.assertEqual(flipped, [])
        mock_update.assert_not_called()

    def test_second_call_with_no_orphans_is_noop(self):
        """After the first sweep flips everything, a second call flips nothing."""
        with patch.object(final_reaper, "sweep_orphan_subagents", return_value=[]), \
             patch.object(final_reaper, "find_subagent_pid_for_feature", return_value=[]), \
             patch.object(final_reaper.db, "list_features", return_value=[]), \
             patch.object(final_reaper.db, "update_feature") as mock_update:
            self.assertEqual(sweep_orphans_on_exit("proj-x"), [])
        mock_update.assert_not_called()

    def test_broken_row_does_not_abort_remaining_sweep(self):
        good = _feature("94c9de63-0000-0000-0000-000000000001")
        bad = _feature("630e1914-0000-0000-0000-000000000005")

        def update(fid, **kwargs):
            if fid == bad.id:
                raise RuntimeError("db write failed for this row")
            return None

        with patch.object(final_reaper, "sweep_orphan_subagents", return_value=[]), \
             patch.object(final_reaper, "find_subagent_pid_for_feature", return_value=[]), \
             patch.object(final_reaper.db, "list_features", return_value=[bad, good]), \
             patch.object(final_reaper.db, "update_feature", side_effect=update):
            flipped = sweep_orphans_on_exit("proj-x")

        # bad row raised and was skipped; good row still flipped.
        self.assertEqual(flipped, [good.id])

    def test_sweep_orphan_subagents_exception_does_not_abort(self):
        orphan = _feature("94c9de63-0000-0000-0000-000000000001")
        with patch.object(final_reaper, "sweep_orphan_subagents", side_effect=RuntimeError("reap boom")), \
             patch.object(final_reaper, "find_subagent_pid_for_feature", return_value=[]), \
             patch.object(final_reaper.db, "list_features", return_value=[orphan]), \
             patch.object(final_reaper.db, "update_feature"):
            flipped = sweep_orphans_on_exit("proj-x")

        self.assertEqual(flipped, [orphan.id])

    def test_list_features_failure_returns_empty(self):
        with patch.object(final_reaper, "sweep_orphan_subagents", return_value=[]), \
             patch.object(final_reaper.db, "list_features", side_effect=RuntimeError("query failed")):
            flipped = sweep_orphans_on_exit("proj-x")
        self.assertEqual(flipped, [])


if __name__ == "__main__":
    unittest.main()
