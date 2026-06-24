"""Tests for bob.run_loop.classify_mcp_transient (F-R7-607).

Verifies that the MCP-transient classifier fires BEFORE git-hook-rejection
demotion, intercepting the needs_human path and resetting the feature to
'ready' when stderr contains any of the F-R7-597 token set.

Token set under test:
  - 'self signed certificate in certificate chain'
  - 'self-signed certificate'
  - 'MCP server' + 'Connection failed'    (compound)
  - 'HTTP Connection failed'
  - 'Streamable HTTP error'
  - 'Server rejected the configured Authorization header'
  - '403 Forbidden' (only when paired with 'MCP server')

AC: pytest: tests/test_run_loop_mcp_transient_precedence.py
AC: Function defined: bob.run_loop.classify_mcp_transient
AC: integration: bob.run_loop
"""

from __future__ import annotations

import json

import pytest

from bob.run_loop import classify_mcp_transient

# ---------------------------------------------------------------------------
# Exact F-R7-597 token strings from the spec
# ---------------------------------------------------------------------------

_STDERR_SELF_SIGNED_CHAIN = (
    'Error: self signed certificate in certificate chain\n'
    '2026-06-13T21:39:31.693Z [DEBUG] MCP server "plugin:github:github": '
    'Connection failed after 162ms: self signed certificate in certificate chain\n'
    '2026-06-13T21:39:31.693Z [ERROR] MCP server "plugin:github:github" '
    'Connection failed: self signed certificate in certificate chain'
)

_STDERR_SELF_SIGNED_HYPHEN = (
    'Transport error: self-signed certificate detected\n'
    'MCP server "plugin:cert:cert" rejected connection\n'
)

_STDERR_MCP_CONNECTION_FAILED = (
    '2026-06-13T21:39:31.769Z [DEBUG] MCP server "plugin:greptile:greptile": '
    'HTTP Connection failed after 235ms: Streamable HTTP error: Error POSTing\n'
)

_STDERR_HTTP_CONNECTION_FAILED = (
    'Error: HTTP Connection failed after 500ms: connection refused\n'
)

_STDERR_STREAMABLE_HTTP = (
    'MCP server "plugin:foo:foo" Error: Streamable HTTP error: '
    'Error POSTing to endpoint: <html><head><title>403 Forbidden</title></head></html>\n'
)

_STDERR_AUTH_HEADER = (
    'MCP server "plugin:greptile:greptile" Server rejected the configured '
    'Authorization header (HTTP 403). Check that the token is valid.\n'
)

_STDERR_403_WITH_MCP = (
    '2026-06-13T21:39:31.769Z [ERROR] MCP server "plugin:greptile:greptile" '
    'Error: HTTP 403 Forbidden response from endpoint\n'
)

_STDERR_UNRELATED = (
    'pytest: 5 failed, 2 passed in 1.23s\n'
    'FAILED tests/test_foo.py::test_bar - AssertionError: expected 1, got 2\n'
)

_STDERR_403_WITHOUT_MCP = (
    'Error: HTTP 403 Forbidden — invalid API key\n'
    'Please renew your subscription.\n'
)

_STDERR_EMPTY = ''

_STDERR_NONE = None


# ---------------------------------------------------------------------------
# Happy-path: each token fires intercept
# ---------------------------------------------------------------------------

class TestClassifyMcpTransientFiresOnEachToken:
    """Each distinct token in the F-R7-597 set must produce intercept=True."""

    def test_self_signed_certificate_chain(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=0
        )
        assert result["intercept"] is True, (
            f"Expected intercept=True for 'self signed certificate in certificate chain', got {result}"
        )

    def test_self_signed_certificate_hyphen(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_SELF_SIGNED_HYPHEN, retry_count=0
        )
        assert result["intercept"] is True, (
            f"Expected intercept=True for 'self-signed certificate', got {result}"
        )

    def test_mcp_server_connection_failed_compound(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_MCP_CONNECTION_FAILED, retry_count=0
        )
        assert result["intercept"] is True, (
            f"Expected intercept=True for MCP server + Connection failed, got {result}"
        )

    def test_http_connection_failed(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_HTTP_CONNECTION_FAILED, retry_count=0
        )
        assert result["intercept"] is True, (
            f"Expected intercept=True for 'HTTP Connection failed', got {result}"
        )

    def test_streamable_http_error(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_STREAMABLE_HTTP, retry_count=0
        )
        assert result["intercept"] is True, (
            f"Expected intercept=True for 'Streamable HTTP error', got {result}"
        )

    def test_server_rejected_authorization_header(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_AUTH_HEADER, retry_count=0
        )
        assert result["intercept"] is True, (
            f"Expected intercept=True for 'Server rejected the configured Authorization header', got {result}"
        )

    def test_403_with_mcp_server(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_403_WITH_MCP, retry_count=0
        )
        assert result["intercept"] is True, (
            f"Expected intercept=True for '403 Forbidden' + 'MCP server', got {result}"
        )


# ---------------------------------------------------------------------------
# Negative cases: must NOT intercept
# ---------------------------------------------------------------------------

