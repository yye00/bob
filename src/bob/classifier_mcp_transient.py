"""MCP-transient classifier pre-hook — F-R7-597 ordering fix (F-R7-607).

Exposes `classify_mcp_transient_pre_hook` as the primary API for the
classifier-precedence hoist: call this BEFORE the git-hook-rejection
demotion path in the orchestrator run_loop so that evaluator crashes
caused by upstream MCP/TLS infrastructure failures are rerouted to
'ready' instead of 'needs_human'.

Public API
----------
classify_mcp_transient_pre_hook
    Primary entry point — wraps bob.run_loop.classify_mcp_transient
    with pre-hook semantics. Returns a dict with 'intercept', 'matched_token',
    'event', and 'feature_id' keys.

drain_pre_hook_transient_summary
    Emit PRE_HOOK_TRANSIENT_SUMMARY telemetry event on drain.
"""

from __future__ import annotations

from typing import Any

from bob.run_loop import (
    classify_mcp_transient,
    drain_mcp_transient_summary,
)


def classify_mcp_transient_pre_hook(
    *,
    stderr: str | None,
    retry_count: int,
    feature_id: str | None = None,
) -> dict[str, Any]:
    """Classify MCP-transient errors BEFORE the git-hook-rejection demotion fires.

    This is the F-R7-607 classifier-precedence hoist entry point. It must be
    called BEFORE the "blocked by git hook rejection; needs human review" emit
    and before flipping a feature to 'needs_human'.

    Decision rules
    --------------
    1. If retry_count >= 5 (the F-R7-597 cap): returns intercept=False so the
       git-hook-rejection path proceeds normally.
    2. If stderr contains any token from the MCP-transient token set:
       - returns intercept=True
       - caller must reset the feature to 'ready' and skip the needs_human transition
    3. Otherwise: returns intercept=False; git-hook-rejection proceeds normally.

    MCP-transient token set (F-R7-597):
      - "self signed certificate in certificate chain"
      - "self-signed certificate"
      - "MCP server" + "Connection failed"  (compound — both must appear)
      - "HTTP Connection failed"
      - "Streamable HTTP error"
      - "Server rejected the configured Authorization header"
      - "MCP server" + "403 Forbidden"      (compound — both must appear)

    Parameters
    ----------
    stderr:
        Captured stderr text from the evaluator sub-agent run. May be None.
    retry_count:
        Number of times this intercept has already fired for the current feature.
        At 5 the cap is exhausted and intercept is False.
    feature_id:
        Optional feature UUID; echoed in the result and in logged events.

    Returns
    -------
    dict with keys:
        intercept: bool — True when the classifier fires (demotion should be skipped).
        matched_token: str | None — the first matched token label.
        event: str — "EVALUATOR_MCP_TRANSIENT_PRE_HOOK" when intercept=True, else "".
        feature_id: str | None — echoed from the argument.
    """
    return classify_mcp_transient(
        stderr=stderr,
        retry_count=retry_count,
        feature_id=feature_id,
    )


def drain_pre_hook_transient_summary(intercepted: int) -> dict[str, Any]:
    """Emit PRE_HOOK_TRANSIENT_SUMMARY telemetry on drain.

    Call once at orchestrator shutdown to record how many git-hook-rejection
    demotions were intercepted this session due to MCP transient errors.

    Parameters
    ----------
    intercepted:
        Total intercept count for the session.

    Returns
    -------
    dict with keys:
        event: "PRE_HOOK_TRANSIENT_SUMMARY"
        intercepted: int
    """
    return drain_mcp_transient_summary(intercepted)


__all__ = [
    "classify_mcp_transient_pre_hook",
    "drain_pre_hook_transient_summary",
]
