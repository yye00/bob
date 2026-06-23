"""Tests for ``bob3.disk_quota`` (F-R6-303).

The tests use real filesystem ops on ``tmp_path`` to exercise the same
``Path.rglob`` / ``Path.stat`` / ``Path.unlink`` code paths the
production callers hit. Only ``shutil.disk_usage`` is mocked, because we
cannot deterministically force the host filesystem under or over a
threshold.
"""
from __future__ import annotations

import os
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.disk_quota import (
    DEFAULT_QUOTA_BYTES,
    check_pre_spawn,
    disk_pressure_warning,
    enforce_session_quota,
    reserve_session_disk,
)


_FakeUsage = namedtuple("_FakeUsage", "total used free")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file(path: Path, *, size: int, mtime: float) -> Path:
    """Create a regular file of ``size`` bytes with the given mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(b"x" * size)
    os.utime(path, (mtime, mtime))
    return path


# ---------------------------------------------------------------------------
# enforce_session_quota
# ---------------------------------------------------------------------------


def test_enforce_quota_empty_session_dir(tmp_path: Path) -> None:
    """An empty directory triggers no pruning and reports zero bytes."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    result = enforce_session_quota(session_dir, quota_bytes=1024)

    assert result == {"before": 0, "after": 0, "pruned": 0, "quota": 1024}
    # Directory must still exist after the call.
    assert session_dir.exists()


def test_enforce_quota_under_quota_no_pruning(tmp_path: Path) -> None:
    """When total < quota, nothing is pruned and totals match."""
    session_dir = tmp_path / "session"
    a = _make_file(session_dir / "a.log", size=100, mtime=1000.0)
    b = _make_file(session_dir / "b.log", size=200, mtime=2000.0)

    result = enforce_session_quota(session_dir, quota_bytes=10_000)

    assert result["pruned"] == 0
    assert result["before"] == 300
    assert result["after"] == 300
    assert a.exists() and b.exists()


def test_enforce_quota_prunes_oldest_first(tmp_path: Path) -> None:
    """Over-quota dirs prune oldest mtime first until under quota."""
    session_dir = tmp_path / "session"
    oldest = _make_file(session_dir / "old.log", size=500, mtime=1_000.0)
    middle = _make_file(session_dir / "mid.log", size=500, mtime=2_000.0)
    newest = _make_file(session_dir / "new.log", size=500, mtime=3_000.0)

    # Total = 1500 bytes; quota 600 forces at least 2 files to go.
    result = enforce_session_quota(session_dir, quota_bytes=600)

    assert result["before"] == 1500
    assert result["after"] <= 600
    assert result["pruned"] == 2
    # Oldest two must be gone; newest must survive.
    assert not oldest.exists()
    assert not middle.exists()
    assert newest.exists()


def test_enforce_quota_recurses_into_subdirs(tmp_path: Path) -> None:
    """rglob covers nested files; quota enforcement spans subdirs."""
    session_dir = tmp_path / "session"
    nested_old = _make_file(
        session_dir / "sub" / "old.bin", size=400, mtime=500.0
    )
    top_new = _make_file(session_dir / "new.bin", size=400, mtime=9_000.0)

    result = enforce_session_quota(session_dir, quota_bytes=500)

    assert result["before"] == 800
    assert result["pruned"] == 1
    assert not nested_old.exists()
    assert top_new.exists()


def test_enforce_quota_missing_session_dir(tmp_path: Path) -> None:
    """A non-existent directory is treated as empty, not an error."""
    missing = tmp_path / "does-not-exist"

    result = enforce_session_quota(missing, quota_bytes=1024)

    assert result == {"before": 0, "after": 0, "pruned": 0, "quota": 1024}


def test_enforce_quota_exactly_at_quota_no_pruning(tmp_path: Path) -> None:
    """When the directory is exactly at quota, nothing is pruned."""
    session_dir = tmp_path / "session"
    f = _make_file(session_dir / "x.log", size=1024, mtime=1_000.0)

    result = enforce_session_quota(session_dir, quota_bytes=1024)

    assert result["pruned"] == 0
    assert f.exists()


# ---------------------------------------------------------------------------
# check_pre_spawn
# ---------------------------------------------------------------------------


def test_check_pre_spawn_allows_when_disk_ample(tmp_path: Path) -> None:
    """Plenty of free disk -> spawn allowed."""
    fake = _FakeUsage(total=100 * 1024**3, used=10 * 1024**3, free=90 * 1024**3)
    with patch("bob3.disk_quota.shutil.disk_usage", return_value=fake):
        ok, reason = check_pre_spawn(tmp_path, quota_bytes=1024)

    assert ok is True
    assert reason == "ok"


