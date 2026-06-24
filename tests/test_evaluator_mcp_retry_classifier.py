"""Tests for bob.evaluator_mcp_retry_classifier (F-R7-597).

AC: pytest: tests/test_evaluator_mcp_retry_classifier.py
"""

from __future__ import annotations

import pytest

from bob.evaluator_mcp_retry_classifier import classify_evaluator_failure, is_mcp_transient_error


class TestClassifyEvaluatorFailure:
    """Tests for classify_evaluator_failure."""

    def test_mcp_transient_cert_error(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Error: self signed certificate in certificate chain",
        )
        assert result["classification"] == "mcp_transient"
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT"
        assert result["matched_token"] is not None
        assert result["retry_count_after"] == 1

    def test_mcp_transient_self_signed_cert(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="TLS handshake failed: self-signed certificate rejected",
        )
        assert result["classification"] == "mcp_transient"

    def test_mcp_transient_mcp_server_connection_failed(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="MCP server 'plugin:github:github': Connection failed",
        )
        assert result["classification"] == "mcp_transient"

    def test_mcp_transient_http_connection_failed(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="HTTP Connection failed during startup",
        )
        assert result["classification"] == "mcp_transient"

    def test_mcp_transient_streamable_http_error(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Streamable HTTP error: connection reset",
        )
        assert result["classification"] == "mcp_transient"

    def test_mcp_transient_authorization_header_rejected(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Server rejected the configured Authorization header",
        )
        assert result["classification"] == "mcp_transient"

    def test_mcp_transient_403_with_mcp_server(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="MCP server 'plugin:github:github': 403 Forbidden",
        )
        assert result["classification"] == "mcp_transient"

    def test_not_transient_when_verdict_not_insufficient_evidence(self):
        result = classify_evaluator_failure(
            verdict="PASS",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_not_transient_when_is_error_false(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=False,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_not_transient_when_confidence_nonzero(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.5,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_not_transient_when_no_matching_stderr(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Some other error occurred",
        )
        assert result["classification"] == "not_transient"

    def test_mcp_persistent_when_cap_exceeded(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert result["classification"] == "mcp_persistent"

    def test_retry_count_incremented_on_mcp_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=2,
        )
        assert result["retry_count_after"] == 3

    def test_feature_id_echoed_in_result(self):
        fid = "test-feature-uuid-1234"
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            feature_id=fid,
        )
        assert result["feature_id"] == fid

    def test_invalid_retry_count_raises_value_error(self):
        with pytest.raises(ValueError, match="retry_count must be an int"):
            classify_evaluator_failure(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count="bad",
            )

    def test_none_stderr_returns_not_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=None,
        )
        assert result["classification"] == "not_transient"

    def test_result_has_all_required_keys(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=None,
        )
        assert {"classification", "matched_token", "event", "feature_id", "retry_count_after"}.issubset(result.keys())


class TestIsMcpTransientError:
    """Tests for is_mcp_transient_error."""

    def test_cert_chain_error_returns_true(self):
        assert is_mcp_transient_error("Error: self signed certificate in certificate chain") is True

    def test_self_signed_cert_returns_true(self):
        assert is_mcp_transient_error("self-signed certificate rejected") is True

    def test_mcp_server_connection_failed_returns_true(self):
        assert is_mcp_transient_error("MCP server 'plugin:github:github': Connection failed") is True

    def test_http_connection_failed_returns_true(self):
        assert is_mcp_transient_error("HTTP Connection failed") is True

    def test_streamable_http_error_returns_true(self):
        assert is_mcp_transient_error("Streamable HTTP error: reset") is True

    def test_authorization_header_rejected_returns_true(self):
        assert is_mcp_transient_error("Server rejected the configured Authorization header") is True

    def test_mcp_server_403_returns_true(self):
        assert is_mcp_transient_error("MCP server 'foo': 403 Forbidden") is True

    def test_unrelated_error_returns_false(self):
        assert is_mcp_transient_error("KeyError: 'missing_key'") is False

    def test_none_returns_false(self):
        assert is_mcp_transient_error(None) is False

    def test_empty_string_returns_false(self):
        assert is_mcp_transient_error("") is False

    def test_403_without_mcp_server_returns_false(self):
        assert is_mcp_transient_error("403 Forbidden from API endpoint") is False

    def test_case_insensitive_match(self):
        assert is_mcp_transient_error("SELF SIGNED CERTIFICATE IN CERTIFICATE CHAIN") is True

    def test_whitespace_only_returns_false(self):
        assert is_mcp_transient_error("   \n  ") is False
