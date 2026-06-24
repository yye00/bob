"""F-R7-478: End-to-end integration test — fake-flaky-spawner recovers from all
transient signatures without consuming any refinement budget.

Each scenario fails the first 10 spawn attempts with a specific transient
error signature, then succeeds on the 11th.  Asserts:
- exit_code == 0 on final result
- total call count == 11
- refinement_attempts == 0 (on_real_failure / on_mid_work_crash never called)
- workspace cleanup path exercised (temp dir with a .git/ sub-directory)
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from bob.orchestrator.spawn_retry import spawn_with_retry

_TRANSIENT_STDERRS = [
    "HTTP 429 Too Many Requests",
    "ECONNRESET: socket hang up",
    "ETIMEDOUT: connection timed out",
    "spawn ENOENT: No such file or directory, spawn 'claude'",
    "self signed certificate in certificate chain",
    "Application 'Claude Code' is a shared API key and is being deprecated",
]


def _make_flaky_spawn_fn(transient_stderr: str, succeed_on: int = 11):
    """Return an async spawn callable that fails the first (succeed_on - 1) calls
    with a transient error, then succeeds."""
    call_count = 0

    async def spawn_fn() -> dict:
        nonlocal call_count
        call_count += 1
        if call_count < succeed_on:
            return {
                "exit_code": 1,
                "stderr": transient_stderr,
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {
            "exit_code": 0,
            "stderr": "",
            "duration_ms": 500,
            "work_events": 1,
            "cost_usd": 0.01,
        }

    def get_count() -> int:
        return call_count

    return spawn_fn, get_count


def _init_git_worktree(path: Path) -> None:
    """Create a minimal .git directory to simulate a git worktree."""
    git_dir = path / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize("transient_stderr", _TRANSIENT_STDERRS)
async def test_flaky_spawner_recovers_without_budget_impact(transient_stderr, tmp_path):
    """Each transient signature: 10 failures then success on 11th, no budget charge."""
    _init_git_worktree(tmp_path)

    spawn_fn, get_count = _make_flaky_spawn_fn(transient_stderr, succeed_on=11)

    real_failure_calls: list = []
    mid_crash_calls: list = []

    async def no_sleep(s: float) -> None:
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="e2e-flaky-test",
        job_name=f"flaky_{id(transient_stderr)}",
        workspace=str(tmp_path),
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        on_real_failure=lambda r: real_failure_calls.append(r),
        on_mid_work_crash=lambda r: mid_crash_calls.append(r),
    )

    assert result["exit_code"] == 0, f"Expected success, got {result}"
    assert get_count() == 11, f"Expected 11 total calls, got {get_count()}"
    assert len(real_failure_calls) == 0, (
        f"refinement_attempts must be 0: on_real_failure called {len(real_failure_calls)} time(s)"
    )
    assert len(mid_crash_calls) == 0, (
        f"on_mid_work_crash called {len(mid_crash_calls)} time(s); should be 0 for transient errors"
    )


@pytest.mark.asyncio
async def test_flaky_spawner_workspace_cleanup_exercised(tmp_path):
    """Lock file present before retry is removed by spawn_with_retry cleanup."""
    feature_id = "e2e-lock-cleanup"
    _init_git_worktree(tmp_path)

    lock_file = tmp_path / ".bob" / "locks" / feature_id
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text("locked", encoding="utf-8")

    spawn_fn, get_count = _make_flaky_spawn_fn("ECONNRESET: socket hang up", succeed_on=2)

    async def no_sleep(s: float) -> None:
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id=feature_id,
        job_name="e2e_lock_cleanup",
        workspace=str(tmp_path),
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )

    assert result["exit_code"] == 0
    assert not lock_file.exists(), "Lock file should have been removed during retry cleanup"
