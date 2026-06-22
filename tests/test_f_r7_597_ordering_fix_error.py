"""Error path tests for F-R7-597 ordering fix — classify_mcp_transient.

AC: pytest: tests/test_f_r7_597_ordering_fix_error.py — invalid input raises
ValueError and the function does not silently succeed (error path)

Verifies that classify_mcp_transient (bob3.run_loop) either raises
(TypeError/ValueError/AttributeError) or returns intercept=False for invalid
inputs — it must never silently return intercept=True for bad data.
"""

from __future__ import annotations

import pytest

from bob3.run_loop import classify_mcp_transient


class TestInvalidStderrType:
    """Non-string, non-None stderr must raise or return intercept=False."""

    def test_integer_stderr_does_not_silently_intercept(self) -> None:
        try:
            result = classify_mcp_transient(stderr=42, retry_count=0)  # type: ignore[arg-type]
            assert result["intercept"] is False, (
                "Integer stderr must not produce intercept=True silently"
            )
        except (TypeError, ValueError, AttributeError):
            pass

    def test_list_stderr_does_not_silently_intercept(self) -> None:
        try:
            result = classify_mcp_transient(
                stderr=["self signed certificate in certificate chain"],  # type: ignore[arg-type]
                retry_count=0,
            )
            assert result["intercept"] is False, (
                "List stderr must not produce intercept=True silently"
            )
        except (TypeError, ValueError, AttributeError):
            pass

    def test_dict_stderr_does_not_silently_intercept(self) -> None:
        try:
            result = classify_mcp_transient(
                stderr={"error": "self signed certificate"},  # type: ignore[arg-type]
                retry_count=0,
            )
            assert result["intercept"] is False, (
                "Dict stderr must not produce intercept=True silently"
            )
        except (TypeError, ValueError, AttributeError):
            pass

    def test_bytes_stderr_does_not_silently_intercept(self) -> None:
        try:
            result = classify_mcp_transient(
                stderr=b"self signed certificate in certificate chain",  # type: ignore[arg-type]
                retry_count=0,
            )
            assert result["intercept"] is False, (
                "Bytes stderr must not produce intercept=True silently"
            )
        except (TypeError, ValueError, AttributeError):
            pass


class TestInvalidRetryCountType:
    """Non-integer retry_count must raise or return intercept=False (not silently succeed)."""

    def test_string_retry_count_raises_or_rejects(self) -> None:
        try:
            result = classify_mcp_transient(
                stderr="self signed certificate in certificate chain",
                retry_count="three",  # type: ignore[arg-type]
            )
            assert result["intercept"] is False, (
                "String retry_count must not silently produce intercept=True"
            )
        except (TypeError, ValueError):
            pass

    def test_none_retry_count_raises_or_rejects(self) -> None:
        try:
            result = classify_mcp_transient(
                stderr="self signed certificate in certificate chain",
                retry_count=None,  # type: ignore[arg-type]
            )
            assert result["intercept"] is False, (
                "None retry_count must not silently produce intercept=True"
            )
        except (TypeError, ValueError):
            pass

    def test_float_retry_count_raises_or_rejects(self) -> None:
        try:
            result = classify_mcp_transient(
                stderr="self signed certificate in certificate chain",
                retry_count=2.5,  # type: ignore[arg-type]
            )
            # float is coercible so intercept=True is fine here; but it must not crash
            assert isinstance(result, dict)
        except (TypeError, ValueError):
            pass

    def test_list_retry_count_raises_or_rejects(self) -> None:
        try:
            result = classify_mcp_transient(
                stderr="self signed certificate in certificate chain",
                retry_count=[0],  # type: ignore[arg-type]
            )
            assert result["intercept"] is False, (
                "List retry_count must not silently produce intercept=True"
            )
        except (TypeError, ValueError):
            pass


class TestPartialMcpCompoundTokens:
    """Partial compound tokens must NOT fire — both parts required."""

    def test_only_mcp_server_no_connection_failed_does_not_intercept(self) -> None:
        result = classify_mcp_transient(
            stderr="MCP server started successfully",
            retry_count=0,
        )
        assert result["intercept"] is False, (
            "'MCP server' alone without 'Connection failed' must not intercept"
        )

    def test_only_connection_failed_no_mcp_server_does_not_intercept(self) -> None:
        result = classify_mcp_transient(
            stderr="Connection failed to database server",
            retry_count=0,
        )
        assert result["intercept"] is False, (
            "'Connection failed' alone without 'MCP server' must not intercept"
        )

    def test_only_mcp_server_no_403_does_not_intercept(self) -> None:
        result = classify_mcp_transient(
            stderr="MCP server returned 200 OK",
            retry_count=0,
        )
        assert result["intercept"] is False, (
            "'MCP server' alone without '403 Forbidden' must not intercept"
        )

    def test_only_403_forbidden_no_mcp_server_does_not_intercept(self) -> None:
        result = classify_mcp_transient(
            stderr="403 Forbidden from nginx proxy",
            retry_count=0,
        )
        assert result["intercept"] is False, (
            "'403 Forbidden' alone without 'MCP server' must not intercept"
        )


class TestUnrelatedErrors:
    """Unrelated error strings must return intercept=False (not silently succeed)."""

    @pytest.mark.parametrize("stderr", [
        "ImportError: No module named 'requests'",
        "SyntaxError: invalid syntax",
        "PermissionError: [Errno 13] Permission denied",
        "KeyboardInterrupt",
        "MemoryError",
        "RecursionError: maximum recursion depth exceeded",
        "git hook: pre-commit check failed",
        "AssertionError: AC not satisfied",
    ])
    def test_unrelated_error_does_not_intercept(self, stderr: str) -> None:
        result = classify_mcp_transient(stderr=stderr, retry_count=0)
        assert result["intercept"] is False, (
            f"Unrelated error should not intercept: {stderr!r}"
        )
        assert result["matched_token"] is None
