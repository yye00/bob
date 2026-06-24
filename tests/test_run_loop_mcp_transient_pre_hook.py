"""Tests for bob.run_loop.classify_mcp_transient_pre_hook (F-R7-607).

Verifies the classifier-precedence hoist: classify_mcp_transient_pre_hook
must fire BEFORE the git-hook-rejection demotion path and intercept when
stderr contains any token from the F-R7-597 token set.

Token set under test:
  - 'self signed certificate in certificate chain'
  - 'self-signed certificate'
  - 'MCP server' + 'Connection failed'    (compound)
  - 'HTTP Connection failed'
  - 'Streamable HTTP error'
  - 'Server rejected the configured Authorization header'
  - '403 Forbidden' (only when paired with 'MCP server')

AC: pytest: tests/test_run_loop_mcp_transient_pre_hook.py
AC: Function defined: bob.run_loop.classify_mcp_transient_pre_hook
AC: integration: bob.run_loop
"""

from __future__ import annotations

import pytest

from bob.run_loop import classify_mcp_transient_pre_hook, drain_mcp_transient_summary


# ---------------------------------------------------------------------------
# Sample stderr strings matching the F-R7-597 token set
# ---------------------------------------------------------------------------

_STDERR_SELF_SIGNED_CHAIN = (
    'Error: self signed certificate in certificate chain\n'
    '2026-06-13T21:39:31.693Z [DEBUG] MCP server "plugin:github:github": '
    'Connection failed after 162ms: self signed certificate in certificate chain\n'
)

_STDERR_SELF_SIGNED_HYPHEN = (
    'Transport error: self-signed certificate detected\n'
    'MCP server rejected connection\n'
)

_STDERR_MCP_CONNECTION_FAILED = (
    '2026-06-13T21:39:31.769Z [DEBUG] MCP server "plugin:greptile:greptile": '
    'Connection failed after 235ms: timeout\n'
)

_STDERR_HTTP_CONNECTION_FAILED = (
    'Error: HTTP Connection failed after 500ms: connection refused\n'
)

_STDERR_STREAMABLE_HTTP = (
    'MCP server "plugin:foo:foo" Error: Streamable HTTP error: '
    'Error POSTing to endpoint\n'
)

_STDERR_AUTH_HEADER = (
    'MCP server "plugin:greptile:greptile" Server rejected the configured '
    'Authorization header (HTTP 403). Check that the token is valid.\n'
)

_STDERR_403_WITH_MCP = (
    '2026-06-13T21:39:31.769Z [ERROR] MCP server "plugin:greptile:greptile" '
    '403 Forbidden response from endpoint\n'
)

_STDERR_UNRELATED = (
    'pytest: 5 failed, 2 passed in 1.23s\n'
    'FAILED tests/test_foo.py::test_bar - AssertionError: expected 1, got 2\n'
)

_STDERR_403_WITHOUT_MCP = (
    'Error: HTTP 403 Forbidden — invalid API key\n'
    'Please renew your subscription.\n'
)

_STDERR_GIT_HOOK_REJECTION = (
    'pre-commit: check failed\n'
    'blocked by git hook rejection; needs human review\n'
)


# ---------------------------------------------------------------------------
# Basic function contract
# ---------------------------------------------------------------------------

