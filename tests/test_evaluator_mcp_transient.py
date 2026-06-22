"""Tests for classify_evaluator_mcp_transient and check_evaluator_mcp_transient_exemption (F-R7-597).

Covers: MCP-transient token matching, cap enforcement, not-transient cases,
and orchestrator-integration exemption check.
"""

from __future__ import annotations

import pytest

from bob3.run_loop import classify_evaluator_mcp_transient, check_evaluator_mcp_transient_exemption


class TestClassifyEvaluatorMcpTransientTokenMatching:
    """Token-matching happy-path tests."""

    def test_self_signed_cert_is_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Error: self signed certificate in certificate chain",
            feature_id="feat-1",
            retry_count=0,
        )
        assert result["classification"] == "mcp_transient"
        assert result["matched_token"] == "self signed certificate in certificate chain"
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT"
        assert result["feature_id"] == "feat-1"
        assert result["retry_count_after"] == 1

    def test_self_signed_hyphenated_is_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self-signed certificate error during handshake",
        )
        assert result["classification"] == "mcp_transient"
        assert result["matched_token"] == "self-signed certificate"

    def test_mcp_server_connection_failed_compound(self):
        stderr = "MCP server 'plugin:github:github': Connection failed due to network error"
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=stderr,
        )
        assert result["classification"] == "mcp_transient"
        assert "MCP server" in result["matched_token"]
        assert "Connection failed" in result["matched_token"]

    def test_http_connection_failed_is_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="HTTP Connection failed: timeout after 30s",
        )
        assert result["classification"] == "mcp_transient"
        assert result["matched_token"] == "HTTP Connection failed"

    def test_streamable_http_error_is_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Streamable HTTP error: 502 Bad Gateway",
        )
        assert result["classification"] == "mcp_transient"
        assert result["matched_token"] == "Streamable HTTP error"

    def test_server_rejected_auth_header_is_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Server rejected the configured Authorization header: 401",
        )
        assert result["classification"] == "mcp_transient"
        assert result["matched_token"] == "Server rejected the configured Authorization header"

    def test_mcp_server_403_compound_is_transient(self):
        stderr = "MCP server 'plugin:github:github': 403 Forbidden"
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=stderr,
        )
        assert result["classification"] == "mcp_transient"
        assert "MCP server" in result["matched_token"]
        assert "403 Forbidden" in result["matched_token"]

    def test_token_matching_is_case_insensitive(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="SELF SIGNED CERTIFICATE IN CERTIFICATE CHAIN",
        )
        assert result["classification"] == "mcp_transient"


class TestClassifyEvaluatorMcpTransientNotTransient:
    """Cases where the classifier should return not_transient."""

    def test_wrong_verdict_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="PASS",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"
        assert result["event"] == ""

    def test_non_zero_confidence_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.5,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_is_error_false_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=False,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_no_matching_token_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="some other error that is not an MCP transient failure",
        )
        assert result["classification"] == "not_transient"
        assert result["matched_token"] is None

    def test_none_verdict_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict=None,
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_403_without_mcp_server_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="403 Forbidden from upstream API",
        )
        assert result["classification"] == "not_transient"

    def test_mcp_server_without_connection_failed_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="MCP server started successfully",
        )
        assert result["classification"] == "not_transient"


class TestClassifyEvaluatorMcpTransientCap:
    """Cap enforcement tests."""

    def test_at_retry_cap_returns_mcp_persistent(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert result["classification"] == "mcp_persistent"
        assert result["event"] == "EVALUATOR_MCP_PERSISTENT"
        assert result["retry_count_after"] == 5

    def test_below_cap_fires_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=4,
        )
        assert result["classification"] == "mcp_transient"
        assert result["retry_count_after"] == 5

    def test_over_cap_returns_mcp_persistent(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=99,
        )
        assert result["classification"] == "mcp_persistent"

    def test_retry_count_increments_on_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="HTTP Connection failed",
            retry_count=2,
        )
        assert result["retry_count_after"] == 3


class TestClassifyEvaluatorMcpTransientDefaults:
    """Default argument and edge-case tests."""

    def test_none_confidence_treated_as_zero(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=None,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "mcp_transient"

    def test_feature_id_echoed_in_result(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            feature_id="abc-123",
        )
        assert result["feature_id"] == "abc-123"

    def test_feature_id_none_by_default(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["feature_id"] is None


class TestCheckEvaluatorMcpTransientExemption:
    """Tests for check_evaluator_mcp_transient_exemption (F-R7-597 integration entry point)."""

    def test_exempt_on_mcp_transient(self):
        result = check_evaluator_mcp_transient_exemption(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            feature_id="feat-1",
            retry_count=0,
        )
        assert result["action"] == "exempt"
        assert result["classification"] == "mcp_transient"
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT"
        assert result["feature_id"] == "feat-1"
        assert result["retry_count_after"] == 1

    def test_cap_reached_when_retry_count_at_cap(self):
        result = check_evaluator_mcp_transient_exemption(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert result["action"] == "cap_reached"
        assert result["classification"] == "mcp_persistent"
        assert result["event"] == "EVALUATOR_MCP_PERSISTENT"

    def test_not_exempt_on_non_transient_failure(self):
        result = check_evaluator_mcp_transient_exemption(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="real test regression: assertion failed",
        )
        assert result["action"] == "not_exempt"
        assert result["classification"] == "not_transient"
        assert result["matched_token"] is None

    def test_not_exempt_on_wrong_verdict(self):
        result = check_evaluator_mcp_transient_exemption(
            verdict="PASS",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["action"] == "not_exempt"

    def test_result_has_all_required_keys(self):
        result = check_evaluator_mcp_transient_exemption(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="HTTP Connection failed",
        )
        for key in ("action", "classification", "matched_token", "event", "feature_id", "retry_count_after"):
            assert key in result, f"Missing key: {key}"

    def test_raises_value_error_on_non_int_retry_count(self):
        with pytest.raises(ValueError):
            check_evaluator_mcp_transient_exemption(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate",
                retry_count="bad",  # type: ignore[arg-type]
            )
