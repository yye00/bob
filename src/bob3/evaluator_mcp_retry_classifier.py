"""Evaluator MCP retry classifier — F-R7-597.

Classifies evaluator sub-agent failures caused by MCP/TLS infrastructure
noise as retryable (MCP_TRANSIENT) rather than feature-rejection.

Public API:
    classify_evaluator_failure  — classify a full evaluator result dict
    is_mcp_transient_error      — quick bool check on stderr alone
"""

from __future__ import annotations

from typing import Any

from bob3.run_loop import classify_evaluator_mcp_transient, _EVALUATOR_MCP_TRANSIENT_TOKENS

__all__ = ["classify_evaluator_failure", "is_mcp_transient_error"]


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
    If stderr matches any MCP-transient token, returns classification
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


def is_mcp_transient_error(stderr: str | None) -> bool:
    """Return True if stderr contains any MCP-transient token.

    Quick boolean check that does NOT enforce the verdict/confidence/is_error
    preconditions — useful for pre-filtering before constructing the full
    classifier call, or for testing token matching in isolation.

    Parameters
    ----------
    stderr:
        Captured stderr text. None or empty string returns False.

    Returns
    -------
    bool
        True if any token from the MCP-transient token list is present in
        the stderr text (case-insensitive). False otherwise.
    """
    if not stderr:
        return False

    stderr_lower = stderr.lower()
    for token in _EVALUATOR_MCP_TRANSIENT_TOKENS:
        if isinstance(token, tuple):
            t1, t2 = token
            if t1.lower() in stderr_lower and t2.lower() in stderr_lower:
                return True
        else:
            if token.lower() in stderr_lower:
                return True

    return False
