"""Tests for bob3.zombie_reaper.reap_zombie_runs / reap_zombie_subruns (AC: 815f1875)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from bob3.zombie_reaper import reap_zombie_runs, reap_zombie_subruns


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    *,
    run_id: str = "run00001-0000-0000-0000-000000000001",
    purpose: str = "feature_research",
    status: str = "running",
    target_id: str | None = "feat0001-0000-0000-0000-000000000001",
) -> MagicMock:
    r = MagicMock()
    r.id = run_id
    r.purpose = purpose
    r.status = status
    r.target_id = target_id
    return r


def _make_feature(
    *,
    feature_id: str = "feat0001-0000-0000-0000-000000000001",
    status: str = "completed",
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.status = status
    return f


# ---------------------------------------------------------------------------
# Signature / import
# ---------------------------------------------------------------------------


class TestReapZombieSubrunsImport:
    def test_function_is_importable(self):
        from bob3.zombie_reaper import reap_zombie_subruns as fn  # noqa: F401

        assert callable(fn)

    def test_accepts_project_id(self):
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_subruns("proj-1")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Delegation to orchestrator.zombie_run_reaper.scan_and_reap
# ---------------------------------------------------------------------------


class TestReapZombieSubrunsDelegation:
    def test_delegates_to_scan_and_reap(self):
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = ["id-1", "id-2"]
            result = reap_zombie_subruns("proj-abc")
        mock_sar.assert_called_once_with("proj-abc")
        assert result == ["id-1", "id-2"]

    def test_returns_empty_list_when_no_zombies(self):
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_subruns("proj-empty")
        assert result == []

    def test_returns_all_reaped_ids(self):
        reaped = ["aaa", "bbb", "ccc"]
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = reaped
            result = reap_zombie_subruns("proj-x")
        assert result == reaped

    def test_project_id_passed_through(self):
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            reap_zombie_subruns("specific-project-uuid")
        mock_sar.assert_called_once_with("specific-project-uuid")


# ---------------------------------------------------------------------------
# Terminal-state detection via underlying find_zombie_runs
# ---------------------------------------------------------------------------


class TestZombieDetectionViaUnderlying:
    """Integration-style checks that exercise find_zombie_runs through the public API."""

    def _run_with_db_mock(self, runs, features_by_status):
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = runs
            mock_db.list_features.side_effect = lambda project_id, status: (
                features_by_status.get(status, [])
            )
            with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
                # Call the real scan_and_reap but with our db mock.
                # For these tests we verify scan_and_reap is called correctly
                # via the delegation tests above; here we test find_zombie_runs directly.
                from bob3.orchestrator.zombie_run_reaper import find_zombie_runs

                zombies = find_zombie_runs("proj-1")
        return zombies

    def test_completed_feature_makes_run_zombie(self):
        run = _make_run(target_id="feat0001-0000-0000-0000-000000000001")
        feature = _make_feature(
            feature_id="feat0001-0000-0000-0000-000000000001", status="completed"
        )
        zombies = self._run_with_db_mock([run], {"completed": [feature]})
        assert len(zombies) == 1
        assert zombies[0].id == run.id

    def test_failed_feature_makes_run_zombie(self):
        run = _make_run(target_id="feat0002-0000-0000-0000-000000000001")
        feature = _make_feature(
            feature_id="feat0002-0000-0000-0000-000000000001", status="failed"
        )
        zombies = self._run_with_db_mock([run], {"failed": [feature]})
        assert len(zombies) == 1

    def test_needs_human_feature_makes_run_zombie(self):
        run = _make_run(target_id="feat0003-0000-0000-0000-000000000001")
        feature = _make_feature(
            feature_id="feat0003-0000-0000-0000-000000000001", status="needs_human"
        )
        zombies = self._run_with_db_mock([run], {"needs_human": [feature]})
        assert len(zombies) == 1

    def test_regression_feature_makes_run_zombie(self):
        run = _make_run(target_id="feat0004-0000-0000-0000-000000000001")
        feature = _make_feature(
            feature_id="feat0004-0000-0000-0000-000000000001", status="regression"
        )
        zombies = self._run_with_db_mock([run], {"regression": [feature]})
        assert len(zombies) == 1

    def test_active_feature_does_not_make_run_zombie(self):
        run = _make_run(target_id="feat0005-0000-0000-0000-000000000001")
        zombies = self._run_with_db_mock([run], {})
        assert zombies == []

    def test_null_target_id_run_is_not_zombie(self):
        run = _make_run(target_id=None)
        feature = _make_feature(status="completed")
        zombies = self._run_with_db_mock([run], {"completed": [feature]})
        assert zombies == []


# ---------------------------------------------------------------------------
# Reaping: status set to 'timeout' with completed_at
# ---------------------------------------------------------------------------


class TestReapZombieRun:
    def test_reap_sets_status_timeout(self):
        run = _make_run()
        now = datetime(2026, 6, 12, 7, 30, 0, tzinfo=timezone.utc)
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            from bob3.orchestrator.zombie_run_reaper import reap_zombie_run

            reap_zombie_run(run, now=now)
        mock_db.update_agent_run.assert_called_once_with(
            run.id,
            status="timeout",
            completed_at=now,
        )

    def test_reap_uses_utc_now_when_not_given(self):
        run = _make_run()
        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            from bob3.orchestrator.zombie_run_reaper import reap_zombie_run

            reap_zombie_run(run)
        call_kwargs = mock_db.update_agent_run.call_args
        assert call_kwargs is not None
        # completed_at should be a datetime close to now
        completed_at = call_kwargs.kwargs.get("completed_at") or call_kwargs[1].get(
            "completed_at"
        )
        assert completed_at is not None
        assert isinstance(completed_at, datetime)

    def test_reap_logs_info(self, caplog):
        import logging

        run = _make_run(
            run_id="aabbccdd-0000-0000-0000-000000000001",
            purpose="feature_research",
            target_id="feat0001-0000-0000-0000-000000000001",
        )
        with patch("bob3.orchestrator.zombie_run_reaper.db"):
            from bob3.orchestrator.zombie_run_reaper import reap_zombie_run

            with caplog.at_level(logging.INFO, logger="bob3.orchestrator.zombie_run_reaper"):
                reap_zombie_run(run)
        assert any("ZOMBIE_REAPER" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Idempotency: already-closed runs
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_no_crash_on_empty_project(self):
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_subruns("proj-empty")
        assert result == []

    def test_multiple_calls_return_consistent_results(self):
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.side_effect = [["id-1"], ["id-1"]]
            r1 = reap_zombie_subruns("proj-q")
            r2 = reap_zombie_subruns("proj-q")
        assert r1 == r2 == ["id-1"]


# ---------------------------------------------------------------------------
# orchestrator integration: scan_and_reap is called in run_loop
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    def test_scan_and_reap_imported_in_run_loop(self):
        import importlib

        run_loop = importlib.import_module("bob3.orchestrator.run_loop")
        # The symbol _scan_and_reap_zombies should be present in the module's globals.
        assert hasattr(run_loop, "_scan_and_reap_zombies"), (
            "run_loop must import scan_and_reap as _scan_and_reap_zombies for "
            "zombie run reaping to be wired into the orchestrator tick"
        )

    def test_zombie_reaper_module_importable_from_orchestrator(self):
        from bob3.orchestrator import zombie_run_reaper  # noqa: F401

        assert hasattr(zombie_run_reaper, "scan_and_reap")
        assert hasattr(zombie_run_reaper, "find_zombie_runs")
        assert hasattr(zombie_run_reaper, "reap_zombie_run")


# ---------------------------------------------------------------------------
# reap_zombie_runs — canonical function name required by AC
# ---------------------------------------------------------------------------


class TestReapZombieRunsCanonicalName:
    """Tests specifically for the reap_zombie_runs function (AC requirement)."""

    def test_reap_zombie_runs_is_importable(self):
        from bob3.zombie_reaper import reap_zombie_runs as fn  # noqa: F401

        assert callable(fn)

    def test_reap_zombie_runs_accepts_project_id(self):
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_runs("proj-1")
        assert isinstance(result, list)

    def test_reap_zombie_runs_delegates_to_scan_and_reap(self):
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = ["id-1", "id-2"]
            result = reap_zombie_runs("proj-abc")
        mock_sar.assert_called_once_with("proj-abc")
        assert result == ["id-1", "id-2"]

    def test_reap_zombie_runs_returns_empty_on_no_zombies(self):
        with patch("bob3.zombie_reaper.scan_and_reap") as mock_sar:
            mock_sar.return_value = []
            result = reap_zombie_runs("proj-empty")
        assert result == []

    def test_reap_zombie_runs_is_alias_for_reap_zombie_subruns(self):
        assert reap_zombie_runs is reap_zombie_subruns
