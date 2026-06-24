"""F-R7-478: Per-feature cost ceiling pauses the feature without failing it."""

import asyncio
import tempfile
from pathlib import Path

import pytest
import yaml

from bob3.orchestrator.spawn_retry import spawn_with_retry


def _write_ceiling_config(tmp_path: Path, ceiling_usd: float) -> Path:
    cfg = tmp_path / "spawn_retry.yaml"
    cfg.write_text(
        yaml.dump({
            "TRANSIENT_PATTERNS": ["ECONNRESET"],
            "RETRY_COST_CEILING_USD": ceiling_usd,
            "BACKOFF_BASE_SECONDS": 0.0,
            "BACKOFF_MULTIPLIER": 1.0,
            "BACKOFF_CAP_SECONDS": 0.0,
        }),
        encoding="utf-8",
    )
    return cfg


@pytest.mark.asyncio
async def test_cost_ceiling_returns_pause_not_exception(tmp_path):
    """When the cost ceiling is hit, spawn_with_retry returns result with
    retry_cost_ceiling=True rather than raising an exception."""
    cfg = _write_ceiling_config(tmp_path, 0.05)

    async def no_sleep(s):
        pass

    call_count = 0

    async def spawn_fn():
        nonlocal call_count
        call_count += 1
        return {
            "exit_code": 1,
            "stderr": "ECONNRESET",
            "duration_ms": 0,
            "work_events": 0,
            "cost_usd": 0.02,  # Each retry costs $0.02; ceiling $0.05 → 3 attempts
        }

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="ceiling-test",
        job_name="cost_ceiling",
        config_path=cfg,
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )

    assert result.get("retry_cost_ceiling") is True, (
        "Expected retry_cost_ceiling=True in result when ceiling is hit"
    )
    # Must not raise — the feature is paused, not failed.


@pytest.mark.asyncio
async def test_cost_ceiling_does_not_increment_budget(tmp_path):
    """When the ceiling is hit, on_real_failure is NOT called (not a failure)."""
    cfg = _write_ceiling_config(tmp_path, 0.03)

    real_failure_calls = []
    mid_crash_calls = []

    async def no_sleep(s):
        pass

    async def spawn_fn():
        return {
            "exit_code": 1,
            "stderr": "ECONNRESET",
            "duration_ms": 0,
            "work_events": 0,
            "cost_usd": 0.02,
        }

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="ceiling-budget-test",
        job_name="ceiling_budget",
        config_path=cfg,
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        on_real_failure=lambda r: real_failure_calls.append(r),
        on_mid_work_crash=lambda r: mid_crash_calls.append(r),
    )

    assert result.get("retry_cost_ceiling") is True
    assert len(real_failure_calls) == 0, "on_real_failure should not be called on cost ceiling"
    assert len(mid_crash_calls) == 0, "on_mid_work_crash should not be called on cost ceiling"
