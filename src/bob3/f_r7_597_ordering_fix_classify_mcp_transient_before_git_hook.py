"""F-R7-597 ordering fix — classify MCP transient BEFORE git-hook-rejection demotion (F-R7-607).

Root cause: the original F-R7-597 classifier was wired to intercept only the
``status == 'failed'`` transition path.  When the evaluator sub-agent crashes
with a TLS / MCP-transient error, the orchestrator emits:

    "blocked by git hook rejection; needs human review"

via a distinct code path that F-R7-597 never saw.  This module closes that gap
by exposing the classifier-precedence hoist as a standalone callable so
callers can invoke it BEFORE the git-hook-rejection branch fires.

Public API
----------
f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook
    Primary entry point — wraps ``bob3.run_loop.classify_mcp_transient``
    with the pre-hook semantics documented in the spec.

classify_mcp_transient_pre_hook
    Alias for the above (convenience import).

drain_pre_hook_transient_summary
    Emit the ``PRE_HOOK_TRANSIENT_SUMMARY`` telemetry event on drain.

Integration note: ``bob3.orchestrator.run_loop`` imports this module and calls
``f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook`` at the
git-hook-rejection site, BEFORE the ``git_hook_failed`` branch increments
``features_failed`` and emits the needs_human log message.  If the function
returns ``intercept=True``, the caller must reset the feature to ``'ready'``
and skip the git-hook-rejection emit entirely (subject to the 5-retry cap).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from bob3.run_loop import (
    classify_mcp_transient,
    drain_mcp_transient_summary,
)

logger = logging.getLogger(__name__)


def f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook(
    *,
    stderr: str | None,
    retry_count: int,
    feature_id: str | None = None,
) -> dict[str, Any]:
    """Classify MCP-transient errors BEFORE the git-hook-rejection demotion fires.

    This is the F-R7-607 classifier-precedence hoist entry point.  It must be
    called by the orchestrator's git-hook-rejection branch BEFORE emitting
    "blocked by git hook rejection; needs human review" and before flipping
    the feature to ``needs_human``.

    Decision rules
    --------------
    1. If ``retry_count >= 5`` (the F-R7-597 cap): returns ``intercept=False``
       so the git-hook-rejection path proceeds normally.
    2. If ``stderr`` contains any token from the MCP-transient set:
       - returns ``intercept=True``
       - emits ``{"event":"EVALUATOR_MCP_TRANSIENT_PRE_HOOK",...}`` via logger
       The caller must reset the feature to ``'ready'`` and skip the
       needs_human transition.
    3. Otherwise: returns ``intercept=False``; git-hook-rejection proceeds.

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
        Captured stderr text from the evaluator sub-agent run.  May be None.
    retry_count:
        Number of times this intercept has already fired for the current
        feature.  At 5 the cap is exhausted and ``intercept`` is False.
    feature_id:
        Optional feature UUID; echoed in the result and in logged events.

    Returns
    -------
    dict with keys:
        intercept: bool — True when the classifier fires (demotion should be skipped).
        matched_token: str | None — the first matched token label.
        event: str — "EVALUATOR_MCP_TRANSIENT_PRE_HOOK" when intercept=True.
        feature_id: str | None — echoed from the argument.
    """
    result = classify_mcp_transient(
        stderr=stderr,
        retry_count=retry_count,
        feature_id=feature_id,
    )

    if result.get("intercept"):
        logger.info(
            json.dumps({
                "event": "EVALUATOR_MCP_TRANSIENT_PRE_HOOK",
                "feature_id": feature_id,
                "matched_token": result.get("matched_token"),
                "retry_count": retry_count,
                "source": "f_r7_597_ordering_fix",
            })
        )

    return result


# Convenience alias.
classify_mcp_transient_pre_hook = f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook


def drain_pre_hook_transient_summary(intercepted: int) -> dict[str, Any]:
    """Emit ``PRE_HOOK_TRANSIENT_SUMMARY`` telemetry on drain.

    Delegates to ``bob3.run_loop.drain_mcp_transient_summary``.  Call once
    at orchestrator shutdown to record how many git-hook-rejection demotions
    were intercepted this session.

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
    "f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook",
    "classify_mcp_transient_pre_hook",
    "drain_pre_hook_transient_summary",
]
