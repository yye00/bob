"""bob.spawn_layer — canonical spawn-layer facade (F-R7-478).

Single import surface for the spawn layer's transient-error recovery. Every
Claude-CLI sub-agent spawn is routed through this layer so that spurious infra
errors (HTTP 429 / rate-limit, ECONNRESET, ETIMEDOUT, env-config ENOENT,
midstream Claude abort) are classified as TRANSIENT and retried unlimited times
without consuming any planning, execution, refinement, or evaluation budget.

Delegates to the canonical implementation in ``bob.orchestrator.spawn_retry``.
The orchestrator spawn dispatcher imports from here so this module is the
wired integration point for ``integration: bob.spawn_layer``.
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
