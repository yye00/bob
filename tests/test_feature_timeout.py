"""Tests for bob3.timeout — per-feature wall-clock timeout enforcement.

Covers:
- enforce_wall_clock_timeout happy path (coroutine completes within timeout)
- enforce_wall_clock_timeout raises FeatureTimeoutError when coroutine exceeds timeout
- TIMEOUT telemetry event emitted on timeout (feature_id and elapsed_seconds logged)
- resolve_timeout_seconds reads BOB3_FEATURE_TIMEOUT_SECONDS env var correctly
- Empty/zero/invalid inputs produce well-defined errors (not silent success/crash)
- Integration: execute_feature in bob3.orchestrator module is importable
"""

from __future__ import annotations

import asyncio
import importlib
import os

import pytest

from bob3.timeout import (
    FeatureTimeoutError,
    enforce_wall_clock_timeout,
    resolve_timeout_seconds,
)


# ---------------------------------------------------------------------------
# resolve_timeout_seconds
# ---------------------------------------------------------------------------


def test_resolve_timeout_seconds_default(monkeypatch):
    monkeypatch.delenv("BOB3_FEATURE_TIMEOUT_SECONDS", raising=False)
    result = resolve_timeout_seconds()
    assert result > 0
    assert isinstance(result, float)


def test_resolve_timeout_seconds_reads_env(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "900")
    result = resolve_timeout_seconds()
    assert result == 900.0


def test_resolve_timeout_seconds_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "not_a_number")
    result = resolve_timeout_seconds()
    assert result > 0


def test_resolve_timeout_seconds_zero_env_falls_back(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "0")
    result = resolve_timeout_seconds()
    assert result > 0


def test_resolve_timeout_seconds_negative_env_falls_back(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "-100")
    result = resolve_timeout_seconds()
    assert result > 0


# ---------------------------------------------------------------------------
# enforce_wall_clock_timeout — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_returns_coro_result():
    async def fast_coro():
        return "done"

    result = await enforce_wall_clock_timeout(
        "feat-001", fast_coro(), timeout_seconds=5.0
    )
    assert result == "done"


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_returns_value_types():
    async def int_coro():
        return 42

    result = await enforce_wall_clock_timeout(
        "feat-002", int_coro(), timeout_seconds=5.0
    )
    assert result == 42


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_returns_none_coro():
    async def none_coro():
        return None

    result = await enforce_wall_clock_timeout(
        "feat-003", none_coro(), timeout_seconds=5.0
    )
    assert result is None


# ---------------------------------------------------------------------------
# enforce_wall_clock_timeout — timeout path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_raises_on_timeout():
    async def slow_coro():
        await asyncio.sleep(100)

    with pytest.raises(FeatureTimeoutError) as exc_info:
        await enforce_wall_clock_timeout(
            "feat-hang-001", slow_coro(), timeout_seconds=0.05
        )

    err = exc_info.value
    assert err.feature_id == "feat-hang-001"
    assert err.elapsed_seconds >= 0.0
    assert err.timeout_seconds == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_error_message_contains_feature_id():
    async def slow_coro():
        await asyncio.sleep(100)

    with pytest.raises(FeatureTimeoutError) as exc_info:
        await enforce_wall_clock_timeout(
            "feat-abc-123", slow_coro(), timeout_seconds=0.05
        )

    assert "feat-abc-123" in str(exc_info.value)


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_emits_telemetry(caplog):
    import logging

    async def slow_coro():
        await asyncio.sleep(100)

    with caplog.at_level(logging.WARNING, logger="bob3.timeout"):
        with pytest.raises(FeatureTimeoutError):
            await enforce_wall_clock_timeout(
                "feat-telemetry-001", slow_coro(), timeout_seconds=0.05
            )

    assert any("TIMEOUT" in record.message for record in caplog.records)
    assert any("feat-telemetry-001" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_telemetry_includes_elapsed(caplog):
    import logging

    async def slow_coro():
        await asyncio.sleep(100)

    with caplog.at_level(logging.WARNING, logger="bob3.timeout"):
        with pytest.raises(FeatureTimeoutError):
            await enforce_wall_clock_timeout(
                "feat-elapsed-001", slow_coro(), timeout_seconds=0.05
            )

    timeout_records = [r for r in caplog.records if "TIMEOUT" in r.message]
    assert len(timeout_records) >= 1
    assert "elapsed_seconds" in timeout_records[0].message


# ---------------------------------------------------------------------------
# enforce_wall_clock_timeout — invalid input (boundary / rejection)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_rejects_empty_feature_id():
    async def coro():
        return "ok"

    with pytest.raises(ValueError, match="feature_id"):
        await enforce_wall_clock_timeout("", coro(), timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_rejects_whitespace_only_feature_id():
    async def coro():
        return "ok"

    with pytest.raises(ValueError, match="feature_id"):
        await enforce_wall_clock_timeout("   ", coro(), timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_rejects_zero_timeout():
    async def coro():
        return "ok"

    with pytest.raises(ValueError, match="timeout_seconds"):
        await enforce_wall_clock_timeout("feat-001", coro(), timeout_seconds=0)


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_rejects_negative_timeout():
    async def coro():
        return "ok"

    with pytest.raises(ValueError, match="timeout_seconds"):
        await enforce_wall_clock_timeout("feat-001", coro(), timeout_seconds=-1.0)


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_empty_input_not_crash():
    """Empty feature_id must return a well-defined ValueError, not crash."""
    async def coro():
        return "ok"

    try:
        await enforce_wall_clock_timeout("", coro(), timeout_seconds=5.0)
        pytest.fail("Expected ValueError was not raised")
    except ValueError:
        pass
    except Exception as exc:
        pytest.fail(f"Expected ValueError but got {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Integration — bob3.orchestrator.execute_feature importable
# ---------------------------------------------------------------------------


def test_orchestrator_has_execute_feature():
    from bob3.orchestrator.run_loop import OrchestrationLoop

    assert hasattr(OrchestrationLoop, "execute_feature"), (
        "OrchestrationLoop must define execute_feature"
    )
    assert callable(OrchestrationLoop.execute_feature)


def test_timeout_module_exports():
    from bob3 import timeout as timeout_mod

    assert hasattr(timeout_mod, "enforce_wall_clock_timeout")
    assert hasattr(timeout_mod, "resolve_timeout_seconds")
    assert hasattr(timeout_mod, "FeatureTimeoutError")


def test_feature_timeout_error_is_runtime_error():
    err = FeatureTimeoutError("feat-x", 65.0, 60.0)
    assert isinstance(err, RuntimeError)
    assert err.feature_id == "feat-x"
    assert err.elapsed_seconds == pytest.approx(65.0)
    assert err.timeout_seconds == pytest.approx(60.0)
