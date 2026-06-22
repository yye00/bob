"""Tests for bob3.evaluator_retry_classifier.classify_evaluator_failure.

AC: pytest: tests/test_evaluator_retry_classifier.py
"""

from __future__ import annotations

import pytest

from bob3.evaluator_retry_classifier import classify_evaluator_failure


class TestClassifyEvaluatorFailureBasicBehavior:
    """classify_evaluator_failure basic contract."""

    def test_cert_chain_error_classified_as_mcp_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Error: self signed certificate in certificate chain",
        )
        assert result["classification"] == "mcp_transient"
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT"

    def test_self_signed_cert_classified_as_mcp_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="TLS error: self-signed certificate rejected",
        )
        assert result["classification"] == "mcp_transient"

    def test_mcp_server_connection_failed_classified_as_mcp_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="MCP server 'plugin:github:github': Connection failed with timeout",
        )
        assert result["classification"] == "mcp_transient"

    def test_http_connection_failed_classified_as_mcp_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="HTTP Connection failed: connection refused",
        )
        assert result["classification"] == "mcp_transient"

    def test_streamable_http_error_classified_as_mcp_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Streamable HTTP error on request",
        )
        assert result["classification"] == "mcp_transient"

    def test_authorization_header_rejected_classified_as_mcp_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Server rejected the configured Authorization header",
        )
        assert result["classification"] == "mcp_transient"

    def test_403_with_mcp_server_classified_as_mcp_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="MCP server returned 403 Forbidden",
        )
        assert result["classification"] == "mcp_transient"

    def test_non_transient_verdict_returns_not_transient(self):
        result = classify_evaluator_failure(
            verdict="PASS",
            confidence=0.9,
            is_error=False,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_non_zero_confidence_returns_not_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.5,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_is_error_false_returns_not_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=False,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_no_token_match_returns_not_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="some random test failure unrelated to MCP",
        )
        assert result["classification"] == "not_transient"


class TestClassifyEvaluatorFailureRetryCapLogic:
    """Retry cap behavior."""

    def test_retry_count_at_cap_returns_mcp_persistent(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert result["classification"] == "mcp_persistent"

    def test_retry_count_below_cap_returns_mcp_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=4,
        )
        assert result["classification"] == "mcp_transient"
        assert result["retry_count_after"] == 5

    def test_retry_count_incremented_on_transient(self):
        for count in range(5):
            result = classify_evaluator_failure(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count=count,
            )
            assert result["retry_count_after"] == count + 1


class TestClassifyEvaluatorFailureResultShape:
    """Return dict structure."""

    def test_result_has_required_keys(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=None,
        )
        assert {"classification", "matched_token", "event", "feature_id", "retry_count_after"}.issubset(result.keys())

    def test_feature_id_echoed_in_result(self):
        fid = "test-feature-id-123"
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            feature_id=fid,
        )
        assert result["feature_id"] == fid

    def test_matched_token_present_when_mcp_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["matched_token"] is not None
        assert len(result["matched_token"]) > 0

    def test_matched_token_none_when_not_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="some unrelated error",
        )
        assert result["matched_token"] is None

    def test_event_empty_string_when_not_transient(self):
        result = classify_evaluator_failure(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=None,
        )
        assert result["event"] == ""


class TestClassifyEvaluatorFailureInvalidInput:
    """Invalid inputs should raise ValueError."""

    def test_non_int_retry_count_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_evaluator_failure(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count="five",
            )

    def test_float_retry_count_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_evaluator_failure(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count=1.5,
            )
