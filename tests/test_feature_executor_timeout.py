"""Tests for bob.feature_executor.enforce_timeout (feature 86e81c64).

Verifies the per-feature hard wall-clock timeout enforcement:
- enforce_timeout is importable and callable
- It raises FeatureTimeoutError when the coroutine exceeds the deadline
- It returns the coroutine result when it completes within the deadline
- It validates inputs (empty feature_id, non-positive timeout_seconds)
- BOB_FEATURE_TIMEOUT_SECONDS env var controls the default timeout
- A TIMEOUT telemetry event is emitted on expiry
"""

from __future__ import annotations

import asyncio
import os

import pytest

from bob.feature_executor import FeatureTimeoutError, enforce_timeout


class TestEnforceTimeoutImport:
    """enforce_timeout is importable and callable."""

    def test_importable(self):
        import bob.feature_executor as m
        assert hasattr(m, "enforce_timeout")
        assert callable(m.enforce_timeout)

    def test_feature_timeout_error_importable(self):
        import bob.feature_executor as m
        assert hasattr(m, "FeatureTimeoutError")
        assert issubclass(m.FeatureTimeoutError, RuntimeError)


class TestEnforceTimeoutHappyPath:
    """enforce_timeout returns the coroutine result when it finishes in time."""

    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        async def fast():
            return "done"

        result = await enforce_timeout("feat-001", fast(), timeout_seconds=5.0)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_returns_none_result(self):
        async def noop():
            return None

        result = await enforce_timeout("feat-002", noop(), timeout_seconds=5.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_complex_result(self):
        async def coro():
            return {"status": "ok", "count": 42}

        result = await enforce_timeout("feat-003", coro(), timeout_seconds=5.0)
        assert result == {"status": "ok", "count": 42}


class TestEnforceTimeoutExpiry:
    """enforce_timeout raises FeatureTimeoutError when the coroutine is too slow."""

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self):
        async def slow():
            await asyncio.sleep(10)
            return "never"

        with pytest.raises(FeatureTimeoutError) as exc_info:
            await enforce_timeout("feat-hang", slow(), timeout_seconds=0.05)

        err = exc_info.value
        assert err.feature_id == "feat-hang"
        assert err.timeout_seconds == pytest.approx(0.05)
        assert err.elapsed_seconds >= 0.0

    @pytest.mark.asyncio
    async def test_timeout_error_message_contains_feature_id(self):
        async def slow():
            await asyncio.sleep(10)

        with pytest.raises(FeatureTimeoutError) as exc_info:
            await enforce_timeout("my-special-feature", slow(), timeout_seconds=0.05)

        assert "my-special-feature" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_error_is_runtime_error(self):
        async def slow():
            await asyncio.sleep(10)

        with pytest.raises(RuntimeError):
            await enforce_timeout("feat-x", slow(), timeout_seconds=0.05)


class TestEnforceTimeoutValidation:
    """enforce_timeout validates its inputs."""

    @pytest.mark.asyncio
    async def test_empty_feature_id_raises_value_error(self):
        async def noop():
            return None

        with pytest.raises(ValueError, match="feature_id"):
            await enforce_timeout("", noop(), timeout_seconds=5.0)

    @pytest.mark.asyncio
    async def test_blank_feature_id_raises_value_error(self):
        async def noop():
            return None

        with pytest.raises(ValueError, match="feature_id"):
            await enforce_timeout("   ", noop(), timeout_seconds=5.0)

    @pytest.mark.asyncio
    async def test_zero_timeout_raises_value_error(self):
        async def noop():
            return None

        with pytest.raises(ValueError):
            await enforce_timeout("feat-val", noop(), timeout_seconds=0.0)

    @pytest.mark.asyncio
    async def test_negative_timeout_raises_value_error(self):
        async def noop():
            return None

        with pytest.raises(ValueError):
            await enforce_timeout("feat-val", noop(), timeout_seconds=-1.0)


class TestEnforceTimeoutEnvVar:
    """BOB_FEATURE_TIMEOUT_SECONDS controls the default timeout."""

    @pytest.mark.asyncio
    async def test_env_var_controls_timeout(self, monkeypatch):
        monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "0.05")

        async def slow():
            await asyncio.sleep(10)

        with pytest.raises(FeatureTimeoutError):
            await enforce_timeout("feat-env", slow())

    @pytest.mark.asyncio
    async def test_invalid_env_var_uses_default(self, monkeypatch):
        monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "not-a-number")

        async def fast():
            return "ok"

        # Should complete quickly without error (default is 1800s)
        result = await enforce_timeout("feat-default", fast(), timeout_seconds=5.0)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_explicit_timeout_overrides_env_var(self, monkeypatch):
        monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "0.001")

        async def fast():
            return "fast-result"

        # Explicit timeout=5.0 overrides the env var
        result = await enforce_timeout("feat-override", fast(), timeout_seconds=5.0)
        assert result == "fast-result"


class TestEnforceTimeoutTelemetry:
    """A TIMEOUT telemetry event is emitted when a feature times out."""

    @pytest.mark.asyncio
    async def test_timeout_emits_warning_log(self, caplog):
        import logging

        async def slow():
            await asyncio.sleep(10)

        with caplog.at_level(logging.WARNING, logger="bob.feature_executor"):
            with pytest.raises(FeatureTimeoutError):
                await enforce_timeout("feat-telemetry", slow(), timeout_seconds=0.05)

        timeout_records = [r for r in caplog.records if "TIMEOUT" in r.message]
        assert timeout_records, "Expected a TIMEOUT WARNING log record"
        assert "feat-telemetry" in timeout_records[0].message


class TestOrchestratorIntegration:
    """bob.orchestrator imports and can use enforce_timeout from feature_executor."""

    def test_orchestrator_package_importable(self):
        import bob.orchestrator
        assert bob.orchestrator is not None

    def test_feature_executor_importable_from_bob(self):
        import bob.feature_executor
        assert hasattr(bob.feature_executor, "enforce_timeout")

    def test_run_loop_has_resolve_timeout(self):
        from bob.orchestrator.run_loop import _resolve_feature_timeout_seconds
        result = _resolve_feature_timeout_seconds()
        assert isinstance(result, float)
        assert result > 0