def test_check_pre_spawn_blocks_when_disk_low(tmp_path: Path) -> None:
    """Free disk below 2x quota -> spawn blocked, reason explains why."""
    # quota=1 MiB -> min free = 2 MiB. Report only 1 MiB free.
    quota = 1 * 1024**2
    fake = _FakeUsage(total=10 * 1024**2, used=9 * 1024**2, free=1 * 1024**2)
    with patch("bob3.disk_quota.shutil.disk_usage", return_value=fake):
        ok, reason = check_pre_spawn(tmp_path, quota_bytes=quota)

    assert ok is False
    assert "free disk" in reason
    assert str(quota) in reason


def test_check_pre_spawn_respects_explicit_min_free(tmp_path: Path) -> None:
    """Explicit min_free_disk_bytes overrides the 2x-quota default."""
    fake = _FakeUsage(total=10 * 1024**2, used=9 * 1024**2, free=1 * 1024**2)
    with patch("bob3.disk_quota.shutil.disk_usage", return_value=fake):
        # Set a very low minimum -> allowed even though disk is "low".
        ok, _ = check_pre_spawn(
            tmp_path, quota_bytes=1024**3, min_free_disk_bytes=512,
        )
    assert ok is True


def test_check_pre_spawn_walks_to_existing_ancestor(tmp_path: Path) -> None:
    """A not-yet-created sessions_root falls back to the nearest ancestor."""
    target = tmp_path / "does" / "not" / "exist" / "yet"
    fake = _FakeUsage(total=10 * 1024**3, used=1 * 1024**3, free=9 * 1024**3)
    with patch(
        "bob3.disk_quota.shutil.disk_usage", return_value=fake,
    ) as du:
        ok, reason = check_pre_spawn(target, quota_bytes=1024)
    assert ok is True
    # disk_usage was called against an actually-existing path.
    called_with = Path(du.call_args.args[0])
    assert called_with.exists()


# ---------------------------------------------------------------------------
# disk_pressure_warning
# ---------------------------------------------------------------------------


def test_disk_pressure_warning_quiet_above_threshold() -> None:
    """>=20% free returns None."""
    fake = _FakeUsage(total=100, used=70, free=30)  # 30% free
    with patch("bob3.disk_quota.shutil.disk_usage", return_value=fake):
        assert disk_pressure_warning(Path("/")) is None


def test_disk_pressure_warning_fires_below_threshold() -> None:
    """<20% free returns a warning string."""
    fake = _FakeUsage(total=100, used=90, free=10)  # 10% free
    with patch("bob3.disk_quota.shutil.disk_usage", return_value=fake):
        msg = disk_pressure_warning(Path("/"))
    assert msg is not None
    assert "DISK PRESSURE" in msg
    assert "10" in msg


def test_disk_pressure_warning_at_exact_threshold_quiet() -> None:
    """Exactly 20% free is the boundary; treat as quiet."""
    fake = _FakeUsage(total=100, used=80, free=20)  # exactly 20%
    with patch("bob3.disk_quota.shutil.disk_usage", return_value=fake):
        assert disk_pressure_warning(Path("/")) is None


def test_disk_pressure_warning_handles_zero_total() -> None:
    """Pathological 0-byte filesystem must not divide by zero."""
    fake = _FakeUsage(total=0, used=0, free=0)
    with patch("bob3.disk_quota.shutil.disk_usage", return_value=fake):
        assert disk_pressure_warning(Path("/")) is None


# ---------------------------------------------------------------------------
# reserve_session_disk
# ---------------------------------------------------------------------------


def test_reserve_session_disk_allows_when_ample(tmp_path: Path) -> None:
    """Plenty of free disk -> reservation allowed."""
    # 100 GiB total, 90 GiB free. Reserving 2 GiB leaves 88 GiB > 5 GiB threshold.
    fake = _FakeUsage(total=100 * 1024**3, used=10 * 1024**3, free=90 * 1024**3)
    with patch("bob3.disk_quota.shutil.disk_usage", return_value=fake):
        ok, reason = reserve_session_disk(tmp_path, estimated_bytes=2 * 1024**3)

    assert ok is True
    assert reason == "ok"


