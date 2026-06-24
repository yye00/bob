"""Tests for bob3.synth_retry — retry primitives for transient upstream API failures.

Covers:
- retry_with_backoff: generic async retry loop with exponential backoff
- synthesize_with_retry: wrapper around synthesize_for_feature with retry
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3.synth_retry import retry_with_backoff, synthesize_with_retry


class TestRetryWithBackoff:
    """Tests for the retry_with_backoff primitive."""

    @pytest.mark.asyncio
    async def test_immediate_success_returns_text(self):
        """When fn returns non-empty text on first attempt, it is returned immediately."""
        async def fn(**kwargs):
            return "synthesized: File exists: src/foo.py"

        result = await retry_with_backoff(fn, label="test-feature", max_attempts=3)
        assert result == "synthesized: File exists: src/foo.py"

    @pytest.mark.asyncio
    async def test_empty_first_then_success_retries(self):
        """Empty return on first attempt triggers retry; success on second is returned."""
        calls = []

        async def fn(**kwargs):
            calls.append(1)
            if len(calls) == 1:
                return ""
            return "success text"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_with_backoff(fn, label="retry-feature", max_attempts=3)

        assert result == "success text"
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_all_empty_exhausts_attempts_returns_empty(self):
        """When all attempts return empty, retry_with_backoff returns empty string."""
        call_count = 0

        async def fn(**kwargs):
            nonlocal call_count
            call_count += 1
            return ""

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_with_backoff(fn, label="always-empty", max_attempts=3)

        assert result == ""
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exception_triggers_retry(self):
        """Exception from fn triggers retry; success on second attempt is returned."""
        calls = []

        async def fn(**kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("HTTP 400: transient upstream error")
            return "recovered text"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_with_backoff(fn, label="exception-feature", max_attempts=3)

        assert result == "recovered text"
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_all_exceptions_returns_empty(self):
        """When fn always raises, all attempts are exhausted and empty string is returned."""
        call_count = 0

        async def fn(**kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("persistent upstream failure")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_with_backoff(fn, label="always-raises", max_attempts=3)

        assert result == ""
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_attempts_one_calls_fn_exactly_once(self):
        """max_attempts=1 means exactly one call, no retries."""
        call_count = 0

        async def fn(**kwargs):
            nonlocal call_count
            call_count += 1
            return ""

        result = await retry_with_backoff(fn, label="single-attempt", max_attempts=1)

        assert result == ""
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_kwargs_forwarded_to_fn(self):
        """fn_kwargs are forwarded correctly to fn on every call."""
        received_kwargs = []

        async def fn(**kwargs):
            received_kwargs.append(kwargs)
            return "result"

        await retry_with_backoff(fn, label="kwarg-check", max_attempts=1, key1="val1", key2=42)

        assert len(received_kwargs) == 1
        assert received_kwargs[0] == {"key1": "val1", "key2": 42}

    @pytest.mark.asyncio
    async def test_retry_logs_warning_on_empty(self, caplog):
        """Empty response is logged at WARNING level so it's observable, not silent."""
        import logging
        call_count = 0

        async def fn(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return ""
            return "success"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with caplog.at_level(logging.WARNING, logger="bob3.synth_retry"):
                await retry_with_backoff(fn, label="log-check", max_attempts=3)

        warning_logs = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_logs) >= 1

    @pytest.mark.asyncio
    async def test_whitespace_only_response_triggers_retry(self):
        """Whitespace-only response is treated as empty and triggers retry."""
        calls = []

        async def fn(**kwargs):
            calls.append(1)
            if len(calls) == 1:
                return "   \n\t  "
            return "real content"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_with_backoff(fn, label="whitespace", max_attempts=3)

        assert result == "real content"
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_env_var_controls_max_attempts(self):
        """BOB3_SYNTH_MAX_ATTEMPTS env var controls max attempts when max_attempts is None."""
        call_count = 0

        async def fn(**kwargs):
            nonlocal call_count
            call_count += 1
            return ""

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch.dict(os.environ, {"BOB3_SYNTH_MAX_ATTEMPTS": "2"}):
                result = await retry_with_backoff(fn, label="env-var", max_attempts=None)

        assert call_count == 2
        assert result == ""

    @pytest.mark.asyncio
    async def test_invalid_env_var_falls_back_to_default(self):
        """Invalid BOB3_SYNTH_MAX_ATTEMPTS value does not crash; falls back to default."""
        async def fn(**kwargs):
            return "success"

        with patch.dict(os.environ, {"BOB3_SYNTH_MAX_ATTEMPTS": "not_a_number"}):
            result = await retry_with_backoff(fn, label="invalid-env", max_attempts=None)

        assert result == "success"

    @pytest.mark.asyncio
    async def test_never_raises_to_caller(self):
        """retry_with_backoff never propagates exceptions to the caller."""
        async def fn(**kwargs):
            raise ValueError("should not propagate")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            # Must not raise
            result = await retry_with_backoff(fn, label="no-raise", max_attempts=2)

        assert result == ""


