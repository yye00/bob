"""Top-level infra_error module.

Public entry point satisfying the AC "Function defined: infra_error.classify_exit"
and "Function defined: infra_error.spawn_with_retry".

Infra errors (HTTP 429, ECONNRESET, ETIMEDOUT, ENOENT, midstream Claude abort)
are classified as TRANSIENT and retried unlimited times without budget impact.

Delegates to the canonical implementation in bob.orchestrator.spawn_retry.
"""

from __future__ import annotations

from bob.orchestrator.spawn_retry import (
    ExitClassification,
    RetryState,
    SpawnCallable,
    classify_exit,
    load_patterns,
    spawn_with_retry,
)

__all__ = [
    "ExitClassification",
    "RetryState",
    "SpawnCallable",
    "classify_exit",
    "load_patterns",
    "spawn_with_retry",
]
