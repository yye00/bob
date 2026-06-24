"""Boundary tests for classify_evaluator_mcp_transient.

AC: pytest: tests/test_evaluator_mcp_transient_cert_conn_crashes_boundary.py
— empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

import pytest

from bob.run_loop import classify_evaluator_mcp_transient


class TestClassifyEvaluatorMcpTransientBoundary:
    """Boundary: zero/empty/minimum inputs must return a dict, never raise."""

    def test_none_stderr_returns_dict(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=None,
        )
        assert isinstance(result, dict)
        assert result["classification"] == "not_transient"

    def test_empty_string_stderr_returns_dict(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="",
        )
        assert isinstance(result, dict)
        assert result["classification"] == "not_transient"

    def test_zero_retry_count_is_valid(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=0,
        )
        assert isinstance(result, dict)
        assert result["classification"] == "mcp_transient"
        assert result["retry_count_after"] == 1

    def test_none_confidence_is_valid(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=None,
            is_error=True,
            stderr=None,
        )
        assert isinstance(result, dict)

    def test_none_feature_id_is_valid(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            feature_id=None,
        )
        assert isinstance(result, dict)
        assert result["feature_id"] is None

    def test_none_verdict_returns_dict(self):
        result = classify_evaluator_mcp_transient(
            verdict=None,
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert isinstance(result, dict)
        assert result["classification"] == "not_transient"

    def test_empty_verdict_returns_dict(self):
        result = classify_evaluator_mcp_transient(
            verdict="",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
        )
        assert isinstance(result, dict)
        assert result["classification"] == "not_transient"

    def test_result_always_has_required_keys(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr=None,
        )
        required_keys = {"classification", "matched_token", "event", "feature_id", "retry_count_after"}
        assert required_keys.issubset(result.keys())

    def test_whitespace_only_stderr_returns_dict(self):
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="   \n\t  ",
        )
        assert isinstance(result, dict)
        assert result["classification"] == "not_transient"

    def test_retry_count_at_cap_boundary(self):
        # retry_count == 5 (at cap) → mcp_persistent, not raises
        result = classify_evaluator_mcp_transient(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            is_error=True,
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert isinstance(result, dict)
        assert result["classification"] == "mcp_persistent"
