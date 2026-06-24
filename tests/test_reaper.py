"""Tests for bob.reaper.reap_zombie_runs (AC: 523e6062)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Import / signature
# ---------------------------------------------------------------------------


class TestReapZombieRunsImport:
    def test_function_is_importable_from_reaper(self):
        from bob.reaper import reap_zombie_runs  # noqa: F401

        assert callable(reap_zombie_runs)

    def test_accepts_project_id(self):
        from bob.reaper import reap_zombie_runs

        with patch("bob.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_runs("proj-1")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Delegation to zombie_run_reaper.scan_and_reap
# ---------------------------------------------------------------------------


class TestReapZombieRunsDelegation:
    def test_delegates_to_scan_and_reap(self):
        from bob.reaper import reap_zombie_runs

        with patch("bob.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = ["id-1", "id-2"]
            result = reap_zombie_runs("proj-abc")
        mock_sar.assert_called_once_with("proj-abc")
        assert result == ["id-1", "id-2"]

    def test_returns_empty_list_when_no_zombies(self):
        from bob.reaper import reap_zombie_runs

        with patch("bob.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_runs("proj-empty")
        assert result == []

    def test_returns_all_reaped_ids(self):
        from bob.reaper import reap_zombie_runs

        reaped = ["aaa", "bbb", "ccc"]
        with patch("bob.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = reaped
            result = reap_zombie_runs("proj-x")
        assert result == reaped

    def test_project_id_passed_through_correctly(self):
        from bob.reaper import reap_zombie_runs

        with patch("bob.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            reap_zombie_runs("specific-project-uuid")
        mock_sar.assert_called_once_with("specific-project-uuid")


# ---------------------------------------------------------------------------
# Return type guarantee
# ---------------------------------------------------------------------------


class TestReapZombieRunsReturnType:
    def test_always_returns_list(self):
        from bob.reaper import reap_zombie_runs

        with patch("bob.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_runs("proj-q")
        assert isinstance(result, list)

    def test_returns_list_of_strings(self):
        from bob.reaper import reap_zombie_runs

        with patch("bob.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = ["run-id-1", "run-id-2"]
            result = reap_zombie_runs("proj-r")
        assert all(isinstance(r, str) for r in result)


# ---------------------------------------------------------------------------
# Integration: orchestrator integration via run_loop
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    def test_scan_and_reap_wired_in_run_loop(self):
        import importlib

        run_loop = importlib.import_module("bob.orchestrator.run_loop")
        assert hasattr(run_loop, "_scan_and_reap_zombies"), (
            "run_loop must expose _scan_and_reap_zombies for zombie reaping to be "
            "wired into the orchestrator tick"
        )

    def test_zombie_run_reaper_importable_from_orchestrator(self):
        from bob.orchestrator import zombie_run_reaper  # noqa: F401

        assert hasattr(zombie_run_reaper, "scan_and_reap")
        assert hasattr(zombie_run_reaper, "find_zombie_runs")
        assert hasattr(zombie_run_reaper, "reap_zombie_run")


# ---------------------------------------------------------------------------
# sweep_orphans_on_exit — final reaper sweep on orchestrator exit (0e103f96)
# ---------------------------------------------------------------------------


class TestSweepOrphansOnExit:
    def test_sweep_orphans_on_orchestrator_exit(self):
        """sweep_orphans_on_exit flips orphan executing rows to failed on orchestrator exit."""
        from bob.reaper import sweep_orphans_on_exit
        from unittest.mock import patch

        feature_id = "feat-orphan-0001-0000-0000-000000000001"

        with patch("bob.final_reaper.sweep_orphans_on_exit") as mock_impl:
            mock_impl.return_value = [feature_id]
            result = sweep_orphans_on_exit("proj-test-exit")

        assert isinstance(result, list)
        assert result == [feature_id]
        mock_impl.assert_called_once_with("proj-test-exit")

    def test_sweep_orphans_on_exit_is_callable(self):
        from bob.reaper import sweep_orphans_on_exit

        assert callable(sweep_orphans_on_exit)

    def test_sweep_orphans_on_exit_invalid_project_id_raises(self):
        from bob.reaper import sweep_orphans_on_exit
        from unittest.mock import patch

        # When project_id is None, final_reaper.sweep_orphans_on_exit raises ValueError
        with pytest.raises((ValueError, TypeError)):
            with patch("bob.final_reaper.sweep_orphans_on_exit") as mock_impl:
                mock_impl.side_effect = ValueError("project_id must be str")
                sweep_orphans_on_exit(None)  # type: ignore[arg-type]

    def test_sweep_orphans_on_exit_returns_list(self):
        from bob.reaper import sweep_orphans_on_exit
        from unittest.mock import patch

        with patch("bob.reaper.sweep_orphans_on_exit") as mock_fn:
            mock_fn.return_value = []
            result = sweep_orphans_on_exit("proj-empty-exit")

        assert isinstance(result, list)

    def test_sweep_orphans_delegates_to_final_reaper(self):
        """sweep_orphans_on_exit in reaper delegates to bob.final_reaper."""
        from bob import reaper
        from unittest.mock import patch

        with patch("bob.final_reaper.sweep_orphans_on_exit") as mock_final:
            mock_final.return_value = ["feat-abc"]
            result = reaper.sweep_orphans_on_exit("proj-delegated")

        mock_final.assert_called_once_with("proj-delegated")
        assert result == ["feat-abc"]
