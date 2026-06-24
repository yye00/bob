"""Tests for zombie_sub_agent_runs_reaper_close_running_rows_whose_target."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from bob.zombie_sub_agent_runs_reaper_close_running_rows_whose_target import (
    zombie_sub_agent_runs_reaper_close_running_rows_whose_target,
)


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


def test_zombie_sub_agent_runs_reaper_close_running_rows_whose_target():
    """Main AC test: running rows whose target feature is terminal are reaped."""
    run = _make_run(target_id="feat0001-0000-0000-0000-000000000001")
    feature = _make_feature(
        feature_id="feat0001-0000-0000-0000-000000000001",
        status="completed",
    )

    with patch(
        "bob.zombie_sub_agent_runs_reaper_close_running_rows_whose_target.db"
    ) as mock_db:
        mock_db.query_agent_runs.return_value = [run]
        mock_db.list_features.side_effect = lambda project_id, status: (
            [feature] if status == "completed" else []
        )
        reaped = zombie_sub_agent_runs_reaper_close_running_rows_whose_target("proj-1")

    assert isinstance(reaped, list)
    assert run.id in reaped
    mock_db.update_agent_run.assert_called_once()
    call_kwargs = mock_db.update_agent_run.call_args
    assert call_kwargs[0][0] == run.id
    assert call_kwargs[1]["status"] == "timeout"
    assert "completed_at" in call_kwargs[1]


def test_no_running_rows_returns_empty():
    """No running rows → empty result, no updates."""
    with patch(
        "bob.zombie_sub_agent_runs_reaper_close_running_rows_whose_target.db"
    ) as mock_db:
        mock_db.query_agent_runs.return_value = []
        reaped = zombie_sub_agent_runs_reaper_close_running_rows_whose_target("proj-2")

    assert reaped == []
    mock_db.update_agent_run.assert_not_called()


def test_running_row_with_non_terminal_target_not_reaped():
    """Running row whose target feature is still 'executing' → not a zombie."""
    run = _make_run(target_id="feat0002-0000-0000-0000-000000000001")

    with patch(
        "bob.zombie_sub_agent_runs_reaper_close_running_rows_whose_target.db"
    ) as mock_db:
        mock_db.query_agent_runs.return_value = [run]
        mock_db.list_features.return_value = []  # no terminal features
        reaped = zombie_sub_agent_runs_reaper_close_running_rows_whose_target("proj-3")

    assert reaped == []
    mock_db.update_agent_run.assert_not_called()


def test_all_terminal_statuses_trigger_reap():
    """Runs targeting features in any terminal state are reaped."""
    terminal_statuses = ("completed", "needs_human", "regression", "failed")
    for ts in terminal_statuses:
        fid = f"feat-{ts}-0000-0000-000000000001"
        run = _make_run(
            run_id=f"run-{ts[:4]}-0000-0000-0000-000000000001",
            target_id=fid,
        )
        feature = _make_feature(feature_id=fid, status=ts)

        with patch(
            "bob.zombie_sub_agent_runs_reaper_close_running_rows_whose_target.db"
        ) as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status, _ts=ts: (
                [feature] if status == _ts else []
            )
            reaped = zombie_sub_agent_runs_reaper_close_running_rows_whose_target(
                "proj-4"
            )

        assert run.id in reaped, f"Expected {ts!r} feature to trigger reap"


def test_run_with_null_target_id_skipped():
    """Runs with no target_id cannot be joined to a feature — skip them."""
    run = _make_run(target_id=None)

    with patch(
        "bob.zombie_sub_agent_runs_reaper_close_running_rows_whose_target.db"
    ) as mock_db:
        mock_db.query_agent_runs.return_value = [run]
        mock_db.list_features.return_value = []
        reaped = zombie_sub_agent_runs_reaper_close_running_rows_whose_target("proj-5")

    assert reaped == []
    mock_db.update_agent_run.assert_not_called()


def test_multiple_zombies_all_reaped():
    """Multiple zombie runs in one project — all get reaped."""
    runs = [
        _make_run(run_id=f"run0000{i}-0000-0000-0000-000000000001", target_id=f"feat000{i}-0000-0000-0000-000000000001")
        for i in range(3)
    ]
    features = [
        _make_feature(feature_id=f"feat000{i}-0000-0000-0000-000000000001", status="completed")
        for i in range(3)
    ]
    terminal_ids = {f.id for f in features}

    with patch(
        "bob.zombie_sub_agent_runs_reaper_close_running_rows_whose_target.db"
    ) as mock_db:
        mock_db.query_agent_runs.return_value = runs
        mock_db.list_features.side_effect = lambda project_id, status: (
            features if status == "completed" else []
        )
        reaped = zombie_sub_agent_runs_reaper_close_running_rows_whose_target("proj-6")

    assert len(reaped) == 3
    assert set(reaped) == {r.id for r in runs}
    assert mock_db.update_agent_run.call_count == 3
