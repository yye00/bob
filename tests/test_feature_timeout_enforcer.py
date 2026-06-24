"""Tests for bob.feature_timeout_enforcer (feature 03cd988a).

Covers:
- Module and function importability
- enforce_feature_timeout: normal execution (completes within timeout)
- enforce_feature_timeout: timeout path (FeatureTimeoutError raised)
- enforce_feature_timeout: invalid inputs raise ValueError
- resolve_timeout_seconds: env var behaviour
- FeatureTimeoutError: attributes
- Integration: orchestrator module can import the enforcer
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import pytest


# ---------------------------------------------------------------------------
# Import checks
# ---------------------------------------------------------------------------


def test_module_importable():
    mod = importlib.import_module("bob.feature_timeout_enforcer")
    assert mod is not None


def test_enforce_feature_timeout_callable():
    mod = importlib.import_module("bob.feature_timeout_enforcer")
    fn = getattr(mod, "enforce_feature_timeout", None)
    assert fn is not None, "enforce_feature_timeout must be defined"
    assert callable(fn), "enforce_feature_timeout must be callable"


def test_feature_timeout_error_importable():
    from bob.feature_timeout_enforcer import FeatureTimeoutError  # noqa: F401


def test_resolve_timeout_seconds_importable():
    from bob.feature_timeout_enforcer import resolve_timeout_seconds
    assert callable(resolve_timeout_seconds)


# ---------------------------------------------------------------------------
# resolve_timeout_seconds
# ---------------------------------------------------------------------------


def test_resolve_timeout_seconds_default(monkeypatch):
    monkeypatch.delenv("BOB_FEATURE_TIMEOUT_SECONDS", raising=False)
    from bob.feature_timeout_enforcer import resolve_timeout_seconds
    # Re-import to get fresh module state
    t = resolve_timeout_seconds()
    assert isinstance(t, float)
    assert t > 0


def test_resolve_timeout_seconds_from_env(monkeypatch):
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "300")
    from bob.feature_timeout_enforcer import resolve_timeout_seconds
    assert resolve_timeout_seconds() == 300.0


def test_resolve_timeout_seconds_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "not-a-number")
    from bob.feature_timeout_enforcer import resolve_timeout_seconds
    t = resolve_timeout_seconds()
    assert t > 0  # must not raise, must return positive default


def test_resolve_timeout_seconds_zero_falls_back(monkeypatch):
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "0")
    from bob.feature_timeout_enforcer import resolve_timeout_seconds
    t = resolve_timeout_seconds()
    assert t > 0


def test_resolve_timeout_seconds_negative_falls_back(monkeypatch):
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "-100")
    from bob.feature_timeout_enforcer import resolve_timeout_seconds
    t = resolve_timeout_seconds()
    assert t > 0


# ---------------------------------------------------------------------------
# enforce_feature_timeout — valid use
# ---------------------------------------------------------------------------


def test_enforce_completes_within_timeout():
    from bob.feature_timeout_enforcer import enforce_feature_timeout

    async def _inner():
        async def fast():
            return 42

        result = await enforce_feature_timeout("feat-001", fast(), timeout_seconds=10.0)
        assert result == 42

    asyncio.run(_inner())


def test_enforce_passes_result_through():
    from bob.feature_timeout_enforcer import enforce_feature_timeout

    async def _inner():
        async def returns_string():
            return "hello"

        result = await enforce_feature_timeout("feat-abc", returns_string(), timeout_seconds=10.0)
        assert result == "hello"

    asyncio.run(_inner())


def test_enforce_timeout_fires():
    from bob.feature_timeout_enforcer import enforce_feature_timeout, FeatureTimeoutError

    async def _inner():
        async def slow():
            await asyncio.sleep(9999)

        with pytest.raises(FeatureTimeoutError) as exc_info:
            await enforce_feature_timeout("feat-slow", slow(), timeout_seconds=0.05)

        err = exc_info.value
        assert err.feature_id == "feat-slow"
        assert err.elapsed_seconds >= 0
        assert err.timeout_seconds == pytest.approx(0.05)

    asyncio.run(_inner())


def test_enforce_timeout_uses_env_when_none(monkeypatch):
    """When timeout_seconds=None the env var is respected."""
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "0.05")
    from bob.feature_timeout_enforcer import enforce_feature_timeout, FeatureTimeoutError

    async def _inner():
        async def slow():
            await asyncio.sleep(9999)

        with pytest.raises(FeatureTimeoutError):
            await enforce_feature_timeout("feat-env", slow(), timeout_seconds=None)

    asyncio.run(_inner())


# ---------------------------------------------------------------------------
# enforce_feature_timeout — invalid inputs raise ValueError
# ---------------------------------------------------------------------------


def test_enforce_raises_on_empty_feature_id():
    from bob.feature_timeout_enforcer import enforce_feature_timeout

    async def _inner():
        async def dummy():
            return None

        with pytest.raises(ValueError, match="feature_id"):
            await enforce_feature_timeout("", dummy(), timeout_seconds=10.0)

    asyncio.run(_inner())


def test_enforce_raises_on_blank_feature_id():
    from bob.feature_timeout_enforcer import enforce_feature_timeout

    async def _inner():
        async def dummy():
            return None

        with pytest.raises(ValueError):
            await enforce_feature_timeout("   ", dummy(), timeout_seconds=10.0)

    asyncio.run(_inner())


def test_enforce_raises_on_zero_timeout():
    from bob.feature_timeout_enforcer import enforce_feature_timeout

    async def _inner():
        async def dummy():
            return None

        with pytest.raises(ValueError):
            await enforce_feature_timeout("feat-001", dummy(), timeout_seconds=0)

    asyncio.run(_inner())


def test_enforce_raises_on_negative_timeout():
    from bob.feature_timeout_enforcer import enforce_feature_timeout

    async def _inner():
        async def dummy():
            return None

        with pytest.raises(ValueError):
            await enforce_feature_timeout("feat-001", dummy(), timeout_seconds=-5.0)

    asyncio.run(_inner())


# ---------------------------------------------------------------------------
# FeatureTimeoutError attributes
# ---------------------------------------------------------------------------


def test_feature_timeout_error_attributes():
    from bob.feature_timeout_enforcer import FeatureTimeoutError

    err = FeatureTimeoutError("feat-xyz", elapsed_seconds=1802.3, timeout_seconds=1800.0)
    assert err.feature_id == "feat-xyz"
    assert err.elapsed_seconds == pytest.approx(1802.3)
    assert err.timeout_seconds == pytest.approx(1800.0)
    assert "feat-xyz" in str(err)


def test_feature_timeout_error_is_runtime_error():
    from bob.feature_timeout_enforcer import FeatureTimeoutError

    err = FeatureTimeoutError("feat-xyz", 1.0, 0.5)
    assert isinstance(err, RuntimeError)


# ---------------------------------------------------------------------------
# Integration: orchestrator can import the enforcer
# ---------------------------------------------------------------------------


def test_orchestrator_integration():
    """The orchestrator package must be importable alongside feature_timeout_enforcer."""
    mod = importlib.import_module("bob.feature_timeout_enforcer")
    assert hasattr(mod, "enforce_feature_timeout")
    # Also verify orchestrator itself is importable (integration link)
    orch = importlib.import_module("bob.orchestrator")
    assert orch is not None