def test_reserve_session_disk_blocks_when_below_halt_threshold(tmp_path: Path) -> None:
    """Reservation blocked when free - estimated < halt_threshold."""
    # 10 GiB free, estimated 6 GiB, halt threshold 5 GiB.
    # free_after = 4 GiB < 5 GiB -> blocked.
    fake = _FakeUsage(
        total=20 * 1024**3, used=10 * 1024**3, free=10 * 1024**3
    )
    with patch("bob3.disk_quota.shutil.disk_usage", return_value=fake):
        ok, reason = reserve_session_disk(
            tmp_path,
            estimated_bytes=6 * 1024**3,
            halt_threshold_bytes=5 * 1024**3,
        )

    assert ok is False
    assert "halt threshold" in reason
    assert "reserving" in reason


def test_reserve_session_disk_respects_custom_halt_threshold(tmp_path: Path) -> None:
    """Custom halt_threshold_bytes is honoured."""
    # 1 MiB free, estimated 512 KiB, halt threshold 256 KiB.
    # free_after = 512 KiB > 256 KiB -> allowed.
    fake = _FakeUsage(
        total=10 * 1024**2, used=9 * 1024**2, free=1 * 1024**2
    )
    with patch("bob3.disk_quota.shutil.disk_usage", return_value=fake):
        ok, _ = reserve_session_disk(
            tmp_path,
            estimated_bytes=512 * 1024,
            halt_threshold_bytes=256 * 1024,
        )

    assert ok is True


def test_reserve_session_disk_walks_to_existing_ancestor(tmp_path: Path) -> None:
    """Not-yet-created sessions_root falls back to nearest existing ancestor."""
    target = tmp_path / "does" / "not" / "exist" / "yet"
    fake = _FakeUsage(total=100 * 1024**3, used=1 * 1024**3, free=99 * 1024**3)
    with patch(
        "bob3.disk_quota.shutil.disk_usage", return_value=fake,
    ) as du:
        ok, _ = reserve_session_disk(target, estimated_bytes=1024)
    assert ok is True
    called_with = Path(du.call_args.args[0])
    assert called_with.exists()


# ---------------------------------------------------------------------------
# Default quota sanity
# ---------------------------------------------------------------------------


def test_default_quota_is_two_gib() -> None:
    assert DEFAULT_QUOTA_BYTES == 2 * 1024**3


# ---------------------------------------------------------------------------
# Integration: spawn_sub_agent honours the pre-spawn disk gate (F-R6-303)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _isolated_db(tmp_path, monkeypatch):
    """Provide an isolated bob3 DB so the regression test does not
    pollute the developer's main database."""
    from bob3 import db

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.mark.asyncio
async def test_spawn_sub_agent_aborts_when_disk_low(
    tmp_path, monkeypatch, _isolated_db,
):
    """When ``check_pre_spawn`` reports the disk is too low, the
    sub-agent must NOT actually invoke claude_code_sdk; the call returns
    an error result so the caller can mark the feature needs_human.
    """
    from bob3 import db
    from bob3.orchestrator.claude_executor import spawn_sub_agent

    # Point the sessions root at tmp_path so disk_usage is called on a
    # known directory (its parent is always present).
    sessions_root = tmp_path / "sessions"
    monkeypatch.setenv("BOB3_SESSIONS_ROOT", str(sessions_root))

    project = db.create_project(
        name="quota-regression",
        workspace_path=str(tmp_path / "workspace"),
    )

    # Force disk_usage to report essentially no free disk. The pre-spawn
    # gate requires >= 2x quota (=4 GiB by default); 1 MiB free is well
    # below that.
    fake = _FakeUsage(total=10 * 1024**2, used=9 * 1024**2, free=1 * 1024**2)

    spawn_calls: list = []

    async def _should_not_run(*args, **kwargs):  # pragma: no cover - asserted not called
        spawn_calls.append((args, kwargs))
        yield None

    with patch("bob3.disk_quota.shutil.disk_usage", return_value=fake), \
         patch(
            "bob3.orchestrator.claude_executor.stream_query",
            _should_not_run,
        ):
        result = await spawn_sub_agent(
            project_id=project.id,
            purpose="implement_feature",
            prompt="should be aborted",
        )

    # The SDK must not have been invoked.
    assert spawn_calls == []
    # The result must signal an error to the caller.
    assert result.execution_result.is_error is True
    assert "disk-quota gate" in (result.execution_result.error_message or "")
    # The audit row must exist and be marked failed.
    if result.agent_run is not None:
        assert result.agent_run.status == "failed"
