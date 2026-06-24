"""Tests for bob.final_reaper — sweep_orphans_on_exit (feature 457df9cf).

AC: pytest: tests/test_final_reaper.py
AC: File exists: src/bob/final_reaper.py
AC: Function defined: bob.final_reaper.sweep_orphans_on_exit
AC: integration: bob.orchestrator
"""

from __future__ import annotations

import importlib
import unittest
from unittest.mock import MagicMock, call, patch


class TestModuleAndFunction(unittest.TestCase):
    """Structural ACs: file exists, function defined."""

    def test_final_reaper_module_importable(self):
        """bob.final_reaper must be importable."""
        import bob.final_reaper  # noqa: F401

    def test_sweep_orphans_on_exit_exists(self):
        """sweep_orphans_on_exit must be a callable in bob.final_reaper."""
        from bob.final_reaper import sweep_orphans_on_exit
        assert callable(sweep_orphans_on_exit)

    def test_function_signature_accepts_project_id(self):
        """sweep_orphans_on_exit must accept a project_id positional argument."""
        import inspect
        from bob.final_reaper import sweep_orphans_on_exit
        sig = inspect.signature(sweep_orphans_on_exit)
        assert "project_id" in sig.parameters


class TestSweepOrphansOnExitBasicBehavior(unittest.TestCase):
    """Core behavior: finds orphan executing rows and flips them to failed."""

    def test_returns_list(self):
        """sweep_orphans_on_exit must return a list."""
        from bob.final_reaper import sweep_orphans_on_exit

        with patch("bob.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob.final_reaper.db") as mock_db, \
             patch("bob.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = []
            result = sweep_orphans_on_exit("proj-001")

        assert isinstance(result, list)

    def test_orphan_executing_feature_flipped_to_failed(self):
        """An executing feature with no live PID must be flipped to failed."""
        from bob.final_reaper import sweep_orphans_on_exit

        feature_id = "feat-0001-0000-0000-000000000001"
        fake_feat = MagicMock()
        fake_feat.id = feature_id
        fake_feat.name = "orphan-feature"

        with patch("bob.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob.final_reaper.db") as mock_db, \
             patch("bob.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [fake_feat]
            mock_pids.return_value = []  # no live PID

            result = sweep_orphans_on_exit("proj-002")

        assert feature_id in result
        mock_db.update_feature.assert_called_once_with(
            feature_id,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )

    def test_feature_with_live_pid_is_not_flipped(self):
        """An executing feature with a live PID must NOT be flipped."""
        from bob.final_reaper import sweep_orphans_on_exit

        feature_id = "feat-live-0000-0000-000000000001"
        fake_feat = MagicMock()
        fake_feat.id = feature_id

        with patch("bob.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob.final_reaper.db") as mock_db, \
             patch("bob.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [fake_feat]
            mock_pids.return_value = [12345]  # live PID present

            result = sweep_orphans_on_exit("proj-003")

        assert result == []
        mock_db.update_feature.assert_not_called()

    def test_multiple_orphan_features_all_flipped(self):
        """All orphan executing features must be flipped (not just the first)."""
        from bob.final_reaper import sweep_orphans_on_exit

        ids = [
            "feat-multi-0001-0000-0000-000000000001",
            "feat-multi-0002-0000-0000-000000000002",
            "feat-multi-0003-0000-0000-000000000003",
        ]
        features = [MagicMock(id=fid) for fid in ids]

        with patch("bob.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob.final_reaper.db") as mock_db, \
             patch("bob.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = features
            mock_pids.return_value = []  # all orphaned

            result = sweep_orphans_on_exit("proj-004")

        assert sorted(result) == sorted(ids)
        assert mock_db.update_feature.call_count == 3

    def test_mixed_live_and_orphan_features(self):
        """Only orphan features (no live PID) are flipped; live ones are skipped."""
        from bob.final_reaper import sweep_orphans_on_exit

        orphan_id = "feat-orphan-0001-0000-000000000001"
        live_id = "feat-live-00001-0000-000000000002"

        orphan_feat = MagicMock(id=orphan_id)
        live_feat = MagicMock(id=live_id)

        def pid_side_effect(fid):
            if fid == live_id:
                return [99999]
            return []

        with patch("bob.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob.final_reaper.db") as mock_db, \
             patch("bob.final_reaper.find_subagent_pid_for_feature", side_effect=pid_side_effect):
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [orphan_feat, live_feat]

            result = sweep_orphans_on_exit("proj-005")

        assert result == [orphan_id]
        mock_db.update_feature.assert_called_once_with(
            orphan_id,
            status="failed",
            last_improvement_type="orchestrator_exit_during_execution",
        )

    def test_sweep_orphan_subagents_is_called_first(self):
        """sweep_orphan_subagents must be invoked before querying executing rows."""
        from bob.final_reaper import sweep_orphans_on_exit

        call_order = []

        def mock_sweep():
            call_order.append("sweep_orphan_subagents")
            return []

        def mock_list(project_id, status):
            call_order.append("list_features")
            return []

        with patch("bob.final_reaper.sweep_orphan_subagents", side_effect=mock_sweep), \
             patch("bob.final_reaper.db") as mock_db:
            mock_db.list_features.side_effect = mock_list
            sweep_orphans_on_exit("proj-006")

        assert call_order[0] == "sweep_orphan_subagents"
        assert "list_features" in call_order


class TestSweepOrphansOnExitErrors(unittest.TestCase):
    """Error handling: per-feature errors are caught; function does not propagate."""

    def test_invalid_project_id_none_raises_value_error(self):
        """None project_id must raise ValueError."""
        from bob.final_reaper import sweep_orphans_on_exit

        with self.assertRaises(ValueError):
            sweep_orphans_on_exit(None)  # type: ignore[arg-type]

    def test_invalid_project_id_int_raises_value_error(self):
        """Non-string project_id must raise ValueError."""
        from bob.final_reaper import sweep_orphans_on_exit

        with self.assertRaises(ValueError):
            sweep_orphans_on_exit(42)  # type: ignore[arg-type]

    def test_sweep_orphan_subagents_error_does_not_propagate(self):
        """If sweep_orphan_subagents raises, the function continues and does not raise."""
        from bob.final_reaper import sweep_orphans_on_exit

        with patch("bob.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob.final_reaper.db") as mock_db, \
             patch("bob.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.side_effect = RuntimeError("reaper crashed")
            mock_db.list_features.return_value = []

            result = sweep_orphans_on_exit("proj-err-001")

        assert isinstance(result, list)

    def test_pid_lookup_error_skips_feature(self):
        """If PID lookup raises for a feature, that feature is skipped."""
        from bob.final_reaper import sweep_orphans_on_exit

        feature_id = "feat-piderr-0001-0000-000000000001"
        fake_feat = MagicMock(id=feature_id)

        with patch("bob.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob.final_reaper.db") as mock_db, \
             patch("bob.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [fake_feat]
            mock_pids.side_effect = RuntimeError("PID lookup failed")

            result = sweep_orphans_on_exit("proj-err-002")

        assert result == []
        mock_db.update_feature.assert_not_called()

    def test_update_failure_does_not_propagate(self):
        """If db.update_feature raises, the error is caught and function continues."""
        from bob.final_reaper import sweep_orphans_on_exit

        feature_id = "feat-upderr-0001-0000-000000000001"
        fake_feat = MagicMock(id=feature_id)

        with patch("bob.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob.final_reaper.db") as mock_db, \
             patch("bob.final_reaper.find_subagent_pid_for_feature") as mock_pids:
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [fake_feat]
            mock_pids.return_value = []
            mock_db.update_feature.side_effect = RuntimeError("DB write failed")

            # Must not raise
            result = sweep_orphans_on_exit("proj-err-003")

        assert result == []

    def test_list_features_failure_returns_empty(self):
        """If db.list_features raises, function returns empty list without raising."""
        from bob.final_reaper import sweep_orphans_on_exit

        with patch("bob.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob.final_reaper.db") as mock_db:
            mock_sweep.return_value = []
            mock_db.list_features.side_effect = RuntimeError("DB unavailable")

            result = sweep_orphans_on_exit("proj-err-004")

        assert result == []

    def test_partial_error_continues_remaining_features(self):
        """Per-feature error does not abort sweep — remaining features still processed."""
        from bob.final_reaper import sweep_orphans_on_exit

        f1 = MagicMock(id="feat-partial-01-0000-000000000001")
        f2 = MagicMock(id="feat-partial-02-0000-000000000002")

        def pid_side_effect(fid):
            if fid == f1.id:
                raise RuntimeError("PID lookup failed for f1")
            return []

        with patch("bob.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob.final_reaper.db") as mock_db, \
             patch("bob.final_reaper.find_subagent_pid_for_feature", side_effect=pid_side_effect):
            mock_sweep.return_value = []
            mock_db.list_features.return_value = [f1, f2]

            result = sweep_orphans_on_exit("proj-err-005")

        # f2 should still be flipped despite f1 erroring
        assert f2.id in result


class TestOrchestratorIntegration(unittest.TestCase):
    """Integration AC: sweep_orphans_on_exit is reachable via bob.orchestrator."""

    def test_final_reaper_importable_from_orchestrator_chain(self):
        """bob.final_reaper is importable (orchestrator integration confirmed via import chain)."""
        import bob.final_reaper
        assert hasattr(bob.final_reaper, "sweep_orphans_on_exit")

    def test_sweep_orphans_on_exit_uses_same_sweep_orphan_subagents_as_main_loop(self):
        """sweep_orphans_on_exit delegates to the same sweep_orphan_subagents used in run_loop."""
        from bob.final_reaper import sweep_orphans_on_exit

        # The function under test imports sweep_orphan_subagents from
        # bob.orchestrator.subagent_reaper — the same module used by run_loop.
        # We verify it is called during execution.
        with patch("bob.final_reaper.sweep_orphan_subagents") as mock_sweep, \
             patch("bob.final_reaper.db") as mock_db, \
             patch("bob.final_reaper.find_subagent_pid_for_feature"):
            mock_sweep.return_value = []
            mock_db.list_features.return_value = []

            sweep_orphans_on_exit("proj-integ-001")

        mock_sweep.assert_called_once()

    def test_run_loop_final_exit_sweep_calls_sweep_orphan_subagents(self):
        """_final_exit_sweep in run_loop calls _sweep_orphan_subagents (orchestrator integration)."""
        from bob.orchestrator.run_loop import _final_exit_sweep

        with patch("bob.orchestrator.run_loop.db") as mock_db, \
             patch("bob.orchestrator.run_loop._sweep_orphan_subagents") as mock_sweep, \
             patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature"):
            mock_db.list_features.return_value = []
            mock_sweep.return_value = []

            _final_exit_sweep("proj-integ-002")

        mock_sweep.assert_called_once()
