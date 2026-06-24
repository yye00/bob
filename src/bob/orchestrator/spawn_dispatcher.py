"""Spawn dispatcher — routes all Claude sub-agent spawns through spawn_with_retry (F-R7-478).

This module is the single integration point that ensures every Claude sub-agent
invocation in the orchestrator passes through spawn_with_retry for transient-
error recovery without budget impact.

Integration: bob.orchestrator.spawn_dispatcher
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from bob.orchestrator.spawn_retry import spawn_with_retry

logger = logging.getLogger(__name__)


async def dispatch_spawn(
    spawn_fn: Callable,
    *,
    feature_id: str,
    job_name: str,
    workspace: str | None = None,
    log_dir: str | None = None,
    config_path: str | None = None,
    on_real_failure: Callable[[dict[str, Any]], None] | None = None,
    on_mid_work_crash: Callable[[dict[str, Any]], None] | None = None,
    on_cost_update: Callable[[float], None] | None = None,
    sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    probe_fn: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Dispatch a sub-agent spawn through the transient-retry wrapper.

    All Claude sub-agent spawns in the orchestrator MUST go through this
    function to ensure:
    - Transient infra errors are retried unlimited times without budget charge.
    - Mid-work crashes charge exactly one refinement attempt.
    - Real failures are returned to the caller for normal budget accounting.

    Args:
        spawn_fn: Async callable that performs the actual spawn.
        feature_id: Feature UUID (used for retry log naming and lock cleanup).
        job_name: Short name for log file disambiguation.
        workspace: Workspace directory for partial-state cleanup.
        log_dir: Override for the .retry.jsonl log directory.
        config_path: Override for config/spawn_retry.yaml.
        on_real_failure: Called when classification is real_failure.
        on_mid_work_crash: Called when classification is mid_work_crash.
        on_cost_update: Called after each spawn with the spawn cost.
        sleep_fn: Async sleep override (for testing).
        probe_fn: Health probe override (for testing).

    Returns:
        Result dict from the spawn callable on the final attempt.
    """
    return await spawn_with_retry(
        spawn_fn,
        feature_id=feature_id,
        job_name=job_name,
        workspace=workspace,
        log_dir=log_dir,
        config_path=config_path,
        on_real_failure=on_real_failure,
        on_mid_work_crash=on_mid_work_crash,
        on_cost_update=on_cost_update,
        sleep_fn=sleep_fn,
        probe_fn=probe_fn,
    )


__all__ = ["dispatch_spawn"]
