"""Evaluator MCP transient classifier (F-R7-597).

Classifies evaluator sub-agent crashes caused by MCP/TLS infrastructure
noise (self-signed cert errors, connection failures) as retryable rather
than feature-failures.

The primary entry point is :func:`classify_mcp_transient`. The full
implementation lives in :mod:`bob.run_loop` as
:func:`~bob.run_loop.classify_evaluator_mcp_transient`; this module
re-exports it under the canonical name expected by the AC.
"""

from __future__ import annotations

from bob.run_loop import classify_evaluator_mcp_transient as classify_mcp_transient

__all__ = ["classify_mcp_transient"]
