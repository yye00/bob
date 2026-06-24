"""Tests for bob3.feature_timeout_executor — per-feature wall-clock timeout.

Feature: 9bdba8e1-c62e-4da4-ac0c-7ce0ad02cb75
"""
from __future__ import annotations

import asyncio
import importlib
import os

import pytest

import bob3.feature_timeout_executor as fte


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------


def test_module_importable():
    mod = importlib.import_module("bob3.feature_timeout_executor")
    assert mod is not None


def test_execute_with_timeout_is_defined():
    assert hasattr(fte, "execute_with_timeout")
    assert callable(fte.execute_with_timeout)


def test_resolve_timeout_seconds_is_defined():
    assert hasattr(fte, "resolve_timeout_seconds")
    assert callable(fte.resolve_timeout_seconds)


def test_feature_execution_timeout_error_class():
    err = fte.FeatureExecutionTimeoutError("feat-1", 120.5, 100.0)
    assert err.feature_id == "feat-1"
    assert err.elapsed_seconds == pytest.approx(120.5)
    assert err.timeout_seconds == pytest.approx(100.0)
    assert "feat-1" in str(err)


def test_default_timeout_constant_is_positive():
    assert fte.DEFAULT_TIMEOUT_SECONDS > 0


# ---------------------------------------------------------------------------
# resolve_timeout_seconds
# ---------------------------------------------------------------------------


def test_resolve_returns_default_when_env_absent(monkeypatch):
    monkeypatch.delenv("BOB3_FEATURE_TIMEOUT_SECONDS", raising=False)
    result = fte.resolve_timeout_seconds()
    assert result == fte.DEFAULT_TIMEOUT_SECONDS
    assert result > 0


def test_resolve_reads_env_var(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "900")
    assert fte.resolve_timeout_seconds() == pytest.approx(900.0)


def test_resolve_falls_back_on_invalid_env(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "not-a-number")
    result = fte.resolve_timeout_seconds()
    assert result == fte.DEFAULT_TIMEOUT_SECONDS


def test_resolve_falls_back_on_zero_env(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "0")
    result = fte.resolve_timeout_seconds()
    assert result == fte.DEFAULT_TIMEOUT_SECONDS


def test_resolve_falls_back_on_negative_env(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "-100")
    result = fte.resolve_timeout_seconds()
    assert result == fte.DEFAULT_TIMEOUT_SECONDS


def test_resolve_accepts_fractional_seconds(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "1800.5")
    result = fte.resolve_timeout_seconds()
    assert result == pytest.approx(1800.5)


# ---------------------------------------------------------------------------
# execute_with_timeout — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_completes_within_timeout():
    async def fast_coro():
        return "done"

    result = await fte.execute_with_timeout("feat-abc", fast_coro(), timeout_seconds=5.0)
    assert result == "done"


@pytest.mark.asyncio
async def test_execute_uses_env_timeout(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "5")

    async def fast_coro():
        return 42

    result = await fte.execute_with_timeout("feat-abc", fast_coro())
    assert result == 42


@pytest.mark.asyncio
async def test_execute_returns_coroutine_result():
    async def coro_with_value():
        return {"key": "value"}

    result = await fte.execute_with_timeout(
        "feat-001", coro_with_value(), timeout_seconds=5.0
    )
    assert result == {"key": "value"}


# ---------------------------------------------------------------------------
# execute_with_timeout — timeout path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_raises_on_timeout():
    async def slow_coro():
        await asyncio.sleep(10)
        return "never"

    with pytest.raises(fte.FeatureExecutionTimeoutError) as exc_info:
        await fte.execute_with_timeout("feat-slow", slow_coro(), timeout_seconds=0.05)

    err = exc_info.value
    assert err.feature_id == "feat-slow"
    assert err.timeout_seconds == pytest.approx(0.05)
    assert err.elapsed_seconds >= 0.0


@pytest.mark.asyncio
async def test_timeout_error_contains_feature_id():
    async def slow_coro():
        await asyncio.sleep(10)

    with pytest.raises(fte.FeatureExecutionTimeoutError) as exc_info:
        await fte.execute_with_timeout("feature-xyz", slow_coro(), timeout_seconds=0.05)

    assert "feature-xyz" in str(exc_info.value)


@pytest.mark.asyncio
async def test_timeout_telemetry_emitted(caplog):
    import logging

    async def slow_coro():
        await asyncio.sleep(10)

    with caplog.at_level(logging.WARNING, logger="bob3.feature_timeout_executor"):
        with pytest.raises(fte.FeatureExecutionTimeoutError):
            await fte.execute_with_timeout("feat-telemetry", slow_coro(), timeout_seconds=0.05)

    # TIMEOUT telemetry must be in the logs
    assert any("TIMEOUT" in record.message for record in caplog.records)
    assert any("feat-telemetry" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# execute_with_timeout — validation / error path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_raises_on_empty_feature_id():
    async def dummy():
        return None

    with pytest.raises(ValueError, match="feature_id"):
        await fte.execute_with_timeout("", dummy(), timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_execute_raises_on_whitespace_feature_id():
    async def dummy():
        return None

    with pytest.raises(ValueError, match="feature_id"):
        await fte.execute_with_timeout("   ", dummy(), timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_execute_raises_on_non_positive_timeout():
    async def dummy():
        return None

    with pytest.raises(ValueError, match="timeout_seconds"):
        await fte.execute_with_timeout("feat-x", dummy(), timeout_seconds=0.0)


@pytest.mark.asyncio
async def test_execute_raises_on_negative_timeout():
    async def dummy():
        return None

    with pytest.raises(ValueError, match="timeout_seconds"):
        await fte.execute_with_timeout("feat-x", dummy(), timeout_seconds=-1.0)


# ---------------------------------------------------------------------------
# Integration: orchestrator imports execute_with_timeout
# ---------------------------------------------------------------------------


def test_orchestrator_imports_execute_with_timeout():
    mod = importlib.import_module("bob3.orchestrator.run_loop")
    assert hasattr(mod, "_execute_with_timeout"), (
        "bob3.orchestrator.run_loop must import execute_with_timeout "
        "from bob3.feature_timeout_executor for integration AC 9bdba8e1"
    )