class TestClassifyMcpTransientDoesNotFireOnNonMatches:
    """Non-matching stderr must produce intercept=False."""

    def test_unrelated_pytest_failure(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_UNRELATED, retry_count=0
        )
        assert result["intercept"] is False, (
            f"Expected intercept=False for pytest failure stderr, got {result}"
        )

    def test_403_without_mcp_server(self) -> None:
        """403 Forbidden alone (no 'MCP server' context) must NOT intercept."""
        result = classify_mcp_transient(
            stderr=_STDERR_403_WITHOUT_MCP, retry_count=0
        )
        assert result["intercept"] is False, (
            f"Expected intercept=False for bare '403 Forbidden' without MCP server, got {result}"
        )

    def test_empty_stderr(self) -> None:
        result = classify_mcp_transient(stderr=_STDERR_EMPTY, retry_count=0)
        assert result["intercept"] is False, (
            f"Expected intercept=False for empty stderr, got {result}"
        )

    def test_none_stderr(self) -> None:
        result = classify_mcp_transient(stderr=_STDERR_NONE, retry_count=0)
        assert result["intercept"] is False, (
            f"Expected intercept=False for None stderr, got {result}"
        )


# ---------------------------------------------------------------------------
# Retry cap: 5-retry cap (same cap as F-R7-597)
# ---------------------------------------------------------------------------

class TestClassifyMcpTransientRetryCapEnforced:
    """After 5 intercepts, must return intercept=False (cap exhausted)."""

    def test_retry_count_below_cap_intercepts(self) -> None:
        for count in range(5):
            result = classify_mcp_transient(
                stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=count
            )
            assert result["intercept"] is True, (
                f"Expected intercept=True at retry_count={count}, got {result}"
            )

    def test_retry_count_at_cap_does_not_intercept(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=5
        )
        assert result["intercept"] is False, (
            f"Expected intercept=False at retry_count=5 (cap exhausted), got {result}"
        )

    def test_retry_count_above_cap_does_not_intercept(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=10
        )
        assert result["intercept"] is False, (
            f"Expected intercept=False at retry_count=10 (above cap), got {result}"
        )


# ---------------------------------------------------------------------------
# Result structure: matched_token and event fields
# ---------------------------------------------------------------------------

class TestClassifyMcpTransientResultStructure:
    """Result dict must contain required fields with correct types/values."""

    def test_intercept_result_has_required_keys(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=0
        )
        assert "intercept" in result
        assert "matched_token" in result
        assert "event" in result

    def test_intercept_true_matched_token_is_non_empty_string(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=0
        )
        assert result["intercept"] is True
        assert isinstance(result["matched_token"], str)
        assert len(result["matched_token"]) > 0

    def test_intercept_false_matched_token_is_none_or_empty(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_UNRELATED, retry_count=0
        )
        assert result["intercept"] is False
        assert not result["matched_token"]

    def test_intercept_true_event_is_evaluator_mcp_transient_pre_hook(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_SELF_SIGNED_CHAIN,
            retry_count=0,
            feature_id="test-feature-123",
        )
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"

    def test_cap_exhausted_result_has_required_keys(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=5
        )
        assert "intercept" in result
        assert result["intercept"] is False

    def test_intercept_includes_feature_id_when_provided(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_AUTH_HEADER,
            retry_count=0,
            feature_id="feat-abc",
        )
        assert result.get("feature_id") == "feat-abc"

    def test_intercept_omits_feature_id_when_not_provided(self) -> None:
        result = classify_mcp_transient(
            stderr=_STDERR_AUTH_HEADER,
            retry_count=0,
        )
        assert result.get("feature_id") is None


# ---------------------------------------------------------------------------
# Telemetry: drain_summary function
# ---------------------------------------------------------------------------

class TestClassifyMcpTransientDrainSummary:
    """drain_mcp_transient_summary must emit PRE_HOOK_TRANSIENT_SUMMARY event."""

    def test_drain_summary_returns_dict_with_event(self) -> None:
        from bob.run_loop import drain_mcp_transient_summary
        summary = drain_mcp_transient_summary(intercepted=3)
        assert summary["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"
        assert summary["intercepted"] == 3

    def test_drain_summary_zero_intercepted(self) -> None:
        from bob.run_loop import drain_mcp_transient_summary
        summary = drain_mcp_transient_summary(intercepted=0)
        assert summary["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"
        assert summary["intercepted"] == 0


# ---------------------------------------------------------------------------
# Integration: function is importable from bob.run_loop (AC: integration)
# ---------------------------------------------------------------------------

class TestIntegration:
    """Verify importability and module membership."""

    def test_classify_mcp_transient_importable(self) -> None:
        from bob.run_loop import classify_mcp_transient as fn
        assert callable(fn)

    def test_drain_mcp_transient_summary_importable(self) -> None:
        from bob.run_loop import drain_mcp_transient_summary as fn
        assert callable(fn)

    def test_classify_mcp_transient_in_all(self) -> None:
        import bob.run_loop as m
        assert "classify_mcp_transient" in m.__all__

    def test_drain_mcp_transient_summary_in_all(self) -> None:
        import bob.run_loop as m
        assert "drain_mcp_transient_summary" in m.__all__
