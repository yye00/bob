"""Tests for bob.sub_agent_runs_reaper.reap_zombie_runs.

Acceptance criteria verified:
- File exists: src/bob/sub_agent_runs_reaper.py
- Function defined: bob.sub_agent_runs_reaper.reap_zombie_runs
- behavior: handles empty/zero input without crashing
- behavior: raises ValueError or returns rejection for invalid input
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bob.sub_agent_runs_reaper import reap_zombie_runs


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


def test_reap_zombie_runs_exists_and_callable():
    """The reap_zombie_runs function must be importable and callable."""
    assert callable(reap_zombie_runs)


def test_reap_zombie_runs_empty_project_no_rows():
    """Empty input (no running rows) returns empty list — does not crash."""
    with patch("bob.sub_agent_runs_reaper.db") as mock_db:
        mock_db.query_agent_runs.return_value = []
        mock_db.list_features.return_value = []
        result = reap_zombie_runs("proj-empty-0000-0000-0000-000000000001")
    assert result == []


def test_reap_zombie_runs_returns_list():
    """reap_zombie_runs always returns a list, even with no zombies."""
    with patch("bob.sub_agent_runs_reaper.db") as mock_db:
        mock_db.query_agent_runs.return_value = []
        mock_db.list_features.return_value = []
        result = reap_zombie_runs("proj-list-0000-0000-0000-000000000001")
    assert isinstance(result, list)


def test_reap_zombie_runs_invalid_project_id_raises():
    """Invalid (None or empty) project_id raises ValueError."""
    with pytest.raises((ValueError, TypeError)):
        reap_zombie_runs(None)  # type: ignore[arg-type]

    with pytest.raises((ValueError, TypeError, Exception)):
        reap_zombie_runs("")


def test_reap_zombie_runs_marks_timeout_status():
    """Running row whose target feature is terminal gets status='timeout'."""
    run = _make_run(target_id="feat0001-0000-0000-0000-000000000001")
    feature = _make_feature(
        feature_id="feat0001-0000-0000-0000-000000000001",
        status="completed",
    )
    with patch("bob.sub_agent_runs_reaper.db") as mock_db:
        mock_db.query_agent_runs.return_value = [run]
        mock_db.list_features.side_effect = lambda project_id, status: (
            [feature] if status == "completed" else []
        )
        result = reap_zombie_runs("proj-reap-0000-0000-0000-000000000001")

    assert run.id in result
    mock_db.update_agent_run.assert_called_once()
    call_args = mock_db.update_agent_run.call_args
    assert call_args[0][0] == run.id
    assert call_args[1]["status"] == "timeout"
    assert "completed_at" in call_args[1]


def test_reap_zombie_runs_all_terminal_statuses():
    """Runs targeting features in any terminal state are reaped."""
    for ts in ("completed", "needs_human", "regression", "failed"):
        fid = f"feat-{ts[:4]}-0000-0000-000000000001"
        run = _make_run(run_id=f"run-{ts[:4]}-0000-0000-0000-000000000001", target_id=fid)
        feature = _make_feature(feature_id=fid, status=ts)
        with patch("bob.sub_agent_runs_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run]
            mock_db.list_features.side_effect = lambda project_id, status, _ts=ts: (
                [feature] if status == _ts else []
            )
            result = reap_zombie_runs("proj-ts-000-0000-0000-000000000001")
        assert run.id in result, f"Terminal status {ts!r} should trigger reap"


def test_reap_zombie_runs_non_terminal_target_not_reaped():
    """Running row with non-terminal target feature is not a zombie."""
    run = _make_run(target_id="feat0002-0000-0000-0000-000000000001")
    with patch("bob.sub_agent_runs_reaper.db") as mock_db:
        mock_db.query_agent_runs.return_value = [run]
        mock_db.list_features.return_value = []
        result = reap_zombie_runs("proj-live-0000-0000-0000-000000000001")
    assert result == []
    mock_db.update_agent_run.assert_not_called()


def test_reap_zombie_runs_null_target_id_skipped():
    """Runs with no target_id are not zombies — skip them."""
    run = _make_run(target_id=None)
    with patch("bob.sub_agent_runs_reaper.db") as mock_db:
        mock_db.query_agent_runs.return_value = [run]
        mock_db.list_features.return_value = []
        result = reap_zombie_runs("proj-null-0000-0000-0000-000000000001")
    assert result == []
    mock_db.update_agent_run.assert_not_called()


def test_reap_zombie_runs_multiple_zombies():
    """Multiple zombie runs are all reaped in one call."""
    runs = [
        _make_run(
            run_id=f"run0000{i}-0000-0000-0000-000000000001",
            target_id=f"feat000{i}-0000-0000-0000-000000000001",
        )
        for i in range(3)
    ]
    features = [
        _make_feature(
            feature_id=f"feat000{i}-0000-0000-0000-000000000001",
            status="completed",
        )
        for i in range(3)
    ]
    with patch("bob.sub_agent_runs_reaper.db") as mock_db:
        mock_db.query_agent_runs.return_value = runs
        mock_db.list_features.side_effect = lambda project_id, status: (
            features if status == "completed" else []
        )
        result = reap_zombie_runs("proj-multi-0000-0000-0000-000000000001")
    assert len(result) == 3
    assert set(result) == {r.id for r in runs}
    assert mock_db.update_agent_run.call_count == 3


def test_reap_zombie_runs_db_error_on_one_run_continues():
    """If a single run update fails, the reaper continues with remaining runs."""
    run1 = _make_run(
        run_id="run00001-0000-0000-0000-000000000001",
        target_id="feat0001-0000-0000-0000-000000000001",
    )
    run2 = _make_run(
        run_id="run00002-0000-0000-0000-000000000001",
        target_id="feat0002-0000-0000-0000-000000000001",
    )
    feature1 = _make_feature(
        feature_id="feat0001-0000-0000-0000-000000000001", status="completed"
    )
    feature2 = _make_feature(
        feature_id="feat0002-0000-0000-0000-000000000001", status="failed"
    )
    all_features = [feature1, feature2]

    call_count = [0]

    def update_side_effect(run_id, **kwargs):
        call_count[0] += 1
        if run_id == run1.id:
            raise RuntimeError("DB write error")

    with patch("bob.sub_agent_runs_reaper.db") as mock_db:
        mock_db.query_agent_runs.return_value = [run1, run2]
        mock_db.list_features.side_effect = lambda project_id, status: [
            f for f in all_features if f.status == status
        ]
        mock_db.update_agent_run.side_effect = update_side_effect
        result = reap_zombie_runs("proj-err-00000-0000-0000-000000000001")

    # run2 should still be in the result despite run1 failing
    assert run2.id in result
    assert run1.id not in result
