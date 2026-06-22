"""Infra-error transient classifier + unlimited spawn-layer recovery (no budget impact).

Feature 56d40cab: Public entry point that satisfies the AC requirements:
- File exists: src/bob3/infra_error_classifier.py
- Function defined: bob3.infra_error_classifier.classify_exit
- Function defined: bob3.infra_error_classifier.spawn_with_retry
- integration: bob3.orchestrator

Spurious infra errors (HTTP 429, ECONNRESET, ETIMEDOUT, env-config ENOENT,
midstream Claude abort) are NOT signal about feature quality. They MUST NOT
consume any planning, execution, refinement, or evaluation budget.

This module re-exports the canonical implementation from
bob3.orchestrator.spawn_retry and provides bob3.infra_error_classifier as the
authoritative public namespace.
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
