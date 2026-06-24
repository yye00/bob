"""Tests for bob.run_loop MCP-transient classifier — F-R7-597 ordering fix.

AC: pytest: tests/test_f_r7_597_mcp_transient_classifier.py
AC: Function defined: bob.run_loop.classify_mcp_transient_before_hook
AC: integration: bob.run_loop

Verifies the classifier-precedence hoist (F-R7-607):
classify_mcp_transient_before_hook must fire BEFORE the git-hook-rejection
demotion path and intercept when stderr contains any token from the
F-R7-597 token set.

Token set:
  - 'self signed certificate in certificate chain'
  - 'self-signed certificate'
  - 'MCP server' + 'Connection failed'    (compound)
  - 'HTTP Connection failed'
  - 'Streamable HTTP error'
  - 'Server rejected the configured Authorization header'
  - 'MCP server' + '403 Forbidden'        (compound)
"""

from __future__ import annotations

import pytest

from bob.run_loop import (
    classify_mcp_transient_before_hook,
    drain_mcp_transient_summary,
)


# ---------------------------------------------------------------------------
# Smoke test — function is importable and callable
# ---------------------------------------------------------------------------

def test_classify_mcp_transient_before_hook_importable() -> None:
    """AC: Function defined: bob.run_loop.classify_mcp_transient_before_hook."""
    assert callable(classify_mcp_transient_before_hook)


# ---------------------------------------------------------------------------
# Token matching — each F-R7-597 token fires intercept=True
# ---------------------------------------------------------------------------

def test_self_signed_certificate_chain_intercepts() -> None:
    result = classify_mcp_transient_before_hook(
        stderr="Error: self signed certificate in certificate chain",
        retry_count=0,
    )
    assert result["intercept"] is True
    assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"
    assert result["matched_token"] is not None


def test_self_signed_certificate_hyphen_intercepts() -> None:
    result = classify_mcp_transient_before_hook(
        stderr="Transport error: self-signed certificate detected",
        retry_count=0,
    )
    assert result["intercept"] is True
    assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"


def test_mcp_server_connection_failed_compound_intercepts() -> None:
    result = classify_mcp_transient_before_hook(
        stderr='MCP server "plugin:github:github": Connection failed after 162ms',
        retry_count=0,
    )
    assert result["intercept"] is True
    assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"


def test_http_connection_failed_intercepts() -> None:
    result = classify_mcp_transient_before_hook(
        stderr="HTTP Connection failed: timeout after 30s",
        retry_count=0,
    )
    assert result["intercept"] is True
    assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"


def test_streamable_http_error_intercepts() -> None:
    result = classify_mcp_transient_before_hook(
        stderr="Streamable HTTP error: unexpected EOF",
        retry_count=0,
    )
    assert result["intercept"] is True
    assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"


def test_server_rejected_authorization_header_intercepts() -> None:
    result = classify_mcp_transient_before_hook(
        stderr="Server rejected the configured Authorization header",
        retry_count=0,
    )
    assert result["intercept"] is True
    assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"


def test_mcp_server_403_forbidden_compound_intercepts() -> None:
    result = classify_mcp_transient_before_hook(
        stderr='MCP server returned 403 Forbidden',
        retry_count=0,
    )
    assert result["intercept"] is True
    assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"


# ---------------------------------------------------------------------------
# Retry cap — at retry_count=5 the cap is exhausted, no intercept
# ---------------------------------------------------------------------------

def test_retry_cap_exhausted_does_not_intercept() -> None:
    result = classify_mcp_transient_before_hook(
        stderr="self signed certificate in certificate chain",
        retry_count=5,
    )
    assert result["intercept"] is False


def test_retry_count_4_below_cap_intercepts() -> None:
    result = classify_mcp_transient_before_hook(
        stderr="self signed certificate in certificate chain",
        retry_count=4,
    )
    assert result["intercept"] is True


# ---------------------------------------------------------------------------
# Non-matching stderr returns intercept=False
# ---------------------------------------------------------------------------

def test_unrelated_error_does_not_intercept() -> None:
    result = classify_mcp_transient_before_hook(
        stderr="ImportError: No module named 'requests'",
        retry_count=0,
    )
    assert result["intercept"] is False
    assert result["matched_token"] is None


def test_none_stderr_does_not_intercept() -> None:
    result = classify_mcp_transient_before_hook(
        stderr=None,
        retry_count=0,
    )
    assert result["intercept"] is False


def test_empty_stderr_does_not_intercept() -> None:
    result = classify_mcp_transient_before_hook(
        stderr="",
        retry_count=0,
    )
    assert result["intercept"] is False


# ---------------------------------------------------------------------------
# feature_id is echoed in result
# ---------------------------------------------------------------------------

def test_feature_id_echoed_when_intercept() -> None:
    fid = "e7175c23-de50-46d5-b20a-dae98e35b33b"
    result = classify_mcp_transient_before_hook(
        stderr="Streamable HTTP error",
        retry_count=0,
        feature_id=fid,
    )
    assert result["intercept"] is True
    assert result["feature_id"] == fid


def test_feature_id_echoed_when_no_intercept() -> None:
    fid = "e7175c23-de50-46d5-b20a-dae98e35b33b"
    result = classify_mcp_transient_before_hook(
        stderr="unrelated error",
        retry_count=0,
        feature_id=fid,
    )
    assert result["intercept"] is False
    assert result["feature_id"] == fid


# ---------------------------------------------------------------------------
# drain_mcp_transient_summary telemetry
# ---------------------------------------------------------------------------

def test_drain_summary_returns_correct_event() -> None:
    result = drain_mcp_transient_summary(intercepted=3)
    assert result["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"
    assert result["intercepted"] == 3


def test_drain_summary_zero_count() -> None:
    result = drain_mcp_transient_summary(intercepted=0)
    assert result["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"
    assert result["intercepted"] == 0


# ---------------------------------------------------------------------------
# Compound token — partial match must NOT intercept
# ---------------------------------------------------------------------------

def test_partial_compound_mcp_connection_no_fire() -> None:
    result = classify_mcp_transient_before_hook(
        stderr="MCP server started successfully",
        retry_count=0,
    )
    assert result["intercept"] is False


def test_partial_compound_403_no_mcp_no_fire() -> None:
    result = classify_mcp_transient_before_hook(
        stderr="403 Forbidden from nginx reverse proxy",
        retry_count=0,
    )
    assert result["intercept"] is False
