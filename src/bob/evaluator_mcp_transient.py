"""Evaluator-MCP transient cert/conn crash classifier (F-R7-597).

When the independent commit-gate evaluator sub-agent crashes on upstream MCP
infrastructure noise (self-signed certs, connection failures, transient HTTP
errors), the orchestrator previously mapped its INSUFFICIENT_EVIDENCE verdict
to a feature failure. That is wrong: MCP-startup noise is the same shape as the
transient-API-400 / rate-limit class that must be retried silently, not triaged.

This module classifies such crashes so the orchestrator can reset the feature to
'ready' (retry) instead of 'failed'. It ONLY downgrades on an explicit set of
MCP-transient tokens; any other evaluator failure (real regression, real rubric
rejection) is left untouched.

Functions
---------
is_mcp_transient(stderr):
    Return (bool, matched_token) — True if stderr contains any MCP-transient token.
classify_evaluator_failure(...):
    Full policy: verdict/confidence/is_error gate + token match + retry cap.
"""

from __future__ import annotations

from typing import Optional, Tuple

# Cap on re-readies per feature per round before demoting to needs_human.
RETRY_CAP = 5

# Single-substring MCP-transient tokens (case-insensitive).
_SINGLE_TOKENS = (
    "self signed certificate in certificate chain",
    "self-signed certificate",
    "HTTP Connection failed",
    "Streamable HTTP error",
    "Server rejected the configured Authorization header",
)

# Compound tokens: ALL substrings must be present. The reported matched_token
# joins the parts with " ... ".
_COMPOUND_TOKENS = (
    ("MCP server", "Connection failed"),
    ("MCP server", "403 Forbidden"),
)


def is_mcp_transient(stderr: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Return (is_transient, matched_token) for the given evaluator stderr.

    Matching is case-insensitive. Returns (False, None) for None/empty stderr.
    """
    if not stderr:
        return False, None
    haystack = stderr.lower()

    for token in _SINGLE_TOKENS:
        if token.lower() in haystack:
            return True, token

    for parts in _COMPOUND_TOKENS:
        if all(part.lower() in haystack for part in parts):
            return True, " ... ".join(parts)

    return False, None


def classify_evaluator_failure(
    verdict: Optional[str],
    confidence: Optional[float],
    is_error: bool,
    stderr: Optional[str],
    feature_id: Optional[str] = None,
    retry_count: int = 0,
) -> dict:
    """Classify an evaluator failure as mcp_transient / mcp_persistent / not_transient.

    Only classifies as transient when the failure is the exact INSUFFICIENT_EVIDENCE +
    confidence==0.0 + is_error=True shape AND stderr contains an MCP-transient token.

    Returns a dict with keys: classification, matched_token, event, feature_id,
    retry_count_after.

    Raises ValueError if retry_count is not an int.
    """
    if isinstance(retry_count, bool) or not isinstance(retry_count, int):
        raise ValueError("retry_count must be an int")

    not_transient = {
        "classification": "not_transient",
        "matched_token": None,
        "event": "",
        "feature_id": feature_id,
        "retry_count_after": retry_count,
    }

    if verdict != "INSUFFICIENT_EVIDENCE":
        return not_transient
    if not is_error:
        return not_transient
    if confidence is not None and confidence != 0.0:
        return not_transient

    transient, matched_token = is_mcp_transient(stderr)
    if not transient:
        return not_transient

    if retry_count >= RETRY_CAP:
        return {
            "classification": "mcp_persistent",
            "matched_token": matched_token,
            "event": "EVALUATOR_MCP_PERSISTENT",
            "feature_id": feature_id,
            "retry_count_after": retry_count,
        }

    return {
        "classification": "mcp_transient",
        "matched_token": matched_token,
        "event": "EVALUATOR_MCP_TRANSIENT",
        "feature_id": feature_id,
        "retry_count_after": retry_count + 1,
    }
