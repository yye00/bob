"""MCP-transient error classifier for F-R7-597 ordering fix (F-R7-607).

Exposes the classifier-precedence hoist as a standalone module so callers
can import it without pulling in all of run_loop.  All actual logic lives in
``bob.run_loop``; this module is a thin re-export façade that satisfies the
AC "File exists: src/bob/mcp_transient_classifier.py".

Public API
----------
classify_mcp_transient
    Classify whether stderr contains an MCP-transient error token.

classify_mcp_transient_pre_hook
    Alias — explicit pre-hook semantics name.

drain_mcp_transient_summary
    Emit ``PRE_HOOK_TRANSIENT_SUMMARY`` telemetry on drain.
"""

from __future__ import annotations

from bob.run_loop import (
    classify_mcp_transient,
    classify_mcp_transient_pre_hook,
    drain_mcp_transient_summary,
)

__all__ = [
    "classify_mcp_transient",
    "classify_mcp_transient_pre_hook",
    "drain_mcp_transient_summary",
]
