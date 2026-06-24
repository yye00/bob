"""Error path tests for classify_evaluator_mcp_transient.

AC: pytest: tests/test_evaluator_mcp_transient_cert_conn_crashes_error.py
— invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob3.run_loop import classify_evaluator_mcp_transient


class TestClassifyEvaluatorMcpTransientErrorPath:
    """Invalid inputs must raise ValueError, not silently succeed."""

    def test_non_int_retry_count_raises_value_error(self):
        with pytest.raises(ValueError, match="retry_count must be an int"):
            classify_evaluator_mcp_transient(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count="five",
            )

    def test_float_retry_count_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_evaluator_mcp_transient(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count=1.5,
            )

    def test_list_retry_count_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_evaluator_mcp_transient(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count=[0],
            )

    def test_none_retry_count_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_evaluator_mcp_transient(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count=None,
            )

    def test_dict_retry_count_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_evaluator_mcp_transient(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count={},
            )

    def test_error_does_not_silently_succeed_with_bad_retry_count(self):
        # Confirm it raises and the function does not return a result silently
        raised = False
        try:
            classify_evaluator_mcp_transient(
                verdict="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                is_error=True,
                stderr="self signed certificate in certificate chain",
                retry_count="bad",
            )
        except ValueError:
            raised = True
        assert raised, "Expected ValueError but function returned silently"
