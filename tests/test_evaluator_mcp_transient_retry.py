"""Tests for the Evaluator-MCP transient retry classifier (F-R7-597).

AC: pytest: tests/test_evaluator_mcp_transient_retry.py

Covers the full retry classification path: MCP-transient token detection,
cap enforcement, structured log event emission, re-ready vs needs_human
decision, and integration with bob.run_loop.
"""

from __future__ import annotations

import pytest

from bob.run_loop import classify_evaluator_mcp_transient, check_evaluator_mcp_transient_exemption


_MCP_TRANSIENT_CAP = 5  # F-R7-597 cap: 5 re-readies before needs_human


class TestRetryClassifierTokenDetection:
    """Verify that each F-R7-597 token triggers MCP_TRANSIENT classification."""

    def test_self_signed_cert_in_chain(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Error: self signed certificate in certificate chain",
            feature_id="f-1",
            retry_count=0,
        )
        assert result["classification"] == "mcp_transient"
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT"
        assert result["retry_count_after"] == 1

    def test_self_signed_hyphenated(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="SSL handshake error: self-signed certificate",
        )
        assert result["classification"] == "mcp_transient"
        assert "self-signed certificate" in result["matched_token"]

    def test_mcp_server_connection_failed(self):
        stderr = "MCP server 'plugin:github:github': Connection failed — connection refused"
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=stderr,
        )
        assert result["classification"] == "mcp_transient"
        assert "MCP server" in result["matched_token"]
        assert "Connection failed" in result["matched_token"]

    def test_http_connection_failed(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="HTTP Connection failed: connection timed out after 30s",
        )
        assert result["classification"] == "mcp_transient"
        assert result["matched_token"] == "HTTP Connection failed"

    def test_streamable_http_error(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Streamable HTTP error: 503 Service Unavailable",
        )
        assert result["classification"] == "mcp_transient"
        assert result["matched_token"] == "Streamable HTTP error"

    def test_server_rejected_authorization_header(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="Server rejected the configured Authorization header: 401 Unauthorized",
        )
        assert result["classification"] == "mcp_transient"
        assert "Server rejected the configured Authorization header" in result["matched_token"]

    def test_mcp_server_403_forbidden(self):
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


class TestRetryClassifierGuardConditions:
    """Classifier only fires when verdict=INSUFFICIENT_EVIDENCE + confidence==0.0 + is_error."""

    def test_non_insufficient_evidence_verdict_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="PASS",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_fail_verdict_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="FAIL",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["classification"] == "not_transient"

    def test_nonzero_confidence_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.1,
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

    def test_unrecognized_stderr_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="assertion error: expected True but got False",
        )
        assert result["classification"] == "not_transient"
        assert result["matched_token"] is None

    def test_403_without_mcp_server_prefix_not_transient(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="403 Forbidden from GitHub API",
        )
        assert result["classification"] == "not_transient"


class TestRetryCapEnforcement:
    """Cap at 5 re-readies; exceeded → mcp_persistent (needs_human)."""

    def test_below_cap_classified_as_transient(self):
        for count in range(_MCP_TRANSIENT_CAP):
            result = classify_evaluator_mcp_transient(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count=count,
            )
            assert result["classification"] == "mcp_transient", (
                f"Expected mcp_transient at retry_count={count}, got {result['classification']}"
            )

    def test_at_cap_classified_as_persistent(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=_MCP_TRANSIENT_CAP,
        )
        assert result["classification"] == "mcp_persistent"
        assert result["event"] == "EVALUATOR_MCP_PERSISTENT"

    def test_over_cap_classified_as_persistent(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=_MCP_TRANSIENT_CAP + 10,
        )
        assert result["classification"] == "mcp_persistent"

    def test_persistent_retry_count_not_incremented(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=_MCP_TRANSIENT_CAP,
        )
        assert result["retry_count_after"] == _MCP_TRANSIENT_CAP

    def test_transient_increments_retry_count(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="HTTP Connection failed",
            retry_count=3,
        )
        assert result["retry_count_after"] == 4


class TestStructuredLogEvent:
    """Result dict must carry the right event name for telemetry."""

    def test_transient_event_name(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=0,
        )
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT"

    def test_persistent_event_name(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=_MCP_TRANSIENT_CAP,
        )
        assert result["event"] == "EVALUATOR_MCP_PERSISTENT"

    def test_not_transient_event_is_empty(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="some unrelated failure",
        )
        assert result["event"] == ""

    def test_feature_id_in_result(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            feature_id="feat-abc",
        )
        assert result["feature_id"] == "feat-abc"


class TestIntegrationEntryPoint:
    """check_evaluator_mcp_transient_exemption maps classification → action."""

    def test_mcp_transient_returns_exempt_action(self):
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
        assert result["retry_count_after"] == 1

    def test_mcp_persistent_returns_cap_reached_action(self):
        result = check_evaluator_mcp_transient_exemption(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=_MCP_TRANSIENT_CAP,
        )
        assert result["action"] == "cap_reached"
        assert result["classification"] == "mcp_persistent"

    def test_not_transient_returns_not_exempt_action(self):
        result = check_evaluator_mcp_transient_exemption(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="assertion error: test_foo failed",
        )
        assert result["action"] == "not_exempt"
        assert result["classification"] == "not_transient"

    def test_wrong_verdict_returns_not_exempt_action(self):
        result = check_evaluator_mcp_transient_exemption(
            verdict="PASS",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert result["action"] == "not_exempt"

    def test_result_contains_all_required_keys(self):
        result = check_evaluator_mcp_transient_exemption(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="HTTP Connection failed",
        )
        for key in ("action", "classification", "matched_token", "event", "feature_id", "retry_count_after"):
            assert key in result, f"Missing required key: {key}"

    def test_invalid_retry_count_raises_value_error(self):
        with pytest.raises(ValueError):
            check_evaluator_mcp_transient_exemption(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate",
                retry_count="not-an-int",
            )
