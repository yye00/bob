"""Tests that reap_zombie_run and scan_and_reap mark zombie runs as
status='timeout' with a completed_at timestamp."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

from bob.orchestrator.zombie_run_reaper import reap_zombie_run, scan_and_reap


def _make_run(
    *,
    run_id: str = "run00001-0000-0000-0000-000000000001",
    purpose: str = "feature_research",
    status: str = "running",
    target_id: str = "feat0001-0000-0000-0000-000000000001",
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


class TestReapZombieRunSetsTimeoutStatus:
    def test_reap_calls_update_agent_run_with_timeout_status(self):
        run = _make_run()
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            reap_zombie_run(run)
            mock_db.update_agent_run.assert_called_once()
            call_args = mock_db.update_agent_run.call_args
            assert call_args[0][0] == run.id
            assert call_args[1]["status"] == "timeout"

    def test_reap_sets_completed_at(self):
        run = _make_run()
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            reap_zombie_run(run, now=now)
            call_args = mock_db.update_agent_run.call_args
        assert call_args[1]["completed_at"] == now

    def test_reap_uses_utc_now_when_no_now_provided(self):
        run = _make_run()
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            reap_zombie_run(run)
            call_args = mock_db.update_agent_run.call_args
        completed_at = call_args[1]["completed_at"]
        assert completed_at is not None
        assert completed_at.tzinfo is not None

    def test_reap_passes_run_id_as_first_argument(self):
        run = _make_run(run_id="aabbccdd-0000-0000-0000-000000000001")
        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            reap_zombie_run(run)
            call_args = mock_db.update_agent_run.call_args
        assert call_args[0][0] == "aabbccdd-0000-0000-0000-000000000001"


class TestScanAndReapReturnsReapedIds:
    def test_scan_and_reap_returns_list_of_run_ids(self):
        run = _make_run(run_id="run00001-0000-0000-0000-000000000001")
        feature = _make_feature()

        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == "completed" else []
            )
            result = scan_and_reap("proj-1")

        assert result == ["run00001-0000-0000-0000-000000000001"]

    def test_scan_and_reap_calls_update_for_each_zombie(self):
        run1 = _make_run(
            run_id="run00001-0000-0000-0000-000000000001",
            target_id="feat0001-0000-0000-0000-000000000001",
        )
        run2 = _make_run(
            run_id="run00002-0000-0000-0000-000000000001",
            target_id="feat0001-0000-0000-0000-000000000001",
        )
        feature = _make_feature()

        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run1, run2]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == "completed" else []
            )
            result = scan_and_reap("proj-1")

        assert len(result) == 2
        assert mock_db.update_agent_run.call_count == 2

    def test_scan_and_reap_continues_after_single_failure(self):
        """A single failed reap must not abort the rest of the sweep."""
        run1 = _make_run(
            run_id="run-fail-00000000000000000000001",
            target_id="feat0001-0000-0000-0000-000000000001",
        )
        run2 = _make_run(
            run_id="run-ok-000000000000000000000001",
            target_id="feat0001-0000-0000-0000-000000000001",
        )
        feature = _make_feature()

        call_count = 0

        def _update_side_effect(run_id, **kwargs):
            nonlocal call_count
            call_count += 1
            if run_id == run1.id:
                raise RuntimeError("simulated DB error")

        with patch("bob.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run1, run2]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feature] if status == "completed" else []
            )
            mock_db.update_agent_run.side_effect = _update_side_effect
            result = scan_and_reap("proj-1")

        # Only the successful run should be in the returned list.
        assert result == [run2.id]
        assert call_count == 2  # both were attempted
