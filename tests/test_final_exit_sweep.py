"""Tests for _final_exit_sweep — final reaper sweep on orchestrator exit.

Verifies that _final_exit_sweep flips orphan 'executing' rows to 'failed'
before the orchestrator returns its LoopTermination, while preserving rows
whose owning PID is still alive.

AC coverage:
  - test_dead_executing_flipped_on_exit: dead PID → status='failed'
  - test_live_executing_preserved_on_exit: live PID → status unchanged
  - test_sweep_idempotent: calling twice with no state change → zero extra writes
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch


class TestDeadExecutingFlippedOnExit(unittest.TestCase):
    """test_dead_executing_flipped_on_exit: dead PID rows must be flipped to 'failed'."""

    def test_dead_executing_flipped_on_exit(self):
        """When a feature is 'executing' and its subagent PID is dead, _final_exit_sweep
        MUST flip its status to 'failed' with reason 'orchestrator_exit_during_execution'."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-dead-exec-0000-0000-000000000001"
        feature_id = "feat-dead-0000-0000-0000-000000000001"

        fake_feature = MagicMock()
        fake_feature.id = feature_id

        # Patch db.list_features to return one 'executing' feature
        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_find_pid:

            mock_db.list_features.return_value = [fake_feature]
            # No live PIDs for this feature → dead
            mock_find_pid.return_value = []
            mock_db.update_feature.return_value = MagicMock()

            _final_exit_sweep(project_id)

        # Must query executing features
        mock_db.list_features.assert_called_once_with(
            project_id=project_id, status="executing"
        )
        # Must flip to failed
        mock_db.update_feature.assert_called_once_with(
            feature_id,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )

    def test_multiple_dead_executing_all_flipped(self):
        """Multiple 'executing' features with dead PIDs are ALL flipped to 'failed'."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-multi-dead-0000-000000000001"
        fids = [
            "feat-dead-a-000-0000-0000-000000000001",
            "feat-dead-b-000-0000-0000-000000000002",
            "feat-dead-c-000-0000-0000-000000000003",
        ]

        fake_features = []
        for fid in fids:
            f = MagicMock()
            f.id = fid
            fake_features.append(f)

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents"), \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_find_pid:

            mock_db.list_features.return_value = fake_features
            mock_find_pid.return_value = []  # all dead
            mock_db.update_feature.return_value = MagicMock()

            _final_exit_sweep(project_id)

        self.assertEqual(mock_db.update_feature.call_count, 3)
        for fid in fids:
            mock_db.update_feature.assert_any_call(
                fid,
                status="failed",
                last_improvement_type="orchestrator_exit_during_execution",
            )


class TestLiveExecutingPreservedOnExit(unittest.TestCase):
    """test_live_executing_preserved_on_exit: live PID rows MUST NOT be touched."""

    def test_live_executing_preserved_on_exit(self):
        """When a feature is 'executing' and its subagent PID is still alive,
        _final_exit_sweep MUST NOT flip its status."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-live-exec-0000-0000-000000000001"
        feature_id = "feat-live-0000-0000-0000-000000000001"
        live_pid = 12345

        fake_feature = MagicMock()
        fake_feature.id = feature_id

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents"), \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_find_pid:

            mock_db.list_features.return_value = [fake_feature]
            # Live PID returned → feature's subagent is still running
            mock_find_pid.return_value = [live_pid]
            mock_db.update_feature.return_value = MagicMock()

            _final_exit_sweep(project_id)

        # Must NOT flip status for a feature with a live PID
        mock_db.update_feature.assert_not_called()

    def test_mixed_live_and_dead_only_dead_flipped(self):
        """With both live and dead 'executing' features, only dead ones are flipped."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-mixed-0000-0000-0000-000000000001"
        dead_fid = "feat-dead-0000-0000-0000-000000000010"
        live_fid = "feat-live-0000-0000-0000-000000000011"

        dead_feature = MagicMock()
        dead_feature.id = dead_fid
        live_feature = MagicMock()
        live_feature.id = live_fid

        def pid_side_effect(fid):
            if fid == live_fid:
                return [99999]
            return []

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents"), \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_find_pid:

            mock_db.list_features.return_value = [dead_feature, live_feature]
            mock_find_pid.side_effect = pid_side_effect
            mock_db.update_feature.return_value = MagicMock()

            _final_exit_sweep(project_id)

        # Only dead_fid should be flipped
        mock_db.update_feature.assert_called_once_with(
            dead_fid,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )


class TestSweepIdempotent(unittest.TestCase):
    """test_sweep_idempotent: calling _final_exit_sweep twice yields zero extra DB writes."""

    def test_sweep_idempotent(self):
        """Calling _final_exit_sweep twice when no executing features remain produces
        zero DB writes on the second call (idempotent guarantee)."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-idempotent-0000-0000-000000000001"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents"), \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature"):

            # First call: no executing features at all
            mock_db.list_features.return_value = []
            _final_exit_sweep(project_id)

            first_call_update_count = mock_db.update_feature.call_count  # 0

            # Second call: still no executing features
            mock_db.list_features.return_value = []
            _final_exit_sweep(project_id)

            second_call_update_count = mock_db.update_feature.call_count  # still 0

        self.assertEqual(first_call_update_count, 0)
        self.assertEqual(second_call_update_count, 0)

    def test_sweep_idempotent_after_flip(self):
        """After the first call flips a dead feature to 'failed', the second call
        sees no 'executing' rows and performs zero additional writes."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-idempotent2-0000-000000000001"
        feature_id = "feat-idem-0000-0000-0000-000000000001"

        fake_feature = MagicMock()
        fake_feature.id = feature_id

        flip_count = {"n": 0}

        def update_side_effect(fid, **kwargs):
            flip_count["n"] += 1
            return MagicMock()

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents"), \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_find_pid:

            mock_db.update_feature.side_effect = update_side_effect

            # First call: one dead executing feature
            mock_db.list_features.return_value = [fake_feature]
            mock_find_pid.return_value = []
            _final_exit_sweep(project_id)

            writes_after_first = flip_count["n"]

            # Second call: now no executing features (the flip happened)
            mock_db.list_features.return_value = []
            _final_exit_sweep(project_id)

            writes_after_second = flip_count["n"]

        self.assertEqual(writes_after_first, 1, "First call should flip exactly one row")
        self.assertEqual(writes_after_second, 1, "Second call should write nothing extra")


class TestFinalExitSweepNoExecutingRows(unittest.TestCase):
    """_final_exit_sweep is a no-op when there are no 'executing' rows."""

    def test_no_op_when_no_executing_features(self):
        """When there are no features in 'executing' status, _final_exit_sweep
        makes no DB writes and does not crash."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-noop-0000-0000-0000-000000000001"

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents"), \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_find_pid:

            mock_db.list_features.return_value = []

            _final_exit_sweep(project_id)  # Must not raise

        mock_db.update_feature.assert_not_called()
        mock_find_pid.assert_not_called()


class TestFinalExitSweepErrorTolerance(unittest.TestCase):
    """_final_exit_sweep tolerates per-feature errors without crashing."""

    def test_error_in_one_feature_does_not_abort_others(self):
        """If checking PIDs for one feature raises, the sweep continues to the next."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        project_id = "proj-error-tol-0000-000000000001"
        fid_error = "feat-err-0000-0000-0000-000000000001"
        fid_ok = "feat-ok-00000-0000-0000-000000000001"

        err_feature = MagicMock()
        err_feature.id = fid_error
        ok_feature = MagicMock()
        ok_feature.id = fid_ok

        def pid_side_effect(fid):
            if fid == fid_error:
                raise RuntimeError("simulated PID lookup failure")
            return []  # dead

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents"), \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_find_pid:

            mock_db.list_features.return_value = [err_feature, ok_feature]
            mock_find_pid.side_effect = pid_side_effect
            mock_db.update_feature.return_value = MagicMock()

            _final_exit_sweep(project_id)  # Must not raise

        # ok_feature must still be flipped
        mock_db.update_feature.assert_called_once_with(
            fid_ok,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )


if __name__ == "__main__":
    unittest.main()
