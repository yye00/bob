"""Tests for bob3.execution_timeout — per-feature hard wall-clock timeout.

Feature: f3a3f1c8-e6a3-433e-970e-74d5d69dc755
"""
from __future__ import annotations

import asyncio
import os
import importlib
import pytest

import bob3.execution_timeout as et


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

def test_module_importable():
    mod = importlib.import_module("bob3.execution_timeout")
    assert mod is not None


def test_enforce_feature_timeout_is_defined():
    assert hasattr(et, "enforce_feature_timeout")
    assert callable(et.enforce_feature_timeout)


def test_feature_timeout_error_class():
    err = et.FeatureTimeoutError("feat-1", 120.5, 100.0)
    assert err.feature_id == "feat-1"
    assert err.elapsed_seconds == pytest.approx(120.5)
    assert err.timeout_seconds == pytest.approx(100.0)
    assert "feat-1" in str(err)


# ---------------------------------------------------------------------------
# resolve_execution_timeout_seconds
# ---------------------------------------------------------------------------

def test_resolve_returns_default_when_env_absent(monkeypatch):
    monkeypatch.delenv("BOB3_FEATURE_TIMEOUT_SECONDS", raising=False)
    result = et.resolve_execution_timeout_seconds()
    assert result == et.DEFAULT_FEATURE_TIMEOUT_SECONDS
    assert result > 0


def test_resolve_reads_env_var(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "3600")
    assert et.resolve_execution_timeout_seconds() == pytest.approx(3600.0)


def test_resolve_falls_back_on_invalid_env(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "not-a-number")
    result = et.resolve_execution_timeout_seconds()
    assert result == et.DEFAULT_FEATURE_TIMEOUT_SECONDS


def test_resolve_falls_back_on_zero_env(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "0")
    result = et.resolve_execution_timeout_seconds()
    assert result == et.DEFAULT_FEATURE_TIMEOUT_SECONDS


def test_resolve_falls_back_on_negative_env(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "-500")
    result = et.resolve_execution_timeout_seconds()
    assert result == et.DEFAULT_FEATURE_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# enforce_feature_timeout — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enforce_feature_timeout_returns_coro_result():
    async def fast():
        return 42

    result = await et.enforce_feature_timeout("feat-a", fast(), timeout_seconds=10.0)
    assert result == 42


@pytest.mark.asyncio
async def test_enforce_feature_timeout_accepts_override_timeout():
    async def fast():
        return "done"

    result = await et.enforce_feature_timeout("feat-b", fast(), timeout_seconds=5.0)
    assert result == "done"


# ---------------------------------------------------------------------------
# enforce_feature_timeout — timeout path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enforce_feature_timeout_raises_on_expiry():
    async def slow():
        await asyncio.sleep(9999)

    with pytest.raises(et.FeatureTimeoutError) as exc_info:
        await et.enforce_feature_timeout("feat-slow", slow(), timeout_seconds=0.05)

    err = exc_info.value
    assert err.feature_id == "feat-slow"
    assert err.elapsed_seconds >= 0
    assert err.timeout_seconds == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_feature_timeout_error_is_runtime_error():
    async def slow():
        await asyncio.sleep(9999)

    with pytest.raises(RuntimeError):
        await et.enforce_feature_timeout("feat-x", slow(), timeout_seconds=0.05)


# ---------------------------------------------------------------------------
# enforce_feature_timeout — error path (ValueError)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_feature_id_raises_value_error():
    async def noop():
        return None

    with pytest.raises(ValueError):
        await et.enforce_feature_timeout("", noop(), timeout_seconds=10.0)


@pytest.mark.asyncio
async def test_whitespace_only_feature_id_raises_value_error():
    async def noop():
        return None

    with pytest.raises(ValueError):
        await et.enforce_feature_timeout("   ", noop(), timeout_seconds=10.0)


@pytest.mark.asyncio
async def test_zero_timeout_seconds_raises_value_error():
    async def noop():
        return None

    with pytest.raises(ValueError):
        await et.enforce_feature_timeout("feat-z", noop(), timeout_seconds=0.0)


@pytest.mark.asyncio
async def test_negative_timeout_seconds_raises_value_error():
    async def noop():
        return None

    with pytest.raises(ValueError):
        await et.enforce_feature_timeout("feat-neg", noop(), timeout_seconds=-1.0)


# ---------------------------------------------------------------------------
# Integration: bob3.orchestrator exposes enforce_feature_timeout
# ---------------------------------------------------------------------------

def test_orchestrator_integration():
    import bob3.orchestrator as orch
    assert hasattr(orch, "enforce_feature_timeout"), (
        "bob3.orchestrator must expose enforce_feature_timeout (integration AC)"
    )
    assert callable(orch.enforce_feature_timeout)


# ---------------------------------------------------------------------------
# Telemetry emission (smoke test via caplog)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_emits_warning_log(caplog):
    import logging

    async def slow():
        await asyncio.sleep(9999)

    with caplog.at_level(logging.WARNING, logger="bob3.execution_timeout"):
        with pytest.raises(et.FeatureTimeoutError):
            await et.enforce_feature_timeout(
                "feat-telemetry", slow(), timeout_seconds=0.05
            )

    assert any("TIMEOUT" in record.message for record in caplog.records)
    assert any("feat-telemetry" in record.message for record in caplog.records)
