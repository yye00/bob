"""bob.transient_classifier — canonical transient-error classification module.

Satisfies ACs:
  - File exists: src/bob/transient_classifier.py
  - Function defined: bob.transient_classifier.classify_exit
  - Function defined: bob.transient_classifier.spawn_with_retry
  - integration: bob.orchestrator

Infra errors (HTTP 429, rate-limit, ECONNRESET, ETIMEDOUT, env-config ENOENT,
midstream Claude abort) are NOT signal about feature quality. This module is the
canonical public entry point for classifying sub-agent exits and retrying them
UNLIMITED times at the spawn layer without consuming any planning, execution,
refinement, or evaluation budget.

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
