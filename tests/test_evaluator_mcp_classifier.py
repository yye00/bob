"""Tests for bob3.evaluator_mcp_classifier.classify_mcp_transient.

AC: pytest: tests/test_evaluator_mcp_classifier.py
"""

from __future__ import annotations

import pytest

from bob3.evaluator_mcp_classifier import classify_mcp_transient


class TestClassifyMcpTransientMcpTransientCases:
    """Cases where the classifier should return mcp_transient."""

    def test_self_signed_cert_classified_as_transient(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Error: self signed certificate in certificate chain",
        )
        assert result["classification"] == "mcp_transient"
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT"
        assert result["matched_token"] is not None

    def test_self_signed_certificate_hyphenated(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="ssl error: self-signed certificate in the chain",
        )
        assert result["classification"] == "mcp_transient"

    def test_mcp_server_connection_failed(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="MCP server 'plugin:github:github': Connection failed due to TLS error",
        )
        assert result["classification"] == "mcp_transient"

    def test_http_connection_failed(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="HTTP Connection failed: timeout",
        )
        assert result["classification"] == "mcp_transient"

    def test_streamable_http_error(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Streamable HTTP error while connecting to MCP endpoint",
        )
        assert result["classification"] == "mcp_transient"

    def test_server_rejected_authorization_header(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Server rejected the configured Authorization header for plugin",
        )
        assert result["classification"] == "mcp_transient"

    def test_403_with_mcp_server(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="MCP server returned 403 Forbidden response",
        )
        assert result["classification"] == "mcp_transient"

    def test_retry_count_incremented_on_transient(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=2,
        )
        assert result["retry_count_after"] == 3

    def test_feature_id_echoed_in_result(self):
        fid = "39256e9a-1022-44fd-b820-bfcd46236c3b"
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            feature_id=fid,
        )
        assert result["feature_id"] == fid


class TestClassifyMcpTransientNotTransientCases:
    """Cases where the classifier should return not_transient."""

    def test_wrong_verdict_not_transient(self):
        result = classify_mcp_transient(
            verdict="FAIL",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_non_zero_confidence_not_transient(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.5,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_is_error_false_not_transient(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=False,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_no_matching_token_not_transient(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="test assertion failed: expected 42 got 0",
        )
        assert result["classification"] == "not_transient"
        assert result["matched_token"] is None
        assert result["event"] == ""

    def test_403_without_mcp_server_not_transient(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="HTTP 403 Forbidden from upstream service",
        )
        assert result["classification"] == "not_transient"


class TestClassifyMcpTransientCapBehavior:
    """Cap enforcement: retry_count >= 5 → mcp_persistent."""

    def test_at_cap_returns_mcp_persistent(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert result["classification"] == "mcp_persistent"

    def test_above_cap_returns_mcp_persistent(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=10,
        )
        assert result["classification"] == "mcp_persistent"

    def test_below_cap_returns_mcp_transient(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=4,
        )
        assert result["classification"] == "mcp_transient"


class TestClassifyMcpTransientReturnShape:
    """Return dict always has the required keys."""

    def test_required_keys_present_on_transient(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert {"classification", "matched_token", "event", "feature_id", "retry_count_after"}.issubset(result)

    def test_required_keys_present_on_not_transient(self):
        result = classify_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=None,
        )
        assert {"classification", "matched_token", "event", "feature_id", "retry_count_after"}.issubset(result)

    def test_invalid_retry_count_raises_value_error(self):
        with pytest.raises(ValueError, match="retry_count must be an int"):
            classify_mcp_transient(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count="bad",
            )
