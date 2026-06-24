"""Tests for bob3.orchestrator.final_reaper.sweep_orphans_on_exit.

AC: pytest: tests/test_orchestrator_final_reaper.py
AC: File exists: src/bob3/orchestrator/final_reaper.py
AC: Function defined: bob3.orchestrator.final_reaper.sweep_orphans_on_exit
AC: integration: bob3.orchestrator.run_loop
"""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import MagicMock, patch


class TestOrchestratorFinalReaperModule(unittest.TestCase):
    """Structural ACs: file exists, module importable, function defined."""

    def test_module_importable(self):
        """bob3.orchestrator.final_reaper must be importable."""
        import bob3.orchestrator.final_reaper  # noqa: F401

    def test_sweep_orphans_on_exit_exists(self):
        """sweep_orphans_on_exit must be a callable in bob3.orchestrator.final_reaper."""
        from bob3.orchestrator.final_reaper import sweep_orphans_on_exit
        assert callable(sweep_orphans_on_exit)

    def test_function_signature_accepts_project_id(self):
        """sweep_orphans_on_exit must accept a project_id parameter."""
        from bob3.orchestrator.final_reaper import sweep_orphans_on_exit
        sig = inspect.signature(sweep_orphans_on_exit)
        assert "project_id" in sig.parameters

    def test_function_returns_list(self):
        """sweep_orphans_on_exit must return a list."""
        from bob3.orchestrator.final_reaper import sweep_orphans_on_exit

        with patch("bob3.orchestrator.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.orchestrator.final_reaper.db") as mock_db, \
             patch("bob3.orchestrator.final_reaper.find_subagent_pid_for_feature"):
            mock_sweep.return_value = []
            mock_db.list_features.return_value = []
            result = sweep_orphans_on_exit("proj-struct-001")

        assert isinstance(result, list)


class TestOrchestratorFinalReaperBehavior(unittest.TestCase):
    """Core behavior: orphan executing rows are flipped to failed."""

    def test_orphan_feature_flipped_to_failed(self):
        """An executing feature with no live PID must be flipped to failed."""
        from bob3.orchestrator.final_reaper import sweep_orphans_on_exit

        feature_id = "feat-orch-0001-0000-0000-000000000001"
        fake_feat = MagicMock()
        fake_feat.id = feature_id

        with patch("bob3.orchestrator.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.orchestrator.final_reaper.db") as mock_db, \
             patch("bob3.orchestrator.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [fake_feat]
            mock_pids.return_value = []

            result = sweep_orphans_on_exit("proj-orch-001")

        assert feature_id in result
        mock_db.update_feature.assert_called_once_with(
            feature_id,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )

    def test_live_pid_feature_not_flipped(self):
        """A feature with a live PID must NOT be touched."""
        from bob3.orchestrator.final_reaper import sweep_orphans_on_exit

        feature_id = "feat-orch-live-0000-0000-000000000002"
        fake_feat = MagicMock()
        fake_feat.id = feature_id

        with patch("bob3.orchestrator.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.orchestrator.final_reaper.db") as mock_db, \
             patch("bob3.orchestrator.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [fake_feat]
            mock_pids.return_value = [55555]

            result = sweep_orphans_on_exit("proj-orch-002")

        assert result == []
        mock_db.update_feature.assert_not_called()

    def test_sweep_orphan_subagents_called_first(self):
        """sweep_orphan_subagents must be invoked before querying executing rows."""
        from bob3.orchestrator.final_reaper import sweep_orphans_on_exit

        call_order = []

        def mock_sweep():
            call_order.append("sweep")
            return []

        def mock_list(project_id, status):
            call_order.append("list")
            return []

        with patch("bob3.orchestrator.final_reaper.sweep_orphan_subagents", side_effect=mock_sweep), \
             patch("bob3.orchestrator.final_reaper.db") as mock_db:
            mock_db.list_features.side_effect = mock_list
            sweep_orphans_on_exit("proj-orch-003")

        assert call_order[0] == "sweep"

    def test_none_project_id_raises_value_error(self):
        """None project_id must raise ValueError."""
        from bob3.orchestrator.final_reaper import sweep_orphans_on_exit

        with self.assertRaises(ValueError):
            sweep_orphans_on_exit(None)  # type: ignore[arg-type]

    def test_non_string_project_id_raises_value_error(self):
        """Non-string project_id must raise ValueError."""
        from bob3.orchestrator.final_reaper import sweep_orphans_on_exit

        with self.assertRaises(ValueError):
            sweep_orphans_on_exit(123)  # type: ignore[arg-type]


class TestOrchestratorFinalReaperRunLoopIntegration(unittest.TestCase):
    """Integration AC: run_loop calls _final_exit_sweep on ALL_BLOCKED/BUDGET_EXCEEDED exit."""

    def test_run_loop_has_final_exit_sweep(self):
        """run_loop must expose _final_exit_sweep as a callable."""
        from bob3.orchestrator.run_loop import _final_exit_sweep
        assert callable(_final_exit_sweep)

    def test_final_exit_sweep_invokes_sweep_orphan_subagents(self):
        """_final_exit_sweep in run_loop must call _sweep_orphan_subagents."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature"):
            mock_db.list_features.return_value = []
            mock_sweep.return_value = []

            _final_exit_sweep("proj-integ-orch-001")

        mock_sweep.assert_called_once()

    def test_final_exit_sweep_flips_orphan_to_failed(self):
        """_final_exit_sweep must flip orphan executing features to failed."""
        from bob3.orchestrator.run_loop import _final_exit_sweep

        feature_id = "feat-integ-orch-0001-0000-0000-000000000001"
        fake_feat = MagicMock()
        fake_feat.id = feature_id
        fake_feat.name = "integ-orphan"
        fake_feat.acceptance_criteria = "[]"

        with patch("bob3.orchestrator.run_loop.db") as mock_db, \
             patch("bob3.orchestrator.run_loop.find_subagent_pid_for_feature") as mock_pids, \
             patch("bob3.orchestrator.run_loop._check_executing_feature_acs") as mock_disk, \
             patch("bob3.orchestrator.run_loop._sweep_orphan_subagents") as mock_orphan:
            mock_db.list_features.return_value = [fake_feat]
            mock_pids.return_value = []
            mock_disk.return_value = False
            mock_orphan.return_value = []

            _final_exit_sweep("proj-integ-orch-002")

        mock_db.update_feature.assert_called_once_with(
            feature_id,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )
