"""F-R7-478: spawn_with_retry cleans up partial workspace state between retries."""

import asyncio
import tempfile
from pathlib import Path

import pytest
from bob3.orchestrator.spawn_retry import spawn_with_retry


@pytest.mark.asyncio
async def test_orphan_lock_removed_before_retry(tmp_path):
    """Orphan .bob3/locks/<feature_id> is removed before each retry attempt."""
    feature_id = "test-feat-lock"
    lock_file = tmp_path / ".bob3" / "locks" / feature_id
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text("locked", encoding="utf-8")

    assert lock_file.exists(), "Lock file must exist before test"

    async def no_sleep(s):
        pass

    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "exit_code": 1,
                "stderr": "ECONNRESET",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.0}

    await spawn_with_retry(
        spawn_fn,
        feature_id=feature_id,
        job_name="lock_cleanup",
        workspace=str(tmp_path),
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )

    assert not lock_file.exists(), "Lock file should have been removed before retry"
    assert call_count == 2


@pytest.mark.asyncio
async def test_no_crash_when_workspace_is_none():
    """spawn_with_retry must not crash when workspace=None (cleanup is skipped)."""
    async def no_sleep(s):
        pass

    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "exit_code": 1,
                "stderr": "ECONNRESET",
                "duration_ms": 0,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 0, "cost_usd": 0.0}

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="no-workspace-test",
        job_name="no_ws",
        workspace=None,
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0
