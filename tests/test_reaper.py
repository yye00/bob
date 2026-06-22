"""Tests for bob3.reaper.reap_zombie_runs (AC: 523e6062)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Import / signature
# ---------------------------------------------------------------------------


class TestReapZombieRunsImport:
    def test_function_is_importable_from_reaper(self):
        from bob3.reaper import reap_zombie_runs  # noqa: F401

        assert callable(reap_zombie_runs)

    def test_accepts_project_id(self):
        from bob3.reaper import reap_zombie_runs

        with patch("bob3.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_runs("proj-1")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Delegation to zombie_run_reaper.scan_and_reap
# ---------------------------------------------------------------------------


class TestReapZombieRunsDelegation:
    def test_delegates_to_scan_and_reap(self):
        from bob3.reaper import reap_zombie_runs

        with patch("bob3.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = ["id-1", "id-2"]
            result = reap_zombie_runs("proj-abc")
        mock_sar.assert_called_once_with("proj-abc")
        assert result == ["id-1", "id-2"]

    def test_returns_empty_list_when_no_zombies(self):
        from bob3.reaper import reap_zombie_runs

        with patch("bob3.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_runs("proj-empty")
        assert result == []

    def test_returns_all_reaped_ids(self):
        from bob3.reaper import reap_zombie_runs

        reaped = ["aaa", "bbb", "ccc"]
        with patch("bob3.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = reaped
            result = reap_zombie_runs("proj-x")
        assert result == reaped

    def test_project_id_passed_through_correctly(self):
        from bob3.reaper import reap_zombie_runs

        with patch("bob3.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            reap_zombie_runs("specific-project-uuid")
        mock_sar.assert_called_once_with("specific-project-uuid")


# ---------------------------------------------------------------------------
# Return type guarantee
# ---------------------------------------------------------------------------


class TestReapZombieRunsReturnType:
    def test_always_returns_list(self):
        from bob3.reaper import reap_zombie_runs

        with patch("bob3.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_runs("proj-q")
        assert isinstance(result, list)

    def test_returns_list_of_strings(self):
        from bob3.reaper import reap_zombie_runs

        with patch("bob3.reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = ["run-id-1", "run-id-2"]
            result = reap_zombie_runs("proj-r")
        assert all(isinstance(r, str) for r in result)


# ---------------------------------------------------------------------------
# Integration: orchestrator integration via run_loop
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    def test_scan_and_reap_wired_in_run_loop(self):
        import importlib

        run_loop = importlib.import_module("bob3.orchestrator.run_loop")
        assert hasattr(run_loop, "_scan_and_reap_zombies"), (
            "run_loop must expose _scan_and_reap_zombies for zombie reaping to be "
            "wired into the orchestrator tick"
        )

    def test_zombie_run_reaper_importable_from_orchestrator(self):
        from bob3.orchestrator import zombie_run_reaper  # noqa: F401

        assert hasattr(zombie_run_reaper, "scan_and_reap")
        assert hasattr(zombie_run_reaper, "find_zombie_runs")
        assert hasattr(zombie_run_reaper, "reap_zombie_run")
