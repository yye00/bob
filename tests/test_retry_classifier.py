"""Tests for bob.retry_classifier.classify_evaluator_result (F-R7-597).

AC: pytest: tests/test_retry_classifier.py
"""

from __future__ import annotations

import pytest

from bob.retry_classifier import classify_evaluator_result


class TestClassifyEvaluatorResultMcpTransient:
    """Happy-path: MCP-transient tokens produce mcp_transient classification."""

    def test_self_signed_cert_is_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Error: self signed certificate in certificate chain",
            feature_id="feat-abc",
            retry_count=0,
        )
        assert result["classification"] == "mcp_transient"
        assert result["matched_token"] == "self signed certificate in certificate chain"
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT"
        assert result["feature_id"] == "feat-abc"
        assert result["retry_count_after"] == 1

    def test_self_signed_hyphenated_is_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self-signed certificate validation failure",
        )
        assert result["classification"] == "mcp_transient"
        assert result["matched_token"] == "self-signed certificate"

    def test_mcp_server_connection_failed_compound(self):
        stderr = "MCP server 'plugin:github:github': Connection failed due to network error"
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=stderr,
        )
        assert result["classification"] == "mcp_transient"
        assert "MCP server" in result["matched_token"]
        assert "Connection failed" in result["matched_token"]

    def test_http_connection_failed_is_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="HTTP Connection failed: timeout",
        )
        assert result["classification"] == "mcp_transient"

    def test_streamable_http_error_is_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Streamable HTTP error encountered during MCP startup",
        )
        assert result["classification"] == "mcp_transient"

    def test_server_rejected_authorization_is_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Server rejected the configured Authorization header",
        )
        assert result["classification"] == "mcp_transient"

    def test_mcp_server_403_forbidden_is_transient(self):
        stderr = "MCP server 'plugin:x': 403 Forbidden response"
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=stderr,
        )
        assert result["classification"] == "mcp_transient"

    def test_retry_count_increments(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=3,
        )
        assert result["retry_count_after"] == 4

    def test_none_confidence_treated_as_zero(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=None,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "mcp_transient"


class TestClassifyEvaluatorResultNotTransient:
    """Cases that must return not_transient."""

    def test_different_verdict_is_not_transient(self):
        result = classify_evaluator_result(
            verdict="PASS",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_nonzero_confidence_is_not_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.5,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_not_is_error_is_not_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=False,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_no_matching_token_is_not_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="The tests failed because the function is wrong",
        )
        assert result["classification"] == "not_transient"
        assert result["matched_token"] is None

    def test_empty_stderr_is_not_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="",
        )
        assert result["classification"] == "not_transient"

    def test_none_stderr_is_not_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=None,
        )
        assert result["classification"] == "not_transient"

    def test_403_without_mcp_server_is_not_transient(self):
        # 403 alone (without "MCP server") must NOT match
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="403 Forbidden from the API endpoint",
        )
        assert result["classification"] == "not_transient"


class TestClassifyEvaluatorResultCapEnforcement:
    """Cap enforcement: retry_count >= 5 → mcp_persistent."""

    def test_at_cap_returns_mcp_persistent(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert result["classification"] == "mcp_persistent"
        assert result["event"] == "EVALUATOR_MCP_PERSISTENT"

    def test_above_cap_returns_mcp_persistent(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=10,
        )
        assert result["classification"] == "mcp_persistent"

    def test_below_cap_returns_mcp_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=4,
        )
        assert result["classification"] == "mcp_transient"
        assert result["retry_count_after"] == 5


class TestClassifyEvaluatorResultReturnSchema:
    """Return dict must always contain required keys."""

    def test_required_keys_present_on_not_transient(self):
        result = classify_evaluator_result(
            verdict="PASS",
            confidence=1.0,
            is_error=False,
            stderr=None,
        )
        required = {"classification", "matched_token", "event", "feature_id", "retry_count_after"}
        assert required.issubset(result.keys())

    def test_required_keys_present_on_mcp_transient(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        required = {"classification", "matched_token", "event", "feature_id", "retry_count_after"}
        assert required.issubset(result.keys())

    def test_feature_id_echoed(self):
        result = classify_evaluator_result(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            feature_id="deadbeef-1234",
        )
        assert result["feature_id"] == "deadbeef-1234"

    def test_feature_id_none_when_not_provided(self):
        result = classify_evaluator_result(
            verdict="PASS",
            confidence=1.0,
            is_error=False,
            stderr=None,
        )
        assert result["feature_id"] is None


class TestClassifyEvaluatorResultErrorPaths:
    """Invalid input raises ValueError."""

    def test_non_int_retry_count_raises(self):
        with pytest.raises(ValueError, match="retry_count must be an int"):
            classify_evaluator_result(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count="five",
            )

    def test_float_retry_count_raises(self):
        with pytest.raises(ValueError):
            classify_evaluator_result(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count=1.0,
            )

    def test_none_retry_count_raises(self):
        with pytest.raises(ValueError):
            classify_evaluator_result(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count=None,
            )
