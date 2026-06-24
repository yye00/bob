"""Tests for bob.classifier_mcp_transient.classify_mcp_transient_pre_hook.

AC: pytest: tests/test_classifier_mcp_transient_pre_hook.py
AC: File exists: src/bob/classifier_mcp_transient.py
AC: Function defined: bob.classifier_mcp_transient.classify_mcp_transient_pre_hook

Verifies that classify_mcp_transient_pre_hook correctly intercepts
MCP-transient errors before the git-hook-rejection demotion path fires,
subject to the 5-retry cap from F-R7-597.
"""

from __future__ import annotations

import pytest

from bob.classifier_mcp_transient import (
    classify_mcp_transient_pre_hook,
    drain_pre_hook_transient_summary,
)


class TestMcpTransientPreHookImport:
    """Module and function must be importable from bob.classifier_mcp_transient."""

    def test_classify_mcp_transient_pre_hook_is_callable(self) -> None:
        assert callable(classify_mcp_transient_pre_hook)

    def test_drain_pre_hook_transient_summary_is_callable(self) -> None:
        assert callable(drain_pre_hook_transient_summary)


class TestMcpTransientPreHookReturnShape:
    """Result dict must have intercept, matched_token, event, feature_id keys."""

    def test_returns_dict(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert isinstance(result, dict)

    def test_has_intercept_key(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert "intercept" in result

    def test_has_matched_token_key(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert "matched_token" in result

    def test_has_event_key(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert "event" in result

    def test_has_feature_id_key(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=None, retry_count=0, feature_id="abc-123"
        )
        assert "feature_id" in result


class TestMcpTransientPreHookTokenMatching:
    """Each token in the MCP-transient set must trigger intercept=True."""

    def test_self_signed_cert_long_intercepts(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=0,
        )
        assert result["intercept"] is True
        assert result["matched_token"] is not None
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"

    def test_self_signed_certificate_short_intercepts(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="Error: self-signed certificate detected",
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_mcp_server_connection_failed_compound_intercepts(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="MCP server unavailable. Connection failed after 30s.",
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_http_connection_failed_intercepts(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="HTTP Connection failed: connection refused",
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_streamable_http_error_intercepts(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="Streamable HTTP error: peer reset connection",
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_server_rejected_authorization_header_intercepts(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="Server rejected the configured Authorization header",
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_mcp_server_403_forbidden_compound_intercepts(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="MCP server returned 403 Forbidden response",
            retry_count=0,
        )
        assert result["intercept"] is True


class TestMcpTransientPreHookRetryCap:
    """At retry_count >= 5 the cap is exhausted and intercept must be False."""

    def test_retry_count_5_does_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert result["intercept"] is False

    def test_retry_count_4_still_intercepts(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="Streamable HTTP error",
            retry_count=4,
        )
        assert result["intercept"] is True

    def test_retry_count_100_does_not_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=100,
        )
        assert result["intercept"] is False


class TestMcpTransientPreHookNonMatching:
    """Non-MCP errors must not trigger intercept."""

    def test_none_stderr_no_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr=None, retry_count=0)
        assert result["intercept"] is False
        assert result["matched_token"] is None

    def test_empty_stderr_no_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(stderr="", retry_count=0)
        assert result["intercept"] is False

    def test_unrelated_git_hook_error_no_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="pre-commit hook failed: lint check",
            retry_count=0,
        )
        assert result["intercept"] is False

    def test_partial_compound_mcp_only_no_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="MCP server started successfully",
            retry_count=0,
        )
        assert result["intercept"] is False

    def test_partial_compound_connection_failed_only_no_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="Connection failed to postgres",
            retry_count=0,
        )
        assert result["intercept"] is False

    def test_partial_compound_403_only_no_intercept(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="403 Forbidden from nginx",
            retry_count=0,
        )
        assert result["intercept"] is False

    @pytest.mark.parametrize("stderr", [
        "ImportError: No module named requests",
        "SyntaxError: invalid syntax at line 42",
        "PermissionError: [Errno 13] Permission denied",
        "git hook: pre-commit check failed",
        "AssertionError: AC not satisfied",
    ])
    def test_unrelated_errors_no_intercept(self, stderr: str) -> None:
        result = classify_mcp_transient_pre_hook(stderr=stderr, retry_count=0)
        assert result["intercept"] is False
        assert result["matched_token"] is None


class TestMcpTransientPreHookFeatureId:
    """feature_id is echoed in the result."""

    def test_feature_id_echoed_on_intercept(self) -> None:
        fid = "test-feature-uuid-1234"
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=0,
            feature_id=fid,
        )
        assert result["feature_id"] == fid

    def test_feature_id_echoed_on_no_intercept(self) -> None:
        fid = "test-feature-uuid-5678"
        result = classify_mcp_transient_pre_hook(
            stderr="unrelated error",
            retry_count=0,
            feature_id=fid,
        )
        assert result["feature_id"] == fid

    def test_none_feature_id_allowed(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=0,
            feature_id=None,
        )
        assert result["feature_id"] is None


class TestDrainPreHookTransientSummary:
    """drain_pre_hook_transient_summary must return the correct telemetry dict."""

    def test_zero_intercepted(self) -> None:
        result = drain_pre_hook_transient_summary(intercepted=0)
        assert result["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"
        assert result["intercepted"] == 0

    def test_nonzero_intercepted(self) -> None:
        result = drain_pre_hook_transient_summary(intercepted=7)
        assert result["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"
        assert result["intercepted"] == 7

    def test_returns_dict(self) -> None:
        result = drain_pre_hook_transient_summary(intercepted=3)
        assert isinstance(result, dict)


class TestRunLoopIntegration:
    """Verify the integration: bob.run_loop exports match what classifier_mcp_transient wraps."""

    def test_pre_hook_matches_run_loop_direct(self) -> None:
        from bob.run_loop import classify_mcp_transient

        stderr = "self signed certificate in certificate chain"
        result_via_module = classify_mcp_transient_pre_hook(stderr=stderr, retry_count=0)
        result_via_run_loop = classify_mcp_transient(stderr=stderr, retry_count=0)
        assert result_via_module["intercept"] == result_via_run_loop["intercept"]
        assert result_via_module["matched_token"] == result_via_run_loop["matched_token"]
        assert result_via_module["event"] == result_via_run_loop["event"]

    def test_drain_summary_matches_run_loop_direct(self) -> None:
        from bob.run_loop import drain_mcp_transient_summary

        result_via_module = drain_pre_hook_transient_summary(intercepted=5)
        result_via_run_loop = drain_mcp_transient_summary(intercepted=5)
        assert result_via_module["event"] == result_via_run_loop["event"]
        assert result_via_module["intercepted"] == result_via_run_loop["intercepted"]