class TestFunctionExists:
    """classify_mcp_transient_pre_hook must be importable and callable."""

    def test_function_importable(self) -> None:
        from bob.run_loop import classify_mcp_transient_pre_hook as fn  # noqa: F401
        assert callable(fn)

    def test_returns_dict(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert isinstance(result, dict)

    def test_result_has_intercept_key(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert "intercept" in result

    def test_result_has_matched_token_key(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert "matched_token" in result

    def test_result_has_event_key(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert "event" in result


# ---------------------------------------------------------------------------
# Positive cases: each token in the F-R7-597 set fires intercept=True
# ---------------------------------------------------------------------------

class TestPositiveInterception:
    """Each token in the MCP-transient set must trigger intercept=True."""

    def test_self_signed_certificate_chain(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_SELF_SIGNED_CHAIN,
            retry_count=0,
        )
        assert result["intercept"] is True
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"
        assert result["matched_token"] is not None

    def test_self_signed_hyphen(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_SELF_SIGNED_HYPHEN,
            retry_count=0,
        )
        assert result["intercept"] is True
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"

    def test_mcp_server_connection_failed_compound(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_MCP_CONNECTION_FAILED,
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_http_connection_failed(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_HTTP_CONNECTION_FAILED,
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_streamable_http_error(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_STREAMABLE_HTTP,
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_server_rejected_auth_header(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_AUTH_HEADER,
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_403_forbidden_with_mcp_server(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_403_WITH_MCP,
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_direct_self_signed_cert_token(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=0,
        )
        assert result["intercept"] is True


# ---------------------------------------------------------------------------
# Negative cases: non-matching stderr must NOT intercept
# ---------------------------------------------------------------------------

class TestNegativeNoInterception:
    """Non-MCP-transient stderr must not trigger interception."""

    def test_unrelated_pytest_output(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_UNRELATED,
            retry_count=0,
        )
        assert result["intercept"] is False
        assert result["matched_token"] is None

    def test_403_without_mcp_server(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_403_WITHOUT_MCP,
            retry_count=0,
        )
        assert result["intercept"] is False

    def test_git_hook_rejection_only(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_GIT_HOOK_REJECTION,
            retry_count=0,
        )
        assert result["intercept"] is False

    def test_none_stderr(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert result["intercept"] is False

    def test_empty_stderr(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr="", retry_count=0)
        assert result["intercept"] is False

    def test_only_mcp_server_no_connection_failed(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="MCP server started successfully",
            retry_count=0,
        )
        assert result["intercept"] is False

    def test_only_connection_failed_no_mcp_server(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="Connection failed to database server",
            retry_count=0,
        )
        assert result["intercept"] is False

    @pytest.mark.parametrize("stderr", [
        "ImportError: No module named 'requests'",
        "SyntaxError: invalid syntax",
        "AssertionError: AC not satisfied",
        "git hook: pre-commit check failed",
        "PermissionError: [Errno 13] Permission denied",
    ])
    def test_unrelated_errors_do_not_intercept(self, stderr: str) -> None:
        result = classify_mcp_transient_pre_hook(stderr=stderr, retry_count=0)
        assert result["intercept"] is False


# ---------------------------------------------------------------------------
# Retry cap: at 5 the cap is exhausted
# ---------------------------------------------------------------------------

class TestRetryCap:
    """Retry cap must be respected: at 5 interceptions, stop firing."""

    def test_retry_count_0_fires(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="Streamable HTTP error occurred",
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_retry_count_4_fires(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="Streamable HTTP error occurred",
            retry_count=4,
        )
        assert result["intercept"] is True

    def test_retry_count_5_does_not_fire(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert result["intercept"] is False

    def test_retry_count_100_does_not_fire(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=100,
        )
        assert result["intercept"] is False


# ---------------------------------------------------------------------------
# Event field correctness
# ---------------------------------------------------------------------------

class TestEventField:
    """Event field must be 'EVALUATOR_MCP_TRANSIENT_PRE_HOOK' on intercept, else ''."""

    def test_event_set_when_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=0,
        )
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"

    def test_event_empty_when_no_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert result["event"] == ""

    def test_event_empty_when_cap_exceeded(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert result["event"] == ""


# ---------------------------------------------------------------------------
# feature_id passthrough
# ---------------------------------------------------------------------------

class TestFeatureIdPassthrough:
    """feature_id must be echoed in the result dict."""

    def test_feature_id_echoed_when_intercept(self) -> None:
        fid = "test-feature-uuid-1234"
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=0,
            feature_id=fid,
        )
        assert result.get("feature_id") == fid

    def test_feature_id_none_when_omitted(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert result.get("feature_id") is None

    def test_feature_id_echoed_when_no_intercept(self) -> None:
        fid = "no-match-feature-uuid"
        result = classify_mcp_transient_pre_hook(
            stderr="unrelated error",
            retry_count=0,
            feature_id=fid,
        )
        assert result.get("feature_id") == fid


# ---------------------------------------------------------------------------
# Case insensitivity
# ---------------------------------------------------------------------------

class TestCaseInsensitivity:
    """Token matching must be case-insensitive."""

    def test_uppercase_self_signed(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="SELF SIGNED CERTIFICATE IN CERTIFICATE CHAIN",
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_mixed_case_streamable(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="Streamable HTTP Error occurred",
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_lowercase_http_connection_failed(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="http connection failed after 100ms",
            retry_count=0,
        )
        assert result["intercept"] is True


# ---------------------------------------------------------------------------
# Drain summary telemetry
# ---------------------------------------------------------------------------

class TestDrainSummaryTelemetry:
    """drain_mcp_transient_summary must emit PRE_HOOK_TRANSIENT_SUMMARY events."""

    def test_drain_returns_dict(self) -> None:
        result = drain_mcp_transient_summary(intercepted=0)
        assert isinstance(result, dict)

    def test_drain_event_key(self) -> None:
        result = drain_mcp_transient_summary(intercepted=3)
        assert result["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"

    def test_drain_intercepted_count(self) -> None:
        result = drain_mcp_transient_summary(intercepted=7)
        assert result["intercepted"] == 7

    def test_drain_zero_intercepted(self) -> None:
        result = drain_mcp_transient_summary(intercepted=0)
        assert result["intercepted"] == 0