class TestSynthesizeWithRetry:
    """Tests for synthesize_with_retry — wrapper around synthesize_for_feature."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """When synthesize_for_feature returns a list on first call, it is returned."""
        criteria = ["File exists: src/foo.py", "pytest: tests/test_foo.py"]

        async def mock_synthesize(*, project_id, title, description, **kwargs):
            return criteria

        with patch("bob3.synth_retry.synthesize_with_retry.__wrapped__" if hasattr(synthesize_with_retry, "__wrapped__") else "bob3.spec_synthesizer.synthesize_for_feature", new=mock_synthesize):
            pass

        # Use the actual function with a mock via the import path
        with patch("bob3.synth_retry._synthesize_import", create=True):
            pass

        # Patch at the import level inside the function
        with patch("bob3.spec_synthesizer.synthesize_for_feature", new=mock_synthesize):
            result = await synthesize_with_retry(
                project_id="proj-1",
                title="test feature",
                description="test description",
                max_attempts=3,
            )

        assert result == criteria

    @pytest.mark.asyncio
    async def test_none_result_triggers_retry(self):
        """None result from synthesize_for_feature triggers retry."""
        calls = []

        async def mock_synthesize(**kwargs):
            calls.append(1)
            if len(calls) < 2:
                return None
            return ["File exists: src/foo.py"]

        with patch("bob3.spec_synthesizer.synthesize_for_feature", new=mock_synthesize):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await synthesize_with_retry(
                    project_id="proj-1",
                    title="retry feature",
                    description="triggers retry",
                    max_attempts=3,
                )

        assert result == ["File exists: src/foo.py"]
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_all_none_returns_none(self):
        """When all attempts return None, synthesize_with_retry returns None."""
        call_count = 0

        async def mock_synthesize(**kwargs):
            nonlocal call_count
            call_count += 1
            return None

        with patch("bob3.spec_synthesizer.synthesize_for_feature", new=mock_synthesize):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await synthesize_with_retry(
                    project_id="proj-1",
                    title="always none",
                    description="all attempts fail",
                    max_attempts=3,
                )

        assert result is None
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exception_in_synthesize_triggers_retry(self):
        """Exception raised by synthesize_for_feature triggers retry."""
        calls = []

        async def mock_synthesize(**kwargs):
            calls.append(1)
            if len(calls) < 2:
                raise RuntimeError("transient upstream error")
            return ["File exists: src/foo.py"]

        with patch("bob3.spec_synthesizer.synthesize_for_feature", new=mock_synthesize):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await synthesize_with_retry(
                    project_id="proj-1",
                    title="exception feature",
                    description="exception then success",
                    max_attempts=3,
                )

        assert result == ["File exists: src/foo.py"]
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_all_exceptions_returns_none(self):
        """When synthesize_for_feature always raises, returns None after exhausting retries."""
        call_count = 0

        async def mock_synthesize(**kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("persistent failure")

        with patch("bob3.spec_synthesizer.synthesize_for_feature", new=mock_synthesize):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await synthesize_with_retry(
                    project_id="proj-1",
                    title="always raises",
                    description="persistent failure",
                    max_attempts=3,
                )

        assert result is None
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_never_raises_to_caller(self):
        """synthesize_with_retry never propagates exceptions to the caller."""
        async def mock_synthesize(**kwargs):
            raise ValueError("should not propagate")

        with patch("bob3.spec_synthesizer.synthesize_for_feature", new=mock_synthesize):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Must not raise
                result = await synthesize_with_retry(
                    project_id="proj-1",
                    title="no raise",
                    description="test",
                    max_attempts=2,
                )

        assert result is None

    @pytest.mark.asyncio
    async def test_forwards_all_kwargs_to_synthesize(self):
        """All kwargs are forwarded to synthesize_for_feature correctly."""
        received = {}

        async def mock_synthesize(**kwargs):
            received.update(kwargs)
            return ["File exists: src/foo.py"]

        with patch("bob3.spec_synthesizer.synthesize_for_feature", new=mock_synthesize):
            from pathlib import Path
            ws = Path("/tmp/workspace")
            await synthesize_with_retry(
                project_id="proj-99",
                title="kwarg test",
                description="check forwarding",
                project_context="ctx",
                workspace=ws,
                retry_feedback="add boundary AC",
                max_attempts=1,
            )

        assert received["project_id"] == "proj-99"
        assert received["title"] == "kwarg test"
        assert received["description"] == "check forwarding"
        assert received["project_context"] == "ctx"
        assert received["workspace"] == ws
        assert received["retry_feedback"] == "add boundary AC"

    @pytest.mark.asyncio
    async def test_logs_retry_attempt_on_none(self, caplog):
        """None result is logged at WARNING level (observable, not silent)."""
        import logging
        call_count = 0

        async def mock_synthesize(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return None
            return ["File exists: src/foo.py"]

        with patch("bob3.spec_synthesizer.synthesize_for_feature", new=mock_synthesize):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with caplog.at_level(logging.WARNING, logger="bob3.synth_retry"):
                    await synthesize_with_retry(
                        project_id="proj-1",
                        title="log test",
                        description="log retry",
                        max_attempts=3,
                    )

        warning_logs = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_logs) >= 1

    @pytest.mark.asyncio
    async def test_max_attempts_one_calls_synthesize_once(self):
        """max_attempts=1 means exactly one synthesize_for_feature call, no retries."""
        call_count = 0

        async def mock_synthesize(**kwargs):
            nonlocal call_count
            call_count += 1
            return None

        with patch("bob3.spec_synthesizer.synthesize_for_feature", new=mock_synthesize):
            result = await synthesize_with_retry(
                project_id="proj-1",
                title="one attempt",
                description="one call only",
                max_attempts=1,
            )

        assert result is None
        assert call_count == 1


class TestModuleImports:
    """Verify module-level importability and __all__."""

    def test_module_imports_successfully(self):
        """bob3.synth_retry imports without error."""
        import bob3.synth_retry as m
        assert m is not None

    def test_synthesize_with_retry_is_callable(self):
        """synthesize_with_retry is defined and callable."""
        assert callable(synthesize_with_retry)

    def test_retry_with_backoff_is_callable(self):
        """retry_with_backoff is defined and callable."""
        assert callable(retry_with_backoff)

    def test_all_exports_present(self):
        """__all__ contains both public functions."""
        import bob3.synth_retry as m
        assert "synthesize_with_retry" in m.__all__
        assert "retry_with_backoff" in m.__all__
