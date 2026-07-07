"""Tests for the F-R7-597/F-R7-607 pre-hook MCP-transient classifier.

AC: Function defined: bob.run_loop.classify_mcp_transient_pre_hook
AC: pytest: tests/test_f_r7_597_pre_hook_classifier.py
AC: integration: bob.run_loop

The classifier-precedence hoist: classify_mcp_transient_pre_hook must run
BEFORE the "blocked by git hook rejection; needs human review" demotion path
and intercept when captured evaluator stderr contains any token from the
F-R7-597 MCP-transient token set.

Token set (case-insensitive):
  - 'self signed certificate in certificate chain'
  - 'self-signed certificate'
  - 'MCP server' + 'Connection failed'    (compound — both required)
  - 'HTTP Connection failed'
  - 'Streamable HTTP error'
  - 'Server rejected the configured Authorization header'
  - 'MCP server' + '403 Forbidden'        (compound — both required)

Subject to a 5-retry cap: at retry_count >= 5 the intercept is exhausted.
"""

from __future__ import annotations

import pytest

from bob.run_loop import (
    classify_mcp_transient_pre_hook,
    drain_mcp_transient_summary,
)


class TestFunctionDefined:
    """AC: Function defined: bob.run_loop.classify_mcp_transient_pre_hook."""

    def test_is_callable(self) -> None:
        assert callable(classify_mcp_transient_pre_hook)

    def test_importable_from_run_loop(self) -> None:
        from bob.run_loop import classify_mcp_transient_pre_hook as fn  # noqa: F401

        assert callable(fn)

    def test_returns_dict(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert isinstance(result, dict)


class TestTokenMatching:
    """Every token in the F-R7-597 set must trigger interception."""

    @pytest.mark.parametrize("stderr", [
        "self signed certificate in certificate chain",
        "TLS: self-signed certificate rejected",
        "HTTP Connection failed while reaching endpoint",
        "Streamable HTTP error during evaluator run",
        "Server rejected the configured Authorization header",
    ])
    def test_single_token_intercepts(self, stderr: str) -> None:
        result = classify_mcp_transient_pre_hook(stderr=stderr, retry_count=0)
        assert result["intercept"] is True
        assert result["matched_token"] is not None
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"

    def test_compound_mcp_connection_failed_intercepts(self) -> None:
        stderr = "MCP server error: Connection failed after retry"
        result = classify_mcp_transient_pre_hook(stderr=stderr, retry_count=0)
        assert result["intercept"] is True
        assert result["matched_token"] is not None

    def test_compound_mcp_403_intercepts(self) -> None:
        stderr = "MCP server responded 403 Forbidden to the request"
        result = classify_mcp_transient_pre_hook(stderr=stderr, retry_count=0)
        assert result["intercept"] is True

    def test_case_insensitive_match(self) -> None:
        stderr = "SELF SIGNED CERTIFICATE IN CERTIFICATE CHAIN"
        result = classify_mcp_transient_pre_hook(stderr=stderr, retry_count=0)
        assert result["intercept"] is True


class TestNonMatching:
    """Non-MCP errors and partial compound tokens must not intercept."""

    def test_git_hook_rejection_alone_does_not_intercept(self) -> None:
        stderr = "blocked by git hook rejection; needs human review"
        result = classify_mcp_transient_pre_hook(stderr=stderr, retry_count=0)
        assert result["intercept"] is False
        assert result["matched_token"] is None

    def test_partial_compound_mcp_server_only(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="MCP server started successfully", retry_count=0
        )
        assert result["intercept"] is False

    def test_partial_compound_connection_failed_only(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="Connection failed to postgres", retry_count=0
        )
        assert result["intercept"] is False

    def test_bare_403_without_mcp_does_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="403 Forbidden from CDN", retry_count=0
        )
        assert result["intercept"] is False

    def test_none_stderr_does_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert result["intercept"] is False

    def test_empty_stderr_does_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr="", retry_count=0)
        assert result["intercept"] is False


class TestRetryCap:
    """The 5-retry cap must exhaust interception."""

    def test_below_cap_intercepts(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain", retry_count=4
        )
        assert result["intercept"] is True

    def test_at_cap_does_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain", retry_count=5
        )
        assert result["intercept"] is False

    def test_above_cap_does_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain", retry_count=10
        )
        assert result["intercept"] is False


class TestFeatureIdEcho:
    """feature_id is threaded into the result for telemetry."""

    def test_feature_id_echoed_on_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="Streamable HTTP error",
            retry_count=0,
            feature_id="c49f4954",
        )
        assert result["feature_id"] == "c49f4954"

    def test_feature_id_echoed_on_no_match(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="unrelated error",
            retry_count=0,
            feature_id="c49f4954",
        )
        assert result["feature_id"] == "c49f4954"


class TestDrainSummary:
    """drain_mcp_transient_summary emits PRE_HOOK_TRANSIENT_SUMMARY telemetry."""

    def test_summary_event_name(self) -> None:
        result = drain_mcp_transient_summary(intercepted=3)
        assert result["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"
        assert result["intercepted"] == 3

    def test_zero_intercepted(self) -> None:
        result = drain_mcp_transient_summary(intercepted=0)
        assert result["intercepted"] == 0


class TestIntegrationRunLoop:
    """AC: integration: bob.run_loop — the hoist lives on the run_loop module."""

    def test_run_loop_exposes_pre_hook(self) -> None:
        import bob.run_loop as run_loop

        assert hasattr(run_loop, "classify_mcp_transient_pre_hook")

    def test_pre_hook_matches_base_classifier(self) -> None:
        import bob.run_loop as run_loop

        stderr = "Streamable HTTP error during evaluator run"
        base = run_loop.classify_mcp_transient(stderr=stderr, retry_count=0)
        hoist = run_loop.classify_mcp_transient_pre_hook(stderr=stderr, retry_count=0)
        assert base["intercept"] == hoist["intercept"]
        assert base["matched_token"] == hoist["matched_token"]
