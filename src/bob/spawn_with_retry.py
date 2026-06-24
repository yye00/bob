"""bob.spawn_with_retry — public entry point for transient-error spawn recovery.

Satisfies ACs:
  - File exists: src/bob/spawn_with_retry.py
  - Function defined: bob.spawn_with_retry.spawn_with_retry
  - Function defined: bob.spawn_with_retry.classify_exit

Delegates to the canonical implementation in bob.orchestrator.spawn_retry.
Infra errors (HTTP 429, ECONNRESET, ETIMEDOUT, ENOENT, midstream Claude abort)
are classified as TRANSIENT and retried unlimited times without budget impact.
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
