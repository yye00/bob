"""Tests for bob3.run_loop MCP-transient classifier (F-R7-597 ordering fix).

AC: pytest: tests/test_run_loop_mcp_transient_classifier.py
AC: Function defined: bob3.run_loop.classify_mcp_transient_pre_hook
AC: integration: bob3.run_loop

Verifies the classifier-precedence hoist introduced by F-R7-607:
classify_mcp_transient_pre_hook must fire BEFORE the git-hook-rejection
demotion path and intercept when stderr contains any token from the
F-R7-597 token set.

Token set under test:
  - 'self signed certificate in certificate chain'
  - 'self-signed certificate'
  - 'MCP server' + 'Connection failed'    (compound)
  - 'HTTP Connection failed'
  - 'Streamable HTTP error'
  - 'Server rejected the configured Authorization header'
  - '403 Forbidden' (only when paired with 'MCP server')
"""

from __future__ import annotations

import pytest

from bob3.run_loop import (
    classify_mcp_transient_pre_hook,
    drain_mcp_transient_summary,
)


# ---------------------------------------------------------------------------
# Representative stderr blobs matching each token
# ---------------------------------------------------------------------------

_STDERR_SELF_SIGNED_CHAIN = (
    "Error: self signed certificate in certificate chain\n"
    'MCP server "plugin:github:github": Connection failed after 162ms\n'
)

_STDERR_SELF_SIGNED_HYPHEN = (
    "Transport error: self-signed certificate detected\n"
    "MCP server rejected connection\n"
)

_STDERR_MCP_CONNECTION_FAILED = (
    'MCP server "plugin:greptile:greptile": Connection failed after 235ms\n'
)

_STDERR_HTTP_CONNECTION_FAILED = (
    "Error: HTTP Connection failed after 500ms: connection refused\n"
)

_STDERR_STREAMABLE_HTTP = (
    'MCP server "plugin:foo:foo" Error: Streamable HTTP error: '
    "Error POSTing to endpoint\n"
)

_STDERR_AUTH_HEADER = (
    'MCP server "plugin:greptile:greptile" Server rejected the configured '
    "Authorization header (HTTP 403). Check that the token is valid.\n"
)

_STDERR_403_WITH_MCP = (
    'MCP server "plugin:greptile:greptile" '
    "403 Forbidden response from endpoint\n"
)

_STDERR_UNRELATED = (
    "pytest: 5 failed, 2 passed in 1.23s\n"
    "FAILED tests/test_foo.py::test_bar - AssertionError: expected 1, got 2\n"
)

_STDERR_403_WITHOUT_MCP = (
    "Error: HTTP 403 Forbidden — invalid API key\n"
    "Please renew your subscription.\n"
)

_STDERR_GIT_HOOK = (
    "pre-commit: check failed\n"
    "blocked by git hook rejection; needs human review\n"
)


class TestImportAndSignature:
    """classify_mcp_transient_pre_hook must be importable and callable."""

    def test_importable(self) -> None:
        from bob3.run_loop import classify_mcp_transient_pre_hook as fn  # noqa: F401
        assert callable(fn)

    def test_returns_dict_for_none_stderr(self) -> None:
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


class TestTokenMatching:
    """Each token in the F-R7-597 set must trigger intercept=True."""

    def test_self_signed_certificate_chain(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=0
        )
        assert result["intercept"] is True

    def test_self_signed_certificate_hyphen(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_SELF_SIGNED_HYPHEN, retry_count=0
        )
        assert result["intercept"] is True

    def test_mcp_server_connection_failed_compound(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_MCP_CONNECTION_FAILED, retry_count=0
        )
        assert result["intercept"] is True

    def test_http_connection_failed(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_HTTP_CONNECTION_FAILED, retry_count=0
        )
        assert result["intercept"] is True

    def test_streamable_http_error(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_STREAMABLE_HTTP, retry_count=0
        )
        assert result["intercept"] is True

    def test_server_rejected_authorization_header(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_AUTH_HEADER, retry_count=0
        )
        assert result["intercept"] is True

    def test_403_forbidden_with_mcp_server(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_403_WITH_MCP, retry_count=0
        )
        assert result["intercept"] is True


class TestNonMatchingInputs:
    """Non-MCP errors and partial compound tokens must not trigger intercept."""

    def test_unrelated_errors_do_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_UNRELATED, retry_count=0
        )
        assert result["intercept"] is False

    def test_403_without_mcp_server_does_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_403_WITHOUT_MCP, retry_count=0
        )
        assert result["intercept"] is False

    def test_git_hook_rejection_alone_does_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_GIT_HOOK, retry_count=0
        )
        assert result["intercept"] is False

    def test_none_stderr_does_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert result["intercept"] is False

    def test_empty_stderr_does_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr="", retry_count=0)
        assert result["intercept"] is False


class TestRetryCap:
    """Intercept must be suppressed when retry_count >= 5 (cap exhausted)."""

    def test_retry_count_4_below_cap_fires(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=4
        )
        assert result["intercept"] is True

    def test_retry_count_5_at_cap_does_not_fire(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=5
        )
        assert result["intercept"] is False

    def test_retry_count_large_does_not_fire(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=100
        )
        assert result["intercept"] is False


class TestEventAndMatchedToken:
    """On intercept, event must be EVALUATOR_MCP_TRANSIENT_PRE_HOOK and matched_token non-None."""

    def test_event_name_on_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=0
        )
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"

    def test_matched_token_non_none_on_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_SELF_SIGNED_CHAIN, retry_count=0
        )
        assert result["matched_token"] is not None

    def test_event_empty_when_no_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_UNRELATED, retry_count=0
        )
        assert result["event"] == ""

    def test_matched_token_none_when_no_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_UNRELATED, retry_count=0
        )
        assert result["matched_token"] is None

    def test_feature_id_echoed_in_result(self) -> None:
        fid = "test-feature-uuid-1234"
        result = classify_mcp_transient_pre_hook(
            stderr=_STDERR_SELF_SIGNED_CHAIN,
            retry_count=0,
            feature_id=fid,
        )
        assert result["feature_id"] == fid


class TestDrainMcpTransientSummary:
    """drain_mcp_transient_summary must return PRE_HOOK_TRANSIENT_SUMMARY telemetry."""

    def test_returns_dict(self) -> None:
        result = drain_mcp_transient_summary(intercepted=3)
        assert isinstance(result, dict)

    def test_event_name(self) -> None:
        result = drain_mcp_transient_summary(intercepted=3)
        assert result["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"

    def test_intercepted_count_preserved(self) -> None:
        result = drain_mcp_transient_summary(intercepted=7)
        assert result["intercepted"] == 7

    def test_zero_intercepted(self) -> None:
        result = drain_mcp_transient_summary(intercepted=0)
        assert result["intercepted"] == 0

    def test_importable(self) -> None:
        from bob3.run_loop import drain_mcp_transient_summary as fn  # noqa: F401
        assert callable(fn)
