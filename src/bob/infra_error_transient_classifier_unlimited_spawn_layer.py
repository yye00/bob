"""Infra-error transient classifier + unlimited spawn-layer recovery (no budget impact).

Feature 8f042049: Public entry point satisfying the AC file-exists and function-defined
requirements. Delegates to the canonical implementation in
bob.orchestrator.spawn_retry via the fuller-named sibling module.

Spurious infra errors (HTTP 429, rate-limit, ECONNRESET, ETIMEDOUT, env-config
ENOENT, midstream Claude abort) are NOT signal about feature quality. This
module provides the canonical entry point for classifying sub-agent exits and
retrying them unlimited times at the spawn layer without consuming any planning,
execution, refinement, or evaluation budget.
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


def infra_error_transient_classifier_unlimited_spawn_layer(
    exit_code: int | None,
    stderr: str | None,
    duration_ms: int | None = None,
    work_events: int | None = None,
    config_path: str | None = None,
) -> ExitClassification:
    """Classify a Claude sub-agent exit for infra-error transient recovery.

    Delegates to classify_exit. Returns "transient" for infra errors that
    must be retried unlimited times without budget impact, "mid_work_crash"
    for crashes after real work was done, or "real_failure" otherwise.

    Args:
        exit_code: Process exit code (0 = success).
        stderr: Combined stderr text from the sub-agent process.
        duration_ms: Milliseconds the sub-agent ran.
        work_events: Count of substantive progress events written to disk.
        config_path: Override config/spawn_retry.yaml path (for testing).

    Returns:
        ExitClassification: "transient", "mid_work_crash", or "real_failure".
    """
    return classify_exit(
        exit_code=exit_code,
        stderr=stderr,
        duration_ms=duration_ms,
        work_events=work_events,
        config_path=config_path,
    )


__all__ = [
    "ExitClassification",
    "RetryState",
    "SpawnCallable",
    "classify_exit",
    "infra_error_transient_classifier_unlimited_spawn_layer",
    "load_patterns",
    "spawn_with_retry",
]
