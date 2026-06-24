"""Tests for bob3.timeout — per-feature wall-clock timeout enforcement."""

from __future__ import annotations

import asyncio
import os

import pytest

from bob3.timeout import (
    FeatureTimeoutError,
    enforce_feature_timeout,
    enforce_wall_clock_timeout,
    resolve_timeout_seconds,
)


# ---------------------------------------------------------------------------
# resolve_timeout_seconds
# ---------------------------------------------------------------------------

def test_resolve_timeout_returns_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("BOB3_FEATURE_TIMEOUT_SECONDS", raising=False)
    result = resolve_timeout_seconds()
    assert result == 1800.0


def test_resolve_timeout_reads_env_var(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "600")
    assert resolve_timeout_seconds() == 600.0


def test_resolve_timeout_falls_back_on_invalid_env(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "not_a_number")
    result = resolve_timeout_seconds()
    assert result == 1800.0


def test_resolve_timeout_falls_back_on_zero(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "0")
    result = resolve_timeout_seconds()
    assert result == 1800.0


def test_resolve_timeout_falls_back_on_negative(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "-5")
    result = resolve_timeout_seconds()
    assert result == 1800.0


# ---------------------------------------------------------------------------
# FeatureTimeoutError
# ---------------------------------------------------------------------------

def test_feature_timeout_error_carries_fields():
    err = FeatureTimeoutError("feat-1", 120.5, 60.0)
    assert err.feature_id == "feat-1"
    assert err.elapsed_seconds == 120.5
    assert err.timeout_seconds == 60.0
    assert isinstance(err, RuntimeError)


def test_feature_timeout_error_message_contains_feature_id():
    err = FeatureTimeoutError("feat-abc", 10.0, 5.0)
    assert "feat-abc" in str(err)


# ---------------------------------------------------------------------------
# enforce_wall_clock_timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_returns_result_on_success():
    async def fast_coro():
        return "done"

    result = await enforce_wall_clock_timeout("feat-1", fast_coro(), timeout_seconds=5.0)
    assert result == "done"


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_raises_on_timeout():
    async def slow_coro():
        await asyncio.sleep(10)

    with pytest.raises(FeatureTimeoutError) as exc_info:
        await enforce_wall_clock_timeout("feat-2", slow_coro(), timeout_seconds=0.01)

    assert exc_info.value.feature_id == "feat-2"
    assert exc_info.value.timeout_seconds == 0.01


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_raises_value_error_on_empty_feature_id():
    async def coro():
        return None

    c = coro()
    with pytest.raises(ValueError, match="feature_id"):
        await enforce_wall_clock_timeout("", c)
    c.close()  # suppress "coroutine was never awaited" warning


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_raises_value_error_on_whitespace_feature_id():
    async def coro():
        return None

    c = coro()
    with pytest.raises(ValueError, match="feature_id"):
        await enforce_wall_clock_timeout("   ", c)
    c.close()


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_raises_value_error_on_non_positive_timeout():
    async def coro():
        return None

    c1 = coro()
    with pytest.raises(ValueError):
        await enforce_wall_clock_timeout("feat-3", c1, timeout_seconds=0.0)
    c1.close()

    c2 = coro()
    with pytest.raises(ValueError):
        await enforce_wall_clock_timeout("feat-3", c2, timeout_seconds=-1.0)
    c2.close()


@pytest.mark.asyncio
async def test_enforce_wall_clock_timeout_uses_env_when_no_override(monkeypatch):
    monkeypatch.setenv("BOB3_FEATURE_TIMEOUT_SECONDS", "9999")

    async def fast_coro():
        return 42

    result = await enforce_wall_clock_timeout("feat-4", fast_coro())
    assert result == 42


# ---------------------------------------------------------------------------
# enforce_feature_timeout (canonical public entry point)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enforce_feature_timeout_returns_result_on_success():
    async def fast_coro():
        return "ok"

    result = await enforce_feature_timeout("feat-5", fast_coro(), timeout_seconds=5.0)
    assert result == "ok"


@pytest.mark.asyncio
async def test_enforce_feature_timeout_raises_on_timeout():
    async def slow_coro():
        await asyncio.sleep(10)

    with pytest.raises(FeatureTimeoutError) as exc_info:
        await enforce_feature_timeout("feat-6", slow_coro(), timeout_seconds=0.01)

    assert exc_info.value.feature_id == "feat-6"


@pytest.mark.asyncio
async def test_enforce_feature_timeout_raises_value_error_on_empty_feature_id():
    async def coro():
        return None

    c = coro()
    with pytest.raises(ValueError):
        await enforce_feature_timeout("", c)
    c.close()


@pytest.mark.asyncio
async def test_enforce_feature_timeout_raises_value_error_on_non_positive_timeout():
    async def coro():
        return None

    c = coro()
    with pytest.raises(ValueError):
        await enforce_feature_timeout("feat-7", c, timeout_seconds=-1.0)
    c.close()


@pytest.mark.asyncio
async def test_enforce_feature_timeout_emits_telemetry_on_timeout(caplog):
    import logging

    async def slow_coro():
        await asyncio.sleep(10)

    with caplog.at_level(logging.WARNING, logger="bob3.timeout"):
        with pytest.raises(FeatureTimeoutError):
            await enforce_feature_timeout("feat-8", slow_coro(), timeout_seconds=0.01)

    assert any("TIMEOUT" in record.message for record in caplog.records)
