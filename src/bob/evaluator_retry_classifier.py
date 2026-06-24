"""Evaluator retry classifier — MCP-transient cert/conn crash detection.

F-R7-597: Classify evaluator failures caused by MCP/TLS infrastructure noise
as retryable (MCP_TRANSIENT) rather than feature-rejection.

This module exposes :func:`classify_evaluator_failure` as the canonical entry
point. It delegates to :func:`bob.run_loop.classify_evaluator_mcp_transient`
so the two implementations stay in sync.
"""

from __future__ import annotations

from typing import Any

from bob.run_loop import classify_evaluator_mcp_transient

__all__ = ["classify_evaluator_failure"]


def classify_evaluator_failure(
    *,
    verdict: str | None,
    confidence: float | None,
    is_error: bool,
    stderr: str | None,
    feature_id: str | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """Classify an evaluator failure as MCP-transient or a genuine rejection.

    Implements F-R7-597. Inspects captured_stderr_head / captured_stderr_log
    when verdict is INSUFFICIENT_EVIDENCE AND confidence==0.0 AND is_error=True.
    If the stderr matches any MCP-transient token, returns classification
    'mcp_transient' (caller should reset feature to 'ready'). If the
    per-feature retry cap (5) is exhausted, returns 'mcp_persistent' (caller
    should demote to needs_human). Otherwise returns 'not_transient'.

    Parameters
    ----------
    verdict:
        Evaluator verdict string. Only "INSUFFICIENT_EVIDENCE" triggers
        classification; any other value returns not_transient immediately.
    confidence:
        Evaluator confidence score. Must be 0.0 (or None treated as 0.0)
        for MCP_TRANSIENT to fire.
    is_error:
        Whether the evaluator sub-agent exited with is_error=True.
    stderr:
        Captured stderr text from the evaluator sub-agent. May be None.
    feature_id:
        Optional feature UUID; echoed in the result and structured log event.
    retry_count:
        Number of times MCP-transient re-ready has already fired for this
        feature in the current round (0-based). Must be an int.

    Returns
    -------
    dict with keys:
        classification: "mcp_transient" | "mcp_persistent" | "not_transient"
        matched_token: str | None — first stderr token that matched
        event: str — "EVALUATOR_MCP_TRANSIENT" when mcp_transient, else ""
        feature_id: str | None — echoed from argument
        retry_count_after: int — retry_count after this decision

    Raises
    ------
    ValueError
        When retry_count is not an integer.
    """
    return classify_evaluator_mcp_transient(
        verdict=verdict,
        confidence=confidence,
        is_error=is_error,
        stderr=stderr,
        feature_id=feature_id,
        retry_count=retry_count,
    )
