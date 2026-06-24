"""Tests for per-feature wall-clock timeout enforcement (feature 0e96dd41).

Verifies that bob.orchestrator.enforce_feature_timeout enforces a hard
wall-clock timeout on feature execution coroutines, emits TIMEOUT telemetry,
and raises FeatureTimeoutError on expiry while returning normally for
fast-completing coroutines.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import time

import pytest

import bob.orchestrator
import bob.timeout as _timeout_mod


# ---------------------------------------------------------------------------
# Module-level contract: enforce_feature_timeout accessible via bob.orchestrator
# ---------------------------------------------------------------------------

def test_enforce_feature_timeout_accessible_from_orchestrator():
    assert hasattr(bob.orchestrator, "enforce_feature_timeout"), (
        "bob.orchestrator must expose enforce_feature_timeout"
    )
    fn = bob.orchestrator.enforce_feature_timeout
    assert callable(fn)


def test_enforce_feature_timeout_is_coroutine_function():
    fn = bob.orchestrator.enforce_feature_timeout
    assert asyncio.iscoroutinefunction(fn), (
        "enforce_feature_timeout must be an async function (coroutinefunction)"
    )


# ---------------------------------------------------------------------------
# enforce_feature_timeout — happy path (completes within timeout)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enforce_feature_timeout_returns_result_on_fast_coroutine():
    async def fast_coro():
        return "done"

    result = await bob.orchestrator.enforce_feature_timeout(
        "feat-001", fast_coro(), timeout_seconds=10.0
    )
    assert result == "done"


@pytest.mark.asyncio
async def test_enforce_feature_timeout_propagates_return_value():
    async def coro():
        return {"status": "ok", "count": 42}

    result = await bob.orchestrator.enforce_feature_timeout(
        "feat-999", coro(), timeout_seconds=5.0
    )
    assert result == {"status": "ok", "count": 42}


# ---------------------------------------------------------------------------
# enforce_feature_timeout — timeout path raises FeatureTimeoutError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enforce_feature_timeout_raises_on_slow_coroutine():
    async def slow_coro():
        await asyncio.sleep(60)
        return "should not get here"

    with pytest.raises(_timeout_mod.FeatureTimeoutError) as exc_info:
        await bob.orchestrator.enforce_feature_timeout(
            "feat-slow", slow_coro(), timeout_seconds=0.05
        )

    err = exc_info.value
    assert err.feature_id == "feat-slow"
    assert err.timeout_seconds == pytest.approx(0.05, rel=0.1)
    assert err.elapsed_seconds >= 0.0


@pytest.mark.asyncio
async def test_enforce_feature_timeout_emits_telemetry_on_expiry(caplog):
    import logging

    async def slow_coro():
        await asyncio.sleep(60)

    with caplog.at_level(logging.WARNING, logger="bob.timeout"):
        with pytest.raises(_timeout_mod.FeatureTimeoutError):
            await bob.orchestrator.enforce_feature_timeout(
                "feat-telemetry", slow_coro(), timeout_seconds=0.05
            )

    # TIMEOUT event must appear in the log
    assert any("TIMEOUT" in r.message for r in caplog.records), (
        "A TIMEOUT log record must be emitted when a feature times out"
    )


# ---------------------------------------------------------------------------
# enforce_feature_timeout — invalid input raises ValueError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enforce_feature_timeout_raises_valueerror_on_empty_feature_id():
    async def noop():
        return None

    with pytest.raises(ValueError):
        await bob.orchestrator.enforce_feature_timeout("", noop(), timeout_seconds=10.0)


@pytest.mark.asyncio
async def test_enforce_feature_timeout_raises_valueerror_on_whitespace_feature_id():
    async def noop():
        return None

    with pytest.raises(ValueError):
        await bob.orchestrator.enforce_feature_timeout("   ", noop(), timeout_seconds=10.0)


@pytest.mark.asyncio
async def test_enforce_feature_timeout_raises_valueerror_on_non_positive_timeout():
    async def noop():
        return None

    with pytest.raises(ValueError):
        await bob.orchestrator.enforce_feature_timeout("feat-x", noop(), timeout_seconds=0)

    with pytest.raises(ValueError):
        await bob.orchestrator.enforce_feature_timeout("feat-x", noop(), timeout_seconds=-1.0)


# ---------------------------------------------------------------------------
# resolve_timeout_seconds — reads BOB_FEATURE_TIMEOUT_SECONDS from env
# ---------------------------------------------------------------------------

def test_resolve_timeout_seconds_default():
    env_backup = os.environ.pop("BOB_FEATURE_TIMEOUT_SECONDS", None)
    try:
        result = _timeout_mod.resolve_timeout_seconds()
        assert result == pytest.approx(1800.0)
    finally:
        if env_backup is not None:
            os.environ["BOB_FEATURE_TIMEOUT_SECONDS"] = env_backup


def test_resolve_timeout_seconds_reads_env(monkeypatch):
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "600")
    result = _timeout_mod.resolve_timeout_seconds()
    assert result == pytest.approx(600.0)


def test_resolve_timeout_seconds_falls_back_on_invalid_env(monkeypatch):
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "not-a-number")
    result = _timeout_mod.resolve_timeout_seconds()
    assert result == pytest.approx(1800.0)


def test_resolve_timeout_seconds_falls_back_on_zero(monkeypatch):
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "0")
    result = _timeout_mod.resolve_timeout_seconds()
    assert result == pytest.approx(1800.0)


def test_resolve_timeout_seconds_falls_back_on_negative(monkeypatch):
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "-500")
    result = _timeout_mod.resolve_timeout_seconds()
    assert result == pytest.approx(1800.0)


# ---------------------------------------------------------------------------
# FeatureTimeoutError attributes
# ---------------------------------------------------------------------------

def test_feature_timeout_error_attributes():
    err = _timeout_mod.FeatureTimeoutError("feat-abc", elapsed_seconds=1805.5, timeout_seconds=1800.0)
    assert err.feature_id == "feat-abc"
    assert err.elapsed_seconds == pytest.approx(1805.5)
    assert err.timeout_seconds == pytest.approx(1800.0)
    assert isinstance(err, RuntimeError)
    assert "feat-abc" in str(err)
    assert "1800" in str(err)


# ---------------------------------------------------------------------------
# enforce_feature_timeout uses env timeout when timeout_seconds is None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enforce_feature_timeout_uses_env_timeout(monkeypatch):
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "0.05")

    async def slow_coro():
        await asyncio.sleep(60)

    with pytest.raises(_timeout_mod.FeatureTimeoutError) as exc_info:
        await bob.orchestrator.enforce_feature_timeout(
            "feat-env-timeout", slow_coro()
        )

    assert exc_info.value.feature_id == "feat-env-timeout"
    assert exc_info.value.timeout_seconds == pytest.approx(0.05, rel=0.1)
