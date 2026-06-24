"""Top-level spawn_with_retry module.

Public entry point satisfying the AC "File exists: src/spawn_with_retry.py".
Delegates to the canonical implementation in bob3.orchestrator.spawn_retry.

Infra errors (HTTP 429, ECONNRESET, ETIMEDOUT, ENOENT, midstream Claude abort)
are classified as TRANSIENT and retried unlimited times without budget impact.
"""

from __future__ import annotations

from bob3.orchestrator.spawn_retry import (
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
