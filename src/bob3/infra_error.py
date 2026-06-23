"""bob3.infra_error — canonical entry point for infra-error classification.

Exposes classify_exit and spawn_with_retry from the orchestrator's
spawn_retry module. Infra errors (HTTP 429, ECONNRESET, ETIMEDOUT,
ENOENT, midstream Claude abort) are classified as TRANSIENT and retried
unlimited times without consuming any budget at any layer.

AC requirements satisfied:
  - Function defined: bob3.infra_error.classify_exit
  - Function defined: bob3.infra_error.spawn_with_retry
  - File exists: src/bob3/infra_error.py
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
