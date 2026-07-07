"""Core tests for the infra-error transient classifier + unlimited spawn-layer recovery.

Covers the central contract of ``bob.orchestrator.spawn_retry``:

* ``classify_exit`` correctly buckets transient infra errors, mid-work crashes,
  and real failures.
* ``spawn_with_retry`` retries transient errors *unlimited* times with backoff.
* Transient retries NEVER consume budget (no on_real_failure / on_mid_work_crash).
* mid_work_crash and real_failure are charged exactly once and end the loop.
"""

from __future__ import annotations

import pytest

from bob.orchestrator.spawn_retry import (
    classify_exit,
    load_patterns,
    spawn_with_retry,
)


# ---------------------------------------------------------------------------
# classify_exit — transient signatures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stderr",
    [
        "HTTP 429 Too Many Requests",
        "Error: rate limit exceeded",
        "read ECONNRESET",
        "connect ETIMEDOUT 1.2.3.4:443",
        "spawn claude ENOENT",
        "No such file or directory: claude",
        "This organization has a shared API key and is being deprecated",
    ],
)
def test_classify_exit_transient_signatures(stderr):
    """Known infra-error stderr signatures classify as transient."""
    assert classify_exit(exit_code=1, stderr=stderr) == "transient"


def test_classify_exit_real_failure_for_generic_error():
    """A generic non-infra error with no work is a real failure."""
    result = classify_exit(exit_code=1, stderr="AssertionError: expected 3 got 4", work_events=0)
    assert result == "real_failure"


def test_classify_exit_mid_work_crash_when_work_done():
    """A crash after substantive work (with non-zero duration) is a mid-work crash."""
    result = classify_exit(exit_code=1, stderr="unexpected end", work_events=5, duration_ms=12000)
    assert result == "mid_work_crash"


def test_classify_exit_zero_duration_with_work_is_transient():
    """work_events>0 with duration_ms==0 is a serialisation race → transient."""
    result = classify_exit(exit_code=1, stderr="", work_events=3, duration_ms=0)
    assert result == "transient"


def test_classify_exit_success_bucket():
    """exit_code 0 is never a failure bucket."""
    assert classify_exit(exit_code=0, stderr="") == "real_failure"


def test_classify_exit_mid_work_stderr_marker():
    """Recognised mid-work stderr markers classify as mid_work_crash without work_events."""
    result = classify_exit(exit_code=1, stderr="Fatal error in message reader", work_events=0)
    assert result == "mid_work_crash"


# ---------------------------------------------------------------------------
# load_patterns
# ---------------------------------------------------------------------------


def test_load_patterns_returns_compiled_regexes():
    patterns = load_patterns()
    assert patterns
    assert all(hasattr(p, "search") for p in patterns)


# ---------------------------------------------------------------------------
# spawn_with_retry — unlimited transient retry, no budget impact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_with_retry_retries_transient_until_success():
    """Transient failures retry until the spawn eventually succeeds."""
    calls = {"n": 0}

    async def spawn_fn():
        calls["n"] += 1
        if calls["n"] < 4:
            return {
                "exit_code": 1,
                "stderr": "read ECONNRESET",
                "duration_ms": 100,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 500, "work_events": 2, "cost_usd": 0.0}

    async def no_sleep(_s):
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="f-transient",
        job_name="job",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )
    assert result["exit_code"] == 0
    assert calls["n"] == 4


@pytest.mark.asyncio
async def test_spawn_with_retry_transient_does_not_charge_budget():
    """Transient retries must not invoke real_failure / mid_work_crash callbacks."""
    calls = {"n": 0}
    real_failure_hits = []
    mid_work_hits = []

    async def spawn_fn():
        calls["n"] += 1
        if calls["n"] < 3:
            return {
                "exit_code": 1,
                "stderr": "HTTP 429 rate limit",
                "duration_ms": 10,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 100, "work_events": 1, "cost_usd": 0.0}

    async def no_sleep(_s):
        pass

    await spawn_with_retry(
        spawn_fn,
        feature_id="f-nobudget",
        job_name="job",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        on_real_failure=lambda r: real_failure_hits.append(r),
        on_mid_work_crash=lambda r: mid_work_hits.append(r),
    )
    assert real_failure_hits == []
    assert mid_work_hits == []


@pytest.mark.asyncio
async def test_spawn_with_retry_real_failure_charged_once_and_returns():
    """A real failure invokes on_real_failure exactly once and stops retrying."""
    calls = {"n": 0}
    real_failure_hits = []

    async def spawn_fn():
        calls["n"] += 1
        return {
            "exit_code": 1,
            "stderr": "AssertionError: boom",
            "duration_ms": 200,
            "work_events": 0,
            "cost_usd": 0.0,
        }

    async def no_sleep(_s):
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="f-real",
        job_name="job",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        on_real_failure=lambda r: real_failure_hits.append(r),
    )
    assert result["exit_code"] == 1
    assert calls["n"] == 1
    assert len(real_failure_hits) == 1


@pytest.mark.asyncio
async def test_spawn_with_retry_mid_work_crash_charged_once():
    """A mid-work crash invokes on_mid_work_crash once and stops retrying."""
    mid_work_hits = []

    async def spawn_fn():
        return {
            "exit_code": 1,
            "stderr": "unexpected termination",
            "duration_ms": 30000,
            "work_events": 7,
            "cost_usd": 1.5,
        }

    async def no_sleep(_s):
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="f-midwork",
        job_name="job",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        on_mid_work_crash=lambda r: mid_work_hits.append(r),
    )
    assert result["exit_code"] == 1
    assert len(mid_work_hits) == 1


@pytest.mark.asyncio
async def test_spawn_with_retry_cost_ceiling_breaks_loop():
    """Accumulated retry cost past the ceiling stops the unlimited loop."""
    cost_updates = []

    async def spawn_fn():
        return {
            "exit_code": 1,
            "stderr": "ECONNRESET",
            "duration_ms": 10,
            "work_events": 0,
            "cost_usd": 30.0,
        }

    async def no_sleep(_s):
        pass

    result = await spawn_with_retry(
        spawn_fn,
        feature_id="f-ceiling",
        job_name="job",
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
        config_path=None,
        on_cost_update=lambda c: cost_updates.append(c),
    )
    assert result.get("retry_cost_ceiling") is True
    assert result["total_retry_cost_usd"] >= 50.0


@pytest.mark.asyncio
async def test_spawn_with_retry_writes_retry_log(tmp_path):
    """Transient retries append a JSONL entry to the retry log."""
    calls = {"n": 0}

    async def spawn_fn():
        calls["n"] += 1
        if calls["n"] < 2:
            return {
                "exit_code": 1,
                "stderr": "ETIMEDOUT",
                "duration_ms": 10,
                "work_events": 0,
                "cost_usd": 0.0,
            }
        return {"exit_code": 0, "stderr": "", "duration_ms": 50, "work_events": 1, "cost_usd": 0.0}

    async def no_sleep(_s):
        pass

    await spawn_with_retry(
        spawn_fn,
        feature_id="f-log",
        job_name="logjob",
        log_dir=tmp_path,
        sleep_fn=no_sleep,
        probe_fn=lambda: True,
    )
    log_file = tmp_path / "logjob.retry.jsonl"
    assert log_file.exists()
    assert log_file.read_text(encoding="utf-8").strip()
